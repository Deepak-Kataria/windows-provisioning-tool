# IT Provisioning - web version

Plan and design: [`docs/WEB_PLAN.md`](../docs/WEB_PLAN.md). Desktop app (repo root) is untouched.

```
web/
  server/   FastAPI: API (auth + MFA, users, machines, jobs, agent channel, audit) + web pages
  agent/    Windows agent (itops_agent): enroll, outbound WSS, runs signed allowlisted actions
  actions/  Action definitions (*.json) - the ONLY things an agent can run
  tools/    bundle_tool.py (sign script bundle), apicli.py (test client until the UI exists)
  deploy/   server-setup.sh, docker-compose.yml, Caddyfile, .env.example, backup.sh
  dev.ps1   local dev helper
```

Work happens on the `web` git branch.

## Pick up on another PC (office)

```powershell
git fetch
git checkout web
git pull
powershell -ExecutionPolicy Bypass -File web\dev.ps1 setup    # once per PC: creates web\.venv
powershell -ExecutionPolicy Bypass -File web\dev.ps1 test     # should say all passed
```

Needs Python 3.11 on PATH. No Docker or Postgres needed locally (dev uses SQLite in `web\.dev\`).

## Try it locally

```powershell
# one time: first admin user (password: 12+ chars, upper+lower+digit)
powershell -ExecutionPolicy Bypass -File web\dev.ps1 admin

# terminal A: the server
powershell -ExecutionPolicy Bypass -File web\dev.ps1 server
```

Open **http://127.0.0.1:8000** in a browser. First login shows a QR code: scan it with
Microsoft/Google Authenticator. Then Machines -> **Add machine** -> copy the code, and:

```powershell
# terminal B: enroll this PC and run its agent
powershell -ExecutionPolicy Bypass -File web\dev.ps1 enroll XXXX-XXXX-XXXX-XXXX
powershell -ExecutionPolicy Bypass -File web\dev.ps1 agent
```

The PC shows up online. Open it: Overview (system info), Security (scan, fix/revert,
CSV export), Apps (install/uninstall from catalog), Job history. Jobs and Audit log pages too.

Run the agent from an **elevated** terminal for real results (as a service it runs as SYSTEM).
Command-line client (no browser): `web\dev.ps1 cli login`, `cli machines`, `cli run <PC> system.info`.
API docs (dev only): http://127.0.0.1:8000/api/docs. Start fresh: delete `web\.dev\`.

## Security model (short)

- Login = password + **mandatory TOTP**. Lockout after 5 failures, per-IP rate limit, generic errors.
- Cookies HttpOnly + SameSite=Strict + Secure (prod); `X-CSRF-Token` header on every write.
- Roles: `viewer` (read), `technician` (run actions), `admin` (users, enrollment, revoke).
- Agents dial **out** over 443. One-time enrollment code (24h) -> per-machine token, stored
  hashed on the server and DPAPI-encrypted on the PC. Revoke = instant disconnect.
- Server sends only `{action id, params}`. Both server and agent validate params against the
  action's JSON schema. Agent runs a fixed script with argv (no shell). Secret params go via
  env vars, are never stored in DB or audit log, and need the machine online.
- Agent only runs files listed in an **Ed25519-signed bundle**. The signing key never goes on the
  server. Dev mode (`ITOPS_AGENT_DEV=1`) skips the signature - never use it in production.

## Adding an action

1. Write `web/actions/<id>.json` (see `system.info.json`, format in `server/app/actions.py`
   and `agent/itops_agent/executor.py`).
2. Script goes in repo `scripts/` (ASCII only). Output `KEY:value` lines (`"output": "kv"`) or JSON.
3. Re-sign the bundle for production: `python web/tools/bundle_tool.py build --key <key>`.

## Production deploy (when the server is ready)

```bash
# on the Ubuntu server
sudo bash web/deploy/server-setup.sh
cd /opt/itops && git clone -b web https://github.com/Deepak-Kataria/windows-provisioning-tool.git .
cd web/deploy && cp .env.example .env && chmod 600 .env && nano .env
docker compose up -d --build
docker compose exec api python -m app.cli create-admin admin
```

DNS: A record `prov.<domain>` -> server IP, before `docker compose up` (Caddy gets the TLS cert).
