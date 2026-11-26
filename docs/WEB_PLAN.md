# Web-Hosted Provisioning Tool - Plan

Status: draft, 2026-11-26. Desktop app (v1.3.0) stays as-is and keeps working in parallel.

## Decisions (from user)

| Question | Answer |
|---|---|
| Server OS | Linux (Ubuntu/Debian) |
| Domain | Have one - use a subdomain, e.g. `prov.<domain>` |
| Admin UI access | Public internet, protected by password + MFA |
| Fleet size | Few admin users now; machine count must scale to any number |

## Architecture

```
 Admin browser ──HTTPS──►  Caddy (TLS, Let's Encrypt)  ──►  FastAPI server  ──►  PostgreSQL
                                     ▲                          │
                                     │ WSS 443 (outbound only)  │ jobs / results
                         Agent (Windows service) on each PC ◄───┘
                                     │
                                     └─► runs bundled, signed scripts/*.ps1 locally
```

- PCs never accept inbound connections. The agent dials out over 443, so it works on fresh,
  pre-domain PCs behind any NAT/firewall. No WinRM.
- The server sends **action IDs + validated parameters**, never raw commands.
- The agent only runs scripts from a **signed script bundle** shipped with it. Even a fully
  compromised server cannot make an agent run new code.

## Stack

| Part | Choice | Why |
|---|---|---|
| Reverse proxy | Caddy | Automatic Let's Encrypt TLS, security headers, simple config |
| Backend | Python 3.11 + FastAPI | Same language as today; reuse `modules/` |
| Database | PostgreSQL 16 | Scales to large fleets from day one (no SQLite migration later) |
| Frontend | Server-rendered Jinja + HTMX + Alpine.js | One language, no JS build chain; live output over WebSocket |
| Agent | Python, PyInstaller exe, runs as Windows service | Reuse `modules/runner.py`, `scripts/`, `config/` |
| Deploy | Docker Compose (caddy, api, postgres) on Ubuntu 24.04 LTS | One-command deploy, easy backup/restore |

Scale notes: one FastAPI box holds thousands of idle agent WebSockets. If it ever needs more
than one API worker, add Redis pub/sub to route jobs between workers - no redesign needed.

## Security (public admin UI, so these are required, not optional)

1. **Login**: bcrypt passwords (reuse `modules/auth.py`), **TOTP MFA mandatory** for every
   account, login rate limit + lockout, generic error messages.
2. **Sessions**: secure, HttpOnly, SameSite=Strict cookies; CSRF tokens on all POSTs; idle timeout.
3. **Roles**: reuse existing role model - `admin` (everything, user mgmt), `technician`
   (run actions), `viewer` (read-only).
4. **Agent enrollment**: admin creates a one-time enrollment code (expires in 24h); agent trades
   it for a unique per-machine token. Tokens hashed in DB, revocable per machine.
5. **Allowlisted actions only**: each action has a JSON schema for its params; server and agent
   both validate. Script bundle signed (Ed25519) with a key kept OFF the server.
6. **Secrets**: domain-join credentials are entered per job, sent once over TLS, never stored
   in DB or logs.
7. **Audit log**: every login, action, param set (secrets redacted), result, who/when/which PC.
8. **Server hardening**: UFW (only 22 from your IP, 80/443 public), SSH keys only, fail2ban,
   unattended-upgrades, nightly encrypted Postgres backups off-box.
9. Optional extra: put the domain behind Cloudflare proxy to hide the server IP and absorb abuse.

## Reuse vs rewrite

| Today | Web version |
|---|---|
| `scripts/*.ps1` | Reused unchanged inside the agent's script bundle |
| `config/*.json` | Moved to server DB (editable in web UI); pushed to agents with jobs |
| `modules/runner.py`, `security_checks.py`, `threat_checks.py`, `appx.py`, `installed_apps.py`, `reg_state.py` | Reused in agent |
| `modules/auth.py`, `logger.py`, `security_report.py`, `threat_report.py` | Reused/adapted in server |
| `ui/*.py` (CustomTkinter) | Rewritten as web pages |
| `config/credentials.json` | Replaced by users table in Postgres |

## Repo layout (monorepo, desktop app untouched)

```
web/
  server/        FastAPI app, templates, static, alembic migrations
  agent/         Windows agent (service, WS client, action registry)
  actions/       Action definitions: id, script, param JSON schema, role required
  deploy/        docker-compose.yml, Caddyfile, backup scripts
```

## Phases

### Phase 0 - Foundation (~1 week)
- Ubuntu server: Docker, UFW, Caddy with TLS on `prov.<domain>`.
- FastAPI skeleton, Postgres, migrations, users + roles, login with mandatory TOTP MFA.
- Agent skeleton: install as service, enroll with code, heartbeat over WSS.
- Machines page: list with online/offline, last seen, revoke.

### Phase 1 - First usable version (~1.5-2 weeks)
- System Info (read-only) per machine.
- Security scan: run 36 checks, show HIGH/MEDIUM/LOW, export report. Fix buttons later.
- Apps: Common + Team apps install via winget, live progress, stop button.
- Audit log page.

### Phase 2 - Configuration actions (~2-3 weeks)
- Debloat (with rollback), Tweaks, Telemetry, Cleanup Hub.
- Security tab Fix buttons.
- Bulk actions: run one action on many machines; machine groups/tags.

### Phase 3 - Identity + reports (~2 weeks)
- PC rename, domain join (OU browser via agent LDAP query), hardware ID.
- Threat Report.
- Restart/shutdown with countdown.

### Phase 4 - Polish (~1-2 weeks)
- Agent self-update (signed), script bundle versioning.
- Job history/search, CSV export, email alerts for failed jobs.

Total: ~7-10 weeks for full parity. Phase 0 + 1 (~3 weeks) gives a working, secure product.

## Getting the agent onto a fresh PC

1. Admin clicks "Add machine" -> gets a one-time code + download link.
2. On the PC: run `agent-setup.exe` (from USB or the `\\daks` share), paste code.
3. Agent installs as a service, enrolls, appears in the Machines list within seconds.
4. After provisioning, admin can keep the agent (ongoing management) or click "Uninstall agent".

## Before starting Phase 0 - need from user

- Subdomain to use (e.g. `prov.<domain>`) and access to its DNS to add an A record.
- SSH access to the Ubuntu server (or user runs the setup commands).
- Confirm Docker is OK on the server.
