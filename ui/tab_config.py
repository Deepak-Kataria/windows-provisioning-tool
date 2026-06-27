import customtkinter as ctk
import subprocess
import threading
from modules.runner import run_inline_powershell
from modules.logger import log
from modules import sheets_sync


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
        self._wu_pending_count = 0
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

        # Windows Update
        ctk.CTkLabel(right, text="Windows Update",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=len(PANELS) + 2, column=0, padx=14, pady=(16, 6), sticky="w")

        wu_btn_row = ctk.CTkFrame(right, fg_color="transparent")
        wu_btn_row.grid(row=len(PANELS) + 3, column=0, padx=14, pady=(0, 4), sticky="w")
        self._wu_check_btn = ctk.CTkButton(wu_btn_row, text="Check for Updates", width=155,
                                            command=self._wu_check)
        self._wu_check_btn.grid(row=0, column=0, padx=(0, 8))
        self._wu_install_btn = ctk.CTkButton(wu_btn_row, text="Install All", width=110,
                                              fg_color="#2e7d32", hover_color="#1b5e20",
                                              command=self._wu_install, state="disabled")
        self._wu_install_btn.grid(row=0, column=1)

        self._wu_count_label = ctk.CTkLabel(right, text="", text_color="gray",
                                             font=ctk.CTkFont(size=11))
        self._wu_count_label.grid(row=len(PANELS) + 4, column=0, padx=14, pady=(2, 2), sticky="w")

        self._wu_list_box = ctk.CTkTextbox(right, height=130, state="disabled",
                                            font=ctk.CTkFont(family="Courier New", size=11))
        self._wu_list_box.grid(row=len(PANELS) + 5, column=0, padx=14, pady=(0, 14), sticky="ew")

        # ── Output ─────────────────────────────────────────────────
        desc_frame = ctk.CTkFrame(wrap, height=44)
        desc_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="ew")
        desc_frame.grid_columnconfigure(0, weight=1)
        desc_frame.grid_propagate(False)
        self._desc_label = ctk.CTkLabel(desc_frame, text="",
                                         text_color="gray", font=ctk.CTkFont(size=11),
                                         anchor="w", wraplength=900)
        self._desc_label.grid(row=0, column=0, padx=12, pady=8, sticky="w")

        # ── Google Sheets Sync ─────────────────────────────────────
        sheets_frame = ctk.CTkFrame(wrap)
        sheets_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="ew")
        sheets_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(sheets_frame, text="Google Sheets Sync",
                      font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=0, column=0, columnspan=3, padx=14, pady=(14, 6), sticky="w")

        ctk.CTkLabel(sheets_frame, text="Sheet ID:").grid(
            row=1, column=0, padx=14, pady=5, sticky="w")
        self._sheet_id_entry = ctk.CTkEntry(sheets_frame, width=360,
                                             placeholder_text="Paste Google Sheet ID from URL")
        self._sheet_id_entry.grid(row=1, column=1, padx=6, pady=5, sticky="w")

        ctk.CTkLabel(sheets_frame, text="Worksheet Name:").grid(
            row=2, column=0, padx=14, pady=5, sticky="w")
        self._ws_name_entry = ctk.CTkEntry(sheets_frame, width=200,
                                            placeholder_text="Provisioning Log")
        self._ws_name_entry.grid(row=2, column=1, padx=6, pady=5, sticky="w")

        btn_row = ctk.CTkFrame(sheets_frame, fg_color="transparent")
        btn_row.grid(row=3, column=0, columnspan=3, padx=14, pady=(8, 14), sticky="w")
        ctk.CTkButton(btn_row, text="Save Settings", width=130,
                       command=self._save_sheets_config).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(btn_row, text="Test Connection", width=140,
                       command=self._test_sheets_connection).grid(row=0, column=1)
        self._sheets_status = ctk.CTkLabel(btn_row, text="", text_color="gray",
                                            font=ctk.CTkFont(size=11))
        self._sheets_status.grid(row=0, column=2, padx=(14, 0))

        self._load_sheets_config()

        ctk.CTkLabel(wrap, text="Output",
                      font=ctk.CTkFont(size=13, weight="bold"), anchor="w").grid(
            row=3, column=0, columnspan=2, padx=10, pady=(0, 2), sticky="w")
        self._output = ctk.CTkTextbox(wrap, height=130, state="disabled",
                                       font=ctk.CTkFont(family="Courier New", size=11))
        self._output.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

    # ── Google Sheets helpers ──────────────────────────────────────

    def _load_sheets_config(self):
        try:
            import json, os
            from modules.paths import get_base_dir
            path = os.path.join(get_base_dir(), "config", "sheets_config.json")
            with open(path) as f:
                cfg = json.load(f)
            if cfg.get("sheet_id"):
                self._sheet_id_entry.insert(0, cfg["sheet_id"])
            ws = cfg.get("worksheet_name", "")
            if ws:
                self._ws_name_entry.insert(0, ws)
        except Exception:
            pass

    def _save_sheets_config(self):
        cfg = {
            "sheet_id":       sheets_sync._extract_sheet_id(self._sheet_id_entry.get().strip()),
            "worksheet_name": self._ws_name_entry.get().strip() or "Provisioning Log",
        }
        try:
            sheets_sync.save_config(cfg)
            self._sheets_status.configure(text="Saved.", text_color="#81C784")
        except Exception as e:
            self._sheets_status.configure(text=f"Save failed: {e}", text_color="#E57373")

    def _test_sheets_connection(self):
        self._save_sheets_config()
        self._sheets_status.configure(text="Testing...", text_color="gray")

        def task():
            ok, msg = sheets_sync.test_connection()

            def done():
                self._sheets_status.configure(
                    text=msg, text_color="#81C784" if ok else "#E57373")
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    # ── Windows Update ─────────────────────────────────────────────

    def _wu_check(self):
        self._wu_check_btn.configure(text="Checking...", state="disabled")
        self._wu_install_btn.configure(state="disabled")
        self._wu_count_label.configure(text="Scanning for pending updates...")
        self._wu_list_box.configure(state="normal")
        self._wu_list_box.delete("1.0", "end")
        self._wu_list_box.configure(state="disabled")

        cmd = (
            "$sess = New-Object -ComObject Microsoft.Update.Session; "
            "$srch = $sess.CreateUpdateSearcher(); "
            "try { "
            "  $res = $srch.Search('IsInstalled=0 and Type=''Software'' and IsHidden=0'); "
            "  Write-Host \"COUNT: $($res.Updates.Count)\"; "
            "  for ($i=0; $i -lt $res.Updates.Count; $i++) { "
            "    Write-Host \"UPDATE: $($res.Updates.Item($i).Title)\" "
            "  } "
            "} catch { Write-Host \"ERROR: $_\" }"
        )

        def task():
            rc, out = run_inline_powershell(cmd)

            def done():
                self._wu_check_btn.configure(text="Check for Updates", state="normal")
                lines = out.splitlines()
                count_line = next((l for l in lines if l.startswith("COUNT:")), "")
                try:
                    count = int(count_line.split(":", 1)[1].strip())
                except Exception:
                    count = 0
                self._wu_pending_count = count
                updates = [l.split(":", 1)[1].strip() for l in lines if l.startswith("UPDATE:")]
                errors  = [l for l in lines if l.startswith("ERROR:")]

                self._wu_list_box.configure(state="normal")
                self._wu_list_box.delete("1.0", "end")
                if errors:
                    self._wu_count_label.configure(text=f"Error: {errors[0]}", text_color="#E57373")
                    self._wu_list_box.insert("1.0", "\n".join(errors))
                elif count == 0:
                    self._wu_count_label.configure(text="Up to date — no pending updates.", text_color="#81C784")
                else:
                    self._wu_count_label.configure(text=f"{count} update(s) pending", text_color="#FFB74D")
                    self._wu_install_btn.configure(state="normal")
                    self._wu_list_box.insert("1.0", "\n".join(f"• {u}" for u in updates))
                self._wu_list_box.configure(state="disabled")

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _wu_install(self):
        if self._wu_pending_count == 0:
            return
        self._wu_install_btn.configure(state="disabled", text="Installing...")
        self._wu_check_btn.configure(state="disabled")
        self._wu_count_label.configure(text="Downloading and installing updates...", text_color="gray")

        cmd = (
            "$sess = New-Object -ComObject Microsoft.Update.Session; "
            "$srch = $sess.CreateUpdateSearcher(); "
            "$res = $srch.Search('IsInstalled=0 and Type=''Software'' and IsHidden=0'); "
            "if ($res.Updates.Count -eq 0) { Write-Host 'No pending updates.'; exit }; "
            "$coll = New-Object -ComObject Microsoft.Update.UpdateColl; "
            "foreach ($u in $res.Updates) { $coll.Add($u) | Out-Null }; "
            "$dl = $sess.CreateUpdateDownloader(); $dl.Updates = $coll; "
            "Write-Host 'Downloading updates...'; $dl.Download() | Out-Null; "
            "$inst = $sess.CreateUpdateInstaller(); $inst.Updates = $coll; "
            "Write-Host 'Installing updates...'; $r = $inst.Install(); "
            "Write-Host \"RESULT: $($r.ResultCode)\"; "
            "if ($r.RebootRequired) { Write-Host 'REBOOT_REQUIRED' }; "
            "Write-Host 'DONE'"
        )

        def task():
            rc, out = run_inline_powershell(cmd, callback=self._safe_append)

            def done():
                self._wu_install_btn.configure(state="normal", text="Install All")
                self._wu_check_btn.configure(state="normal")
                if "DONE" in out:
                    reboot = "REBOOT_REQUIRED" in out
                    result_line = next((l for l in out.splitlines() if l.startswith("RESULT:")), "")
                    success = "2" in result_line or "3" in result_line
                    msg = "Updates installed." + (" Reboot required." if reboot else "")
                    self._wu_count_label.configure(
                        text=msg,
                        text_color="#81C784" if success else "#FFB74D")
                    log(f"WU install: {msg}", "success" if success else "warn")
                    self._wu_pending_count = 0
                else:
                    self._wu_count_label.configure(text="Install may have failed — check Output.", text_color="#E57373")

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

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
