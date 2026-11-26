"""Machines and enrollment codes."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..db import get_db, utcnow
from ..hub import hub
from ..models import JOB_ACTIVE, EnrollmentCode, Job, Machine, User
from ..netutil import client_ip
from ..deps import require_role
from ..schemas import (
    EnrollmentCodeIn,
    EnrollmentCodeInfo,
    EnrollmentCodeOut,
    MachineOut,
    MachineUpdateIn,
)
from ..security import hash_token, new_enrollment_code

router = APIRouter(prefix="/api", tags=["machines"])


def _out(m: Machine) -> MachineOut:
    o = MachineOut.model_validate(m)
    o.online = hub.is_online(m.id)
    return o


def get_machine(db: Session, machine_id: str) -> Machine:
    m = db.get(Machine, machine_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found")
    return m


# ---------------------------------------------------------------- enrollment codes

@router.post("/enrollment-codes", response_model=EnrollmentCodeOut, status_code=201)
def create_code(
    body: EnrollmentCodeIn,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_role("admin")),
):
    code = new_enrollment_code()
    ec = EnrollmentCode(
        code_hash=hash_token(code),
        label=body.label,
        created_by=me.id,
        expires_at=utcnow() + timedelta(hours=get_settings().enrollment_code_hours),
    )
    db.add(ec)
    db.commit()
    audit(db, "enrollment_code_created", user=me, ip=client_ip(request), code_id=ec.id, label=ec.label)
    from .install import install_command

    return EnrollmentCodeOut(
        id=ec.id, code=code, label=ec.label, expires_at=ec.expires_at, install_command=install_command(code)
    )


@router.get("/enrollment-codes", response_model=list[EnrollmentCodeInfo])
def list_codes(
    include_used: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    q = select(EnrollmentCode).order_by(EnrollmentCode.created_at.desc()).limit(200)
    if not include_used:
        q = q.where(EnrollmentCode.used_at.is_(None), EnrollmentCode.expires_at > utcnow())
    return db.scalars(q).all()


@router.delete("/enrollment-codes/{code_id}", status_code=204)
def delete_code(
    code_id: int, request: Request, db: Session = Depends(get_db), me: User = Depends(require_role("admin"))
):
    ec = db.get(EnrollmentCode, code_id)
    if ec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Code not found")
    db.delete(ec)
    db.commit()
    audit(db, "enrollment_code_deleted", user=me, ip=client_ip(request), code_id=code_id)


# ---------------------------------------------------------------- machines

@router.get("/machines", response_model=list[MachineOut])
def list_machines(
    q: str = Query(default="", max_length=128),
    online: bool | None = None,
    include_revoked: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer")),
):
    stmt = select(Machine).order_by(Machine.hostname)
    if not include_revoked:
        stmt = stmt.where(Machine.revoked_at.is_(None))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Machine.hostname).like(like), func.lower(Machine.label).like(like))
        )
    if online is not None:
        ids = hub.online_ids()
        stmt = stmt.where(Machine.id.in_(ids) if online else Machine.id.not_in(ids or [""]))
    return [_out(m) for m in db.scalars(stmt.limit(limit).offset(offset))]


@router.get("/machines/summary")
def machines_summary(db: Session = Depends(get_db), _: User = Depends(require_role("viewer"))):
    total = db.scalar(
        select(func.count()).select_from(Machine).where(Machine.revoked_at.is_(None))
    ) or 0
    return {"total": total, "online": len(hub.online_ids())}


@router.get("/machines/{machine_id}", response_model=MachineOut)
def get_one(machine_id: str, db: Session = Depends(get_db), _: User = Depends(require_role("viewer"))):
    return _out(get_machine(db, machine_id))


@router.patch("/machines/{machine_id}", response_model=MachineOut)
def update_machine(
    machine_id: str,
    body: MachineUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_role("technician")),
):
    m = get_machine(db, machine_id)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(m, k, v)
    db.commit()
    audit(db, "machine_updated", user=me, machine_id=m.id, ip=client_ip(request), changes=changes)
    return _out(m)


@router.post("/machines/{machine_id}/revoke", response_model=MachineOut)
async def revoke(
    machine_id: str,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_role("admin")),
):
    m = get_machine(db, machine_id)
    if m.revoked_at is None:
        m.revoked_at = utcnow()
        for job in db.scalars(
            select(Job).where(Job.machine_id == m.id, Job.status.in_(JOB_ACTIVE))
        ):
            job.status = "cancelled"
            job.error = "machine revoked"
            job.finished_at = utcnow()
        db.commit()
        audit(db, "machine_revoked", user=me, machine_id=m.id, ip=client_ip(request), hostname=m.hostname)
    await hub.kick(m.id)
    return _out(m)


@router.delete("/machines/{machine_id}", status_code=204)
def delete_machine(
    machine_id: str,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(require_role("admin")),
):
    m = get_machine(db, machine_id)
    if m.revoked_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Revoke the machine before deleting it")
    hostname = m.hostname
    db.delete(m)
    db.commit()
    audit(db, "machine_deleted", user=me, ip=client_ip(request), machine=machine_id, hostname=hostname)
