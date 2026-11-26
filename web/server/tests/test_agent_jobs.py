import json
from datetime import timedelta
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from app.actions import Registry
from app.config import get_settings
from app.db import new_session, utcnow
from app.models import EnrollmentCode, Job

from .conftest import login, make_user


def enroll(admin, hostname="PC-01"):
    code = admin.post("/api/enrollment-codes", json={"label": "desk 4"}).json()["code"]
    r = admin.c.post(
        "/api/agent/enroll",
        json={"code": code, "hostname": hostname, "agent_version": "0.1.0", "os_info": {"build": "26100"}},
    )
    assert r.status_code == 200, r.text
    return r.json()


def agent_ws(client, token, running=()):
    ws = client.websocket_connect("/api/agent/ws", headers={"Authorization": f"Bearer {token}"})
    ws.__enter__()
    ws.send_json({"type": "hello", "agent_version": "0.1.0", "hostname": "PC-01", "running_jobs": list(running)})
    welcome = ws.receive_json()
    assert welcome["type"] == "welcome"
    ws.close = lambda *a, **k: ws.__exit__(None, None, None)  # disconnect and join the session
    return ws


# ------------------------------------------------------------------ enrollment

def test_enroll_creates_machine_and_code_is_single_use(admin):
    code = admin.post("/api/enrollment-codes", json={"label": "x"}).json()["code"]
    body = {"code": code.lower().replace("-", ""), "hostname": "PC-01"}  # normalised
    assert admin.c.post("/api/agent/enroll", json=body).status_code == 200
    assert admin.c.post("/api/agent/enroll", json=body).status_code == 401
    machines = admin.get("/api/machines").json()
    assert [m["hostname"] for m in machines] == ["PC-01"]
    assert machines[0]["label"] == "x"
    assert machines[0]["online"] is False


def test_expired_code_rejected(admin):
    code = admin.post("/api/enrollment-codes", json={}).json()["code"]
    with new_session() as db:
        for ec in db.query(EnrollmentCode):
            ec.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    r = admin.c.post("/api/agent/enroll", json={"code": code, "hostname": "PC"})
    assert r.status_code == 401


def test_only_admin_creates_codes(client, clock, admin):
    make_user("tech", "technician")
    tech = login(client, clock, "tech")
    assert tech.post("/api/enrollment-codes", json={}).status_code == 403


# ------------------------------------------------------------------ agent channel

def test_ws_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/api/agent/ws", headers={"Authorization": "Bearer nope"}):
            pass
    assert e.value.code == 4401


def test_online_status_and_hello_updates_machine(admin):
    a = enroll(admin)
    ws = agent_ws(admin.c, a["token"])
    m = admin.get(f"/api/machines/{a['machine_id']}").json()
    assert m["online"] is True and m["last_seen_at"] is not None
    assert admin.get("/api/machines/summary").json() == {"total": 1, "online": 1}
    ws.close()


def test_ping_job_roundtrip(admin):
    a = enroll(admin)
    ws = agent_ws(admin.c, a["token"])
    r = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping", "params": {"message": "hi"}})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    msg = ws.receive_json()
    assert msg == {"type": "job", "job_id": job_id, "action": "agent.ping", "params": {"message": "hi"}, "timeout_seconds": 30}
    assert admin.get(f"/api/jobs/{job_id}").json()["status"] == "sent"

    ws.send_json({"type": "job_started", "job_id": job_id})
    ws.send_json({"type": "job_output", "job_id": job_id, "lines": [{"stream": "stdout", "data": "pong hi"}]})
    ws.send_json({"type": "job_done", "job_id": job_id, "status": "succeeded", "exit_code": 0, "result": {"echo": "hi"}})
    ws.send_json({"type": "heartbeat"})  # round-trip barrier
    _wait_status(admin, job_id, "succeeded")
    job = admin.get(f"/api/jobs/{job_id}").json()
    assert job["result"] == {"echo": "hi"} and job["exit_code"] == 0
    logs = admin.get(f"/api/jobs/{job_id}/logs").json()
    assert [l["data"] for l in logs] == ["pong hi"]
    ws.close()


def _wait_status(admin, job_id, status, tries=50):
    import time

    for _ in range(tries):
        if admin.get(f"/api/jobs/{job_id}").json()["status"] == status:
            return
        time.sleep(0.05)
    raise AssertionError(f"job never reached {status}: {admin.get(f'/api/jobs/{job_id}').json()}")


def test_job_queued_while_offline_is_sent_on_connect(admin):
    a = enroll(admin)
    r = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"})
    job_id = r.json()["id"]
    assert r.json()["status"] == "queued"
    ws = agent_ws(admin.c, a["token"])
    assert ws.receive_json()["job_id"] == job_id
    ws.close()


def test_lost_job_marked_failed_on_reconnect(admin):
    a = enroll(admin)
    ws = agent_ws(admin.c, a["token"])
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).json()["id"]
    ws.receive_json()
    ws.close()
    ws = agent_ws(admin.c, a["token"], running=[])  # agent restarted, forgot the job
    assert admin.get(f"/api/jobs/{job_id}").json()["status"] == "failed"
    ws.close()


def test_agent_cannot_touch_another_machines_job(admin):
    a = enroll(admin, "PC-A")
    b = enroll(admin, "PC-B")
    ws_a = agent_ws(admin.c, a["token"])
    ws_b = agent_ws(admin.c, b["token"])
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).json()["id"]
    ws_a.receive_json()
    ws_b.send_json({"type": "job_done", "job_id": job_id, "status": "succeeded", "result": {"evil": 1}})
    ws_b.send_json({"type": "heartbeat"})
    import time

    time.sleep(0.2)
    assert admin.get(f"/api/jobs/{job_id}").json()["status"] == "sent"
    ws_a.close()
    ws_b.close()


def test_unknown_action_and_bad_params_rejected(admin):
    a = enroll(admin)
    url = f"/api/machines/{a['machine_id']}/jobs"
    assert admin.post(url, json={"action": "rm.rf"}).status_code == 422
    assert admin.post(url, json={"action": "agent.ping", "params": {"cmd": "whoami"}}).status_code == 422
    assert admin.post(url, json={"action": "agent.ping", "params": {"message": 5}}).status_code == 422


def test_viewer_cannot_run_jobs(client, clock, admin):
    a = enroll(admin)
    make_user("view", "viewer")
    v = login(client, clock, "view")
    assert v.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).status_code == 403
    assert v.get("/api/machines").status_code == 200


def test_revoke_kicks_agent_and_blocks_reconnect(admin):
    a = enroll(admin)
    ws = agent_ws(admin.c, a["token"])
    assert admin.post(f"/api/machines/{a['machine_id']}/revoke").status_code == 200
    with pytest.raises(WebSocketDisconnect):
        ws.receive_json()
    ws.close()
    with pytest.raises(WebSocketDisconnect) as e:
        with admin.c.websocket_connect("/api/agent/ws", headers={"Authorization": f"Bearer {a['token']}"}):
            pass
    assert e.value.code == 4401
    assert admin.delete(f"/api/machines/{a['machine_id']}").status_code == 204


def test_cancel_queued_job(admin):
    a = enroll(admin)
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).json()["id"]
    assert admin.post(f"/api/jobs/{job_id}/cancel").json()["status"] == "cancelled"


def test_cancel_running_job_is_sent_to_agent(admin):
    a = enroll(admin)
    ws = agent_ws(admin.c, a["token"])
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).json()["id"]
    ws.receive_json()
    admin.post(f"/api/jobs/{job_id}/cancel")
    assert ws.receive_json() == {"type": "cancel", "job_id": job_id}
    ws.close()


def test_secret_params_never_stored_and_require_online(admin, tmp_path):
    (tmp_path / "secret.json").write_text(
        json.dumps(
            {
                "id": "test.secret",
                "title": "t",
                "min_role": "technician",
                "params": {"properties": {"user": {"type": "string"}, "password": {"type": "string"}}},
                "secret_params": ["password"],
            }
        )
    )
    admin.c.app.state.registry = Registry(tmp_path)
    a = enroll(admin)
    url = f"/api/machines/{a['machine_id']}/jobs"
    body = {"action": "test.secret", "params": {"user": "u", "password": "hunter2-Secret"}}
    assert admin.post(url, json=body).status_code == 409  # offline

    ws = agent_ws(admin.c, a["token"])
    r = admin.post(url, json=body)
    assert r.status_code == 201
    assert r.json()["params"] == {"user": "u", "password": "***"}
    assert ws.receive_json()["params"]["password"] == "hunter2-Secret"  # agent gets the real one
    audit = admin.get("/api/audit").json()
    assert "hunter2-Secret" not in json.dumps(audit)
    with new_session() as db:
        assert all("hunter2" not in json.dumps(j.params) for j in db.query(Job))
    ws.close()


def test_browser_stream_gets_backlog_and_live_lines(admin):
    a = enroll(admin)
    ws = agent_ws(admin.c, a["token"])
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).json()["id"]
    ws.receive_json()
    ws.send_json({"type": "job_output", "job_id": job_id, "lines": [{"data": "one"}]})
    ws.send_json({"type": "heartbeat"})
    import time

    time.sleep(0.1)
    with admin.c.websocket_connect(f"/api/jobs/{job_id}/stream") as view:
        assert view.receive_json() == {"type": "line", "seq": 1, "stream": "stdout", "data": "one"}
        assert view.receive_json()["type"] == "status"
        ws.send_json({"type": "job_output", "job_id": job_id, "lines": [{"data": "two"}]})
        assert view.receive_json()["data"] == "two"
        ws.send_json({"type": "job_done", "job_id": job_id, "status": "succeeded", "exit_code": 0})
        assert view.receive_json() == {"type": "status", "status": "succeeded", "exit_code": 0}
    ws.close()


def test_browser_stream_requires_login(client, admin):
    a = enroll(admin)
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).json()["id"]
    client.cookies.clear()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/jobs/{job_id}/stream") as v:
            v.receive_json()


def test_browser_stream_rejects_foreign_origin(admin):
    a = enroll(admin)
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).json()["id"]
    with pytest.raises(WebSocketDisconnect):
        with admin.c.websocket_connect(f"/api/jobs/{job_id}/stream", headers={"Origin": "https://evil.example"}) as v:
            v.receive_json()


def test_all_real_action_files_load():
    reg = Registry(get_settings().actions_dir)
    assert "agent.ping" in reg.actions
    assert Path(get_settings().actions_dir).is_dir()
