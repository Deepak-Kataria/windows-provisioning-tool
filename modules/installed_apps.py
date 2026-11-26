"""Which of our apps are already installed.

Two sources, because winget is accurate but slow (a cold `winget export` can take a minute):
  1. registry_programs(): the Windows "Programs and Features" list. Instant; matched by name.
  2. winget_installed(): `winget export --include-versions`. Exact winget IDs plus versions;
     run it in the background and merge the result when it arrives.
An app entry may carry "match": ["text", ...] for names that differ from the registry
DisplayName (e.g. "VS Code" is registered as "Microsoft Visual Studio Code").
"""
import json
import os
import re
import subprocess
import tempfile
import winreg

_UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]

# Common names whose registry DisplayName is different
_ALIASES = {
    "vs code": ["visual studio code"],
    "vscode": ["visual studio code"],
    "microsoft office 365": ["microsoft 365", "microsoft office"],
    "office 365": ["microsoft 365", "microsoft office"],
    "java (runtime)": ["java "],
    "adobe acrobat reader": ["adobe acrobat"],
    "8x8 work": ["8x8 work"],
}


def _norm(s):
    return re.sub(r"[^a-z0-9+]+", " ", s.lower()).strip()


def registry_programs():
    """[(display_name, version)] from the Uninstall keys (fast, no subprocess)."""
    out = []
    for hive, path in _UNINSTALL_KEYS:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                        name = winreg.QueryValueEx(k, "DisplayName")[0]
                        try:
                            ver = str(winreg.QueryValueEx(k, "DisplayVersion")[0])
                        except OSError:
                            ver = ""
                        out.append((str(name), ver))
                except OSError:
                    continue
    return out


def match_registry(app, programs):
    """Version string ('' if unknown) when the app looks installed, else None."""
    needles = [app["name"]] + list(app.get("match", []))
    needles += _ALIASES.get(app["name"].lower(), [])
    needles = [_norm(n) for n in needles if n.strip()]
    for name, ver in programs:
        hay = _norm(name)
        if " add in" in f" {hay}" or "addin" in hay:   # e.g. "Microsoft Teams Meeting Add-in"
            continue
        if any(n and (hay == n or hay.startswith(n + " ") or f" {n} " in f" {hay} ") for n in needles):
            return ver
    return None


def winget_installed(timeout=150):
    """{winget_id: version} from `winget export`, or None if winget is missing / fails."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="wg_export_")
    os.close(fd)
    try:
        subprocess.run(["winget", "export", "-o", path, "--include-versions",
                        "--accept-source-agreements", "--disable-interactivity"],
                       capture_output=True, timeout=timeout,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return {p["PackageIdentifier"].lower(): p.get("Version", "")
                for s in data.get("Sources", []) for p in s.get("Packages", [])}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
