# IT Provisioning Tool

A Windows desktop application for IT administrators to provision and configure Windows machines quickly and consistently across an organisation.

Built with Python and CustomTkinter. Runs as a standalone `.exe` — no Python installation required on target machines.

---

## Features

| Tab | What it does |
|-----|-------------|
| **System** | Rename PC (DT/LT convention), auto-generate name from hardware ID, join domain with OU browser |
| **Debloat** | Remove pre-installed Windows bloatware via PowerShell |
| **Privacy / Telemetry** | Disable Windows telemetry, diagnostics, location tracking, advertising ID — with rollback support |
| **Apps** | Install common apps and team-specific apps via winget — with uninstall/rollback |
| **Org Settings** | Apply organisation-standard registry tweaks — with rollback support |
| **User Management** | Add, delete, and reset passwords for tool users (admin only) |

All tabs include live progress bars and a completion summary dialog.

---

## Requirements

**To run the built `.exe`:**
- Windows 10 / 11
- No additional software needed

**To build from source:**
- Windows 10 / 11
- Python 3.11+ (optional — `build.bat` downloads it automatically if not found)
- Run as Administrator

**To run from source (dev):**
- Python 3.11+
- `pip install -r requirements.txt`

---

## Quick Start

### Run (from network share or local)

Double-click `run.bat` or the built `.exe`.

> If launched from a network share, the app automatically copies itself to local temp before starting — this is required for Windows DLL loading.

### Build standalone `.exe`

```
build.bat
```

This will:
1. Find or download Python 3.11
2. Install dependencies from `requirements.txt`
3. Build with PyInstaller into `dist\IT-Provisioning-Tool.exe` (single file)
4. Bundle all required DLLs (bcrypt, cffi, customtkinter, etc.)

Copy `dist\IT-Provisioning-Tool.exe` to any machine and run — no Python or dependencies needed.

### Run from source (dev)

```
pip install -r requirements.txt
python main.py
```

---

## Authentication

Auth is currently disabled during development — the tool opens directly to the dashboard as admin.

To re-enable: set `AUTH_ENABLED = True` in `main.py` and uncomment the login imports.

---

## Project Structure

```
windows-provisioning-tool/
├── main.py                  # Entry point
├── run.bat                  # Launcher (handles UNC paths)
├── build.bat                # Build script (auto-elevates)
├── build.ps1                # PyInstaller build logic
├── requirements.txt
│
├── config/
│   ├── domain_config.json   # Domain name, DC IP, OU path, company prefix
│   ├── apps_common.json     # Apps installed on all machines
│   ├── apps_teams.json      # Team-specific apps (IT, Finance, Dev, etc.)
│   ├── debloat_list.json    # Packages to remove
│   └── org_settings.json   # Registry tweaks
│
├── modules/
│   ├── auth.py              # Login, bcrypt password hashing, user management
│   ├── logger.py            # Audit logger
│   ├── runner.py            # PowerShell + winget runner
│   └── paths.py             # PyInstaller-aware base path helper
│
├── scripts/
│   ├── rename_computer.ps1
│   ├── join_domain.ps1
│   ├── get_ous.ps1
│   ├── get_hardware_id.ps1
│   ├── debloat.ps1
│   ├── disable_telemetry.ps1
│   └── apply_org_settings.ps1
│
└── ui/
    ├── login_screen.py
    ├── dashboard.py
    ├── first_run_dialog.py
    ├── tab_system.py
    ├── tab_debloat.py
    ├── tab_telemetry.py
    ├── tab_apps.py
    ├── tab_org_settings.py
    └── tab_users.py
```

---

## Configuration

Edit JSON files in `config/` before building to pre-populate defaults:

**`domain_config.json`**
```json
{
  "domain_name": "company.local",
  "dns_server": "192.168.1.10",
  "ou_path": "",
  "company_prefix": "ACME"
}
```

**`apps_common.json`** — add/remove winget IDs for apps installed on every machine.

**`apps_teams.json`** — define teams and their app lists.

**`org_settings.json`** — registry tweaks applied by the Org Settings tab.

---

## Version History

See [CHANGELOG.md](CHANGELOG.md) for full version history and backlog.

---

## Security Notes

- Passwords stored as bcrypt hashes (`config/credentials.json`)
- `credentials.json` excluded from git via `.gitignore`
- Domain join password passed via stdin — never as a CLI argument
- Tool requests UAC elevation on launch
