"""HTML pages. Each page is a server-rendered shell; its JS module (static/pages/*.js) loads
data from the JSON API. All scripts are files (CSP: script-src 'self'), no inline JS."""
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import get_db
from .deps import _load_session
from .models import WebSession

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=HERE / "templates")
router = APIRouter(include_in_schema=False)

# path -> (template, nav key, minimum role)
PAGES = {
    "/": ("dashboard.html", "dashboard", "viewer"),
    "/machines": ("machines.html", "machines", "viewer"),
    "/jobs": ("jobs.html", "jobs", "viewer"),
    "/users": ("users.html", "users", "admin"),
    "/audit": ("audit.html", "audit", "admin"),
    "/account": ("account.html", "account", "viewer"),
}


def _session(request: Request, db: Session) -> WebSession | None:
    ws = _load_session(request, db)
    return ws if ws is not None and ws.mfa_verified else None


def _render(request: Request, ws: WebSession, template: str, nav: str, minimum: str, **ctx):
    user = ws.user
    if user.must_change_password and nav != "account":
        return RedirectResponse("/account", status_code=303)
    if not user.has_role(minimum):
        return templates.TemplateResponse(
            request, "error.html", {"user": user, "csrf": ws.csrf_token, "nav": "", "message": "You do not have access to this page."},
            status_code=403,
        )
    return templates.TemplateResponse(
        request, template, {"user": user, "csrf": ws.csrf_token, "nav": nav, **ctx}
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if _session(request, db):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


def _page(path: str):
    template, nav, minimum = PAGES[path]

    def view(request: Request, db: Session = Depends(get_db)):
        ws = _session(request, db)
        if ws is None:
            return RedirectResponse("/login", status_code=303)
        return _render(request, ws, template, nav, minimum)

    return view


for _path in PAGES:
    router.add_api_route(_path, _page(_path), methods=["GET"], response_class=HTMLResponse)


@router.get("/machines/{machine_id}", response_class=HTMLResponse)
def machine_page(machine_id: str, request: Request, db: Session = Depends(get_db)):
    ws = _session(request, db)
    if ws is None:
        return RedirectResponse("/login", status_code=303)
    return _render(request, ws, "machine.html", "machines", "viewer", machine_id=machine_id)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str, request: Request, db: Session = Depends(get_db)):
    ws = _session(request, db)
    if ws is None:
        return RedirectResponse("/login", status_code=303)
    return _render(request, ws, "job.html", "jobs", "viewer", job_id=job_id)
