"""Login with mandatory TOTP MFA.

Flow:
  1. POST /api/auth/login        password ok -> pending session, next = "mfa" or "mfa_setup"
  2a. POST /api/auth/mfa         6-digit code -> full session
  2b. POST /api/auth/mfa/setup   (first login) get secret + otpauth URI for the QR code
      POST /api/auth/mfa/confirm 6-digit code -> MFA enrolled, full session
The session id is rotated when MFA completes.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..db import get_db, utcnow
from ..deps import create_session, end_session, get_any_session, get_session
from ..models import User, WebSession
from ..netutil import client_ip
from ..ratelimit import login_limiter
from ..schemas import CodeIn, LoginIn, LoginOut, MeOut, MfaSetupOut, PasswordChangeIn, UserOut
from ..security import (
    decrypt,
    encrypt,
    hash_password,
    new_totp_secret,
    password_problem,
    totp_uri,
    verify_password,
    verify_totp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Invalid username or password"
GENERIC_MFA_ERROR = "Invalid code"


def _rate_limit(request: Request, bucket: str) -> None:
    s = get_settings()
    if not login_limiter.allow(f"{bucket}:{client_ip(request)}", s.login_rate_per_minute):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, wait a minute")


def _register_failure(db: Session, user: User, request: Request, event: str) -> None:
    s = get_settings()
    user.failed_logins += 1
    locked = False
    if user.failed_logins >= s.max_failed_logins:
        user.locked_until = utcnow() + timedelta(minutes=s.lockout_minutes)
        user.failed_logins = 0
        locked = True
    audit(db, event, user=user, ip=client_ip(request), commit=False)
    if locked:
        audit(db, "account_locked", user=user, ip=client_ip(request), commit=False)
    db.commit()


def _is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > utcnow()


def _promote(db: Session, request: Request, response: Response, old: WebSession) -> WebSession:
    """Replace a pending session with a fully verified one (new id = no fixation)."""
    user = old.user
    db.delete(old)
    db.commit()
    user.failed_logins = 0
    user.last_login_at = utcnow()
    db.commit()
    return create_session(db, response, request, user, mfa_verified=True)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _rate_limit(request, "login")
    ip = client_ip(request)
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))

    if user is None or not user.is_active:
        verify_password(body.password, None)  # same cost as a real check
        audit(db, "login_failed", username=body.username[:64], ip=ip, reason="unknown_user")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_LOGIN_ERROR)

    if _is_locked(user):
        verify_password(body.password, None)
        audit(db, "login_failed", user=user, ip=ip, reason="locked")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_LOGIN_ERROR)

    if not verify_password(body.password, user.password_hash):
        _register_failure(db, user, request, "login_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_LOGIN_ERROR)

    ws = create_session(db, response, request, user, mfa_verified=False)
    audit(db, "login_password_ok", user=user, ip=ip)
    return LoginOut(next="mfa" if user.totp_confirmed else "mfa_setup", csrf_token=ws.csrf_token)


@router.post("/mfa", response_model=LoginOut)
def mfa_verify(
    body: CodeIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    ws: WebSession = Depends(get_any_session),
):
    _rate_limit(request, "mfa")
    user = ws.user
    if ws.mfa_verified:
        return LoginOut(next="done", csrf_token=ws.csrf_token)
    if not user.totp_confirmed or not user.totp_secret_enc:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA not set up")
    if _is_locked(user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_MFA_ERROR)

    secret = decrypt(user.totp_secret_enc)
    step = verify_totp(secret, body.code, user.totp_last_step) if secret else None
    if step is None:
        _register_failure(db, user, request, "mfa_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_MFA_ERROR)

    user.totp_last_step = step
    new_ws = _promote(db, request, response, ws)
    audit(db, "login_ok", user=user, ip=client_ip(request))
    return LoginOut(next="done", csrf_token=new_ws.csrf_token)


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(db: Session = Depends(get_db), ws: WebSession = Depends(get_any_session)):
    user = ws.user
    if user.totp_confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA already set up")
    secret = new_totp_secret()
    user.totp_secret_enc = encrypt(secret)
    db.commit()
    return MfaSetupOut(secret=secret, otpauth_uri=totp_uri(secret, user.username))


@router.post("/mfa/confirm", response_model=LoginOut)
def mfa_confirm(
    body: CodeIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    ws: WebSession = Depends(get_any_session),
):
    _rate_limit(request, "mfa")
    user = ws.user
    if user.totp_confirmed:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA already set up")
    secret = decrypt(user.totp_secret_enc) if user.totp_secret_enc else None
    if not secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start MFA setup first")
    step = verify_totp(secret, body.code, 0)
    if step is None:
        _register_failure(db, user, request, "mfa_setup_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_MFA_ERROR)

    user.totp_confirmed = True
    user.totp_last_step = step
    new_ws = _promote(db, request, response, ws)
    audit(db, "mfa_enrolled", user=user, ip=client_ip(request))
    return LoginOut(next="done", csrf_token=new_ws.csrf_token)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    ws: WebSession = Depends(get_any_session),
):
    user = ws.user
    end_session(db, response, ws)
    audit(db, "logout", user=user, ip=client_ip(request))
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(ws: WebSession = Depends(get_session)):
    return MeOut(user=UserOut.model_validate(ws.user), csrf_token=ws.csrf_token)


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    ws: WebSession = Depends(get_session),
):
    user = ws.user
    if not verify_password(body.current_password, user.password_hash):
        _register_failure(db, user, request, "password_change_failed")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    problem = password_problem(body.new_password)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    user.must_change_password = False
    # Log out every other session of this user.
    db.execute(delete(WebSession).where(WebSession.user_id == user.id, WebSession.id != ws.id))
    db.commit()
    audit(db, "password_changed", user=user, ip=client_ip(request))
    response.status_code = 204
    return response
