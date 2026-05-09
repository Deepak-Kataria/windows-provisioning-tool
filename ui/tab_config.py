import customtkinter as ctk
import subprocess
import threading
from modules.runner import run_inline_powershell
from modules.logger import log


FEATURES = [
    {
        "id": "dotnet",
        "name": ".NET Framework 2, 3, 4 - Enable",
        "description": "Installs .NET 2/3/4 via Windows Features. Required by many legacy business and ERP applications.",
        "cmd": "dism /online /enable-feature /featurename:NetFx3 /All /Source:\"$env:windir\\WinSxS\" /LimitAccess"
    },
    {
        "id": "nfs",
        "name": "Network File System (NFS) - Enable",
        "description": "Enables NFS client to mount Linux/Unix network shares on this machine.",
        "cmd": "Enable-WindowsOptionalFeature -Online -FeatureName ServicesForNFS-ClientOnly -All -NoRestart"
    },
    {
        "id": "reg_backup",
        "name": "Registry Backup Daily Task - Enable",
        "description": "Creates a scheduled task to back up registry hives daily at 12:30am to C:\\RegBack.",
        "cmd": (
            "$action = New-ScheduledTaskAction -Execute 'reg.exe' -Argument 'export HKLM C:\\RegBack\\HKLM.reg /y'; "
            "$trigger = New-ScheduledTaskTrigger -Daily -At '00:30'; "
            "$settings = New-ScheduledTaskSettingsSet -RunOnlyIfIdle:$false; "
            "Register-ScheduledTask -TaskName 'RegistryDailyBackup' -Action $action -Trigger $trigger "
            "-Settings $settings -RunLevel Highest -Force | Out-Null; "
            "Write-Host 'Registry backup task created.'"
        )
    },
]

FIXES = [
    {
        "id": "net_reset",
        "name": "Network - Reset",
        "description": "Resets Winsock, IP stack, flushes DNS. Fixes most network connectivity issues.",
        "cmd": "netsh winsock reset; netsh int ip reset; ipconfig /release; ipconfig /flushdns; ipconfig /renew; Write-Host 'Network stack reset complete.'"
    },
    {
        "id": "ntp",
        "name": "NTP Server - Enable",
        "description": "Configures Windows Time to sync with pool.ntp.org. Keeps clock accurate.",
        "cmd": (
            "w32tm /config /manualpeerlist:\"pool.ntp.org\" /syncfromflags:manual /reliable:YES /update; "
            "Restart-Service w32tm -Force; "
            "w32tm /resync /force; "
            "Write-Host 'NTP configured and synced.'"
        )
    },
    {
        "id": "sfc_dism",
        "name": "System Corruption Scan - Run",
        "description": "Runs SFC /scannow then DISM /RestoreHealth. Repairs corrupted Windows files. Takes 5-15 mins.",
        "cmd": "Write-Host 'Running SFC...'; sfc /scannow; Write-Host 'Running DISM...'; DISM /Online /Cleanup-Image /RestoreHealth; Write-Host 'Scan complete.'"
    },
    {
        "id": "wu_reset",
        "name": "Windows Update - Reset",
        "description": "Stops update services, clears download cache, restarts. Fixes stuck or broken Windows Update.",
        "cmd": (
            "Stop-Service wuauserv,bits,cryptsvc,msiserver -Force -ErrorAction SilentlyContinue; "
            "Remove-Item -Path '$env:SystemRoot\\SoftwareDistribution' -Recurse -Force -ErrorAction SilentlyContinue; "
            "Remove-Item -Path '$env:SystemRoot\\System32\\catroot2' -Recurse -Force -ErrorAction SilentlyContinue; "
            "Start-Service wuauserv,bits,cryptsvc -ErrorAction SilentlyContinue; "
            "Write-Host 'Windows Update reset complete.'"
        )
    },
    {
        "id": "winget_reinstall",
        "name": "WinGet - Reinstall",
        "description": "Re-registers WinGet (App Installer). Fixes 'winget not found' or broken package installs.",
        "cmd": (
            "Add-AppxPackage -RegisterByFamilyName "
            "-MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe -ErrorAction SilentlyContinue; "
            "Write-Host 'WinGet reinstalled.'"
        )
    },
]

PANELS = [
    ("Computer Management",  "compmgmt.msc"),
    ("Control Panel",        "control"),
    ("Network Connections",  "ncpa.cpl"),
    ("Power Panel",          "powercfg.cpl"),
    ("Printer Panel",        "printmanagement.msc"),
    ("Region",               "intl.cpl"),
    ("Sound Settings",       "mmsys.cpl"),
    ("System Properties",    "sysdm.cpl"),
    ("Time and Date",        "timedate.cpl"),
    ("Windows Restore",      "rstrui.exe"),
]


class ConfigTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._feature_vars = {}
        self._build()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        wrap = ctk.CTkScrollableFrame(self, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)

        # ── Left: Features + Fixes ─────────────────────────────────
        left = ctk.CTkFrame(wrap)
        left.grid(row=0, column=0, padx=(10, 4), pady=10, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        # Features
        ctk.CTkLabel(left, text="Features",
                      font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=0, column=0, padx=14, pady=(14, 6), sticky="w")

        for i, feat in enumerate(FEATURES):
            var = ctk.BooleanVar(value=False)
            self._feature_vars[feat["id"]] = (var, feat)
            cb = ctk.CTkCheckBox(left, text=feat["name"], variable=var,
                                  font=ctk.CTkFont(size=12))
            cb.grid(row=i + 1, column=0, sticky="w", padx=20, pady=3)
            cb.bind("<Enter>", lambda e, d=feat["description"]: self._set_desc(d))
            cb.bind("<Leave>", lambda e: self._set_desc(""))

        self._run_feat_btn = ctk.CTkButton(
            left, text="Run Features", command=self._run_features)
        self._run_feat_btn.grid(row=len(FEATURES) + 1, column=0,
                                 padx=14, pady=(10, 4), sticky="w")

        # Fixes
        ctk.CTkLabel(left, text="Fixes",
                      font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=len(FEATURES) + 2, column=0, padx=14, pady=(16, 6), sticky="w")

        for j, fix in enumerate(FIXES):
            row = len(FEATURES) + 3 + j
            btn = ctk.CTkButton(left, text=fix["name"], anchor="w",
                                  command=lambda f=fix: self._run_fix(f))
            btn.grid(row=row, column=0, padx=14, pady=3, sticky="ew")
            btn.bind("<Enter>", lambda e, d=fix["description"]: self._set_desc(d))
            btn.bind("<Leave>", lambda e: self._set_desc(""))

        # ── Right: Legacy Panels ───────────────────────────────────
        right = ctk.CTkFrame(wrap)
        right.grid(row=0, column=1, padx=(4, 10), pady=10, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="Legacy Windows Panels",
                      font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=0, column=0, padx=14, pady=(14, 6), sticky="w")

        for k, (label, target) in enumerate(PANELS):
            btn = ctk.CTkButton(right, text=label, anchor="w",
                                 command=lambda t=target: self._open_panel(t))
            btn.grid(row=k + 1, column=0, padx=14, pady=3, sticky="ew")

        # ── Output ─────────────────────────────────────────────────
        desc_frame = ctk.CTkFrame(wrap, height=44)
        desc_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="ew")
        desc_frame.grid_columnconfigure(0, weight=1)
        desc_frame.grid_propagate(False)
        self._desc_label = ctk.CTkLabel(desc_frame, text="",
                                         text_color="gray", font=ctk.CTkFont(size=11),
                                         anchor="w", wraplength=900)
        self._desc_label.grid(row=0, column=0, padx=12, pady=8, sticky="w")

        ctk.CTkLabel(wrap, text="Output",
                      font=ctk.CTkFont(size=13, weight="bold"), anchor="w").grid(
            row=2, column=0, columnspan=2, padx=10, pady=(0, 2), sticky="w")
        self._output = ctk.CTkTextbox(wrap, height=130, state="disabled",
                                       font=ctk.CTkFont(family="Courier New", size=11))
        self._output.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

    # ── Helpers ────────────────────────────────────────────────────

    def _set_desc(self, text):
        self._desc_label.configure(text=text)

    def _append(self, text):
        self._output.configure(state="normal")
        self._output.insert("end", text + "\n")
        self._output.see("end")
        self._output.configure(state="disabled")

    def _safe_append(self, text):
        self.after(0, self._append, text)

    def _open_panel(self, target):
        try:
            subprocess.Popen(["cmd", "/c", "start", target],
                              creationflags=subprocess.CREATE_NO_WINDOW)
            log(f"Config: opened panel {target}")
        except Exception as e:
            self._append(f"ERROR opening {target}: {e}")

    # ── Feature runner ─────────────────────────────────────────────

    def _run_features(self):
        if self._running:
            return
        selected = [(fid, feat) for fid, (var, feat) in self._feature_vars.items() if var.get()]
        if not selected:
            self._append("No features selected.")
            return

        self._running = True
        self._run_feat_btn.configure(state="disabled")
        self._append(f"Running {len(selected)} feature(s)...")
        log(f"Config: features {[f for f, _ in selected]}")

        def task():
            for fid, feat in selected:
                self._safe_append(f"\n>>> {feat['name']}")
                rc, out = run_inline_powershell(feat["cmd"], callback=self._safe_append)
                self._safe_append(f"  {'OK' if rc == 0 else 'FAILED'} (exit {rc})")
                log(f"Config feature {fid} rc={rc}")

            def finish():
                self._running = False
                self._run_feat_btn.configure(state="normal")
                self._append("\nDone.")
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── Fix runner ─────────────────────────────────────────────────

    def _run_fix(self, fix):
        if self._running:
            return
        self._running = True
        self._append(f"\n>>> {fix['name']}")
        log(f"Config: fix {fix['id']}")

        def task():
            rc, out = run_inline_powershell(fix["cmd"], callback=self._safe_append)
            self._safe_append(f"  {'OK' if rc == 0 else 'FAILED'} (exit {rc})")
            log(f"Config fix {fix['id']} rc={rc}")

            def finish():
                self._running = False
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()
