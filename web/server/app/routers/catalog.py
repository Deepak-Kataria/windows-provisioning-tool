"""Read-only data for the UI: app catalog, latest action results, report exports."""
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import require_role
from ..models import Job, User
from ..schemas import JobOut
from .machines import get_machine

router = APIRouter(prefix="/api", tags=["catalog"])


def load_app_catalog() -> dict:
    d = get_settings().config_dir
    try:
        common = json.loads((d / "apps_common.json").read_text(encoding="utf-8"))
        teams = json.loads((d / "apps_teams.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "app catalog not available") from None
    return {
        "common": [{"name": a["name"], "winget_id": a["winget_id"]} for a in common.get("common_apps", [])],
        "teams": {
            team: [{"name": a["name"], "winget_id": a["winget_id"]} for a in apps]
            for team, apps in teams.get("teams", {}).items()
        },
    }


@router.get("/catalog/apps")
def app_catalog(_: User = Depends(require_role("viewer"))):
    return load_app_catalog()


@router.get("/machines/{machine_id}/latest", response_model=JobOut | None)
def latest_result(
    machine_id: str,
    action: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("viewer")),
):
    """Most recent successful run of an action on a machine (e.g. last security scan)."""
    get_machine(db, machine_id)
    return db.scalars(
        select(Job)
        .where(Job.machine_id == machine_id, Job.action_id == action, Job.status == "succeeded")
        .order_by(Job.finished_at.desc())
        .limit(1)
    ).first()


def _csv_safe(value) -> str:
    """Stop spreadsheet formula injection from values a PC reported."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get("/jobs/{job_id}/report.csv")
def security_report_csv(
    job_id: str, db: Session = Depends(get_db), _: User = Depends(require_role("viewer"))
):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.action_id != "security.scan" or job.status != "succeeded" or not job.result:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only finished security scans have a report")
    m = get_machine(db, job.machine_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    s = job.result.get("summary", {})
    w.writerow(["Machine", m.hostname, "Scanned (UTC)", job.finished_at.isoformat(timespec="seconds"),
                "Score", s.get("score"), "Risk", s.get("level")])
    w.writerow([])
    cols = ["severity", "category", "name", "status", "detail", "impact", "id"]
    w.writerow([c.title() for c in cols])
    for row in job.result.get("checks", []):
        w.writerow([_csv_safe(row.get(c)) for c in cols])
    name = f"security-{m.hostname}-{job.finished_at:%Y%m%d-%H%M}.csv".replace(" ", "_")
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
