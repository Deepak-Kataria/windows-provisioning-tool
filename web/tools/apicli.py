"""Tiny command-line client for the web API, for testing until the web UI exists.

  python web/tools/apicli.py login [--server URL] [--user admin]
  python web/tools/apicli.py code [label]            new enrollment code
  python web/tools/apicli.py machines
  python web/tools/apicli.py actions
  python web/tools/apicli.py run <machine> <action> [json-params]   machine = id or hostname
  python web/tools/apicli.py jobs [machine]
  python web/tools/apicli.py job <job-id>
  python web/tools/apicli.py cancel <job-id>
  python web/tools/apicli.py audit

The session cookie is kept in web/.dev/apicli.json. First login sets up MFA: the TOTP
secret is printed once - add it to your authenticator app (Microsoft/Google Authenticator).
"""
import argparse
import getpass
import json
import sys
import time
from pathlib import Path

import httpx

STATE = Path(__file__).resolve().parents[1] / ".dev" / "apicli.json"
TERMINAL = ("succeeded", "failed", "cancelled")


def load() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d))


def client(st: dict) -> httpx.Client:
    c = httpx.Client(base_url=st.get("server", "http://127.0.0.1:8000"), timeout=30)
    if st.get("cookie"):
        c.cookies.set("itops_session", st["cookie"])
    c.headers["X-CSRF-Token"] = st.get("csrf", "")
    return c


def check(r: httpx.Response):
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except Exception:
            detail = r.text
        sys.exit(f"HTTP {r.status_code}: {detail}")
    return r.json() if r.content else None


def cmd_login(a) -> None:
    st = {"server": a.server.rstrip("/")}
    c = client(st)
    pw = getpass.getpass(f"Password for {a.user}: ")
    r = check(c.post("/api/auth/login", json={"username": a.user, "password": pw}))
    c.headers["X-CSRF-Token"] = r["csrf_token"]
    if r["next"] == "mfa_setup":
        s = check(c.post("/api/auth/mfa/setup"))
        print("\nFirst login: set up MFA. Add this to your authenticator app:")
        print(f"  secret: {s['secret']}")
        print(f"  uri:    {s['otpauth_uri']}\n")
        r = check(c.post("/api/auth/mfa/confirm", json={"code": input("6-digit code: ").strip()}))
    else:
        r = check(c.post("/api/auth/mfa", json={"code": input("6-digit code: ").strip()}))
    st.update(cookie=c.cookies.get("itops_session"), csrf=r["csrf_token"])
    save(st)
    me = check(client(st).get("/api/auth/me"))["user"]
    print(f"Logged in as {me['username']} ({me['role']})")
    if me["must_change_password"]:
        print("You must change your password: POST /api/auth/password")


def find_machine(c, ref: str) -> dict:
    ms = check(c.get("/api/machines", params={"limit": 1000}))
    hits = [m for m in ms if m["id"] == ref or m["hostname"].lower() == ref.lower()]
    if len(hits) != 1:
        sys.exit(f"machine not found (or ambiguous): {ref}")
    return hits[0]


def show_job(c, job_id: str, follow: bool) -> None:
    seq = 0
    while True:
        for line in check(c.get(f"/api/jobs/{job_id}/logs", params={"after_seq": seq})):
            seq = line["seq"]
            print(("ERR " if line["stream"] == "stderr" else "    ") + line["data"])
        j = check(c.get(f"/api/jobs/{job_id}"))
        if not follow or j["status"] in TERMINAL:
            break
        time.sleep(1)
    print(f"\nstatus: {j['status']}  exit: {j['exit_code']}  {j['error']}")
    if j["result"] is not None:
        print(json.dumps(j["result"], indent=2))


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login")
    lg.add_argument("--server", default="http://127.0.0.1:8000")
    lg.add_argument("--user", default="admin")
    sub.add_parser("code").add_argument("label", nargs="?", default="")
    sub.add_parser("machines")
    sub.add_parser("actions")
    r = sub.add_parser("run")
    r.add_argument("machine")
    r.add_argument("action")
    r.add_argument("params", nargs="?", default="{}")
    sub.add_parser("jobs").add_argument("machine", nargs="?")
    sub.add_parser("job").add_argument("job_id")
    sub.add_parser("cancel").add_argument("job_id")
    sub.add_parser("audit")
    a = p.parse_args()

    if a.cmd == "login":
        return cmd_login(a)
    c = client(load())
    if a.cmd == "code":
        r = check(c.post("/api/enrollment-codes", json={"label": a.label}))
        print(f"{r['code']}   (expires {r['expires_at']} UTC, single use)")
    elif a.cmd == "machines":
        for m in check(c.get("/api/machines", params={"limit": 1000})):
            state = "ONLINE " if m["online"] else "offline"
            print(f"{state}  {m['hostname']:<20} {m['label']:<16} {m['id']}  last seen {m['last_seen_at']}")
    elif a.cmd == "actions":
        for x in check(c.get("/api/actions")):
            print(f"{x['id']:<24} {x['min_role']:<11} {x['title']}")
    elif a.cmd == "run":
        m = find_machine(c, a.machine)
        job = check(c.post(f"/api/machines/{m['id']}/jobs", json={"action": a.action, "params": json.loads(a.params)}))
        print(f"job {job['id']} {job['status']}")
        show_job(c, job["id"], follow=True)
    elif a.cmd == "jobs":
        params = {"machine_id": find_machine(c, a.machine)["id"]} if a.machine else {}
        for j in check(c.get("/api/jobs", params=params)):
            print(f"{j['created_at'][:19]}  {j['status']:<10} {j['action_id']:<22} {j['id']}")
    elif a.cmd == "job":
        show_job(c, a.job_id, follow=False)
    elif a.cmd == "cancel":
        print(check(c.post(f"/api/jobs/{a.job_id}/cancel"))["status"])
    elif a.cmd == "audit":
        for e in check(c.get("/api/audit")):
            print(f"{e['ts'][:19]}  {e['username']:<10} {e['event']:<24} {json.dumps(e['detail'])[:80]}")


if __name__ == "__main__":
    main()
