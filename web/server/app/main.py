"""FastAPI application factory.

Run locally:  uvicorn app.main:app --reload   (from web/server)
"""
import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import timedelta

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete

from .actions import Registry
from .config import Settings, get_settings
from .db import Base, get_engine, init_engine, new_session, utcnow
from .models import WebSession
from . import web
from .routers import agent, auth, catalog, install, jobs, machines, users

APP_VERSION = "0.1.0"


def _cleanup_sessions() -> None:
    s = get_settings()
    with new_session() as db:
        db.execute(
            delete(WebSession).where(
                (WebSession.last_seen_at < utcnow() - timedelta(minutes=s.session_idle_minutes))
                | (WebSession.created_at < utcnow() - timedelta(hours=s.session_max_hours))
            )
        )
        db.commit()


async def _housekeeping() -> None:
    while True:
        await asyncio.sleep(3600)
        with contextlib.suppress(Exception):
            await asyncio.to_thread(_cleanup_sessions)


def _dev_migrate(url: str) -> None:
    """Local SQLite: bring the schema up to date. (Postgres: the container runs `alembic upgrade head`.)"""
    from sqlalchemy import inspect

    from . import models  # noqa: F401

    if url in ("sqlite://", "sqlite:///:memory:"):
        Base.metadata.create_all(get_engine())  # tests
        return
    from alembic import command
    from alembic.config import Config

    here = Path(__file__).resolve().parents[1]
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    tables = set(inspect(get_engine()).get_table_names())
    if "users" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "0001")  # old dev DB made by create_all before migrations existed
    command.upgrade(cfg, "head")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.is_sqlite:
            _dev_migrate(settings.database_url)
        task = asyncio.create_task(_housekeeping())
        yield
        task.cancel()

    app = FastAPI(
        title="IT Provisioning",
        version=APP_VERSION,
        lifespan=lifespan,
        # API docs only in dev; no need to advertise the API surface on the public site.
        docs_url="/api/docs" if not settings.cookie_secure else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not settings.cookie_secure else None,
    )
    app.state.registry = Registry(settings.actions_dir)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        if not request.url.path.startswith("/static/"):
            h.setdefault("Cache-Control", "no-store")
        h.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        if settings.cookie_secure:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

    for r in (auth.router, users.router, machines.router, jobs.router, catalog.router, agent.router, install.router):
        app.include_router(r)
    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": APP_VERSION}

    return app


app = create_app()
