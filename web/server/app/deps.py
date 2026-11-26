"""Request dependencies: sessions, current user, roles, CSRF."""
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, utcnow
from .models import User, WebSession
from .netutil import client_ip
from .security import hash_token, new_token, tokens_equal

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def create_session(
    db: Session, response: Response, request: Request, user: User, mfa_verified: bool
) -> WebSession:
    s = get_settings()
    token = new_token()
    ws = WebSession(
        id=hash_token(token),
        user_id=user.id,
        mfa_verified=mfa_verified,
        csrf_token=new_token(24),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:256],
    )
    db.add(ws)
    db.commit()
    response.set_cookie(
        s.session_cookie,
        token,
        httponly=True,
        secure=s.cookie_secure,
        samesite="strict",
        max_age=s.session_max_hours * 3600,
        path="/",
    )
    return ws


def end_session(db: Session, response: Response, ws: WebSession | None) -> None:
    if ws is not None:
        db.delete(ws)
        db.commit()
    response.delete_cookie(get_settings().session_cookie, path="/")


def _load_session(request: Request, db: Session) -> WebSession | None:
    s = get_settings()
    token = request.cookies.get(s.session_cookie)
    if not token:
        return None
    ws = db.get(WebSession, hash_token(token))
    if ws is None:
        return None
    now = utcnow()
    idle_limit = (
        timedelta(minutes=s.session_idle_minutes)
        if ws.mfa_verified
        else timedelta(minutes=s.pending_mfa_minutes)
    )
    if (
        now - ws.last_seen_at > idle_limit
        or now - ws.created_at > timedelta(hours=s.session_max_hours)
        or not ws.user.is_active
    ):
        db.delete(ws)
        db.commit()
        return None
    # Avoid a DB write on every request; 30s granularity is plenty for idle timeout.
    if now - ws.last_seen_at > timedelta(seconds=30):
        ws.last_seen_at = now
        db.commit()
    return ws


def _check_csrf(request: Request, ws: WebSession) -> None:
    if request.method in SAFE_METHODS:
        return
    sent = request.headers.get("x-csrf-token", "")
    if not sent or not tokens_equal(sent, ws.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")


def get_any_session(request: Request, db: Session = Depends(get_db)) -> WebSession:
    """Any logged-in session, including one still waiting for MFA."""
    ws = _load_session(request, db)
    if ws is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    _check_csrf(request, ws)
    return ws


def get_session(ws: WebSession = Depends(get_any_session)) -> WebSession:
    """A fully authenticated session (password + MFA)."""
    if not ws.mfa_verified:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA required")
    return ws


def current_user(ws: WebSession = Depends(get_session)) -> User:
    return ws.user


def require_role(minimum: str):
    def _dep(user: User = Depends(current_user)) -> User:
        if user.must_change_password:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Password change required")
        if not user.has_role(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _dep
