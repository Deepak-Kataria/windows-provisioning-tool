import re
from pathlib import Path

from .conftest import PASSWORD, login, make_user

APP = Path(__file__).resolve().parents[1] / "app"


def test_pages_redirect_to_login_when_logged_out(client):
    for path in ("/", "/machines", "/jobs", "/users", "/audit", "/account", "/machines/x", "/jobs/x"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path


def test_login_page_and_static(client):
    assert "Sign in" in client.get("/login").text
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/pages/login.js").status_code == 200


def test_pending_mfa_session_cannot_see_pages(client):
    make_user("alice")
    client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert client.get("/", follow_redirects=False).status_code == 303


def test_admin_sees_all_pages(admin):
    for path in ("/", "/machines", "/jobs", "/users", "/audit", "/account", "/machines/abc", "/jobs/abc"):
        r = admin.get(path)
        assert r.status_code == 200, path
        assert f'data-csrf="{admin.csrf}"' in r.text


def test_logged_in_user_skips_login_page(admin):
    r = admin.get("/login", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_viewer_blocked_from_admin_pages(client, clock):
    make_user("view", "viewer")
    v = login(client, clock, "view")
    assert v.get("/users").status_code == 403
    assert v.get("/audit").status_code == 403
    page = v.get("/machines").text
    assert "Add machine" not in page and 'href="/users"' not in page


def test_must_change_password_redirects_to_account(client, clock, admin):
    admin.post("/api/users", json={"username": "bob", "role": "technician", "password": PASSWORD})
    bob = login(client, clock, "bob")
    r = bob.get("/machines", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/account"
    assert "Choose a new one" in bob.get("/account").text


def test_mfa_setup_returns_qr(client):
    make_user("alice")
    r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    s = client.post("/api/auth/mfa/setup", headers={"X-CSRF-Token": r.json()["csrf_token"]}).json()
    assert s["qr_svg"].startswith("data:image/svg+xml;base64,")


def test_templates_have_no_inline_script_or_handlers():
    """CSP is script-src 'self': inline scripts and on*= attributes would be blocked."""
    for f in (APP / "templates").glob("*.html"):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text), f.name
        assert not re.search(r"\son[a-z]+\s*=", text), f.name


def test_js_never_uses_innerhtml():
    for f in (APP / "static").rglob("*.js"):
        assert ".innerHTML" not in f.read_text(encoding="utf-8"), f.name
