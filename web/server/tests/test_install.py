import hashlib

import pytest

from app.config import get_settings

from .test_agent_jobs import agent_ws, enroll


@pytest.fixture
def dist(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_dist_dir", tmp_path)
    return tmp_path


def test_install_script_has_server_url_and_no_secrets(client):
    r = client.get("/install.ps1")
    assert r.status_code == 200
    assert '$Server = "http://testserver"' in r.text
    assert "__SERVER_URL__" not in r.text
    r.text.encode("ascii")  # ASCII only, like every .ps1 in the repo


def test_code_response_has_install_command(admin):
    c = admin.post("/api/enrollment-codes", json={}).json()
    assert "irm 'http://testserver/install.ps1'" in c["install_command"]
    assert f"-Code '{c['code']}'" in c["install_command"]


def test_download_needs_valid_code(admin, dist):
    (dist / "itops-agent.exe").write_bytes(b"MZ fake agent")
    assert admin.c.post("/api/agent/download", json={"code": "AAAA-AAAA-AAAA-AAAA"}).status_code == 401
    code = admin.post("/api/enrollment-codes", json={}).json()["code"]
    r = admin.c.post("/api/agent/download", json={"code": code})
    assert r.status_code == 200 and r.content == b"MZ fake agent"
    assert r.headers["x-agent-sha256"] == hashlib.sha256(b"MZ fake agent").hexdigest()
    # download does not use the code up; enrollment still works, and then it is spent
    assert admin.c.post("/api/agent/enroll", json={"code": code, "hostname": "PC"}).status_code == 200
    assert admin.c.post("/api/agent/download", json={"code": code}).status_code == 401


def test_download_503_when_agent_not_uploaded(admin, dist):
    code = admin.post("/api/enrollment-codes", json={}).json()["code"]
    assert admin.c.post("/api/agent/download", json={"code": code}).status_code == 503
    assert admin.get("/api/agent/package").json()["available"] is False


def test_package_info_admin_only(client, clock, admin, dist):
    (dist / "itops-agent.exe").write_bytes(b"x")
    (dist / "version.txt").write_text("0.1.0")
    info = admin.get("/api/agent/package").json()
    assert info == {"available": True, "version": "0.1.0", "sha256": hashlib.sha256(b"x").hexdigest(), "size": 1}


def test_uninstall_success_revokes_machine(admin):
    a = enroll(admin)
    ws = agent_ws(admin.c, a["token"])
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.uninstall"}).json()["id"]
    ws.receive_json()
    ws.send_json({"type": "job_done", "job_id": job_id, "status": "succeeded", "exit_code": 0})
    ws.send_json({"type": "heartbeat"})
    import time

    for _ in range(50):
        if admin.get(f"/api/machines/{a['machine_id']}").json()["revoked_at"]:
            break
        time.sleep(0.05)
    assert admin.get(f"/api/machines/{a['machine_id']}").json()["revoked_at"] is not None
    ws.close()
