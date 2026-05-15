import os
import threading
from datetime import datetime
import customtkinter as ctk
from modules.runner import run_inline_powershell
from modules.logger import log, log_change
from modules.utils import writable_path


CHECKS = [
    {
        "id": "firewall",
        "name": "Windows Firewall",
        "description": "All firewall profiles (Domain/Private/Public) must be enabled.",
        "severity": "HIGH",
        "check_ps": (
            "$off = Get-NetFirewallProfile -EA SilentlyContinue"
            " | Where-Object { $_.Enabled -eq $false }"
            " | Select-Object -ExpandProperty Name;"
            " if ($off) { \"FAIL: Profiles disabled: $($off -join ', ')\" } else { 'PASS' }"
        ),
        "fix_ps":  "Set-NetFirewallProfile -All -Enabled True; Write-Host 'Firewall enabled.'",
        "fix_label": "Enable Firewall",
        "undo_ps": "Set-NetFirewallProfile -All -Enabled False; Write-Host 'Firewall disabled.'",
        "undo_label": "Revert (Disable)",
    },
    {
        "id": "rdp",
        "name": "RDP Exposure",
        "description": "RDP should be disabled on machines not requiring remote access.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server'"
            " -Name fDenyTSConnections -EA SilentlyContinue).fDenyTSConnections;"
            " if ($v -eq 0) { 'FAIL: RDP is enabled (port 3389 open)' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server'"
            " -Name fDenyTSConnections -Value 1 -Force; Write-Host 'RDP disabled.'"
        ),
        "fix_label": "Disable RDP",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server'"
            " -Name fDenyTSConnections -Value 0 -Force; Write-Host 'RDP re-enabled.'"
        ),
        "undo_label": "Revert (Re-enable RDP)",
    },
    {
        "id": "smb1",
        "name": "SMBv1 Protocol",
        "description": "SMBv1 enables EternalBlue/WannaCry exploits. Must be disabled.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-SmbServerConfiguration -EA SilentlyContinue).EnableSMB1Protocol;"
            " if ($v) { 'FAIL: SMBv1 enabled (EternalBlue/WannaCry risk)' } else { 'PASS' }"
        ),
        "fix_ps":  "Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force; Write-Host 'SMBv1 disabled.'",
        "fix_label": "Disable SMBv1",
        "undo_ps": "Set-SmbServerConfiguration -EnableSMB1Protocol $true -Force; Write-Host 'SMBv1 re-enabled.'",
        "undo_label": "Revert (Re-enable SMBv1)",
    },
    {
        "id": "guest",
        "name": "Guest Account",
        "description": "Guest account provides unauthenticated access. Must be disabled.",
        "severity": "HIGH",
        "check_ps": (
            "$g = Get-LocalUser -Name 'Guest' -EA SilentlyContinue;"
            " if ($g -and $g.Enabled) { 'FAIL: Guest account is enabled' } else { 'PASS' }"
        ),
        "fix_ps":  "Disable-LocalUser -Name 'Guest'; Write-Host 'Guest account disabled.'",
        "fix_label": "Disable Guest",
        "undo_ps": "Enable-LocalUser -Name 'Guest'; Write-Host 'Guest account re-enabled.'",
        "undo_label": "Revert (Re-enable Guest)",
    },
    {
        "id": "autologon",
        "name": "Auto-Login (AutoLogon)",
        "description": "AutoLogon stores plaintext credentials in the registry.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"
            " -Name AutoAdminLogon -EA SilentlyContinue).AutoAdminLogon;"
            " if ($v -eq '1') { 'FAIL: Auto-login enabled (credentials in registry)' } else { 'PASS' }"
        ),
        "fix_ps": (
            "$p = 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon';"
            " Set-ItemProperty $p AutoAdminLogon '0' -Force;"
            " Remove-ItemProperty $p DefaultPassword -EA SilentlyContinue;"
            " Write-Host 'Auto-login disabled.'"
        ),
        "fix_label": "Disable Auto-Login",
        "undo_ps": (
            "Set-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon'"
            " AutoAdminLogon '1' -Force; Write-Host 'Auto-login re-enabled (no password set).'"
        ),
        "undo_label": "Revert (Re-enable AutoLogon)",
    },
    {
        "id": "defender",
        "name": "Windows Defender",
        "description": "Real-time protection must be active.",
        "severity": "HIGH",
        "check_ps": (
            "$s = Get-MpComputerStatus -EA SilentlyContinue;"
            " if (-not $s) { 'WARN: Could not query Defender status' }"
            " elseif (-not $s.RealTimeProtectionEnabled) { 'FAIL: Real-time protection disabled' }"
            " else { 'PASS' }"
        ),
        "fix_ps":  "Set-MpPreference -DisableRealtimeMonitoring $false; Write-Host 'Defender enabled.'",
        "fix_label": "Enable Defender",
        "undo_ps": "Set-MpPreference -DisableRealtimeMonitoring $true; Write-Host 'Defender real-time disabled.'",
        "undo_label": "Revert (Disable Defender)",
    },
    {
        "id": "uac",
        "name": "User Account Control (UAC)",
        "description": "UAC prevents unauthorised privilege escalation.",
        "severity": "HIGH",
        "check_ps": (
            "$v = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System'"
            " -Name EnableLUA -EA SilentlyContinue).EnableLUA;"
            " if ($v -eq 0) { 'FAIL: UAC is disabled' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System'"
            " -Name EnableLUA -Value 1 -Force; Write-Host 'UAC enabled. Restart required.'"
        ),
        "fix_label": "Enable UAC",
        "undo_ps": (
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System'"
            " -Name EnableLUA -Value 0 -Force; Write-Host 'UAC disabled. Restart required.'"
        ),
        "undo_label": "Revert (Disable UAC)",
    },
    {
        "id": "windows_updates",
        "name": "Windows Updates",
        "description": "System should have recent updates installed (within 30 days).",
        "severity": "MEDIUM",
        "check_ps": (
            "$h = Get-HotFix -EA SilentlyContinue | Sort-Object InstalledOn -Descending | Select-Object -First 1;"
            " if ($h -and $h.InstalledOn) {"
            " $days = [int]((Get-Date) - $h.InstalledOn).TotalDays;"
            " if ($days -gt 30) { \"WARN: Last update $days days ago ($($h.InstalledOn.ToString('yyyy-MM-dd')))\" }"
            " else { \"PASS: Last update $days days ago\" } }"
            " else { 'WARN: No Windows Update history found' }"
        ),
        "fix_ps": "Start-Process 'ms-settings:windowsupdate'; Write-Host 'Windows Update opened.'",
        "fix_label": "Open Updates",
    },
    {
        "id": "bitlocker",
        "name": "BitLocker (Drive C:)",
        "description": "Full-disk encryption protects data if device is lost or stolen.",
        "severity": "MEDIUM",
        "check_ps": (
            "$bl = Get-BitLockerVolume -MountPoint 'C:' -EA SilentlyContinue;"
            " if (-not $bl) { 'WARN: BitLocker not available or could not query' }"
            " elseif ($bl.ProtectionStatus -ne 'On') { 'WARN: BitLocker not enabled on C: (data unencrypted)' }"
            " else { 'PASS: BitLocker protection active' }"
        ),
        "fix_ps": "control /name Microsoft.BitLockerDriveEncryption; Write-Host 'BitLocker panel opened.'",
        "fix_label": "Open BitLocker",
    },
    {
        "id": "smb_signing",
        "name": "SMB Signing",
        "description": "SMB signing prevents man-in-the-middle relay attacks.",
        "severity": "MEDIUM",
        "check_ps": (
            "$v = (Get-SmbServerConfiguration -EA SilentlyContinue).RequireSecuritySignature;"
            " if ($v -eq $false) { 'WARN: SMB signing not required (MITM risk)' } else { 'PASS' }"
        ),
        "fix_ps":  "Set-SmbServerConfiguration -RequireSecuritySignature $true -Force; Write-Host 'SMB signing required.'",
        "fix_label": "Require SMB Signing",
        "undo_ps": "Set-SmbServerConfiguration -RequireSecuritySignature $false -Force; Write-Host 'SMB signing reverted.'",
        "undo_label": "Revert SMB Signing",
    },
    {
        "id": "password_policy",
        "name": "Password Max Age Policy",
        "description": "Passwords should expire within 90 days.",
        "severity": "MEDIUM",
        "check_ps": (
            "$out = net accounts 2>&1 | Out-String;"
            " if ($out -match 'Maximum password age:\\s+(\\S+)') {"
            " $age = $matches[1];"
            " if ($age -eq 'Unlimited') { 'WARN: Password max age: Unlimited' }"
            " elseif ([int]$age -gt 90) { \"WARN: Password max age: $age days (>90)\" }"
            " else { \"PASS: Max age $age days\" } }"
            " else { 'WARN: Could not read password policy' }"
        ),
        "fix_ps":  "net accounts /maxpwage:90; Write-Host 'Password max age set to 90 days.'",
        "fix_label": "Set 90-Day Expiry",
        "undo_ps": "net accounts /maxpwage:unlimited; Write-Host 'Password max age set to Unlimited.'",
        "undo_label": "Revert (Set Unlimited)",
    },
    {
        "id": "remote_registry",
        "name": "Remote Registry Service",
        "description": "Remote Registry allows remote editing of registry hives. Should be disabled.",
        "severity": "LOW",
        "check_ps": (
            "$s = Get-Service -Name RemoteRegistry -EA SilentlyContinue;"
            " if ($s -and $s.Status -eq 'Running') { 'WARN: Remote Registry service is running' } else { 'PASS' }"
        ),
        "fix_ps": (
            "Stop-Service RemoteRegistry -Force -EA SilentlyContinue;"
            " Set-Service RemoteRegistry -StartupType Disabled;"
            " Write-Host 'Remote Registry disabled.'"
        ),
        "fix_label": "Disable Service",
        "undo_ps": (
            "Set-Service RemoteRegistry -StartupType Automatic;"
            " Start-Service RemoteRegistry -EA SilentlyContinue;"
            " Write-Host 'Remote Registry re-enabled.'"
        ),
        "undo_label": "Revert (Re-enable)",
    },
    {
        "id": "telnet",
        "name": "Telnet Client",
        "description": "Telnet transmits data in plaintext. Should not be installed.",
        "severity": "LOW",
        "check_ps": (
            "$f = Get-WindowsOptionalFeature -Online -FeatureName TelnetClient -EA SilentlyContinue;"
            " if ($f -and $f.State -eq 'Enabled') { 'WARN: Telnet client installed (insecure)' } else { 'PASS' }"
        ),
        "fix_ps":  "Disable-WindowsOptionalFeature -Online -FeatureName TelnetClient -NoRestart; Write-Host 'Telnet removed.'",
        "fix_label": "Remove Telnet",
        "undo_ps": "Enable-WindowsOptionalFeature -Online -FeatureName TelnetClient -NoRestart; Write-Host 'Telnet installed.'",
        "undo_label": "Revert (Install Telnet)",
    },
]

_SEV_COLOR  = {"HIGH": "#c0392b", "MEDIUM": "#d35400", "LOW": "#7f8c8d"}
_SEV_HDR_BG = {
    "HIGH":   ("#fdecea", "#3a1010"),
    "MEDIUM": ("#fef0e8", "#2e1a08"),
    "LOW":    ("#efefef", "#252525"),
}
_STATUS_COLOR = {"PASS": "#27ae60", "FAIL": "#e74c3c", "WARN": "#e67e22"}
_STATUS_ICON  = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠"}


def _parse_result(out):
    line = out.strip().splitlines()[0].strip() if out.strip() else ""
    for prefix in ("FAIL:", "WARN:", "PASS:"):
        if line.upper().startswith(prefix):
            return prefix.rstrip(":"), line[len(prefix):].strip()
    if line.upper() == "PASS":
        return "PASS", ""
    return "UNKNOWN", line


class SecurityTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._results  = {}   # id → (status, detail)
        self._fixed    = set()  # ids where fix was applied this session
        self._row_widgets = {}  # id → {"row", "detail_lbl", "fix_btn", "revert_btn"}
        self._build()

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, height=56, corner_radius=0,
                           fg_color=("gray90", "gray17"))
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(2, weight=1)
        top.grid_propagate(False)

        self._scan_btn = ctk.CTkButton(
            top, text="Run Vulnerability Scan", width=190,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._run_scan)
        self._scan_btn.grid(row=0, column=0, padx=(14, 8), pady=10)

        self._export_btn = ctk.CTkButton(
            top, text="Export Report", width=120,
            fg_color="transparent", border_width=1,
            state="disabled", command=self._export_report)
        self._export_btn.grid(row=0, column=1, padx=6, pady=10)

        self._status_lbl = ctk.CTkLabel(
            top, text="Click 'Run Vulnerability Scan' to start.",
            text_color="gray", font=ctk.CTkFont(size=11))
        self._status_lbl.grid(row=0, column=2, padx=12, sticky="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._scroll,
            text="No scan results yet.\nRun a scan to see the security report.",
            text_color="gray", font=ctk.CTkFont(size=13), justify="center"
        ).grid(row=0, column=0, pady=60)

    # ── Report rendering ───────────────────────────────────────────

    def _clear_report(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._row_widgets.clear()

    def _render_report(self):
        self._clear_report()

        passed = sum(1 for s, _ in self._results.values() if s == "PASS")
        failed = sum(1 for s, _ in self._results.values() if s == "FAIL")
        warned = sum(1 for s, _ in self._results.values() if s == "WARN")

        # Summary header
        summary = ctk.CTkFrame(self._scroll, corner_radius=8)
        summary.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        summary.grid_columnconfigure(0, weight=1)

        ts = datetime.now().strftime("%Y-%m-%d  %H:%M")
        ctk.CTkLabel(summary, text="Security Report",
                     font=ctk.CTkFont(size=15, weight="bold"), anchor="w").grid(
            row=0, column=0, padx=14, pady=(12, 2), sticky="w")
        ctk.CTkLabel(summary,
                     text=f"Scanned: {ts}   |   {len(CHECKS)} checks",
                     text_color="gray", font=ctk.CTkFont(size=11), anchor="w").grid(
            row=1, column=0, padx=14, pady=(0, 8), sticky="w")

        pills = ctk.CTkFrame(summary, fg_color="transparent")
        pills.grid(row=2, column=0, padx=10, pady=(0, 12), sticky="w")
        for col, (label, count, color) in enumerate([
            (f"  {failed} FAILED  ",  failed,  "#c0392b"),
            (f"  {warned} WARNING  ", warned,  "#d35400"),
            (f"  {passed} PASSED  ",  passed,  "#27ae60"),
        ]):
            ctk.CTkLabel(pills, text=label, fg_color=color, text_color="white",
                         corner_radius=5, font=ctk.CTkFont(size=11, weight="bold"),
                         height=28).grid(row=0, column=col, padx=(0, 6))

        # Grouped check rows
        grid_row = 1
        for sev, sev_label in [("HIGH", "High Risk"), ("MEDIUM", "Medium Risk"), ("LOW", "Low Risk")]:
            group = [c for c in CHECKS if c["severity"] == sev]
            if not group:
                continue

            sec_hdr = ctk.CTkFrame(self._scroll, fg_color=_SEV_HDR_BG[sev],
                                    corner_radius=0, height=30)
            sec_hdr.grid(row=grid_row, column=0, padx=12, pady=(10, 0), sticky="ew")
            sec_hdr.grid_propagate(False)
            sec_hdr.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(sec_hdr, text=f"  {sev_label}",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=_SEV_COLOR[sev], anchor="w").grid(
                row=0, column=0, padx=6, pady=4, sticky="w")
            grid_row += 1

            grp_frame = ctk.CTkFrame(self._scroll, corner_radius=0)
            grp_frame.grid(row=grid_row, column=0, padx=12, pady=(0, 4), sticky="ew")
            grp_frame.grid_columnconfigure(2, weight=1)
            grid_row += 1

            for r_idx, check in enumerate(group):
                status, detail = self._results.get(check["id"], ("UNKNOWN", ""))
                self._add_result_row(grp_frame, check, status, detail, r_idx)

        self._export_btn.configure(state="normal")

    def _add_result_row(self, parent, check, status, detail, row_idx):
        color = _STATUS_COLOR.get(status, "gray")
        icon  = _STATUS_ICON.get(status, "?")
        bg    = ("gray95", "gray18") if row_idx % 2 == 0 else ("gray90", "gray20")

        row = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0)
        row.grid(row=row_idx, column=0, columnspan=4, sticky="ew")
        row.grid_columnconfigure(2, weight=1)

        # Icon
        icon_lbl = ctk.CTkLabel(row, text=f" {icon} ", width=30,
                                 font=ctk.CTkFont(size=14, weight="bold"),
                                 text_color=color)
        icon_lbl.grid(row=0, column=0, padx=(8, 2), pady=8)

        # Name
        name_lbl = ctk.CTkLabel(row, text=check["name"], width=200,
                                  font=ctk.CTkFont(size=12, weight="bold"),
                                  text_color=color, anchor="w")
        name_lbl.grid(row=0, column=1, padx=(0, 12), pady=8, sticky="w")

        # Detail
        detail_text  = detail if detail else check["description"]
        detail_color = color if detail else "gray"
        detail_lbl = ctk.CTkLabel(row, text=detail_text,
                                   font=ctk.CTkFont(size=11),
                                   text_color=detail_color, anchor="w",
                                   wraplength=400, justify="left")
        detail_lbl.grid(row=0, column=2, padx=(0, 12), pady=8, sticky="w")

        # Action buttons column
        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.grid(row=0, column=3, padx=(0, 10), pady=6)

        fix_btn    = None
        revert_btn = None

        if status in ("FAIL", "WARN") and check.get("fix_ps"):
            fix_btn = ctk.CTkButton(
                btn_frame, text=check["fix_label"], width=145, height=28,
                fg_color="#2980b9", hover_color="#1a5276",
                command=lambda c=check: self._run_fix(c))
            fix_btn.grid(row=0, column=0, padx=(0, 4))

        if check.get("undo_ps"):
            revert_btn = ctk.CTkButton(
                btn_frame, text=check.get("undo_label", "Revert"), width=160, height=28,
                fg_color="#7f8c8d", hover_color="#5d6d7e",
                command=lambda c=check: self._run_revert(c))
            revert_btn.grid(row=0, column=1, padx=(4, 0))

        self._row_widgets[check["id"]] = {
            "row": row, "icon_lbl": icon_lbl, "name_lbl": name_lbl,
            "detail_lbl": detail_lbl, "btn_frame": btn_frame,
            "fix_btn": fix_btn, "revert_btn": revert_btn,
        }

    # ── Row update (after fix / revert) ───────────────────────────

    def _update_row(self, check_id, status, detail):
        check = next(c for c in CHECKS if c["id"] == check_id)
        w = self._row_widgets.get(check_id)
        if not w:
            return

        color = _STATUS_COLOR.get(status, "gray")
        icon  = _STATUS_ICON.get(status, "?")

        w["icon_lbl"].configure(text=f" {icon} ", text_color=color)
        w["name_lbl"].configure(text_color=color)
        w["detail_lbl"].configure(
            text=detail if detail else check["description"],
            text_color=color if detail else "gray")

        # Rebuild action buttons
        for child in w["btn_frame"].winfo_children():
            child.destroy()
        w["fix_btn"] = None
        w["revert_btn"] = None

        col = 0
        if status in ("FAIL", "WARN") and check.get("fix_ps"):
            btn = ctk.CTkButton(
                w["btn_frame"], text=check["fix_label"], width=145, height=28,
                fg_color="#2980b9", hover_color="#1a5276",
                command=lambda c=check: self._run_fix(c))
            btn.grid(row=0, column=col, padx=(0, 4))
            w["fix_btn"] = btn
            col += 1

        if check.get("undo_ps"):
            rbtn = ctk.CTkButton(
                w["btn_frame"], text=check.get("undo_label", "Revert"), width=160, height=28,
                fg_color="#7f8c8d", hover_color="#5d6d7e",
                command=lambda c=check: self._run_revert(c))
            rbtn.grid(row=0, column=col, padx=(4, 0))
            w["revert_btn"] = rbtn

    def _update_summary_header(self):
        passed = sum(1 for s, _ in self._results.values() if s == "PASS")
        failed = sum(1 for s, _ in self._results.values() if s == "FAIL")
        warned = sum(1 for s, _ in self._results.values() if s == "WARN")
        color  = "#e74c3c" if failed else ("#e67e22" if warned else "#27ae60")
        self._status_lbl.configure(
            text=f"Scan complete  |  {failed} failed  {warned} warnings  {passed} passed",
            text_color=color)

    # ── Scan ───────────────────────────────────────────────────────

    def _run_scan(self):
        if self._running:
            return
        self._running = True
        self._fixed.clear()
        self._scan_btn.configure(state="disabled", text="Scanning...")
        self._export_btn.configure(state="disabled")
        self._status_lbl.configure(text="Running checks...", text_color="gray")
        self._clear_report()

        prog = ctk.CTkLabel(self._scroll, text="Scanning... 0 / 13",
                            text_color="gray", font=ctk.CTkFont(size=13))
        prog.grid(row=0, column=0, pady=60)
        self._results.clear()
        log("Security: scan started")

        def task():
            total = len(CHECKS)
            for i, check in enumerate(CHECKS):
                self.after(0, prog.configure,
                           {"text": f"Scanning...  {i + 1} / {total}  —  {check['name']}"})
                rc, out = run_inline_powershell(check["check_ps"])
                status, detail = _parse_result(out)
                self._results[check["id"]] = (status, detail)
                log(f"Security {check['id']}: {status} {detail}")

            self.after(0, self._render_report)
            self.after(0, self._update_summary_header)
            self.after(0, self._scan_btn.configure,
                       {"state": "normal", "text": "Run Vulnerability Scan"})
            self._running = False

        threading.Thread(target=task, daemon=True).start()

    # ── Fix ────────────────────────────────────────────────────────

    def _run_fix(self, check):
        if self._running:
            return
        self._running = True
        self._scan_btn.configure(state="disabled")
        w = self._row_widgets.get(check["id"])
        if w and w["fix_btn"]:
            w["fix_btn"].configure(state="disabled", text="Fixing...")

        before = self._results.get(check["id"], ("?", ""))
        before_str = f"{before[0]}: {before[1]}" if before[1] else before[0]

        def task():
            run_inline_powershell(check["fix_ps"])
            rc2, out2 = run_inline_powershell(check["check_ps"])
            status, detail = _parse_result(out2)
            self._results[check["id"]] = (status, detail)
            self._fixed.add(check["id"])
            after_str = f"{status}: {detail}" if detail else status
            log_change("Security", f"{check['name']} — {check['fix_label']}",
                       before=before_str, after=after_str)
            log(f"Security fix {check['id']}: {status}")
            self.after(0, self._update_row, check["id"], status, detail)
            self.after(0, self._update_summary_header)
            self.after(0, self._scan_btn.configure, {"state": "normal"})
            self._running = False

        threading.Thread(target=task, daemon=True).start()

    # ── Revert ─────────────────────────────────────────────────────

    def _run_revert(self, check):
        if self._running:
            return
        self._running = True
        self._scan_btn.configure(state="disabled")
        w = self._row_widgets.get(check["id"])
        if w and w["revert_btn"]:
            w["revert_btn"].configure(state="disabled", text="Reverting...")

        before = self._results.get(check["id"], ("?", ""))
        before_str = f"{before[0]}: {before[1]}" if before[1] else before[0]

        def task():
            run_inline_powershell(check["undo_ps"])
            rc2, out2 = run_inline_powershell(check["check_ps"])
            status, detail = _parse_result(out2)
            self._results[check["id"]] = (status, detail)
            self._fixed.discard(check["id"])
            after_str = f"{status}: {detail}" if detail else status
            log_change("Security", f"{check['name']} — REVERTED ({check.get('undo_label','')})",
                       before=before_str, after=after_str)
            log(f"Security revert {check['id']}: {status}")
            self.after(0, self._update_row, check["id"], status, detail)
            self.after(0, self._update_summary_header)
            self.after(0, self._scan_btn.configure, {"state": "normal"})
            self._running = False

        threading.Thread(target=task, daemon=True).start()

    # ── Export ─────────────────────────────────────────────────────

    def _export_report(self):
        if not self._results:
            return
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        log_dir = writable_path("logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"security_scan_{ts}.txt")

        lines = [
            "IT Provisioning Tool — Security Scan Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60, "",
        ]
        for sev, label in [("HIGH", "HIGH RISK"), ("MEDIUM", "MEDIUM RISK"), ("LOW", "LOW RISK")]:
            lines.append(f"\n[ {label} ]")
            for check in [c for c in CHECKS if c["severity"] == sev]:
                r = self._results.get(check["id"])
                status, detail = r if r else ("----", "")
                icon = _STATUS_ICON.get(status, "-")
                reverted = " [REVERTED]" if check["id"] in self._fixed else ""
                line = f"  {icon} {check['name']}{reverted}"
                if detail:
                    line += f"\n      {detail}"
                lines.append(line)

        passed = sum(1 for s, _ in self._results.values() if s == "PASS")
        failed = sum(1 for s, _ in self._results.values() if s == "FAIL")
        warned = sum(1 for s, _ in self._results.values() if s == "WARN")
        lines += ["", "=" * 60,
                  f"Summary: {passed} PASS  {failed} FAIL  {warned} WARN",
                  f"Total: {len(CHECKS)} checks"]

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self._status_lbl.configure(text=f"Report saved: {path}", text_color="gray")
            log(f"Security report exported: {path}")
        except Exception as e:
            self._status_lbl.configure(text=f"Export failed: {e}", text_color="#e74c3c")
