# IT Provisioning Tool — Task Tracker

Last updated: 2026-11-12

---

## Pending

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

### #10 — Expand Security tab with more vulnerability checks ✓
**Completed:** 2026-11-12 (needs a test run on a real machine — see below)
**Result:** 36 checks (was 23). Check definitions moved to `modules/security_checks.py` and report builders to `modules/security_report.py` so #13 can reuse both.
- **13 new checks:** open listening ports, shared folder exposure (Everyone/Guest), LLMNR/NetBIOS poisoning, local admin accounts, LAPS status, running services audit (SNMP/UPnP/WinRM/FTP/IIS/sshd/TeamViewer/AnyDesk/VNC…), suspicious scheduled tasks (unsigned exes in user-writable paths, encoded/download one-liners), known-vulnerable/EOL software (static `KNOWN_VULNERABLE` list — review periodically), machine certificate expiry, AutoRun on removable drives, Secure Boot/UEFI/TPM, driver health/outdated drivers, USB mass storage policy.
- **Categories:** Network / Accounts / System / Policy / Hardware; within a category failures sort first. Each row shows a severity badge.
- **Risk score:** CLEAN/LOW/MEDIUM/HIGH/CRITICAL level (same scale #13 will use) + 0–100 score from weighted severity×status penalties.
- **Fix All per category:** confirmation dialog lists only reversible fixes (have `undo_ps`) for failing checks, with impact text; fixes marked disruptive (RDP, Spooler, admin shares, USB, TLS 1.0, cached logons, SMBv1, LLMNR/NetBIOS) are unticked by default. Each fix is re-verified and logged via `log_change()`.
- **Export:** writes HTML + structured TXT to `logs/security_scan_<PC>_<timestamp>.*` and opens the HTML. Header includes machine, domain, OS, user, risk level.
- Checks now run 6 in parallel via new `run_encoded_powershell()` (`-EncodedCommand`, 120s timeout, no quoting issues).
- "Open X" style fixes (Updates, BitLocker, review consoles) just open the console — no longer logged as changes.
- Fixed: export tagged fixed checks as "[REVERTED]"; `after(0, widget.configure, {...})` calls passed options as `require_redraw` so progress text never updated.

### #9 — Cleanup Hub (3 sections: User Profiles, Windows Cleanup, Disk Analysis) ✓
**Completed:** 2026-07-10
**Result:** Cleanup tab restructured into a hub (`ui/tab_cleanup.py`) with an inner `CTkTabview` hosting three sections:
- **User Profiles** (`ui/cleanup_profiles.py`, new) — lists real profiles via new `scripts/get_user_profiles.ps1` (SID/username/path/last-login/loaded). Scan Sizes computes reclaimable AppData junk per profile (Temp, browser caches, INetCache, cookies, recent items, WER, thumbnail/icon cache). Clean Selected wipes junk for checked profiles with before/after size report. Active/current-user profiles are flagged and require an extra confirm. Delete Profile uses `Win32_UserProfile.Delete()` (proper deprovisioning, not raw folder removal), blocked for active/current profiles.
- **Windows Cleanup** — the pre-existing fully-built tab (`ui/cleanup_windows.py`, moved/renamed `WindowsCleanupSection`, no behavior change) already covered every bullet in this section's original spec (WU cache, WinSxS/DISM, Temp/Prefetch, WER, Recycle Bin, hiberfil.sys, Windows.old).
- **Disk Analysis** (`ui/cleanup_disk.py`, new) — drive panel via new `scripts/get_drive_health.ps1` (size/free/SMART-ish health from `Get-PhysicalDisk`), free-space bar colored red under 10% free, health badge. Folder breakdown is a WinDirStat-lite browser: drive dropdown + editable path + Up/Go, "Scan This Folder" lists immediate subfolders sorted by size (largest first), click a row to drill in.
- Added shared `format_size()` to `modules/utils.py` (was duplicated locally in the old cleanup tab).

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
