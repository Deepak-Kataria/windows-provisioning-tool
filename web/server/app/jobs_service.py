"""Job dispatch and agent result handling (shared by routers)."""
from typing import Any

from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from .actions import Action
from .audit import audit
from .db import new_session, utcnow
from .hub import hub
from .models import JOB_ACTIVE, Job, JobLog

MAX_LOG_LINES_PER_JOB = 20_000
MAX_LINE_CHARS = 8_000
TERMINAL_FROM_AGENT = ("succeeded", "failed", "cancelled")


def job_message(job: Job, action: Action, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "job",
        "job_id": job.id,
        "action": job.action_id,
        "params": params,
        "timeout_seconds": action.timeout_seconds,
    }


def _mark_sent(job_id: str) -> None:
    with new_session() as db:
        job = db.get(Job, job_id)
        if job is not None and job.status == "queued":
            job.status = "sent"
            job.sent_at = utcnow()
            db.commit()


async def dispatch(job: Job, action: Action, params: dict[str, Any]) -> bool:
    """Send a job to its agent if online. params may contain secrets (never stored)."""
    ok = await hub.send(job.machine_id, job_message(job, action, params))
    if ok:
        await run_in_threadpool(_mark_sent, job.id)
        hub.publish(job.id, {"type": "status", "status": "sent"})
    return ok


def _queued(machine_id: str) -> list[Job]:
    with new_session() as db:
        return list(
            db.scalars(
                select(Job)
                .where(Job.machine_id == machine_id, Job.status == "queued")
                .order_by(Job.created_at)
            )
        )


async def dispatch_queued(machine_id: str, registry) -> None:
    for job in await run_in_threadpool(_queued, machine_id):
        try:
            action = registry.get(job.action_id)
        except ValueError:
            await run_in_threadpool(_finish_server_side, job.id, "failed", "action no longer exists")
            continue
        if not await dispatch(job, action, job.params):
            break


def _finish_server_side(job_id: str, status: str, error: str) -> None:
    with new_session() as db:
        job = db.get(Job, job_id)
        if job is not None and job.status in JOB_ACTIVE:
            job.status = status
            job.error = error
            job.finished_at = utcnow()
            db.commit()


def fail_lost_jobs(machine_id: str, still_running: list[str]) -> list[str]:
    """After an agent (re)connects: sent/running jobs it no longer knows about are lost."""
    with new_session() as db:
        lost = db.scalars(
            select(Job).where(
                Job.machine_id == machine_id,
                Job.status.in_(("sent", "running")),
                Job.id.not_in(still_running or [""]),
            )
        ).all()
        for job in lost:
            job.status = "failed"
            job.error = "agent restarted or lost the job"
            job.finished_at = utcnow()
        db.commit()
        return [j.id for j in lost]


def _own_active_job(db, machine_id: str, job_id: str) -> Job | None:
    job = db.get(Job, job_id)
    if job is None or job.machine_id != machine_id or job.status not in JOB_ACTIVE:
        return None  # agents may only touch their own, unfinished jobs
    return job


def job_started(machine_id: str, job_id: str) -> bool:
    with new_session() as db:
        job = _own_active_job(db, machine_id, job_id)
        if job is None:
            return False
        job.status = "running"
        job.started_at = utcnow()
        db.commit()
        return True


def job_output(machine_id: str, job_id: str, lines: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Store output lines; returns the stored lines (with seq) for live viewers."""
    with new_session() as db:
        job = _own_active_job(db, machine_id, job_id)
        if job is None:
            return []
        if job.status == "sent":
            job.status = "running"
            job.started_at = utcnow()
        seq = db.scalar(select(func.max(JobLog.seq)).where(JobLog.job_id == job_id)) or 0
        if seq >= MAX_LOG_LINES_PER_JOB:
            db.commit()
            return []
        stored = []
        for line in lines:
            seq += 1
            if seq > MAX_LOG_LINES_PER_JOB:
                data, stream = "[output truncated]", "system"
            else:
                data = str(line.get("data", ""))[:MAX_LINE_CHARS]
                stream = line.get("stream", "stdout")
                stream = stream if stream in ("stdout", "stderr", "system") else "stdout"
            db.add(JobLog(job_id=job_id, seq=seq, stream=stream, data=data))
            stored.append({"seq": seq, "stream": stream, "data": data})
            if seq > MAX_LOG_LINES_PER_JOB:
                break
        db.commit()
        return stored


def job_done(
    machine_id: str,
    job_id: str,
    status: str,
    exit_code: int | None,
    result: dict[str, Any] | None,
    error: str,
) -> Job | None:
    if status not in TERMINAL_FROM_AGENT:
        status = "failed"
    with new_session() as db:
        job = _own_active_job(db, machine_id, job_id)
        if job is None:
            return None
        job.status = status
        job.exit_code = exit_code
        job.result = result
        job.error = (error or "")[:10_000]
        job.finished_at = utcnow()
        if job.started_at is None:
            job.started_at = job.finished_at
        audit(
            db,
            "job_finished",
            username="agent",
            machine_id=machine_id,
            commit=False,
            job_id=job.id,
            action=job.action_id,
            status=status,
            exit_code=exit_code,
        )
        db.commit()
        return job
