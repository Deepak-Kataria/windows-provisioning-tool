import os

os.environ["ITOPS_DATABASE_URL"] = "sqlite://"
os.environ["ITOPS_SECRET_KEY"] = "test-secret"
os.environ["ITOPS_BASE_URL"] = "http://testserver"

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import security  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, get_engine, new_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import User  # noqa: E402
from app.ratelimit import enroll_limiter, login_limiter  # noqa: E402

PASSWORD = "Correct-Horse-9"


class Clock:
    """Fake clock for TOTP so tests never hit the replay guard by accident."""

    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def time(self) -> float:
        return self.now

    def code(self, secret: str) -> str:
        self.now += 30
        return pyotp.TOTP(secret).at(self.now)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(security.time, "time", c.time)
    return c


@pytest.fixture
def client(clock):
    get_settings.cache_clear()
    app = create_app()
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    login_limiter.reset()
    enroll_limiter.reset()
    with TestClient(app) as c:
        yield c


def make_user(username: str, role: str = "admin", **kw) -> User:
    with new_session() as db:
        u = User(
            username=username,
            display_name=username,
            role=role,
            password_hash=security.hash_password(PASSWORD),
            **kw,
        )
        db.add(u)
        db.commit()
        return u


class Session:
    """A logged-in browser: keeps cookies + CSRF token and sends it on writes."""

    def __init__(self, client: TestClient, csrf: str, secret: str) -> None:
        self.c = client
        self.csrf = csrf
        self.secret = secret

    def _h(self):
        return {"X-CSRF-Token": self.csrf}

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self._h(), **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self._h(), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h(), **kw)


def login(client: TestClient, clock: Clock, username: str, secret: str | None = None) -> Session:
    """Full login. First login enrolls MFA and returns the new secret on the Session."""
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    h = {"X-CSRF-Token": body["csrf_token"]}
    if body["next"] == "mfa_setup":
        r = client.post("/api/auth/mfa/setup", headers=h)
        assert r.status_code == 200, r.text
        secret = r.json()["secret"]
        r = client.post("/api/auth/mfa/confirm", headers=h, json={"code": clock.code(secret)})
    else:
        assert secret, "user already has MFA; pass its secret"
        r = client.post("/api/auth/mfa", headers=h, json={"code": clock.code(secret)})
    assert r.status_code == 200, r.text
    assert r.json()["next"] == "done"
    return Session(client, r.json()["csrf_token"], secret)


@pytest.fixture
def admin(client, clock) -> Session:
    make_user("admin", "admin")
    return login(client, clock, "admin")
