from .conftest import login, make_user
from .test_agent_jobs import agent_ws, enroll


def test_tags_set_filter_and_list(admin):
    a = enroll(admin, "PC-A")
    b = enroll(admin, "PC-B")
    r = admin.patch(f"/api/machines/{a['machine_id']}", json={"tags": ["Sales", "floor2", "sales"]})
    assert r.json()["tags"] == ["floor2", "sales"]
    admin.patch(f"/api/machines/{b['machine_id']}", json={"tags": ["floor2"]})
    assert [m["hostname"] for m in admin.get("/api/machines", params={"tag": "sales"}).json()] == ["PC-A"]
    assert len(admin.get("/api/machines", params={"tag": "floor2"}).json()) == 2
    assert admin.get("/api/machines", params={"tag": "floor"}).json() == []  # whole tag only
    assert admin.get("/api/tags").json() == [{"tag": "floor2", "machines": 2}, {"tag": "sales", "machines": 1}]


def test_bad_tags_rejected(admin):
    a = enroll(admin)
    assert admin.patch(f"/api/machines/{a['machine_id']}", json={"tags": ["a,b"]}).status_code == 422
    assert admin.patch(f"/api/machines/{a['machine_id']}", json={"tags": ["%"]}).status_code == 422


def test_bulk_by_tag_sends_online_and_queues_offline(admin):
    a = enroll(admin, "PC-A")
    b = enroll(admin, "PC-B")
    c = enroll(admin, "PC-C")
    for m in (a, b):
        admin.patch(f"/api/machines/{m['machine_id']}", json={"tags": ["lab"]})
    ws = agent_ws(admin.c, a["token"])
    try:
        r = admin.post("/api/bulk-jobs", json={"action": "agent.ping", "tag": "lab"})
        assert r.status_code == 201, r.text
        out = r.json()
        assert (out["total"], out["sent"], out["queued"]) == (2, 1, 1)
        assert ws.receive_json()["action"] == "agent.ping"
        batch = admin.get(f"/api/batches/{out['batch_id']}").json()
        assert sorted(j["machine_id"] for j in batch["jobs"]) == sorted([a["machine_id"], b["machine_id"]])
        assert batch["counts"] == {"sent": 1, "queued": 1}
        assert c["machine_id"] not in [j["machine_id"] for j in batch["jobs"]]
        assert admin.get("/api/batches").json()[0]["batch_id"] == out["batch_id"]
        assert len(admin.get("/api/jobs", params={"batch_id": out["batch_id"]}).json()) == 2
    finally:
        ws.close()


def test_bulk_by_ids_and_cancel(admin):
    a = enroll(admin, "PC-A")
    b = enroll(admin, "PC-B")
    r = admin.post("/api/bulk-jobs", json={"action": "system.info", "machine_ids": [a["machine_id"], b["machine_id"]]})
    bid = r.json()["batch_id"]
    assert admin.post(f"/api/batches/{bid}/cancel").json() == {"cancelled": 2}
    assert admin.get(f"/api/batches/{bid}").json()["counts"] == {"cancelled": 2}


def test_bulk_rules(client, clock, admin):
    a = enroll(admin)
    assert admin.post("/api/bulk-jobs", json={"action": "agent.ping"}).status_code == 422  # no targets
    assert admin.post("/api/bulk-jobs", json={"action": "agent.uninstall", "machine_ids": [a["machine_id"]]}).status_code == 422
    assert admin.post("/api/bulk-jobs", json={"action": "agent.ping", "tag": "nobody"}).status_code == 404
    bad = {"action": "apps.install", "params": {"ids": ["x y"]}, "machine_ids": [a["machine_id"]]}
    assert admin.post("/api/bulk-jobs", json=bad).status_code == 422
    make_user("view", "viewer")
    v = login(client, clock, "view")
    assert v.post("/api/bulk-jobs", json={"action": "agent.ping", "machine_ids": [a["machine_id"]]}).status_code == 403


def test_revoked_machines_never_in_bulk(admin):
    a = enroll(admin, "PC-A")
    admin.patch(f"/api/machines/{a['machine_id']}", json={"tags": ["lab"]})
    admin.post(f"/api/machines/{a['machine_id']}/revoke")
    assert admin.post("/api/bulk-jobs", json={"action": "agent.ping", "tag": "lab"}).status_code == 404


def test_phase2_catalogs(admin):
    deb = admin.get("/api/catalog/debloat").json()
    assert any(x["package"] == "Microsoft.XboxApp" for x in deb)
    tw = admin.get("/api/catalog/tweaks").json()
    assert {"essential", "advanced"} <= {t["section"] for t in tw}
