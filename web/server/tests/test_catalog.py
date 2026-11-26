import csv
import io

from .test_agent_jobs import agent_ws, enroll

SCAN_RESULT = {
    "summary": {"score": 80, "level": "LOW", "counts": {}},
    "checks": [
        {"id": "firewall", "name": "Windows Firewall", "severity": "HIGH", "category": "Network",
         "status": "PASS", "detail": "", "impact": "x"},
        {"id": "evil", "name": "=HYPERLINK(\"http://x\")", "severity": "LOW", "category": "System",
         "status": "FAIL", "detail": "+cmd", "impact": ""},
    ],
}


def test_app_catalog(admin):
    cat = admin.get("/api/catalog/apps").json()
    assert any(a["winget_id"] == "7zip.7zip" for a in cat["common"])
    assert isinstance(cat["teams"], dict)


def _finished_scan(admin):
    a = enroll(admin)
    ws = agent_ws(admin.c, a["token"])
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "security.scan"}).json()["id"]
    ws.receive_json()
    ws.send_json({"type": "job_done", "job_id": job_id, "status": "succeeded", "exit_code": 0, "result": SCAN_RESULT})
    ws.send_json({"type": "heartbeat"})
    import time

    for _ in range(50):
        if admin.get(f"/api/jobs/{job_id}").json()["status"] == "succeeded":
            break
        time.sleep(0.05)
    ws.close()
    return a["machine_id"], job_id


def test_latest_result(admin):
    machine_id, job_id = _finished_scan(admin)
    r = admin.get(f"/api/machines/{machine_id}/latest", params={"action": "security.scan"}).json()
    assert r["id"] == job_id and r["result"]["summary"]["score"] == 80
    assert admin.get(f"/api/machines/{machine_id}/latest", params={"action": "system.info"}).json() is None


def test_security_csv_escapes_formulas(admin):
    _machine_id, job_id = _finished_scan(admin)
    r = admin.get(f"/api/jobs/{job_id}/report.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:2] == ["Machine", "PC-01"]
    evil = next(row for row in rows if row and row[-1] == "evil")
    assert evil[2].startswith("'=") and evil[4].startswith("'+")


def test_csv_only_for_scans(admin):
    a = enroll(admin)
    job_id = admin.post(f"/api/machines/{a['machine_id']}/jobs", json={"action": "agent.ping"}).json()["id"]
    assert admin.get(f"/api/jobs/{job_id}/report.csv").status_code == 409
