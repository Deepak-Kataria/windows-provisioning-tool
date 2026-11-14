"""Read current registry state for tweaks and preferences, without starting PowerShell.

A tweak counts as "applied" when every `Set-ItemProperty -Path ... -Name ... -Value ...` in its
apply command already holds that value. Tweaks whose apply command does anything else
(services, powercfg, removing apps or files) can't be checked this way and return None.
"""
import re
import subprocess
import winreg

_HIVES = {
    "HKLM": winreg.HKEY_LOCAL_MACHINE, "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    "HKCU": winreg.HKEY_CURRENT_USER, "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
    "HKCR": winreg.HKEY_CLASSES_ROOT, "HKU": winreg.HKEY_USERS,
}
_SET = re.compile(r"Set-ItemProperty\s+-Path\s+'([^']+)'\s+-Name\s+'([^']+)'\s+-Value\s+('[^']*'|[^\s;]+)", re.I)
_NEW_ITEM = re.compile(r"If\s*\(!\(Test-Path\s+'[^']+'\)\)\s*\{\s*New-Item\s+-Path\s+'[^']+'\s+-Force\s*\|\s*Out-Null\s*\}", re.I)
_NOISE = re.compile(r"-Force|-Type\s+\w+|-ErrorAction\s+\w+|;|\s+", re.I)


def read_value(path, name):
    """Value at 'HKLM:\\...\\Key' / name, or None if the key or value is missing."""
    hive_name, _, sub = path.partition(":\\")
    hive = _HIVES.get(hive_name.upper())
    if hive is None:
        return None
    try:
        with winreg.OpenKey(hive, sub) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _parse(value):
    value = value.strip()
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        return int(value, 0)
    except ValueError:
        return value


def registry_writes(command):
    """[(path, name, value)] if the command is only registry writes, else None."""
    if not command:
        return None
    sets = _SET.findall(command)
    if not sets:
        return None
    rest = _NOISE.sub(" ", _SET.sub("", _NEW_ITEM.sub("", command))).strip()
    if rest:
        return None
    return [(p, n, _parse(v)) for p, n, v in sets]


def _same(current, wanted):
    if current is None:
        return False
    if isinstance(wanted, int):
        try:
            return int(current) == wanted
        except (TypeError, ValueError):
            return False
    return str(current) == str(wanted)


def tweak_applied(tweak):
    """True / False if checkable from the registry, None otherwise."""
    writes = registry_writes(tweak.get("apply", ""))
    if writes is None:
        return None
    return all(_same(read_value(p, n), v) for p, n, v in writes)


def pref_on(pref):
    """True / False for a preference toggle, None if the value isn't set."""
    cur = read_value(pref["reg_path"], pref["reg_name"])
    if cur is None:
        return None
    return _same(cur, pref["on_value"])


def active_power_plan():
    """Name of the active power plan, e.g. 'Balanced', or None."""
    try:
        out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True,
                             timeout=10, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"\((.+)\)\s*$", out.strip())
    return m.group(1) if m else None
