"""Installed Store (Appx) package names, shared by the Home and Debloat pages."""
from modules.runner import run_encoded_powershell

_APPX_PS = r"""
try { Get-AppxPackage -AllUsers -ErrorAction Stop | Select-Object -ExpandProperty Name -Unique }
catch { Get-AppxPackage | Select-Object -ExpandProperty Name -Unique }
"""


def installed_appx_names(timeout=60):
    """Set of installed package names (all users when elevated). Raises RuntimeError on failure.
    Slow (2-4 s): call from a worker thread."""
    rc, out = run_encoded_powershell(_APPX_PS, timeout=timeout)
    names = {line.strip() for line in out.splitlines() if line.strip() and " " not in line.strip()}
    if not names:
        raise RuntimeError(f"Get-AppxPackage returned nothing (rc={rc})")
    return names
