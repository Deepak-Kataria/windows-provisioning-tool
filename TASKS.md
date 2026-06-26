# IT Provisioning Tool — Task Tracker

Last updated: 2026-06-26

---

## Pending



### #9 — Cleanup Hub (3 sections: User Profiles, Windows Cleanup, Disk Analysis)
**Status:** Pending  
**Details:**  

**Section A — User Profile Cleanup:**
- List all user profiles on machine with last login date + profile size
- Select profiles to clean AppData\Local and AppData\Roaming junk (Temp, cache, browser caches, thumbnails, crash dumps)
- Show size before/after per profile
- Warning before touching active/current user profile
- Option to delete entire stale/orphaned profiles (with confirmation)

**Section B — Windows Cleanup:**
- Expand existing Cleanup tab into structured sections
- Windows Update cache (`C:\Windows\SoftwareDistribution\Download`)
- WinSxS component cleanup (via DISM `/StartComponentCleanup`)
- Temp files (User Temp, Windows Temp, Prefetch)
- Windows Error Reporting / crash dumps
- Recycle Bin (all users)
- Hibernate file (`hiberfil.sys`) — disable option to reclaim space
- Old Windows installations (`Windows.old`)
- Show size per category, select/clean individually

**Section C — Disk Analysis:**
- Folder size breakdown (top-level tree — which folders eat most space, WinDirStat-lite view)
- Drill-down: click folder to see sub-folder breakdown
- Drive health: SMART status via PowerShell/WMI, free space per drive, health status (Good/Warning/Critical)
- Free space bar per drive (visual)
- Flag drives below 10% free as warning

---

### #13 — System Compromise & Threat Report
**Status:** Pending  
**Details:**  

**Goal:** Full report answering "has this machine been compromised, and what vulnerabilities exist that could allow it?"

**Compromise Indicators (was it hacked?):**
- Unusual local admin accounts (accounts not in approved list)
- Unexpected scheduled tasks (non-Microsoft, recently created)
- Suspicious startup entries (Run/RunOnce registry keys, Startup folder)
- Running processes — flag unknown/unsigned processes
- Recently installed software (last 30/60/90 days) — list for review
- Open outbound connections — active network connections to external IPs
- Windows Event Log analysis: failed logins (4625), account lockouts (4740), new account creation (4720), privilege escalation (4672), RDP sessions (4624 logon type 10)
- Modified system files / unexpected files in System32
- Antivirus/Defender last scan date + any quarantined threats

**Vulnerability Exposure (can it be hacked?):**
- All checks from Security tab (#10) included
- Unpatched CVEs — compare installed software versions against known-vulnerable list
- Weak/blank local account passwords (test with net accounts policy)
- RDP exposed + no NLA
- SMB shares open to Everyone
- PowerShell execution policy (Unrestricted = risk)
- WinRM enabled unexpectedly
- AutoRun enabled on removable drives
- Outdated BIOS/firmware version check

**Report output:**
- Overall risk score: CLEAN / LOW / MEDIUM / HIGH / CRITICAL
- Two sections: "Signs of Compromise" + "Vulnerability Exposure"
- Each finding: severity badge, description, recommended action
- Export to HTML report file (readable, shareable)
- Export to TXT (plain, for tickets)
- Timestamp + machine name in report header

---

### #10 — Expand Security tab with more vulnerability checks
**Status:** Pending  
**Details:**  
- Current: 13 checks (Firewall, RDP, SMBv1, Guest, AutoLogon, Defender, UAC, Updates, BitLocker, SMB signing, Password policy, Remote Registry, Telnet)
- Add: open ports scan, running services audit, scheduled tasks (suspicious), installed software vs known-vulnerable list, outdated driver check, local admin account audit, shared folders exposure, LAPS status, certificate expiry, boot integrity (Secure Boot/UEFI), NTLM settings, USB/removable media policy, DNS poisoning exposure
- Group checks into categories (Network, Accounts, System, Policy, Hardware)
- Severity scoring — show overall risk score at top
- Bulk Fix All button per category
- Export report improvements (HTML or structured txt)

---

### #11 — Domain join self-service for normal users
**Status:** Pending  
**Details:**  
- Goal: non-IT user can join their own PC to domain without IT help
- Simplified wizard-style flow: enter PC name -> enter domain credentials -> join (no OU browsing required for basic join)
- Auto-fill domain from config, user only provides their AD username + password
- Clear plain-English status messages ("Connecting...", "Almost done...", "Restart needed")
- Handle common errors with user-friendly explanations (wrong password, PC already joined, network unreachable, stale account)
- Optional: pre-join checklist (network reachable? DNS correct? PC name set?) with green/red indicators
- Post-join prompt to restart with one-click restart button
- Keep advanced/IT mode (current full UI) accessible for admins

---

### #12 — UI/UX improvements across all tabs
**Status:** Pending  
**Details:**  
- Select All / Deselect All buttons on every tab that has checkboxes (Debloat, Privacy, Cleanup, Security)
- Undo/rollback section per tab — show last N actions with individual undo buttons
- Apply button consistency — confirm what will run before applying, not just after
- Results dialog improvements — cleaner layout, copy-to-clipboard, collapse/expand per item
- Tab-level status indicator — show last run time + pass/fail badge on each tab header
- Progress feedback — spinner or progress bar during any long-running operation
- Keyboard shortcuts (Select All = Ctrl+A, Apply = Ctrl+Enter)
- Tooltips on all buttons explaining what they do
- Responsive layout — panels resize cleanly on smaller screens

---

## In Progress

*(none)*

---

## Completed (this session continued)

### #6 — Update project memory with session context ✓
**Completed:** 2026-06-24
**Result:** Updated `project_overview.md` and `project_sheets_sync.md` memory files. Captured: Brand Name column, upsert Serial col index fix, runner CREATE_NO_WINDOW, rename domain-detection fix (RENAME_CONTEXT output), Cleanup tab SECTIONS refactor, run_dev.bat testing note.

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
