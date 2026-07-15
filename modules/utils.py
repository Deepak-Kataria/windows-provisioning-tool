"""Utility helpers for path resolution in both dev and PyInstaller bundled modes."""
import os
import sys


def resource_path(*parts):
    """Return absolute path to a bundled resource (read-only assets like scripts, config)."""
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def writable_path(*parts):
    """Return absolute path to a writable file stored next to the exe (or project root in dev)."""
    if hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def format_size(n):
    """Human-readable byte size, e.g. 1536 -> '1.5 KB'."""
    if n is None:
        return "---"
    for unit, div in [("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)]:
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


def resolve_installer_path(installer: str):
    """Resolve installer path: relative to exe location first, then as absolute. Returns None if not found."""
    relative = writable_path(installer)
    if os.path.exists(relative):
        return relative
    if os.path.exists(installer):
        return installer
    return None
