"""Phase 2 handlers: debloat, tweaks, cleanup, disk.

All PowerShell run here comes from the agent's own signed bundle (config/*.json) or from the
desktop app's modules (shipped inside the agent) - never from the server. The server only
picks ids from those lists; ids are checked here against the lists before anything runs.

The agent runs as SYSTEM, so HKCU would be SYSTEM's own hive. Per-user registry changes are
redirected to every signed-in user's hive (HKEY_USERS\\<SID>).
"""
import asyncio
import fnmatch
import json
import os
import re
import sys
from typing import Any

from .executor import ActionFailed, JobContext

PARALLEL = 4


def _repo_module(name: str):
    """A module from the desktop app's modules/ package (bundled with the agent)."""
    from .paths import bundle_dir

    root = str(bundle_dir())
    if root not in sys.path:
        sys.path.insert(0, root)
    import importlib

    return importlib.import_module(f"modules.{name}")


def _config(ctx: JobContext, name: str) -> Any:
    return json.loads(ctx.bundle.check(f"config/{name}").read_text(encoding="utf-8"))


def _last_int(out: str) -> int:
    lines = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("ERR:")]
    try:
        return int(lines[-1]) if lines else 0
    except ValueError:
        return 0


async def _gather_limited(coros, limit: int = PARALLEL):
    sem = asyncio.Semaphore(limit)

    async def run(c):
        async with sem:
            return await c

    return await asyncio.gather(*(run(c) for c in coros))


# ---------------------------------------------------------------- per-user registry

_USER_SID = re.compile(r"^S-1-(5-21|12-1)-[\d-]+$")


def user_sids() -> list[str]:
    """SIDs of user hives loaded right now (= users signed in to this PC)."""
    if os.name != "nt":
        return []
    import winreg

    sids, i = [], 0
    while True:
        try:
            name = winreg.EnumKey(winreg.HKEY_USERS, i)
        except OSError:
            break
        if _USER_SID.match(name):
            sids.append(name)
        i += 1
    return sids


def sid_name(sid: str) -> str:
    try:
        import win32security

        name, domain, _ = win32security.LookupAccountSid(None, win32security.ConvertStringSidToSid(sid))
        return f"{domain}\\{name}" if domain else name
    except Exception:
        return sid


def redirect_hkcu(cmd: str, sid: str) -> str:
    target = f"Registry::HKEY_USERS\\{sid}"
    return (cmd.replace("HKCU:\\", target + "\\").replace("HKCU:", target)
            .replace("HKEY_CURRENT_USER\\", f"HKEY_USERS\\{sid}\\"))


def uses_hkcu(cmd: str) -> bool:
    return "HKCU:" in cmd or "HKEY_CURRENT_USER" in cmd


def read_reg(path: str, name: str, sid: str | None = None):
    """Value at 'HKLM:\\Key' / 'HKCU:\\Key' (HKCU read from the user's hive), or None."""
    import winreg

    hive_name, _, sub = path.partition(":\\")
    hive_name = hive_name.upper()
    if hive_name in ("HKCU", "HKEY_CURRENT_USER"):
        if not sid:
            return None
        hive, sub = winreg.HKEY_USERS, f"{sid}\\{sub}"
    elif hive_name in ("HKLM", "HKEY_LOCAL_MACHINE"):
        hive = winreg.HKEY_LOCAL_MACHINE
    else:
        return None
    try:
        with winreg.OpenKey(hive, sub) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


async def _run_maybe_per_user(ctx: JobContext, cmd: str) -> tuple[int, str, list[str]]:
    """Run once, or once per signed-in user when the command touches HKCU.
    Returns (worst rc, combined output, users it ran for)."""
    if not uses_hkcu(cmd):
        rc, out = await ctx.powershell(cmd)
        return rc, out, []
    sids = user_sids()
    if not sids:
        return -1, "no user is signed in to this PC, per-user setting skipped", []
    worst, outs, users = 0, [], []
    for sid in sids:
        rc, out = await ctx.powershell(redirect_hkcu(cmd, sid))
        worst = worst or rc
        users.append(sid_name(sid))
        if out.strip():
            outs.append(out)
    return worst, "\n".join(outs), users


# ---------------------------------------------------------------- debloat

_APPX_PS = r"""
try { Get-AppxPackage -AllUsers -ErrorAction Stop | Select-Object -ExpandProperty Name -Unique }
catch { Get-AppxPackage | Select-Object -ExpandProperty Name -Unique }
Write-Output '---PROVISIONED---'
Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue | Select-Object -ExpandProperty DisplayName -Unique
"""


def _debloat_catalog(ctx: JobContext) -> list[dict]:
    return _config(ctx, "debloat_list.json")["appx_packages"]


async def debloat_scan(ctx: JobContext, _params: dict, _spec: dict):
    catalog = _debloat_catalog(ctx)
    rc, out = await ctx.powershell(_APPX_PS)
    installed, provisioned, target = set(), set(), None
    target = installed
    for line in out.splitlines():
        line = line.strip()
        if line == "---PROVISIONED---":
            target = provisioned
        elif line and " " not in line and not line.startswith("ERR:"):
            target.add(line.lower())
    if not installed:
        raise ActionFailed("could not list installed Store apps")

    def match(pattern, names):
        return any(fnmatch.fnmatch(n, pattern.lower()) for n in names)

    apps = []
    for a in catalog:
        apps.append({**a, "installed": match(a["package"], installed), "provisioned": match(a["package"], provisioned)})
    n = sum(1 for a in apps if a["installed"])
    await ctx.sink.line(f"{n} of {len(apps)} listed apps are installed", "system")
    return 0, {"apps": apps}


def _pick_catalog(ctx: JobContext, packages: list[str]) -> list[dict]:
    by_pkg = {a["package"]: a for a in _debloat_catalog(ctx)}
    unknown = [p for p in packages if p not in by_pkg]
    if unknown:
        raise ActionFailed(f"not in the debloat list: {', '.join(unknown)}")
    return [by_pkg[p] for p in packages]


async def debloat_remove(ctx: JobContext, params: dict, _spec: dict):
    apps = _pick_catalog(ctx, params["packages"])
    script = ctx.bundle.check("scripts/debloat.ps1")
    rc, out, _err = await ctx.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script), "-Packages", ",".join(a["package"] for a in apps)])
    status = {}
    for line in out:
        kind, _, pkg = line.partition(": ")
        if kind in ("REMOVED", "NOT_FOUND"):
            status[pkg.strip()] = "removed" if kind == "REMOVED" else "not found"
    rows = [{"package": a["package"], "name": a["name"], "status": status.get(a["package"], "unknown")} for a in apps]
    return rc, {"apps": rows}


async def debloat_reinstall(ctx: JobContext, params: dict, _spec: dict):
    from .handlers import find_winget

    apps = _pick_catalog(ctx, params["packages"])
    exe = find_winget()
    rows, failed = [], 0
    for a in apps:
        name = re.sub(r"[*?]", "", a["name"])
        await ctx.sink.line(f"Reinstalling {a['name']}", "system")
        ok = False
        for source in (["--source", "msstore"], []):
            rc, _o, _e = await ctx.run(
                [exe, "install", "--name", name, *source, "--silent", "--accept-package-agreements",
                 "--accept-source-agreements", "--disable-interactivity"])
            if rc == 0:
                ok = True
                break
        failed += not ok
        rows.append({"package": a["package"], "name": a["name"], "status": "reinstalled" if ok else "failed"})
        await ctx.sink.line(f"{a['name']}: {'reinstalled' if ok else 'failed'}", "system")
    return (1 if failed else 0), {"apps": rows}


# ---------------------------------------------------------------- tweaks

TWEAK_SECTIONS = ("essential", "advanced", "privacy", "org")


def _tweaks(ctx: JobContext) -> tuple[dict, dict[str, dict], dict[str, dict]]:
    cfg = _config(ctx, "tweaks.json")
    tweaks = {t["id"]: {**t, "section": s} for s in TWEAK_SECTIONS for t in cfg.get(s, [])}
    prefs = {p["id"]: p for p in cfg.get("preferences", [])}
    return cfg, tweaks, prefs


def _same(current, wanted) -> bool:
    if current is None:
        return False
    if isinstance(wanted, int):
        try:
            return int(current) == wanted
        except (TypeError, ValueError):
            return False
    return str(current) == str(wanted)


def _tweak_state(tweak: dict, sids: list[str]) -> bool | None:
    writes = _repo_module("reg_state").registry_writes(tweak.get("apply", ""))
    if writes is None:
        return None
    results = []
    for path, name, value in writes:
        if path.upper().startswith(("HKCU:", "HKEY_CURRENT_USER")):
            if not sids:
                return None
            results += [_same(read_reg(path, name, sid), value) for sid in sids]
        else:
            results.append(_same(read_reg(path, name), value))
    return all(results)


async def tweaks_state(ctx: JobContext, _params: dict, _spec: dict):
    cfg, tweaks, prefs = _tweaks(ctx)
    sids = user_sids()
    users = [sid_name(s) for s in sids]
    out_tweaks = []
    for t in tweaks.values():
        out_tweaks.append({
            "id": t["id"], "name": t["name"], "description": t.get("description", ""), "section": t["section"],
            "applied": _tweak_state(t, sids), "can_undo": bool(t.get("undo")), "per_user": uses_hkcu(t.get("apply") or ""),
        })
    out_prefs = []
    for p in prefs.values():
        vals = ([read_reg(p["reg_path"], p["reg_name"], sid) for sid in sids]
                if uses_hkcu(p["reg_path"]) else [read_reg(p["reg_path"], p["reg_name"])])
        on = None if not vals or any(v is None for v in vals) else all(_same(v, p["on_value"]) for v in vals)
        out_prefs.append({"id": p["id"], "name": p["name"], "description": p.get("description", ""), "on": on})
    rc, plan_out = await ctx.powershell("powercfg /getactivescheme")
    m = re.search(r"\((.+)\)\s*$", plan_out.strip())
    await ctx.sink.line(f"Signed-in users: {', '.join(users) or 'none'}", "system")
    return 0, {"tweaks": out_tweaks, "preferences": out_prefs, "power_plan": m.group(1) if m else None,
               "users": users, "has_power": "performance" in cfg}


async def tweaks_apply(ctx: JobContext, params: dict, _spec: dict):
    _cfg, tweaks, _prefs = _tweaks(ctx)
    mode = params.get("mode", "apply")
    unknown = [i for i in params["ids"] if i not in tweaks]
    if unknown:
        raise ActionFailed(f"unknown tweaks: {', '.join(unknown)}")
    rows, failed = [], 0
    for tid in params["ids"]:
        t = tweaks[tid]
        cmd = t.get("apply" if mode == "apply" else "undo")
        if not cmd:
            rows.append({"id": tid, "name": t["name"], "status": "no undo for this tweak"})
            await ctx.sink.line(f"{t['name']}: no undo, skipped", "system")
            continue
        await ctx.sink.line(f"{'Applying' if mode == 'apply' else 'Undoing'}: {t['name']}", "system")
        rc, out, users = await _run_maybe_per_user(ctx, cmd)
        for line in out.splitlines():
            await ctx.sink.line(line, "stderr" if line.startswith("ERR:") else "stdout")
        ok = rc == 0
        failed += not ok
        status = ("done" if ok else (out if rc == -1 else f"failed (exit {rc})"))
        if users:
            status += f" for {', '.join(users)}"
        rows.append({"id": tid, "name": t["name"], "status": status, "ok": ok})
    return (1 if failed else 0), {"tweaks": rows, "mode": mode}


def _pref_cmd(p: dict, on: bool) -> str:
    value = p["on_value"] if on else p["off_value"]
    path = p["reg_path"].replace("'", "''")
    name = p["reg_name"].replace("'", "''")
    if isinstance(value, int):
        val, typ = str(int(value)), "DWord"
    else:
        val, typ = "'" + str(value).replace("'", "''") + "'", "String"
    return (f"if (!(Test-Path '{path}')) {{ New-Item -Path '{path}' -Force | Out-Null }}; "
            f"Set-ItemProperty -Path '{path}' -Name '{name}' -Value {val} -Type {typ} -Force")


async def tweaks_pref(ctx: JobContext, params: dict, _spec: dict):
    _cfg, _tweaks_, prefs = _tweaks(ctx)
    p = prefs.get(params["id"])
    if p is None:
        raise ActionFailed(f"unknown preference {params['id']!r}")
    rc, out, users = await _run_maybe_per_user(ctx, _pref_cmd(p, params["on"]))
    if rc == -1:
        raise ActionFailed(out)
    who = f" for {', '.join(users)}" if users else ""
    await ctx.sink.line(f"{p['name']}: {'on' if params['on'] else 'off'}{who}. Explorer may need a restart or sign-out.", "system")
    return rc, {"id": p["id"], "on": params["on"], "users": users}


async def tweaks_power(ctx: JobContext, params: dict, _spec: dict):
    cfg, _t, _p = _tweaks(ctx)
    perf = cfg.get("performance") or {}
    cmd = perf.get("enable_cmd" if params["plan"] == "ultimate" else "disable_cmd")
    if not cmd:
        raise ActionFailed("power plan commands missing from tweaks.json")
    rc, out = await ctx.powershell(cmd, stream=True)
    return rc, {"plan": params["plan"]}


# ---------------------------------------------------------------- cleanup: windows

def _locations():
    return _repo_module("cleanup_locations")


async def _size(ctx: JobContext, size_ps: str) -> int:
    _rc, out = await ctx.powershell(size_ps)
    return _last_int(out)


async def cleanup_scan(ctx: JobContext, _params: dict, _spec: dict):
    cl = _locations()
    sizes = await _gather_limited([_size(ctx, loc["size_ps"]) for loc in cl.LOCATIONS])
    by_id = {loc["id"]: s for loc, s in zip(cl.LOCATIONS, sizes, strict=True)}
    groups = []
    for g in cl.GROUPS:
        groups.append({"label": g["label"], "items": [
            {"id": i["id"], "label": i["label"], "default": bool(i.get("default")), "confirm": bool(i.get("confirm")),
             "confirm_msg": i.get("confirm_msg", ""), "slow": bool(i.get("slow")), "size": by_id[i["id"]]}
            for i in g["items"]]})
    total = sum(sizes)
    await ctx.sink.line(f"{len(sizes)} locations scanned, {total / 1e9:.2f} GB reclaimable", "system")
    return 0, {"groups": groups, "total": total}


async def cleanup_clean(ctx: JobContext, params: dict, _spec: dict):
    cl = _locations()
    by_id = {loc["id"]: loc for loc in cl.LOCATIONS}
    unknown = [i for i in params["ids"] if i not in by_id]
    if unknown:
        raise ActionFailed(f"unknown cleanup locations: {', '.join(unknown)}")
    locs = [by_id[i] for i in params["ids"]]
    before = await _gather_limited([_size(ctx, loc["size_ps"]) for loc in locs])
    for loc in locs:
        await ctx.sink.line(f">>> {loc['label']}", "system")
        _rc, out = await ctx.powershell(loc["clean_ps"])
        for line in out.splitlines():
            await ctx.sink.line(line, "stderr" if line.startswith("ERR:") else "stdout")
    after = await _gather_limited([_size(ctx, loc["size_ps"]) for loc in locs])
    rows = [{"id": loc["id"], "label": loc["label"], "before": b, "after": a}
            for loc, b, a in zip(locs, before, after, strict=True)]
    freed = max(0, sum(before) - sum(after))
    await ctx.sink.line(f"Freed {freed / 1e6:.1f} MB", "system")
    return 0, {"items": rows, "freed": freed}


# ---------------------------------------------------------------- cleanup: user profiles

async def _profiles(ctx: JobContext) -> list[dict]:
    script = ctx.bundle.check("scripts/get_user_profiles.ps1")
    _rc, out, _err = await ctx.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        stream=False)
    profiles = []
    for line in out:
        parts = line.split("|")
        if len(parts) == 5 and parts[0].startswith("S-1-"):
            sid, user, path, last, loaded = parts
            profiles.append({"sid": sid, "user": user, "path": path, "last_use": last, "loaded": loaded == "1"})
        elif parts[0] == "ERROR":
            raise ActionFailed(line)
    return profiles


async def cleanup_profiles(ctx: JobContext, params: dict, _spec: dict):
    cl = _locations()
    profiles = await _profiles(ctx)
    with_sizes = params.get("sizes", True)
    for p in profiles:
        cats = cl.junk_categories(p["path"]) if p["path"] else []
        sizes = await _gather_limited([_size(ctx, c["size_ps"]) for c in cats]) if with_sizes else [None] * len(cats)
        p["categories"] = [{"id": c["id"], "label": c["label"], "size": s} for c, s in zip(cats, sizes, strict=True)]
        p["junk"] = sum(s or 0 for s in sizes)
        await ctx.sink.line(f"{p['user']}: {p['junk'] / 1e6:.1f} MB junk", "stdout")
    return 0, {"profiles": profiles}


async def cleanup_profile_clean(ctx: JobContext, params: dict, _spec: dict):
    cl = _locations()
    prof = next((p for p in await _profiles(ctx) if p["sid"] == params["sid"]), None)
    if prof is None or not prof["path"]:
        raise ActionFailed("profile not found on this PC")
    cats = {c["id"]: c for c in cl.junk_categories(prof["path"])}
    unknown = [i for i in params["categories"] if i not in cats]
    if unknown:
        raise ActionFailed(f"unknown categories: {', '.join(unknown)}")
    freed = 0
    for cid in params["categories"]:
        c = cats[cid]
        before = await _size(ctx, c["size_ps"])
        _rc, out = await ctx.powershell(c["clean_ps"])
        after = await _size(ctx, c["size_ps"])
        freed += max(0, before - after)
        await ctx.sink.line(f"{prof['user']} - {c['label']}: freed {(before - after) / 1e6:.1f} MB", "stdout")
    return 0, {"sid": prof["sid"], "user": prof["user"], "freed": freed}


# ---------------------------------------------------------------- disk

async def disk_health(ctx: JobContext, _params: dict, _spec: dict):
    script = ctx.bundle.check("scripts/get_drive_health.ps1")
    _rc, out, _err = await ctx.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        stream=False)
    drives = []
    for line in out:
        parts = line.split("|")
        if len(parts) == 4 and parts[0] != "ERROR":
            letter, size, free, health = parts

            def num(v):
                try:
                    return int(float(v))
                except ValueError:
                    return 0

            drives.append({"letter": letter, "size": num(size), "free": num(free), "health": health})
    return 0, {"drives": drives}


# Path comes from the server, so it goes in an env var, never into the script text.
_FOLDERS_PS = r"""
$p = $env:ITOPS_PATH
if (-not (Test-Path -LiteralPath $p -PathType Container)) { Write-Output 'MISSING'; exit 0 }
Get-ChildItem -LiteralPath $p -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
  $s = (Get-ChildItem -LiteralPath $_.FullName -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
  if (-not $s) { $s = 0 }
  Write-Output ("{0}`t{1}" -f [int64]$s, $_.FullName)
}
$f = (Get-ChildItem -LiteralPath $p -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
Write-Output ("FILES`t{0}" -f [int64]$f)
"""


async def disk_folders(ctx: JobContext, params: dict, _spec: dict):
    import base64

    path = params["path"]
    prelude = "$ProgressPreference='SilentlyContinue';[Console]::OutputEncoding=[Text.Encoding]::UTF8;\n"
    encoded = base64.b64encode((prelude + _FOLDERS_PS).encode("utf-16-le")).decode("ascii")
    env = dict(os.environ, ITOPS_PATH=path)
    _rc, out, _err = await ctx.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        env=env, stream=False)
    if out[:1] == ["MISSING"]:
        raise ActionFailed(f"folder not found: {path}")
    folders, files = [], 0
    for line in out:
        a, _, b = line.partition("\t")
        if a == "FILES":
            files = int(b or 0)
        elif a.isdigit():
            folders.append({"path": b, "size": int(a)})
    folders.sort(key=lambda f: f["size"], reverse=True)
    await ctx.sink.line(f"{len(folders)} folders in {path}", "system")
    return 0, {"path": path, "folders": folders, "files_size": files}


REGISTRY = {
    "debloat_scan": debloat_scan,
    "debloat_remove": debloat_remove,
    "debloat_reinstall": debloat_reinstall,
    "tweaks_state": tweaks_state,
    "tweaks_apply": tweaks_apply,
    "tweaks_pref": tweaks_pref,
    "tweaks_power": tweaks_power,
    "cleanup_scan": cleanup_scan,
    "cleanup_clean": cleanup_clean,
    "cleanup_profiles": cleanup_profiles,
    "cleanup_profile_clean": cleanup_profile_clean,
    "disk_health": disk_health,
    "disk_folders": disk_folders,
}
