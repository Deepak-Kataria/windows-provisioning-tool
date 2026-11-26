"""Builtin action handlers (code shipped inside the agent).

Each handler: async (ctx: JobContext, params: dict, agent_spec: dict) -> (exit_code, result)
"""
import asyncio
import glob
import json
import os
import re
import shutil
import socket
import sys
from typing import Any

from . import VERSION
from .executor import ActionFailed, JobContext
from .paths import bundle_dir

SCAN_PARALLEL = 4
CHECK_TIMEOUT = 120


def _security_module():
    """The desktop app's check definitions (modules/security_checks.py), reused unchanged."""
    root = str(bundle_dir())
    if root not in sys.path:
        sys.path.insert(0, root)
    from modules import security_checks  # noqa: PLC0415

    return security_checks


# ---------------------------------------------------------------- ping

async def ping(ctx: JobContext, params: dict, _spec: dict):
    msg = params.get("message", "")
    await ctx.sink.line(f"pong {msg}".strip())
    return 0, {"echo": msg, "hostname": socket.gethostname(), "agent_version": VERSION}


# ---------------------------------------------------------------- security

async def security_scan(ctx: JobContext, params: dict, _spec: dict):
    sc = _security_module()
    wanted = params.get("check_ids")
    checks = [c for c in sc.CHECKS if not wanted or c["id"] in wanted]
    unknown = set(wanted or []) - {c["id"] for c in checks}
    if unknown:
        raise ActionFailed(f"unknown check ids: {', '.join(sorted(unknown))}")

    sem = asyncio.Semaphore(SCAN_PARALLEL)
    results: dict[str, tuple[str, str]] = {}

    async def one(check):
        async with sem:
            try:
                _rc, out = await asyncio.wait_for(
                    ctx.powershell(check["check_ps"]), check.get("timeout", CHECK_TIMEOUT)
                )
                status, detail = sc.evaluate(check, out)
            except TimeoutError:
                status, detail = "UNKNOWN", f"check timed out after {check.get('timeout', CHECK_TIMEOUT)}s"
            results[check["id"]] = (status, detail)
            await ctx.sink.line(f"[{check['severity']:<6}] {status:<7} {check['name']}" + (f" - {detail}" if detail else ""))

    await asyncio.gather(*(one(c) for c in checks))
    summary = sc.risk_summary(results, checks)
    await ctx.sink.line(f"Score {summary['score']}/100, risk {summary['level']}", "system")
    rows = []
    for c in sorted(checks, key=lambda c: (sc.SEVERITIES.index(c["severity"]), sc.STATUS_ORDER.get(results[c["id"]][0], 9))):
        status, detail = results[c["id"]]
        rows.append(
            {
                "id": c["id"],
                "name": c["name"],
                "severity": c["severity"],
                "category": c.get("category", ""),
                "status": status,
                "detail": detail,
                "description": c.get("description", ""),
                "impact": c.get("impact", ""),
                "fix_label": c.get("fix_label", ""),
                # Remote fix only for real setting changes that can be reverted; desktop-only
                # "fixes" that just open a Windows tool (shares, programs, ...) are useless remotely.
                "can_fix": sc.is_auto_fixable(c),
                "can_undo": bool(c.get("undo_ps")),
                "disruptive": bool(c.get("disruptive")),
            }
        )
    return 0, {"summary": summary, "checks": rows}


async def security_fix(ctx: JobContext, params: dict, _spec: dict):
    sc = _security_module()
    check = sc.CHECKS_BY_ID.get(params["check_id"])
    if check is None:
        raise ActionFailed(f"unknown check {params['check_id']!r}")
    mode = params.get("mode", "fix")
    if mode == "fix" and not sc.is_auto_fixable(check):
        raise ActionFailed(f"check {check['id']!r} has no remote fix (it needs a person at the PC)")
    script = check.get("fix_ps" if mode == "fix" else "undo_ps")
    if not script:
        raise ActionFailed(f"check {check['id']!r} has no {mode} script")
    await ctx.sink.line(f"{'Applying fix' if mode == 'fix' else 'Reverting'}: {check['name']}", "system")
    rc, out = await ctx.powershell(script)
    for line in out.splitlines():
        await ctx.sink.line(line, "stderr" if line.startswith("ERR:") else "stdout")
    _rc2, out2 = await ctx.powershell(check["check_ps"])
    status, detail = sc.evaluate(check, out2)
    await ctx.sink.line(f"Re-check: {status} {detail}".strip(), "system")
    return rc, {"check_id": check["id"], "mode": mode, "status": status, "detail": detail}


# ---------------------------------------------------------------- winget apps

WINGET_OK = {0: "done"}
WINGET_ALREADY = {-1978335189: "already installed", -1978335135: "already installed"}
WINGET_NOT_INSTALLED = -1978335212  # no installed package found
WINGET_NO_MACHINE_SCOPE = -1978335216  # no applicable installer for --scope machine
_SPINNER = re.compile(r"^[\s\-\\|/]*$|^\s*[\u2580-\u259f\s]+\d*%?\s*$|^\s*[\d.]+ [KMG]B / [\d.]+ [KMG]B\s*$")


def find_winget() -> str:
    """winget is not on PATH for SYSTEM (the service account), so look in WindowsApps too."""
    found = shutil.which("winget")
    if found:
        return found
    pattern = os.path.join(
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        "WindowsApps",
        "Microsoft.DesktopAppInstaller_*_x64__8wekyb3d8bbwe",
        "winget.exe",
    )

    def ver(path: str):
        m = re.search(r"DesktopAppInstaller_([\d.]+)_", path)
        return tuple(int(x) for x in m.group(1).split(".")) if m else ()

    hits = sorted(glob.glob(pattern), key=ver)
    if not hits:
        raise ActionFailed("winget not found on this PC (install App Installer from the Store)")
    return hits[-1]


def app_catalog(ctx: JobContext) -> dict[str, str]:
    """winget id -> display name, from the signed bundle's config/apps_*.json."""
    out: dict[str, str] = {}
    common = json.loads(ctx.bundle.check("config/apps_common.json").read_text(encoding="utf-8"))
    for a in common.get("common_apps", []):
        out[a["winget_id"]] = a["name"]
    teams = json.loads(ctx.bundle.check("config/apps_teams.json").read_text(encoding="utf-8"))
    for apps in teams.get("teams", {}).values():
        for a in apps:
            out.setdefault(a["winget_id"], a["name"])
    return out


async def winget(ctx: JobContext, params: dict, spec: dict):
    mode = spec.get("mode", "install")
    catalog = app_catalog(ctx)
    ids = params["ids"]
    not_allowed = [i for i in ids if i not in catalog]
    if not_allowed:
        raise ActionFailed(f"not in the app catalog: {', '.join(not_allowed)}")
    exe = find_winget()
    noise = _SPINNER.match
    rows: list[dict[str, Any]] = []
    for n, app_id in enumerate(ids, 1):
        name = catalog[app_id]
        await ctx.sink.line(f"[{n}/{len(ids)}] {mode} {name} ({app_id})", "system")
        if mode == "install":
            base = [exe, "install", "--id", app_id, "--exact", "--silent",
                    "--accept-package-agreements", "--accept-source-agreements",
                    "--disable-interactivity"]
            rc, _out, _err = await ctx.run(base + ["--scope", "machine"], noise=lambda s: bool(noise(s)))
            if rc == WINGET_NO_MACHINE_SCOPE:
                await ctx.sink.line("no machine-wide installer, retrying default scope", "system")
                rc, _out, _err = await ctx.run(base, noise=lambda s: bool(noise(s)))
        else:
            rc, _out, _err = await ctx.run(
                [exe, "uninstall", "--id", app_id, "--exact", "--silent",
                 "--accept-source-agreements", "--disable-interactivity"],
                noise=lambda s: bool(noise(s)),
            )
        if rc in WINGET_OK:
            status, ok = ("installed" if mode == "install" else "uninstalled"), True
        elif mode == "install" and rc in WINGET_ALREADY:
            status, ok = "already installed", True
        elif mode == "uninstall" and rc == WINGET_NOT_INSTALLED:
            status, ok = "not installed", True
        else:
            status, ok = f"failed (exit {rc} / 0x{rc & 0xFFFFFFFF:08X})", False
        await ctx.sink.line(f"{name}: {status}", "system")
        rows.append({"id": app_id, "name": name, "status": status, "ok": ok, "exit_code": rc})
    failed = sum(1 for r in rows if not r["ok"])
    return (1 if failed else 0), {"apps": rows, "failed": failed}


# ---------------------------------------------------------------- self-uninstall

def _cleanup_script(install_dir: str, state_dir: str) -> str:
    q = lambda p: "'" + p.replace("'", "''") + "'"  # noqa: E731  (PowerShell single-quoted literal)
    return (
        "Start-Sleep -Seconds 5\n"
        "sc.exe stop ITOpsAgent | Out-Null\n"
        "Start-Sleep -Seconds 3\n"
        "sc.exe delete ITOpsAgent | Out-Null\n"
        "Get-Process itops-agent -ErrorAction SilentlyContinue | Stop-Process -Force\n"
        "Start-Sleep -Seconds 2\n"
        f"Remove-Item -LiteralPath {q(install_dir)} -Recurse -Force -ErrorAction SilentlyContinue\n"
        f"Remove-Item -LiteralPath {q(state_dir)} -Recurse -Force -ErrorAction SilentlyContinue\n"
    )


async def uninstall(ctx: JobContext, _params: dict, _spec: dict):
    """Remove this agent: service, program folder and enrollment state. The server revokes
    the machine when this job succeeds, so the token is dead even if cleanup fails."""
    import base64
    import subprocess

    from .paths import state_dir
    from .state import State

    frozen = getattr(sys, "frozen", False)
    sdir = str(state_dir())
    if not frozen:
        State.clear()
        await ctx.sink.line("source/dev agent: enrollment removed; stop it by hand", "system")
        asyncio.get_running_loop().call_later(3, os._exit, 0)
        return 0, {"removed": ["state"]}
    install_dir = os.path.dirname(sys.executable)
    script = _cleanup_script(install_dir, sdir)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
           "-EncodedCommand", encoded]
    # Not DETACHED_PROCESS: powershell.exe exits at once without a console. NO_WINDOW gives it a hidden one.
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        # Leave any job object, or the cleanup dies together with this process.
        subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, close_fds=True)
    except OSError:
        subprocess.Popen(cmd, creationflags=flags, close_fds=True)
    await ctx.sink.line(f"Removing service ITOpsAgent, {install_dir} and {sdir} in a few seconds.", "system")
    asyncio.get_running_loop().call_later(4, os._exit, 0)  # after job_done is sent
    return 0, {"removed": ["service", install_dir, sdir]}


REGISTRY = {
    "uninstall": uninstall,
    "ping": ping,
    "security_scan": security_scan,
    "security_fix": security_fix,
    "winget": winget,
}

# Phase 2 handlers (debloat, tweaks, cleanup, disk)
from . import manage  # noqa: E402

REGISTRY.update(manage.REGISTRY)
