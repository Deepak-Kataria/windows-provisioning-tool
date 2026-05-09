# IT Provisioning Tool

A Windows desktop application for IT administrators to provision and configure Windows machines quickly and consistently across an organisation.

Built with Python and CustomTkinter. Runs as a standalone `.exe` — no Python installation required on target machines.

---

## Features

| Tab | What it does |
|-----|-------------|
| **System** | Rename PC (DT/LT convention), auto-generate name from hardware ID, join domain with OU browser |
| **Debloat** | Remove pre-installed Windows bloatware via PowerShell |
| **Apps** | Install common + team apps via winget; install offline/local apps from network share or local path; uninstall/rollback support; Stop button; auto-detect silent args |
| **Tweaks** | Essential tweaks, advanced tweaks, privacy/telemetry settings, org registry settings, customise preferences (toggles), performance plans — all with Apply + Undo and full log dialog |
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

### Run the app (any machine)

Double-click `run.bat`.

- If `dist\IT-Provisioning-Tool.exe` exists: launches it directly (no Python needed)
- If no exe: falls back to Python dev mode (dev machine only)

### Build the standalone exe (dev machine only)

Run once on your **local dev PC** (requires Python):

```
build.bat
```

Produces `dist\IT-Provisioning-Tool.exe` — copy this to the network share.
Network machines run it via `run.bat`. They do **not** need Python or `build.bat`.

Build steps:
1. Finds Python (downloads 3.11 if not found)
2. Installs dependencies from `requirements.txt`
3. Builds with PyInstaller into `dist\IT-Provisioning-Tool.exe` (single file)
4. Bundles all DLLs (bcrypt, cffi, customtkinter, etc.)

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
├── main.py                  # Entry point (self-elevates to admin in source mode)
├── run.bat                  # Launcher — exe if built, Python fallback, always admin
├── build.bat                # Build script (dev PC only, auto-elevates)
├── build.ps1                # PyInstaller build logic
├── launch.ps1               # Launch logic called by run.bat
├── requirements.txt
│
├── config/
│   ├── domain_config.json   # Domain name, DC IP, OU path, company prefix
│   ├── apps_common.json     # Apps installed on all machines (winget or local)
│   ├── apps_teams.json      # Team-specific apps (IT, Finance, Dev, etc.)
│   ├── apps_local.json      # Offline/local installers (managed via UI by admin)
│   ├── debloat_list.json    # Packages to remove
│   ├── org_settings.json    # Legacy org registry tweaks (now also in tweaks.json)
│   └── tweaks.json          # All tweaks: essential, advanced, privacy, org, preferences
│
├── modules/
│   ├── auth.py              # Login, bcrypt password hashing, user management
│   ├── logger.py            # Audit logger
│   ├── runner.py            # PowerShell + winget + local installer runner
│   ├── utils.py             # Path helpers: resource_path, writable_path, resolve_installer_path
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
    ├── tab_apps.py          # Winget + local/offline installer support
    ├── tab_tweaks.py        # All tweaks, privacy, org settings, preferences
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

**`apps_common.json`** — winget IDs for apps installed on every machine. Supports offline installers via `"installer"` key.

**`apps_teams.json`** — define teams and their app lists.

**`apps_local.json`** — offline/local installer entries. Managed via the "+ Add App" button in the Apps tab (admin only). Example:
```json
{"name": "My ERP", "installer": "installers\\erp_setup.exe", "installer_args": ["/silent"]}
```
Place installer files in an `installers\` folder next to the exe on the network share, or use absolute/UNC paths.

**`tweaks.json`** — all tweaks for the Tweaks tab. Add entries to `essential`, `advanced`, `privacy`, or `org` arrays. Each entry needs `id`, `name`, `description`, `apply` (PowerShell), and optional `undo`.

---

## Version History

See [CHANGELOG.md](CHANGELOG.md) for full version history and backlog.

---

## Security Notes

- Passwords stored as bcrypt hashes (`config/credentials.json`)
- `credentials.json` excluded from git via `.gitignore`
- Domain join password passed via stdin — never as a CLI argument
- Tool requests UAC elevation on launch
