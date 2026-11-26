"""Actions, jobs, live job output, and the audit log."""
import asyncio
import contextlib

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import jobs_service as js
from ..actions import ActionError, Registry
from ..audit import audit
from ..config import get_settings
from ..db import get_db, new_session, utcnow
from ..deps import _load_session, require_role
from ..hub import hub
from ..models import JOB_ACTIVE, JOB_STATUSES, AuditLog, Job, JobLog, Machine, User
from ..netutil import client_ip
from ..schemas import ActionOut, AuditOut, JobCreateIn, JobLogOut, JobOut
from .machines import get_machine

router = APIRouter(prefix="/api", tags=["jobs"])


def get_registry(request: Request) -> Registry:
    return request.app.state.registry


@router.get("/actions", response_model=list[ActionOut])
def list_actions(registry: Registry = Depends(get_registry), _: User = Depends(require_role("viewer"))):
    return [
        ActionOut(
            id=a.id,
            title=a.title,
            description=a.description,
            min_role=a.min_role,
            params_schema=a.params_schema,
            secret_params=list(a.secret_params),
            timeout_seconds=a.timeout_seconds,
        )
        for a in registry.all()
    ]


@router.post("/machines/{machine_id}/jobs", response_model=JobOut, status_code=201)
async def create_job(
    machine_id: str,
    body: JobCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    registry: Registry = Depends(get_registry),
    me: User = Depends(require_role("technician")),
):
    try:
        action = registry.get(body.action)
        action.validate(body.params)
    except ActionError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    if not me.has_role(action.min_role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role for this action")

    m = get_machine(db, machine_id)
    if m.revoked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Machine is revoked")
    secrets = action.has_secrets(body.params)
    if secrets and not hub.is_online(m.id):
        # Secrets are never stored, so a job carrying them cannot wait in the queue.
        raise HTTPException(status.HTTP_409_CONFLICT, "Machine must be online for this action")

    job = Job(
        machine_id=m.id, action_id=action.id, params=action.redact(body.params), created_by=me.id
    )
    db.add(job)
    db.commit()
    audit(
        db,
        "job_created",
        user=me,
        machine_id=m.id,
        ip=client_ip(request),
        job_id=job.id,
        action=action.id,
        params=job.params,
    )
    sent = await js.dispatch(job, action, body.params)
    if not sent and secrets:
        await run_in_threadpool(js._finish_server_side, job.id, "failed", "machine went offline")
    db.refresh(job)
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    machine_id: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    action: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer")),
):
    stmt = select(Job).order_by(Job.created_at.desc())
    if machine_id:
        stmt = stmt.where(Job.machine_id == machine_id)
    if status_:
        if status_ not in JOB_STATUSES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad status")
        stmt = stmt.where(Job.status == status_)
    if action:
        stmt = stmt.where(Job.action_id == action)
    return db.scalars(stmt.limit(limit).offset(offset)).all()


def _job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db), _: User = Depends(require_role("viewer"))):
    return _job(db, job_id)


@router.get("/jobs/{job_id}/logs", response_model=list[JobLogOut])
def get_logs(
    job_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer")),
):
    _job(db, job_id)
    return db.scalars(
        select(JobLog)
        .where(JobLog.job_id == job_id, JobLog.seq > after_seq)
        .order_by(JobLog.seq)
        .limit(limit)
    ).all()


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_role("technician")),
):
    job = _job(db, job_id)
    if job.status not in JOB_ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Job already {job.status}")
    audit(db, "job_cancel_requested", user=me, machine_id=job.machine_id, ip=client_ip(request), job_id=job.id)
    if job.status == "queued":
        job.status = "cancelled"
        job.error = f"cancelled by {me.username}"
        job.finished_at = utcnow()
        db.commit()
        hub.publish(job.id, {"type": "status", "status": "cancelled"})
    else:
        # Agent stops the process and reports job_done with status "cancelled".
        await hub.send(job.machine_id, {"type": "cancel", "job_id": job.id})
    db.refresh(job)
    return job


@router.websocket("/jobs/{job_id}/stream")
async def stream_job(ws: WebSocket, job_id: str):
    """Live output for the browser: backlog first, then new lines and status changes."""

    def _auth_and_backlog():
        with new_session() as db:
            sess = _load_session(ws, db)
            if sess is None or not sess.mfa_verified or sess.user.must_change_password:
                return None
            job = db.get(Job, job_id)
            if job is None:
                return None
            logs = db.scalars(select(JobLog).where(JobLog.job_id == job_id).order_by(JobLog.seq)).all()
            return job.status, [{"seq": l.seq, "stream": l.stream, "data": l.data} for l in logs]

    # Same-origin check: cookies are SameSite=Strict, but WebSockets are not covered by CORS.
    origin = ws.headers.get("origin")
    if origin and origin.rstrip("/") != get_settings().base_url.rstrip("/"):
        await ws.close(code=4403)
        return
    queue = hub.subscribe(job_id)  # subscribe before reading backlog so nothing is missed
    try:
        found = await run_in_threadpool(_auth_and_backlog)
        if found is None:
            await ws.close(code=4401)
            return
        await ws.accept()
        status_now, backlog = found
        last_seq = 0
        for line in backlog:
            await ws.send_json({"type": "line", **line})
            last_seq = line["seq"]
        await ws.send_json({"type": "status", "status": status_now})
        if status_now not in JOB_ACTIVE:
            await ws.close()
            return
        while True:
            event = await queue.get()
            if event["type"] == "line":
                if event["seq"] <= last_seq:
                    continue
                last_seq = event["seq"]
            await ws.send_json(event)
            if event["type"] == "status" and event["status"] not in JOB_ACTIVE:
                await ws.close()
                return
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(job_id, queue)


@router.get("/audit", response_model=list[AuditOut])
def audit_log(
    event: str | None = None,
    username: str | None = None,
    machine_id: str | None = None,
    before_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if event:
        stmt = stmt.where(AuditLog.event == event)
    if username:
        stmt = stmt.where(AuditLog.username == username.lower())
    if machine_id:
        stmt = stmt.where(AuditLog.machine_id == machine_id)
    if before_id:
        stmt = stmt.where(AuditLog.id < before_id)
    return db.scalars(stmt.limit(limit)).all()
