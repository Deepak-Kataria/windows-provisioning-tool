# IT Provisioning Tool — Task Tracker

Last updated: 2026-05-11

---

## Pending

### #3 — Fix Cam 350 InstallShield silent install failure
**Status:** Pending  
**Details:**  
- Exit code `0x80041F00` (InstallShield HRESULT error)  
- Try manual `installer_args: ["/s"]` in `config/apps_local.json`  
- Check if software is already installed on the machine  
- Path uses forward slashes (`//server/...`) — normalisation fix applied, needs real-world test  

---


### #6 — Update project memory with session context
**Status:** Pending  
**Details:** Save current session work to Claude memory files so next session starts with full context (new tabs, config files, features, pending issues).

---



### #9 — AppData user profile cleanup
**Status:** Pending  
**Details:**  
- List all user profiles on the machine with last login date  
- Select profiles to clean AppData\Local and AppData\Roaming junk (temp, cache folders)  
- Show size per profile  
- Warning before touching active/current user profile data

---

## In Progress

*(none)*

---

## Completed (this session continued)

### #7 — Vulnerability scan tab ✓
**Completed:** 2026-05-11  
**Result:** New Security tab (`ui/tab_security.py`). 13 checks across HIGH/MEDIUM/LOW severity: Firewall, RDP, SMBv1, Guest account, AutoLogon, Defender, UAC, Windows Updates, BitLocker, SMB signing, Password policy, Remote Registry, Telnet. Per-check Fix button that re-verifies after fix. Export report to `logs/security_scan_YYYY-MM-DD_HH-MM.txt`. All fixes logged via `log_change()` in `modules/logger.py` to persistent `logs/changes.log`.

---

### #8 — Temp file master cleaner ✓
**Completed:** 2026-05-11  
**Result:** New Cleanup tab (`ui/tab_cleanup.py`). 9 locations: User Temp, Windows Temp, Prefetch, WU Cache, WER, Chrome/Edge/Firefox caches, Recycle Bin. Per-checkbox selection, Scan Sizes calculates sizes first, Clean Selected runs PS + auto-rescans to report freed space. Admin-only tab.

---

### #5 — run.bat admin elevation ✓
**Completed:** 2026-05-11  
**Result:** Verified UNC + admin flow correct. Fixed `pause` — now only fires on error (`if %errorlevel% neq 0 pause`). Task #4 (gen1.bat) removed — separate app, not in scope.

---

### Config Tab ✓
**Completed:** 2026-05-09  
**Result:** New Config tab with Features, Fixes, Legacy Panels. Committed to master.

---

## Completed

### #1 — Commit tweaks error detail improvements ✓
**Completed:** 2026-05-09  
**Result:** Committed + pushed. try/catch wrapper, red error msg, grey CMD line in failure dialog.

---

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
