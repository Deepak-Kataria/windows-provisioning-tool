# Changelog

All versions tagged in git. Rollback: `git checkout v<version>`

---

## [Unreleased] — In Progress

### Added
- System tab: hardware-based auto-generate computer name (motherboard serial → SHA256 → 8-char ID)
- `scripts/get_hardware_id.ps1` — reads mobo serial, falls back to BIOS UUID

---

## [v1.1.0] - 2026-04-20

### Added
- Auto-create `credentials.json` on first run with placeholder admin account
- First-run mandatory password change dialog (blocks dashboard until complete)
- User management tab (admin only): add users, delete users, reset passwords
- System tab: DC Server IP field for targeted domain join
- System tab: OU browser — fetches OUs from Active Directory via LDAP (port 389)
- `scripts/get_ous.ps1` — PowerShell script to query AD OUs

### Fixed
- `scripts/debloat.ps1` — now accepts comma-separated string instead of array
- `scripts/join_domain.ps1` — domain join password passed via stdin, never as CLI arg (security)

### Changed
- Desktop/Laptop radio buttons now render side by side

---

## [v1.0.0] - 2026-04-15

### Added
- Login screen with role-based access (admin / user)
- System tab: PC rename with DT/LT naming convention, domain join
- Debloat tab: remove Windows bloatware via PowerShell
- Privacy/Telemetry tab: disable Windows telemetry and tracking
- Apps tab: install common apps + team-based apps via winget
- Org Settings tab: apply registry tweaks for org standards
- Audit logger (`modules/logger.py`)
- PowerShell scripts: rename, join domain, debloat, telemetry, org settings
- JSON configs: domain, apps (common + teams), debloat list, org settings

---

## Backlog (Phase-wise)

### Phase 2 — Domain & System Enhancements
- [ ] System tab: show current computer name
- [ ] Domain: "Test Connection" button — verify DC reachable before join attempt
- [ ] Domain: "Check Domain Status" — show if machine is already joined
- [ ] Domain: "Leave Domain" option

### Phase 3 — Debloat Expansion
- [ ] Add packages: Bing News, Bing Weather, Bing Finance
- [ ] Add packages: Clipchamp, Windows Widgets, Quick Assist
- [ ] Add packages: Microsoft Family, Phone Link, Power Automate Desktop
- [ ] Add packages: Microsoft To-Do, Voice Recorder, Camera (desktop)
- [ ] Add packages: Disney+, Netflix (if present)
- [ ] Add category grouping (Gaming, Microsoft Apps, Third-party)
- [ ] Add services debloat: Xbox services, Print Spooler, Fax service

### Phase 4 — Privacy Hardening
- [ ] Disable Bing search in Start menu
- [ ] Disable Cortana service completely
- [ ] Disable Windows Error Reporting
- [ ] Disable Clipboard history
- [ ] Disable Timeline / Task View history
- [ ] Disable WiFi Sense
- [ ] Disable SMBv1 (security hardening)
- [ ] Disable LLMNR (security hardening)
- [ ] Force Windows Firewall on all profiles

### Phase 5 — Apps Expansion
- [ ] Common apps: Microsoft Teams, Zoom, AnyDesk, Bitwarden, TreeSize Free, Malwarebytes
- [ ] New teams: HR, Sales, Marketing
- [ ] Manual install field: enter any winget ID directly

### Phase 6 — Org Settings & Maintenance
- [ ] OneDrive Known Folder Move (Desktop / Documents / Pictures → OneDrive)
- [ ] Storage Sense: auto-enable and configure cleanup schedule
- [ ] Temp files immediate cleanup script
- [ ] AppData / browser cache size reduction
- [ ] Power plan selector (Balanced / High Performance / Power Saver)
- [ ] Windows Update deferral policy (defer feature updates N days)
- [ ] Network drive mapping (configure drive letter + UNC path)
