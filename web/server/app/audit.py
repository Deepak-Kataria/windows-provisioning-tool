"""Audit log helper. Never pass secrets in detail; redact first."""
from sqlalchemy.orm import Session

from .models import AuditLog, User


def audit(
    db: Session,
    event: str,
    *,
    user: User | None = None,
    username: str = "",
    machine_id: str | None = None,
    ip: str = "",
    commit: bool = True,
    **detail,
) -> None:
    db.add(
        AuditLog(
            event=event,
            user_id=user.id if user else None,
            username=user.username if user else username,
            machine_id=machine_id,
            ip=ip,
            detail=detail,
        )
    )
    if commit:
        db.commit()
