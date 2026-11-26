from app.db import new_session
from app.models import AuditLog, User
from sqlalchemy import select

from .conftest import PASSWORD, login, make_user


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_security_headers(client):
    h = client.get("/api/health").headers
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_first_login_requires_mfa_setup_then_works(client, clock):
    make_user("alice")
    s = login(client, clock, "alice")
    r = s.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["user"]["totp_confirmed"] is True
    # second login now asks for the code, not setup
    s2 = login(client, clock, "alice", secret=s.secret)
    assert s2.get("/api/auth/me").status_code == 200


def test_session_cookie_flags(client):
    make_user("alice")
    r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_wrong_password_and_unknown_user_look_the_same(client):
    make_user("alice")
    a = client.post("/api/auth/login", json={"username": "alice", "password": "nope"})
    b = client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_failures(client):
    make_user("alice")
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "alice", "password": "bad"})
    r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 401  # locked, even with the right password
    with new_session() as db:
        events = db.scalars(select(AuditLog.event)).all()
    assert "account_locked" in events


def test_login_rate_limit(client):
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "x", "password": "y"})
    r = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert r.status_code == 429


def test_pending_session_cannot_use_api(client):
    make_user("alice")
    client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert client.get("/api/machines").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_mfa_code_rejected(client, clock):
    make_user("alice")
    s = login(client, clock, "alice")
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    h = {"X-CSRF-Token": r.json()["csrf_token"]}
    assert client.post("/api/auth/mfa", headers=h, json={"code": "000000"}).status_code == 401
    assert client.post("/api/auth/mfa", headers=h, json={"code": clock.code(s.secret)}).status_code == 200


def test_mfa_code_cannot_be_replayed(client, clock):
    make_user("alice")
    s = login(client, clock, "alice")
    code = clock.code(s.secret)
    for expected in (200, 401):
        client.cookies.clear()
        r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
        h = {"X-CSRF-Token": r.json()["csrf_token"]}
        assert client.post("/api/auth/mfa", headers=h, json={"code": code}).status_code == expected


def test_csrf_required_on_writes(admin):
    r = admin.c.post("/api/enrollment-codes", json={})  # no CSRF header
    assert r.status_code == 403
    assert admin.post("/api/enrollment-codes", json={}).status_code == 201


def test_session_id_rotates_after_mfa(client, clock):
    make_user("alice")
    r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    pending_cookie = client.cookies.get("itops_session")
    h = {"X-CSRF-Token": r.json()["csrf_token"]}
    secret = client.post("/api/auth/mfa/setup", headers=h).json()["secret"]
    client.post("/api/auth/mfa/confirm", headers=h, json={"code": clock.code(secret)})
    assert client.cookies.get("itops_session") != pending_cookie


def test_logout(admin):
    assert admin.post("/api/auth/logout").status_code == 204
    assert admin.get("/api/auth/me").status_code == 401


def test_must_change_password_blocks_until_changed(client, clock, admin):
    r = admin.post(
        "/api/users", json={"username": "bob", "role": "technician", "password": PASSWORD}
    )
    assert r.status_code == 201
    bob = login(client, clock, "bob")
    assert bob.get("/api/machines").status_code == 403
    r = bob.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": "Another-Good-77"},
    )
    assert r.status_code == 204
    assert bob.get("/api/machines").status_code == 200


def test_weak_password_rejected(admin):
    r = admin.post("/api/users", json={"username": "bob", "password": "short"})
    assert r.status_code == 400


def test_admin_cannot_demote_self_or_last_admin(admin):
    me = admin.get("/api/auth/me").json()["user"]
    r = admin.patch(f"/api/users/{me['id']}", json={"role": "viewer"})
    assert r.status_code == 400


def test_disable_user_kills_sessions(client, clock, admin):
    make_user("bob", "viewer")
    bob = login(client, clock, "bob")
    bob_cookie = client.cookies.get("itops_session")
    with new_session() as db:
        bob_id = db.scalar(select(User.id).where(User.username == "bob"))
    client.cookies.clear()
    admin = login(client, clock, "admin", secret=admin.secret)
    assert admin.patch(f"/api/users/{bob_id}", json={"is_active": False}).status_code == 200
    client.cookies.clear()
    client.cookies.set("itops_session", bob_cookie)
    assert bob.get("/api/auth/me").status_code == 401


def test_totp_secret_encrypted_at_rest(client, clock):
    make_user("alice")
    s = login(client, clock, "alice")
    with new_session() as db:
        u = db.scalar(select(User).where(User.username == "alice"))
    assert s.secret not in (u.totp_secret_enc or "")
