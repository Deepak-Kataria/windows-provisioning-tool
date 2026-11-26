"""User management (admin only)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db, utcnow
from ..deps import require_role
from ..models import User, WebSession
from ..netutil import client_ip
from ..schemas import PasswordResetIn, UserCreateIn, UserOut, UserUpdateIn
from ..security import hash_password, password_problem

router = APIRouter(prefix="/api/users", tags=["users"])
admin_only = require_role("admin")


def _get(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return u


def _kill_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(WebSession).where(WebSession.user_id == user_id))


def _active_admins(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
    ) or 0


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreateIn, request: Request, db: Session = Depends(get_db), me: User = Depends(admin_only)
):
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    u = User(
        username=body.username.lower(),
        display_name=body.display_name or body.username,
        role=body.role,
        password_hash=hash_password(body.password),
        must_change_password=True,
    )
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists") from None
    audit(db, "user_created", user=me, ip=client_ip(request), target=u.username, role=u.role)
    return u


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(admin_only),
):
    u = _get(db, user_id)
    changes = body.model_dump(exclude_none=True)
    demoting = "role" in changes and changes["role"] != "admin" and u.role == "admin"
    disabling = changes.get("is_active") is False and u.is_active
    if u.id == me.id and (demoting or disabling):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot demote or disable yourself")
    if (demoting or disabling) and u.role == "admin" and _active_admins(db) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one active admin is required")
    for k, v in changes.items():
        setattr(u, k, v)
    if disabling or demoting:
        _kill_sessions(db, u.id)
    db.commit()
    audit(db, "user_updated", user=me, ip=client_ip(request), target=u.username, changes=changes)
    return u


@router.post("/{user_id}/password", response_model=UserOut)
def reset_password(
    user_id: int,
    body: PasswordResetIn,
    request: Request,
    db: Session = Depends(get_db),
    me: User = Depends(admin_only),
):
    u = _get(db, user_id)
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    u.password_hash = hash_password(body.password)
    u.password_changed_at = utcnow()
    u.must_change_password = u.id != me.id
    _kill_sessions(db, u.id)
    db.commit()
    audit(db, "user_password_reset", user=me, ip=client_ip(request), target=u.username)
    return u


@router.post("/{user_id}/reset-mfa", response_model=UserOut)
def reset_mfa(
    user_id: int, request: Request, db: Session = Depends(get_db), me: User = Depends(admin_only)
):
    u = _get(db, user_id)
    if u.id == me.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ask another admin to reset your MFA")
    u.totp_secret_enc = None
    u.totp_confirmed = False
    u.totp_last_step = 0
    _kill_sessions(db, u.id)
    db.commit()
    audit(db, "user_mfa_reset", user=me, ip=client_ip(request), target=u.username)
    return u


@router.post("/{user_id}/unlock", response_model=UserOut)
def unlock(user_id: int, request: Request, db: Session = Depends(get_db), me: User = Depends(admin_only)):
    u = _get(db, user_id)
    u.locked_until = None
    u.failed_logins = 0
    db.commit()
    audit(db, "user_unlocked", user=me, ip=client_ip(request), target=u.username)
    return u
