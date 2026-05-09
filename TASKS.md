# IT Provisioning Tool — Task Tracker

Last updated: 2026-05-09

---

## Pending

### #1 — Commit tweaks error detail improvements
**Status:** Pending  
**Details:** Latest changes to `ui/tab_tweaks.py` (try/catch wrapper, CMD shown in failure dialog, red error text) not yet committed to git.

---

### #3 — Fix Cam 350 InstallShield silent install failure
**Status:** Pending  
**Details:**  
- Exit code `0x80041F00` (InstallShield HRESULT error)  
- Try manual `installer_args: ["/s"]` in `config/apps_local.json`  
- Check if software is already installed on the machine  
- Path uses forward slashes (`//server/...`) — normalisation fix applied, needs real-world test  

---

### #4 — Fix gen1.bat 7-Zip replace prompt
**Status:** Pending  
**Details:**  
- `gen1.bat` runs `7z x` without `-y` flag  
- 7-Zip prompts "replace existing file?" → subprocess has no stdin → hangs forever  
- Fix: add `-y` to every `7z` command inside `gen1.bat`  
- Example: `7z x nutc.zip -oc:\Windows\SysWOW64 -y`  

---

### #5 — Verify run.bat admin elevation works end-to-end
**Status:** Pending  
**Details:**  
- Confirm `run.bat` → `launch.ps1` → app launches as Administrator  
- Test from network share (UNC path)  
- Verify local installers inherit admin rights (no UAC re-prompt mid-install)  

---

### #6 — Update project memory with session context
**Status:** Pending  
**Details:** Save current session work to Claude memory files so next session starts with full context (new tabs, config files, features, pending issues).

---

## In Progress

*(none)*

---

## Completed

### #2 — Test Tweaks tab after restart ✓
**Completed:** 2026-05-09  
**Result:** Tweaks tab visible with all sections — Essential, Advanced, Privacy & Tracking, Org Settings, Customize Preferences, Performance Plans. Apply runs and shows detailed results dialog.

---

## Feature Log (this session)

| Feature | Files Changed |
|---------|--------------|
| Local/Offline Apps installer support | `modules/runner.py`, `modules/utils.py`, `ui/tab_apps.py`, `config/apps_local.json` |
| Admin-managed local app list (Add/Remove via UI) | `ui/tab_apps.py` |
| Auto-detect silent install args (NSIS/Inno/InstallShield/WiX/MSI) | `modules/runner.py` |
| Stop button for installs | `ui/tab_apps.py`, `modules/runner.py` |
| Scrollable Apps tab (output always visible) | `ui/tab_apps.py` |
| Tweaks tab (new) — replaces Privacy + Org Settings tabs | `ui/tab_tweaks.py`, `config/tweaks.json`, `ui/dashboard.py` |
| Tweaks results dialog with per-item status + PS log | `ui/tab_tweaks.py` |
| Tweaks error detail (try/catch, CMD shown on failure) | `ui/tab_tweaks.py` |
| Admin self-elevation in source mode | `main.py` |
| Consistent elevation pattern (run.bat = build.bat) | `run.bat`, `launch.ps1` |
| Batch files (.bat/.cmd) run in own console window | `modules/runner.py` |
| UNC path forward-slash normalisation | `modules/runner.py` |
| README updated | `README.md` |
