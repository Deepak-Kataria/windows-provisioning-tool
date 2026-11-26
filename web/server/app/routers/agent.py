"""Agent-facing endpoints: enrollment (HTTPS) and the job channel (WSS).

Agent -> server messages:
  {"type": "hello", "agent_version": "...", "hostname": "...", "os_info": {...}, "running_jobs": [ids]}
  {"type": "heartbeat"}
  {"type": "job_started", "job_id": "..."}
  {"type": "job_output", "job_id": "...", "lines": [{"stream": "stdout", "data": "..."}]}
  {"type": "job_done", "job_id": "...", "status": "succeeded|failed|cancelled",
   "exit_code": 0, "result": {...}, "error": ""}
Server -> agent messages:
  {"type": "welcome", "machine_id": "...", "heartbeat_seconds": 30}
  {"type": "job", "job_id": "...", "action": "...", "params": {...}, "timeout_seconds": 300}
  {"type": "cancel", "job_id": "..."}
"""
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import jobs_service as js
from ..audit import audit
from ..config import get_settings
from ..db import get_db, new_session, utcnow
from ..hub import AgentConn, hub
from ..models import EnrollmentCode, Machine
from ..netutil import client_ip
from ..ratelimit import enroll_limiter
from ..schemas import AgentEnrollIn, AgentEnrollOut
from ..security import hash_token, new_token, normalise_enrollment_code

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/enroll", response_model=AgentEnrollOut)
def enroll(body: AgentEnrollIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if not enroll_limiter.allow(f"enroll:{ip}", 10):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts")
    code_hash = hash_token(normalise_enrollment_code(body.code))
    ec = db.scalar(select(EnrollmentCode).where(EnrollmentCode.code_hash == code_hash))
    if ec is None or ec.used_at is not None or ec.expires_at < utcnow():
        audit(db, "agent_enroll_failed", username="agent", ip=ip, hostname=body.hostname[:64])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired enrollment code")

    token = new_token()
    m = Machine(
        hostname=body.hostname,
        label=ec.label,
        token_hash=hash_token(token),
        enrolled_by=ec.created_by,
        agent_version=body.agent_version,
        os_info=body.os_info,
        last_ip=ip,
    )
    db.add(m)
    db.flush()
    ec.used_at = utcnow()
    ec.machine_id = m.id
    audit(db, "agent_enrolled", username="agent", machine_id=m.id, ip=ip, hostname=m.hostname)
    return AgentEnrollOut(
        machine_id=m.id, token=token, heartbeat_seconds=get_settings().heartbeat_seconds
    )


# ---------------------------------------------------------------- WebSocket channel

class _Hello(BaseModel):
    type: Literal["hello"]
    agent_version: str = Field(default="", max_length=32)
    hostname: str = Field(default="", max_length=255)
    os_info: dict[str, Any] = Field(default_factory=dict)
    running_jobs: list[str] = Field(default_factory=list, max_length=100)


class _Line(BaseModel):
    stream: str = "stdout"
    data: str = ""


class _Output(BaseModel):
    type: Literal["job_output"]
    job_id: str = Field(max_length=36)
    lines: list[_Line] = Field(max_length=500)


class _Started(BaseModel):
    type: Literal["job_started"]
    job_id: str = Field(max_length=36)


class _Done(BaseModel):
    type: Literal["job_done"]
    job_id: str = Field(max_length=36)
    status: str
    exit_code: int | None = None
    result: dict[str, Any] | None = None
    error: str = ""


def _auth_machine(token: str) -> Machine | None:
    with new_session() as db:
        m = db.scalar(select(Machine).where(Machine.token_hash == hash_token(token)))
        if m is None or m.revoked_at is not None:
            return None
        return m


def _apply_hello(machine_id: str, hello: _Hello, ip: str) -> None:
    with new_session() as db:
        m = db.get(Machine, machine_id)
        if m is None:
            return
        m.last_seen_at = utcnow()
        m.last_ip = ip
        if hello.agent_version:
            m.agent_version = hello.agent_version
        if hello.hostname:
            m.hostname = hello.hostname
        if hello.os_info:
            m.os_info = hello.os_info
        db.commit()


def _touch(machine_id: str) -> None:
    with new_session() as db:
        m = db.get(Machine, machine_id)
        if m is not None:
            m.last_seen_at = utcnow()
            db.commit()


@router.websocket("/ws")
async def agent_ws(ws: WebSocket):
    auth = ws.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    machine = await run_in_threadpool(_auth_machine, token) if token else None
    if machine is None:
        await ws.close(code=4401, reason="unauthorized")
        return

    await ws.accept()
    s = get_settings()
    registry = ws.app.state.registry
    conn = AgentConn(machine_id=machine.id, ws=ws)
    ip = client_ip(ws)

    try:
        try:
            hello = _Hello.model_validate(await ws.receive_json())
        except (ValidationError, ValueError):
            await ws.close(code=4400, reason="expected hello")
            return
        await hub.register(conn)
        await run_in_threadpool(_apply_hello, machine.id, hello, ip)
        conn.last_seen_written = time.monotonic()
        for job_id in await run_in_threadpool(js.fail_lost_jobs, machine.id, hello.running_jobs):
            hub.publish(job_id, {"type": "status", "status": "failed"})
        await conn.send(
            {"type": "welcome", "machine_id": machine.id, "heartbeat_seconds": s.heartbeat_seconds}
        )
        await js.dispatch_queued(machine.id, registry)

        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            now = time.monotonic()
            if now - conn.last_seen_written > s.last_seen_write_seconds:
                conn.last_seen_written = now
                await run_in_threadpool(_touch, machine.id)
            try:
                if kind == "heartbeat":
                    continue
                if kind == "job_started":
                    m = _Started.model_validate(msg)
                    if await run_in_threadpool(js.job_started, machine.id, m.job_id):
                        hub.publish(m.job_id, {"type": "status", "status": "running"})
                elif kind == "job_output":
                    m = _Output.model_validate(msg)
                    lines = [line.model_dump() for line in m.lines]
                    stored = await run_in_threadpool(js.job_output, machine.id, m.job_id, lines)
                    for line in stored:
                        hub.publish(m.job_id, {"type": "line", **line})
                elif kind == "job_done":
                    m = _Done.model_validate(msg)
                    job = await run_in_threadpool(
                        js.job_done, machine.id, m.job_id, m.status, m.exit_code, m.result, m.error
                    )
                    if job is not None:
                        hub.publish(
                            m.job_id,
                            {"type": "status", "status": job.status, "exit_code": job.exit_code},
                        )
            except ValidationError:
                continue  # ignore malformed messages, keep the channel up
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister(conn)
