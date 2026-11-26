"""Web-only agent install: /install.ps1 bootstrap + agent download gated by an enrollment code.

Nobody is handed an .exe. The PC runs one PowerShell line (shown by "Add machine"), which
fetches /install.ps1 and then downloads the agent with its one-time code.
"""
import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..db import get_db, utcnow
from ..deps import require_role
from ..models import EnrollmentCode, User
from ..netutil import client_ip
from ..ratelimit import enroll_limiter
from ..schemas import CodeDownloadIn
from ..security import hash_token, normalise_enrollment_code

router = APIRouter(tags=["install"])
TEMPLATE = Path(__file__).resolve().parents[1] / "install.ps1"
EXE_NAME = "itops-agent.exe"
_sha_cache: dict[tuple[str, float], str] = {}


def _agent_file() -> Path | None:
    p = get_settings().agent_dist_dir / EXE_NAME
    return p if p.is_file() else None


def _sha256(p: Path) -> str:
    key = (str(p), p.stat().st_mtime)
    if key not in _sha_cache:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _sha_cache.clear()
        _sha_cache[key] = h.hexdigest()
    return _sha_cache[key]


def _version() -> str:
    v = get_settings().agent_dist_dir / "version.txt"
    return v.read_text(encoding="utf-8").strip()[:32] if v.is_file() else ""


def server_url() -> str:
    url = get_settings().base_url.rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", url):
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "ITOPS_BASE_URL is not a plain URL")
    return url


def install_command(code: str) -> str:
    """The one line an admin pastes into an elevated PowerShell on the new PC."""
    return (
        "[Net.ServicePointManager]::SecurityProtocol='Tls12'; "
        f"& ([scriptblock]::Create((irm '{server_url()}/install.ps1'))) -Code '{code}'"
    )


@router.get("/install.ps1", response_class=PlainTextResponse, include_in_schema=False)
def install_script():
    text = TEMPLATE.read_text(encoding="utf-8").replace("__SERVER_URL__", server_url())
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@router.post("/api/agent/download")
def download_agent(body: CodeDownloadIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if not enroll_limiter.allow(f"download:{ip}", 10):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts")
    ec = db.scalar(
        select(EnrollmentCode).where(EnrollmentCode.code_hash == hash_token(normalise_enrollment_code(body.code)))
    )
    if ec is None or ec.used_at is not None or ec.expires_at < utcnow():
        audit(db, "agent_download_denied", username="agent", ip=ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired enrollment code")
    exe = _agent_file()
    if exe is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Agent build is not uploaded to the server yet")
    audit(db, "agent_downloaded", username="agent", ip=ip, code_id=ec.id)
    return FileResponse(
        exe,
        media_type="application/octet-stream",
        filename=EXE_NAME,
        headers={"X-Agent-SHA256": _sha256(exe), "X-Agent-Version": _version()},
    )


@router.get("/api/agent/package")
def agent_package_info(_: User = Depends(require_role("admin"))):
    exe = _agent_file()
    if exe is None:
        return {"available": False, "version": "", "sha256": "", "size": 0}
    return {"available": True, "version": _version(), "sha256": _sha256(exe), "size": exe.stat().st_size}
