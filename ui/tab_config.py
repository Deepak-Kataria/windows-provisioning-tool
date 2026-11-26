"""Config: Windows features, repair fixes, Windows Update, legacy control panels and Google Sheets sync."""
import json
import os
import subprocess
import threading
import winreg

import customtkinter as ctk

from modules import sheets_sync
from modules.logger import log
from modules.paths import get_base_dir
from modules.reg_state import read_value
from modules.runner import run_inline_powershell
from ui import theme as T
from ui.widgets import LogDrawer, confirm_run, section_header, tip


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


# How long each fix takes, and what it interrupts (shown on the row and in the confirmation)
FIX_META = {
    "net_reset": ("~15 s", "Drops the network connection; a restart is recommended."),
    "ntp": ("~10 s", None),
    "sfc_dism": ("5-15 min", None),
    "wu_reset": ("~1 min", "Clears the update download cache; pending updates download again."),
    "winget_reinstall": ("~30 s", None),
}

# (label, command, Segoe MDL2 glyph)
PANELS = [
    ("Computer Management", "compmgmt.msc", ""),
    ("Control Panel", "control", ""),
    ("Network Connections", "ncpa.cpl", ""),
    ("Power Options", "powercfg.cpl", ""),
    ("Printers", "printmanagement.msc", ""),
    ("Region", "intl.cpl", ""),
    ("Sound", "mmsys.cpl", ""),
    ("System Properties", "sysdm.cpl", ""),
    ("Date & Time", "timedate.cpl", ""),
    ("System Restore", "rstrui.exe", ""),
]

_NET35_KEY = r"HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v3.5"
_NFS_KEY = r"SYSTEM\CurrentControlSet\Services\NfsClnt"


def _key_exists(path):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path))
        return True
    except OSError:
        return False


def feature_enabled(fid):
    """True / False for the features we can check quickly, None otherwise."""
    try:
        if fid == "dotnet":
            return read_value(_NET35_KEY, "Install") == 1
        if fid == "nfs":
            return _key_exists(_NFS_KEY)
        if fid == "reg_backup":
            r = subprocess.run(["schtasks", "/query", "/tn", "RegistryDailyBackup"], capture_output=True,
                               timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return None
    return None


class ConfigTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._feature_vars = {}
        self._feature_lbls = {}
        self._fix_btns = []
        self._wu_pending_count = 0
        self._build()
        self._refresh_features()

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1, uniform="col")
        self.grid_columnconfigure(1, weight=1, uniform="col")
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.grid_columnconfigure(0, weight=1)
        right = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)

        # Features
        hdr, col = section_header(left, "Windows features", height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text=f"{len(FEATURES)} available", font=T.mono(10), text_color=T.MUTED).grid(
            row=0, column=col, padx=4, sticky="w")
        self._run_feat_btn = ctk.CTkButton(hdr, text="Enable selected", width=120, height=22,
                                           font=T.ui(11), command=self._run_features)
        self._run_feat_btn.grid(row=0, column=col + 1, padx=8)
        tip(self._run_feat_btn, "Enable the ticked features (asks first)")
        box = ctk.CTkFrame(left, fg_color=T.PANEL, corner_radius=0)
        box.grid(row=1, column=0, sticky="ew")
        box.grid_columnconfigure(1, weight=1)
        for i, feat in enumerate(FEATURES):
            var = ctk.BooleanVar(value=False)
            var.trace_add("write", lambda *_: self._update_feature_btn())
            self._feature_vars[feat["id"]] = (var, feat)
            row = self._row(box, i)
            ctk.CTkCheckBox(row, text="", variable=var, width=20, checkbox_width=16,
                            checkbox_height=16).grid(row=0, column=0, rowspan=2, padx=(10, 6), pady=6, sticky="n")
            ctk.CTkLabel(row, text=feat["name"].replace(" - Enable", ""), font=T.ui(12, "bold"),
                         text_color=T.TEXT_BRIGHT, anchor="w", height=18).grid(row=0, column=1, sticky="w", pady=(5, 0))
            ctk.CTkLabel(row, text=feat["description"], font=T.ui(11), text_color=T.MUTED, anchor="w",
                         justify="left", wraplength=430, height=16).grid(row=1, column=1, sticky="w", pady=(0, 6))
            lbl = ctk.CTkLabel(row, text="…", font=T.mono(9, "bold"), text_color=T.DIM, width=70)
            lbl.grid(row=0, column=2, rowspan=2, padx=(6, 10))
            self._feature_lbls[feat["id"]] = lbl

        # Fixes
        hdr, col = section_header(left, "Repair fixes", height=30)
        hdr.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkLabel(hdr, text="one at a time · each asks first", font=T.mono(10), text_color=T.MUTED).grid(
            row=0, column=col, padx=4, sticky="w")
        box = ctk.CTkFrame(left, fg_color=T.PANEL, corner_radius=0)
        box.grid(row=3, column=0, sticky="ew")
        box.grid_columnconfigure(0, weight=1)
        for i, fix in enumerate(FIXES):
            took, disrupt = FIX_META.get(fix["id"], ("", None))
            row = self._row(box, i)
            row.grid_columnconfigure(0, weight=1)
            name = ctk.CTkFrame(row, fg_color="transparent")
            name.grid(row=0, column=0, sticky="w", padx=12, pady=(5, 0))
            ctk.CTkLabel(name, text=fix["name"].replace(" - Run", "").replace(" - Reset", " reset")
                         .replace(" - Enable", "").replace(" - Reinstall", " reinstall"),
                         font=T.ui(12, "bold"), text_color=T.TEXT_BRIGHT, height=18).grid(row=0, column=0)
            if disrupt:
                tag = ctk.CTkLabel(name, text=" DISRUPTIVE ", font=T.mono(8, "bold"), text_color=T.WARN,
                                   fg_color=T.PANEL_3, corner_radius=2, height=14)
                tag.grid(row=0, column=1, padx=6)
                tip(tag, disrupt)
            ctk.CTkLabel(row, text=fix["description"], font=T.ui(11), text_color=T.MUTED, anchor="w",
                         justify="left", wraplength=400, height=16).grid(row=1, column=0, sticky="w",
                                                                          padx=12, pady=(0, 6))
            ctk.CTkLabel(row, text=took, font=T.mono(10), text_color=T.MUTED, width=64).grid(
                row=0, column=1, rowspan=2)
            btn = T.outline_button(row, text="Run", width=56, height=24, command=lambda f=fix: self._run_fix(f))
            btn.grid(row=0, column=2, rowspan=2, padx=(4, 10))
            self._fix_btns.append(btn)

        # Windows Update
        hdr, col = section_header(left, "Windows Update", height=30)
        hdr.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self._wu_chip = ctk.CTkLabel(hdr, text="NOT CHECKED", font=T.mono(9, "bold"), text_color=T.DIM)
        self._wu_chip.grid(row=0, column=col, padx=4, sticky="w")
        self._wu_install_btn = ctk.CTkButton(hdr, text="Install all", width=90, height=22, font=T.ui(11),
                                             state="disabled", command=self._wu_install)
        self._wu_install_btn.grid(row=0, column=col + 1, padx=(8, 4))
        tip(self._wu_install_btn, "Download and install every pending update (asks first)")
        self._wu_check_btn = T.outline_button(hdr, text="Check", width=70, height=22, font=T.ui(11),
                                              command=self._wu_check)
        self._wu_check_btn.grid(row=0, column=col + 2, padx=(0, 8))
        tip(self._wu_check_btn, "Search Windows Update for pending software updates")
        card = ctk.CTkFrame(left, fg_color=T.PANEL, corner_radius=0)
        card.grid(row=5, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        self._wu_count_label = ctk.CTkLabel(card, text="Press Check to list pending updates.",
                                            font=T.ui(11), text_color=T.MUTED, anchor="w")
        self._wu_count_label.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")
        self._wu_list_box = ctk.CTkTextbox(card, height=120, state="disabled", font=T.mono(11),
                                           text_color=T.TEXT, fg_color=T.PANEL_2, corner_radius=0)
        self._wu_list_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")

        # Legacy panels
        hdr, col = section_header(right, "Legacy Windows panels", height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text="open directly", font=T.mono(10), text_color=T.MUTED).grid(
            row=0, column=col, padx=4, sticky="w")
        grid = ctk.CTkFrame(right, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="panel")
        for k, (label, target, glyph) in enumerate(PANELS):
            self._panel_tile(grid, k, label, target, glyph)

        # Google Sheets sync
        hdr, col = section_header(right, "Google Sheets sync", height=30)
        hdr.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self._sheets_chip = ctk.CTkLabel(hdr, text="", font=T.mono(9, "bold"), text_color=T.DIM)
        self._sheets_chip.grid(row=0, column=col + 1, padx=10, sticky="e")
        card = ctk.CTkFrame(right, fg_color=T.PANEL, corner_radius=0)
        card.grid(row=3, column=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text="SHEET ID", font=T.mono(10), text_color=T.MUTED, width=90, anchor="w").grid(
            row=0, column=0, padx=(12, 6), pady=(12, 4), sticky="w")
        self._sheet_id_entry = ctk.CTkEntry(card, height=28, font=T.mono(11),
                                            placeholder_text="Paste the sheet ID or its URL")
        self._sheet_id_entry.grid(row=0, column=1, padx=(0, 12), pady=(12, 4), sticky="ew")
        ctk.CTkLabel(card, text="WORKSHEET", font=T.mono(10), text_color=T.MUTED, anchor="w").grid(
            row=1, column=0, padx=(12, 6), pady=4, sticky="w")
        self._ws_name_entry = ctk.CTkEntry(card, height=28, placeholder_text="Provisioning Log")
        self._ws_name_entry.grid(row=1, column=1, padx=(0, 12), pady=4, sticky="ew")
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=2, column=0, columnspan=2, padx=12, pady=(6, 12), sticky="ew")
        btns.grid_columnconfigure(0, weight=1)
        self._sheets_status = ctk.CTkLabel(btns, text="", text_color=T.MUTED, font=T.ui(11), anchor="w")
        self._sheets_status.grid(row=0, column=0, sticky="w")
        T.outline_button(btns, text="Test connection", width=120, height=28,
                         command=self._test_sheets_connection).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(btns, text="Save", width=80, height=28, command=self._save_sheets_config).grid(
            row=0, column=2)
        self._load_sheets_config()

        # Output
        self._log = LogDrawer(self, height=160)
        self._log.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._log.append("Ready.")
        self._update_feature_btn()

    @staticmethod
    def _row(parent, i):
        row = ctk.CTkFrame(parent, fg_color=T.PANEL if i % 2 == 0 else T.PANEL_2, corner_radius=0)
        row.grid(row=i, column=0, columnspan=3, sticky="ew")
        row.grid_columnconfigure(1, weight=1)
        return row

    def _panel_tile(self, grid, k, label, target, glyph):
        tile = ctk.CTkFrame(grid, fg_color=T.PANEL, corner_radius=3, border_width=1,
                            border_color=T.BORDER, height=40, cursor="hand2")
        tile.grid(row=k // 2, column=k % 2, sticky="ew", padx=(0 if k % 2 == 0 else 3, 3 if k % 2 == 0 else 0),
                  pady=3)
        tile.grid_propagate(False)
        tile.grid_rowconfigure(0, weight=1)
        tile.grid_columnconfigure(1, weight=1)
        icon = ctk.CTkLabel(tile, text=glyph, font=T.icon(15), text_color=T.ACCENT, width=24)
        icon.grid(row=0, column=0, padx=(12, 8))
        text = ctk.CTkLabel(tile, text=label, font=T.ui(12), anchor="w")
        text.grid(row=0, column=1, sticky="w")
        arrow = ctk.CTkLabel(tile, text="↗", font=T.ui(11), text_color=T.DIM)
        arrow.grid(row=0, column=2, padx=10)
        for w in (tile, icon, text, arrow):
            w.bind("<Button-1>", lambda e, t=target: self._open_panel(t))
            w.bind("<Enter>", lambda e: (tile.configure(border_color=T.ACCENT), arrow.configure(text_color=T.ACCENT)))
            w.bind("<Leave>", lambda e: (tile.configure(border_color=T.BORDER), arrow.configure(text_color=T.DIM)))
        tip(tile, f"Open {label} ({target})")

    # ── Feature state ──────────────────────────────────────────────

    def _refresh_features(self):
        def task():
            states = {fid: feature_enabled(fid) for fid in self._feature_vars}
            try:
                self.after(0, self._apply_features, states)
            except RuntimeError:
                pass
        threading.Thread(target=task, daemon=True).start()

    def _apply_features(self, states):
        if not self.winfo_exists():
            return
        for fid, on in states.items():
            text, color = ("ENABLED", T.OK) if on else ("NOT ENABLED", T.DIM) if on is False else ("—", T.DIM)
            self._feature_lbls[fid].configure(text=text, text_color=color)

    def _update_feature_btn(self):
        if not hasattr(self, "_run_feat_btn"):
            return
        n = sum(1 for var, _ in self._feature_vars.values() if var.get())
        self._run_feat_btn.configure(text=f"Enable {n} selected" if n else "Enable selected",
                                     state="normal" if n and not self._running else "disabled")

    def on_show(self):
        if not self._running:
            self._refresh_features()

    # ── Google Sheets helpers ──────────────────────────────────────

    def _set_sheets_chip(self, text, color):
        self._sheets_chip.configure(text=text, text_color=color)

    def _load_sheets_config(self):
        try:
            path = os.path.join(get_base_dir(), "config", "sheets_config.json")
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            if cfg.get("sheet_id"):
                self._sheet_id_entry.insert(0, cfg["sheet_id"])
            if cfg.get("worksheet_name"):
                self._ws_name_entry.insert(0, cfg["worksheet_name"])
        except Exception:
            pass
        configured = bool(self._sheet_id_entry.get().strip())
        self._set_sheets_chip("NOT TESTED" if configured else "NOT SET UP", T.MUTED if configured else T.DIM)

    def _save_sheets_config(self):
        cfg = {
            "sheet_id": sheets_sync._extract_sheet_id(self._sheet_id_entry.get().strip()),
            "worksheet_name": self._ws_name_entry.get().strip() or "Provisioning Log",
        }
        try:
            sheets_sync.save_config(cfg)
            self._sheets_status.configure(text="Saved.", text_color=T.OK)
            return True
        except Exception as e:
            self._sheets_status.configure(text=f"Save failed: {e}", text_color=T.FAIL)
            return False

    def _test_sheets_connection(self):
        if not self._save_sheets_config():
            return
        self._sheets_status.configure(text="Testing…", text_color=T.MUTED)
        self._set_sheets_chip("TESTING…", T.MUTED)

        def task():
            ok, msg = sheets_sync.test_connection()

            def done():
                self._sheets_status.configure(text=msg, text_color=T.OK if ok else T.FAIL)
                self._set_sheets_chip("CONNECTED" if ok else "FAILED", T.OK if ok else T.FAIL)
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    # ── Windows Update ─────────────────────────────────────────────

    _WU_SEARCH = "IsInstalled=0 and Type=''Software'' and IsHidden=0"

    def _wu_set(self, chip, color, text=None):
        self._wu_chip.configure(text=chip, text_color=color)
        if text is not None:
            self._wu_count_label.configure(text=text, text_color=color if color != T.DIM else T.MUTED)

    def _wu_check(self):
        self._wu_check_btn.configure(text="Checking…", state="disabled")
        self._wu_install_btn.configure(state="disabled")
        self._wu_set("SCANNING…", T.MUTED, "Searching for pending updates (can take a minute)…")
        self._wu_list_box.configure(state="normal")
        self._wu_list_box.delete("1.0", "end")
        self._wu_list_box.configure(state="disabled")

        cmd = (
            "$sess = New-Object -ComObject Microsoft.Update.Session; "
            "$srch = $sess.CreateUpdateSearcher(); "
            "try { "
            f"  $res = $srch.Search('{self._WU_SEARCH}'); "
            "  Write-Host \"COUNT: $($res.Updates.Count)\"; "
            "  for ($i=0; $i -lt $res.Updates.Count; $i++) { "
            "    Write-Host \"UPDATE: $($res.Updates.Item($i).Title)\" "
            "  } "
            "} catch { Write-Host \"ERROR: $_\" }"
        )

        def task():
            rc, out = run_inline_powershell(cmd)

            def done():
                if not self.winfo_exists():
                    return
                self._wu_check_btn.configure(text="Check", state="normal")
                lines = out.splitlines()
                count_line = next((l for l in lines if l.startswith("COUNT:")), "")
                try:
                    count = int(count_line.split(":", 1)[1].strip())
                except (IndexError, ValueError):
                    count = 0
                updates = [l.split(":", 1)[1].strip() for l in lines if l.startswith("UPDATE:")]
                errors = [l for l in lines if l.startswith("ERROR:")]
                self._wu_pending_count = 0 if errors else count

                self._wu_list_box.configure(state="normal")
                self._wu_list_box.delete("1.0", "end")
                if errors:
                    self._wu_set("ERROR", T.FAIL, errors[0])
                    self._wu_list_box.insert("1.0", "\n".join(errors))
                elif count == 0:
                    self._wu_set("UP TO DATE", T.OK, "No pending updates.")
                else:
                    self._wu_set(f"{count} PENDING", T.WARN, f"{count} update(s) pending")
                    self._wu_install_btn.configure(state="normal")
                    self._wu_list_box.insert("1.0", "\n".join(f"• {u}" for u in updates))
                self._wu_list_box.configure(state="disabled")
                log(f"Config: WU check found {self._wu_pending_count} pending")

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _wu_install(self):
        if self._wu_pending_count == 0 or self._running:
            return
        titles = self._wu_list_box.get("1.0", "end").strip().splitlines()
        if not confirm_run(self, "Install updates?",
                           f"Download and install {self._wu_pending_count} pending update(s):",
                           [t.lstrip("• ") for t in titles] or ["All pending updates"],
                           action_text=f"Install {self._wu_pending_count}",
                           footer="Can take a long time; some updates need a restart."):
            return
        self._set_running(True)
        self._wu_install_btn.configure(state="disabled", text="Installing…")
        self._wu_check_btn.configure(state="disabled")
        self._wu_set("INSTALLING…", T.MUTED, "Downloading and installing updates…")
        if not self._log._expanded:
            self._log.toggle()
        self._append("\n>>> Windows Update - install all")
        log("Config: WU install started")

        cmd = (
            "$sess = New-Object -ComObject Microsoft.Update.Session; "
            "$srch = $sess.CreateUpdateSearcher(); "
            f"$res = $srch.Search('{self._WU_SEARCH}'); "
            "if ($res.Updates.Count -eq 0) { Write-Host 'No pending updates.'; Write-Host 'DONE'; exit }; "
            "$coll = New-Object -ComObject Microsoft.Update.UpdateColl; "
            "foreach ($u in $res.Updates) { if (-not $u.EulaAccepted) { $u.AcceptEula() }; $coll.Add($u) | Out-Null }; "
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
                if not self.winfo_exists():
                    return
                self._set_running(False)
                self._wu_install_btn.configure(text="Install all")
                self._wu_check_btn.configure(state="normal")
                if "DONE" in out:
                    reboot = "REBOOT_REQUIRED" in out
                    result_line = next((l for l in out.splitlines() if l.startswith("RESULT:")), "")
                    try:
                        code = int(result_line.split(":", 1)[1].strip())
                    except (IndexError, ValueError):
                        code = 2 if "No pending updates." in out else -1
                    # OperationResultCode: 2 = succeeded, 3 = succeeded with errors
                    success = code in (2, 3)
                    msg = ("Updates installed." if code == 2 else
                           "Installed with some errors." if code == 3 else
                           f"Install finished with result code {code}.")
                    if reboot:
                        msg += " Restart required."
                    self._wu_set("RESTART NEEDED" if reboot else ("DONE" if success else "CHECK LOG"),
                                 T.WARN if reboot or code == 3 else (T.OK if success else T.FAIL), msg)
                    log(f"WU install: {msg}", "success" if success else "warning")
                    self._wu_pending_count = 0
                else:
                    self._wu_set("FAILED", T.FAIL, "Install may have failed; check the output log.")
                    self._wu_install_btn.configure(state="normal")

            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    # ── Helpers ────────────────────────────────────────────────────

    def _append(self, text):
        self._log.append(text)

    def _safe_append(self, text):
        self.after(0, self._append, text)

    def _set_running(self, running):
        self._running = running
        for b in self._fix_btns:
            b.configure(state="disabled" if running else "normal")
        self._update_feature_btn()

    def _open_panel(self, target):
        try:
            subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=subprocess.CREATE_NO_WINDOW)
            log(f"Config: opened panel {target}")
            self._append(f"Opened {target}")
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
        if not confirm_run(self, "Enable features?", f"These {len(selected)} feature(s) will be enabled:",
                           [f["name"].replace(" - Enable", "") for _, f in selected],
                           action_text=f"Enable {len(selected)}"):
            return
        self._set_running(True)
        if not self._log._expanded:
            self._log.toggle()
        self._append(f"Running {len(selected)} feature(s)...")
        log(f"Config: features {[f for f, _ in selected]}")

        def task():
            for fid, feat in selected:
                self._safe_append(f"\n>>> {feat['name']}")
                rc, out = run_inline_powershell(feat["cmd"], callback=self._safe_append)
                self._safe_append(f"  {'OK' if rc == 0 else 'FAILED'} (exit {rc})")
                log(f"Config feature {fid} rc={rc}")

            def finish():
                self._set_running(False)
                for var, _ in self._feature_vars.values():
                    var.set(False)
                self._append("\nDone.")
                self._refresh_features()
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── Fix runner ─────────────────────────────────────────────────

    def _run_fix(self, fix):
        if self._running:
            return
        took, disrupt = FIX_META.get(fix["id"], ("", None))
        if not confirm_run(self, "Run fix?", fix["description"],
                           [(fix["name"] + (f"  ({took})" if took else ""), bool(disrupt))],
                           action_text="Run fix", danger=bool(disrupt), footer=disrupt):
            return
        self._set_running(True)
        if not self._log._expanded:
            self._log.toggle()
        self._append(f"\n>>> {fix['name']}")
        log(f"Config: fix {fix['id']}")

        def task():
            rc, out = run_inline_powershell(fix["cmd"], callback=self._safe_append)
            self._safe_append(f"  {'OK' if rc == 0 else 'FAILED'} (exit {rc})")
            log(f"Config fix {fix['id']} rc={rc}")
            self.after(0, self._set_running, False)

        threading.Thread(target=task, daemon=True).start()
