"""Where things live, in source mode and in the PyInstaller exe."""
import os
import sys
from pathlib import Path


def bundle_dir() -> Path:
    """Folder holding actions/ and scripts/ (the signed script bundle)."""
    override = os.environ.get("ITOPS_AGENT_BUNDLE")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # source mode: web/agent/itops_agent -> repo root
    return Path(__file__).resolve().parents[3]


def actions_dir() -> Path:
    b = bundle_dir()
    return b / "actions" if (b / "actions").is_dir() else b / "web" / "actions"


def scripts_dir() -> Path:
    return bundle_dir() / "scripts"


def state_dir() -> Path:
    override = os.environ.get("ITOPS_AGENT_STATE")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ITOpsAgent"
    return Path.home() / ".itops-agent"
