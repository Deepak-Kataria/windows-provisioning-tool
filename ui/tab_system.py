import csv
import customtkinter as ctk

from ui import theme as T
import json
import re
import os
import threading
import tkinter.messagebox as msgbox
import tkinter.filedialog as filedialog
from modules.runner import run_powershell, run_powershell_with_secret
from modules.logger import log
from modules import sheets_sync
from modules.reg_state import read_value
from ui.widgets import LogDrawer, section_header, tile_row, tip

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


_TCPIP = r"HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"


_CPU_MODEL = re.compile(r"(i[3579]-\w+|Core Ultra \d+ \w+|Ryzen \d+ \w+|Xeon\S* [\w-]+|"
                        r"Celeron\S* \w+|Pentium\S* \w+|Snapdragon\S* [\w-]+)", re.I)


def _domain_name():
    return read_value(_TCPIP, "Domain") or ""


def _domain_joined():
    """True when this PC is a member of a domain (registry; no PowerShell)."""
    return bool(_domain_name())


def _parse_system_info(out: str) -> dict:
    """Parse the KEY: value lines from get_system_info.ps1 output."""
    data = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    return data


class SystemTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.device_type = ctk.StringVar(value="Desktop")
        self.local_rename_only = ctk.BooleanVar(value=False)
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "domain_config.json")) as f:
            self.domain_config = json.load(f)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        tiles_host = ctk.CTkFrame(self, fg_color="transparent")
        tiles_host.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tiles_host.grid_columnconfigure(0, weight=1)
        row, self._tiles = tile_row(tiles_host, [
            ("Computer", os.environ.get("COMPUTERNAME", "?"), T.ACCENT,
             "domain-joined" if _domain_joined() else "workgroup"),
            ("Model", "…", T.TEXT_BRIGHT, "reading hardware…"),
            ("CPU", "…", T.TEXT_BRIGHT, ""),
            ("RAM", "…", T.TEXT_BRIGHT, ""),
            ("Disk", "…", T.TEXT_BRIGHT, ""),
            ("Serial", "…", T.TEXT_BRIGHT, ""),
        ])
        row.grid(row=0, column=0, sticky="ew")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure((0, 1), weight=1, uniform="col")

        left = ctk.CTkFrame(scroll, fg_color="transparent")
        left.grid(row=0, column=0, sticky="new", padx=(0, 6))
        left.grid_columnconfigure(0, weight=1)
        right = ctk.CTkFrame(scroll, fg_color="transparent")
        right.grid(row=0, column=1, sticky="new", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)

        # ── Rename ───────────────────────────────────────────────────
        hdr, col = section_header(left, "Rename computer", height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        seg = ctk.CTkSegmentedButton(hdr, values=["Desktop", "Laptop"], variable=self.device_type,
                                     command=lambda v: self._update_preview(), height=22)
        seg.grid(row=0, column=col + 1, padx=8)
        tip(seg, "DT or LT in the generated name")
        card = self._card(left, 1)
        self.prefix_entry = self._field(card, 0, "PREFIX", "e.g. ACME", width=160)
        prefix = self.domain_config.get("company_prefix", "")
        if prefix:
            self.prefix_entry.insert(0, prefix)
        self.prefix_entry.bind("<KeyRelease>", lambda e: self._update_preview())

        self._label(card, 1, "NUMBER / ID")
        number_row = ctk.CTkFrame(card, fg_color="transparent")
        number_row.grid(row=1, column=1, sticky="w", pady=4, padx=(0, 12))
        self.number_entry = ctk.CTkEntry(number_row, width=160, height=28, placeholder_text="e.g. 001")
        self.number_entry.grid(row=0, column=0)
        self.number_entry.bind("<KeyRelease>", lambda e: self._update_preview())
        self._autogen_btn = T.outline_button(number_row, text="From hardware", width=120, height=28,
                                             command=self._auto_generate_name)
        self._autogen_btn.grid(row=0, column=1, padx=(8, 0))
        tip(self._autogen_btn, "Build a short ID from this PC's hardware")

        self._label(card, 2, "NEW NAME")
        self.preview_label = ctk.CTkLabel(card, text="---", font=T.mono(22, "bold"), text_color=T.ACCENT)
        self.preview_label.grid(row=2, column=1, sticky="w", pady=(6, 6))

        joined = _domain_joined()
        self._label(card, 3, "DOMAIN")
        dom_row = ctk.CTkFrame(card, fg_color="transparent")
        dom_row.grid(row=3, column=1, sticky="w", pady=4)
        ctk.CTkLabel(dom_row, text=(f"{_domain_name()} · credentials needed" if joined
                                    else "not joined · local rename only"),
                     font=T.mono(11), text_color=T.TEXT if joined else T.MUTED).grid(row=0, column=0)
        self._creds = ctk.CTkFrame(card, fg_color="transparent")
        self._creds.grid_columnconfigure(1, weight=1)
        self.rename_user_entry = self._field(self._creds, 0, "", "DOMAIN\\username")
        self.rename_pass_entry = self._field(self._creds, 1, "", "password", secret=True)
        self._creds_btn = T.outline_button(dom_row, text="", width=120, height=22, font=T.ui(11),
                                           command=self._toggle_creds)
        self._creds_btn.grid(row=0, column=1, padx=(10, 0))
        self._creds_shown = not joined
        self._toggle_creds()

        foot = ctk.CTkFrame(card, fg_color="transparent")
        foot.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 12))
        foot.grid_columnconfigure(1, weight=1)
        local_only_cb = ctk.CTkCheckBox(foot, text="Local rename only (skip the AD update)",
                                        variable=self.local_rename_only, font=T.ui(11), text_color=T.MUTED,
                                        checkbox_width=16, checkbox_height=16)
        local_only_cb.grid(row=0, column=0, sticky="w")
        tip(local_only_cb, "Use when the computer account is missing in the domain")
        ctk.CTkButton(foot, text="Apply rename", width=130, command=self._apply_rename).grid(
            row=0, column=2, sticky="e")

        # ── Join domain ──────────────────────────────────────────────
        hdr, _ = section_header(left, "Join domain", height=30)
        hdr.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        card = self._card(left, 3)
        self.domain_name_entry = self._field(card, 0, "DOMAIN", "e.g. company.local")
        if self.domain_config.get("domain_name"):
            self.domain_name_entry.insert(0, self.domain_config["domain_name"])
        self.dc_ip_entry = self._field(card, 1, "DC SERVER IP", "optional, e.g. 192.168.1.10")
        if self.domain_config.get("dns_server"):
            self.dc_ip_entry.insert(0, self.domain_config["dns_server"])
        self._label(card, 2, "OU PATH")
        ou_row = ctk.CTkFrame(card, fg_color="transparent")
        ou_row.grid(row=2, column=1, sticky="ew", pady=4, padx=(0, 12))
        ou_row.grid_columnconfigure(0, weight=1)
        self.ou_entry = ctk.CTkEntry(ou_row, height=28, font=T.mono(11),
                                     placeholder_text="optional, e.g. OU=Computers,DC=company,DC=local")
        if self.domain_config.get("ou_path"):
            self.ou_entry.insert(0, self.domain_config["ou_path"])
        self.ou_entry.grid(row=0, column=0, sticky="ew")
        self._browse_btn = T.outline_button(ou_row, text="Browse…", width=80, height=28, command=self._browse_ous)
        self._browse_btn.grid(row=0, column=1, padx=(8, 0))
        self.join_user_entry = self._field(card, 3, "ADMIN USER", "domain admin username")
        self.join_pass_entry = self._field(card, 4, "PASSWORD", "domain admin password", secret=True)
        ctk.CTkButton(card, text="Join domain", width=130, command=self._join_domain).grid(
            row=5, column=1, sticky="e", padx=12, pady=(6, 12))

        # ── Operator & system details ────────────────────────────────
        hdr, col = section_header(right, "Operator & system details", height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text="for the provisioning log", font=T.mono(10), text_color=T.MUTED).grid(
            row=0, column=col, padx=4, sticky="w")
        self._fetch_details_btn = T.outline_button(hdr, text="Refresh", width=80, height=22, font=T.ui(11),
                                                   command=self._fetch_system_details)
        self._fetch_details_btn.grid(row=0, column=col + 1, padx=8)
        tip(self._fetch_details_btn, "Read the hardware and operator details again")
        card = self._card(right, 1)
        self.sys_computer_name_entry = self._field(card, 0, "COMPUTER", "e.g. RCS-DT-7FA78902", mono=True)
        self.sys_computer_name_entry.insert(0, os.environ.get("COMPUTERNAME", ""))
        self.op_user_entry = self._field(card, 1, "OPERATOR", "Windows username")
        self._label(card, 2, "EMAIL(S)", top=True)
        self.op_email_box = ctk.CTkTextbox(card, height=52, font=T.ui(12), text_color=T.TEXT_BRIGHT)
        self.op_email_box.grid(row=2, column=1, sticky="ew", pady=4, padx=(0, 12))
        self.sys_brand_entry = self._field(card, 3, "BRAND", "e.g. Dell, HP, Lenovo")
        self.sys_model_entry = self._field(card, 4, "MODEL", "e.g. Dell Latitude 5420")
        self.sys_serial_entry = self._field(card, 5, "SERIAL", "BIOS serial number", mono=True)
        self.sys_cpu_entry = self._field(card, 6, "PROCESSOR", "CPU model")
        self.sys_ram_entry = self._field(card, 7, "RAM", "total RAM", mono=True)
        self.sys_disk_entry = self._field(card, 8, "DISK", "primary disk", mono=True)
        self.sys_display_entry = self._field(card, 9, "DISPLAY / GPU", "GPU / display adapter")
        self.sys_winver_entry = self._field(card, 10, "WINDOWS", "e.g. Windows 11 Pro")
        self.sys_lastupdate_entry = self._field(card, 11, "LAST UPDATE", "date of last installed update", mono=True)
        self._label(card, 12, "MONITORS", top=True)
        self.sys_monitor_box = ctk.CTkTextbox(card, height=52, font=T.ui(12), text_color=T.TEXT_BRIGHT)
        self.sys_monitor_box.grid(row=12, column=1, sticky="ew", pady=4, padx=(0, 12))
        act = ctk.CTkFrame(card, fg_color="transparent")
        act.grid(row=13, column=1, sticky="e", padx=12, pady=(6, 12))
        self._export_csv_btn = T.outline_button(act, text="Export CSV", width=110,
                                                command=self._export_csv)
        self._export_csv_btn.grid(row=0, column=0, padx=(0, 8))
        tip(self._export_csv_btn, "Save these details to a .csv file")
        self._sync_sheet_btn = ctk.CTkButton(act, text="Send to Google Sheet", width=170,
                                             command=self._sync_to_sheet)
        self._sync_sheet_btn.grid(row=0, column=1)

        self._log = LogDrawer(self)
        self._log.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.after(300, self._fetch_system_details)

    # ── Layout helpers ───────────────────────────────────────────────

    @staticmethod
    def _card(parent, row):
        card = ctk.CTkFrame(parent, fg_color=T.PANEL, corner_radius=0)
        card.grid(row=row, column=0, sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        return card

    @staticmethod
    def _label(card, row, text, top=False):
        ctk.CTkLabel(card, text=text, font=T.mono(10), text_color=T.MUTED, width=110, anchor="w").grid(
            row=row, column=0, sticky="nw" if top else "w", padx=(12, 6), pady=(10 if top else 4, 4))

    def _field(self, card, row, label, placeholder, secret=False, mono=False, width=None):
        if label:
            self._label(card, row, label)
        kw = {"width": width} if width else {}
        entry = ctk.CTkEntry(card, height=28, placeholder_text=placeholder, show="*" if secret else "",
                             font=T.mono(11) if mono else T.ui(12), **kw)
        entry.grid(row=row, column=1, sticky="w" if width else "ew", pady=4, padx=(0, 12))
        return entry

    def _toggle_creds(self):
        self._creds_shown = not self._creds_shown
        if self._creds_shown:
            self._creds.grid(row=4, column=0, columnspan=2, sticky="ew")
        else:
            self._creds.grid_remove()
        self._creds_btn.configure(text="Hide credentials" if self._creds_shown else "Enter credentials")

    def _update_tiles(self, data):
        def short(v, n=16):
            v = (v or "").strip()
            return v if len(v) <= n else v[:n - 1] + "…"
        model = data.get("MODEL", "")
        self._tiles["Model"].set(short(model) or "?", T.TEXT_BRIGHT, data.get("BRAND", ""))
        cpu = data.get("PROCESSOR", "")
        m = _CPU_MODEL.search(cpu.replace("(TM)", "").replace("(R)", ""))
        cpu_short = m.group(0).strip() if m else cpu.split("@")[0].replace("(R)", "").replace("(TM)", "").strip()
        speed = cpu.split("@")[-1].strip() if "@" in cpu else ""
        self._tiles["CPU"].set(short(cpu_short) or "?", T.TEXT_BRIGHT, speed or short(cpu, 30))
        self._tiles["RAM"].set(short(data.get("RAM", "")) or "?", T.TEXT_BRIGHT, "installed memory")
        self._tiles["Disk"].set(short(data.get("DISK", ""), 12) or "?", T.TEXT_BRIGHT, "primary disk")
        self._tiles["Serial"].set(short(data.get("SERIAL", "")) or "?", T.TEXT_BRIGHT,
                                  short(data.get("WIN_VERSION", ""), 30))

    def _fetch_system_details(self):
        self._fetch_details_btn.configure(text="Reading…", state="disabled")

        def task():
            rc, out = run_powershell("get_system_info.ps1", [], callback=None)

            def apply():
                self._fetch_details_btn.configure(text="Refresh", state="normal")
                if rc != 0:
                    first_err = next((l for l in out.splitlines() if l.startswith("ERROR")), out)
                    self._append_output(f"Fetch details failed: {first_err}")
                    return
                self._apply_fetched_details_to_ui(_parse_system_info(out))
                self._append_output("System details fetched.")

            self.after(0, apply)

        threading.Thread(target=task, daemon=True).start()

    def _apply_fetched_details_to_ui(self, data: dict):
        """Populate the Operator & System Details fields from get_system_info.ps1 output."""
        def _set(entry, key):
            val = data.get(key, "")
            entry.delete(0, "end")
            if val:
                entry.insert(0, val)

        def _set_box(box, text):
            box.configure(state="normal")
            box.delete("1.0", "end")
            if text:
                box.insert("1.0", text)

        _set(self.op_user_entry,        "USER")
        _set(self.sys_brand_entry,      "BRAND")
        _set(self.sys_model_entry,      "MODEL")
        _set(self.sys_serial_entry,     "SERIAL")
        _set(self.sys_cpu_entry,        "PROCESSOR")
        _set(self.sys_ram_entry,        "RAM")
        _set(self.sys_disk_entry,       "DISK")
        _set(self.sys_display_entry,    "DISPLAY")
        _set(self.sys_winver_entry,     "WIN_VERSION")
        _set(self.sys_lastupdate_entry, "WIN_LAST_UPDATE")

        # Emails — one per line
        emails_raw = data.get("EMAILS", "")
        emails_text = "\n".join(e for e in emails_raw.split("|") if e) if emails_raw else ""
        _set_box(self.op_email_box, emails_text)

        # Monitors — numbered, one per line
        count = int(data.get("MONITOR_COUNT", "0") or "0")
        mon_lines = []
        for i in range(1, count + 1):
            val = data.get(f"MONITOR_{i}", "")
            if val:
                mon_lines.append(f"Monitor {i}: {val}")
        _set_box(self.sys_monitor_box, "\n".join(mon_lines) if mon_lines else "N/A")
        self._update_tiles(data)

    def _auto_generate_name(self):
        self._autogen_btn.configure(text="Reading…", state="disabled")

        def task():
            rc, out = run_powershell("get_hardware_id.ps1", [], callback=None)
            hw_id = out.strip().splitlines()[-1].strip() if out.strip() else ""

            def apply():
                self._autogen_btn.configure(text="From hardware", state="normal")
                if rc != 0 or hw_id.startswith("ERROR") or not hw_id:
                    msg = hw_id if hw_id else "Unknown error reading hardware ID."
                    self._append_output(f"Auto-generate failed: {msg}")
                    msgbox.showerror("Hardware ID Error", msg)
                    return
                self.number_entry.delete(0, "end")
                self.number_entry.insert(0, hw_id)
                self._update_preview()
                self._append_output(f"Hardware ID generated: {hw_id}")

            self.after(0, apply)

        threading.Thread(target=task, daemon=True).start()

    def _update_preview(self):
        prefix = self.prefix_entry.get().strip().upper()
        number = self.number_entry.get().strip().zfill(3)
        dtype = "DT" if self.device_type.get() == "Desktop" else "LT"
        if prefix and number:
            self.preview_label.configure(text=f"{prefix}-{dtype}-{number}")
        else:
            self.preview_label.configure(text="---")

    def _append_output(self, text):
        self._log.append(text)

    def _safe_append(self, text):
        self.after(0, self._append_output, text)

    def _set_computer_name_field(self, name: str):
        """Fill the Computer Name field after a successful rename (UI only — no sheet sync)."""
        self.sys_computer_name_entry.delete(0, "end")
        self.sys_computer_name_entry.insert(0, name)

    def _fill_domain_credential_fields(self, user: str):
        """Persist the domain username used for a successful credential-prompt rename."""
        self.rename_user_entry.delete(0, "end")
        self.rename_user_entry.insert(0, user)

    def _ask_domain_credentials_blocking(self):
        """Show a modal credential dialog from the background rename thread.

        Runs the dialog on the main thread via .after() and blocks the calling
        thread until it's closed. Returns (username, password) or None if cancelled.
        """
        result = {}
        event = threading.Event()

        def show():
            dlg = ctk.CTkToplevel(self)
            dlg.title("Domain Credentials Required")
            dlg.resizable(False, False)
            dlg.grab_set()
            dlg.lift()
            dlg.attributes("-topmost", True)

            ctk.CTkLabel(dlg, text="Domain Admin Credentials Required",
                         font=ctk.CTkFont(size=15, weight="bold")).pack(padx=30, pady=(24, 6))
            ctk.CTkLabel(dlg, text="This computer is domain-joined. Renaming it requires\n"
                                    "an account with permission to update the AD computer object.",
                         text_color=T.MUTED, justify="center").pack(padx=30, pady=(0, 16))

            user_entry = ctk.CTkEntry(dlg, width=260, placeholder_text="DOMAIN\\username")
            user_entry.pack(padx=30, pady=(0, 8))
            pass_entry = ctk.CTkEntry(dlg, width=260, show="*", placeholder_text="Password")
            pass_entry.pack(padx=30, pady=(0, 16))
            user_entry.focus_set()

            btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
            btn_row.pack(padx=30, pady=(0, 24))

            def submit():
                u = user_entry.get().strip()
                p = pass_entry.get()
                if u and p:
                    result["creds"] = (u, p)
                dlg.destroy()

            def cancel():
                dlg.destroy()

            ctk.CTkButton(btn_row, text="Cancel", width=110,
                          fg_color="#555", hover_color="#444",
                          command=cancel).grid(row=0, column=0, padx=(0, 12))
            ctk.CTkButton(btn_row, text="Continue", width=110,
                          command=submit).grid(row=0, column=1)

            pass_entry.bind("<Return>", lambda e: submit())
            dlg.protocol("WM_DELETE_WINDOW", cancel)
            dlg.bind("<Destroy>", lambda e: event.set())

        self.after(0, show)
        event.wait()
        return result.get("creds")

    def _apply_rename(self):
        prefix = self.prefix_entry.get().strip().upper()
        number = self.number_entry.get().strip().zfill(3)
        dtype = "DT" if self.device_type.get() == "Desktop" else "LT"

        if not prefix or not number:
            self._append_output("ERROR: Please enter company prefix and number.")
            return

        new_name = f"{prefix}-{dtype}-{number}"
        self._append_output(f"Renaming computer to {new_name}...")
        log(f"Renaming computer to {new_name}")

        domain_user = self.rename_user_entry.get().strip()
        domain_pass = self.rename_pass_entry.get()
        local_only = self.local_rename_only.get()

        def task():
            if local_only:
                rc, out = run_powershell("rename_computer.ps1",
                                          ["-NewName", new_name, "-LocalOnly"],
                                          callback=self._safe_append)
            elif domain_user:
                rc, out = run_powershell_with_secret(
                    "rename_computer.ps1",
                    ["-NewName", new_name, "-DomainUser", domain_user],
                    domain_pass,
                    callback=self._safe_append
                )
            else:
                rc, out = run_powershell("rename_computer.ps1", ["-NewName", new_name],
                                          callback=self._safe_append)
                if rc != 0 and "Access is denied" in out:
                    is_domain_joined = "RENAME_CONTEXT: DOMAIN_JOINED" in out
                    if not is_domain_joined:
                        log(f"Rename to {new_name} failed — access denied (non-domain)", "error")
                        self._safe_append("ERROR: Access denied — tool must run as administrator.")
                        self.after(0, msgbox.showerror, "Rename Failed",
                                   "Access denied.\n\n"
                                   "Ensure the provisioning tool is running as administrator.")
                        return
                    self._safe_append("Access denied — domain admin credentials required.")
                    creds = self._ask_domain_credentials_blocking()
                    if not creds:
                        log(f"Rename to {new_name} cancelled — no domain credentials", "error")
                        self._safe_append("ERROR: Rename cancelled — domain credentials required.")
                        self.after(0, msgbox.showerror, "Rename Failed",
                                   "This computer is domain-joined.\n\n"
                                   "Renaming requires domain admin credentials.")
                        return
                    user, pwd = creds
                    self.after(0, self._fill_domain_credential_fields, user)
                    rc, out = run_powershell_with_secret(
                        "rename_computer.ps1",
                        ["-NewName", new_name, "-DomainUser", user],
                        pwd,
                        callback=self._safe_append
                    )
            if rc == 0 and "SUCCESS" in out:
                log(f"Computer renamed to {new_name}", "success")
                self.after(0, self._set_computer_name_field, new_name)
                self.after(0, self._prompt_reboot, new_name)
            else:
                err = out.strip() or "Unknown error"
                log(f"Rename failed: {err}", "error")
                self._safe_append(f"ERROR: {err}")
                self.after(0, msgbox.showerror, "Rename Failed", f"Could not rename computer:\n\n{err}")

        threading.Thread(target=task, daemon=True).start()

    def _prompt_reboot(self, new_name):
        import subprocess
        dlg = ctk.CTkToplevel(self)
        dlg.title("Reboot Required")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.attributes("-topmost", True)

        ctk.CTkLabel(dlg, text="Computer Renamed Successfully",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(padx=30, pady=(24, 6))
        ctk.CTkLabel(dlg, text=f"New name:  {new_name}",
                     font=ctk.CTkFont(size=13)).pack(padx=30, pady=(0, 12))
        ctk.CTkLabel(dlg, text="A restart is required for the name change to take effect.",
                     text_color=T.MUTED).pack(padx=30, pady=(0, 16))

        countdown_var = ctk.StringVar(value="Restarting in 30 seconds...")
        ctk.CTkLabel(dlg, textvariable=countdown_var,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=T.WARN).pack(padx=30, pady=(0, 20))

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(padx=30, pady=(0, 24))

        cancelled = [False]

        def do_restart():
            cancelled[0] = True
            dlg.destroy()
            subprocess.Popen(["shutdown", "/r", "/t", "0"],
                             creationflags=subprocess.CREATE_NO_WINDOW)

        def cancel():
            cancelled[0] = True
            subprocess.Popen(["shutdown", "/a"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            dlg.destroy()

        ctk.CTkButton(btn_row, text="Cancel Restart", width=130,
                      fg_color="#555", hover_color="#444",
                      command=cancel).grid(row=0, column=0, padx=(0, 12))
        ctk.CTkButton(btn_row, text="Restart Now", width=130,
                      fg_color=T.DANGER, hover_color=T.DANGER_HOVER,
                      command=do_restart).grid(row=0, column=1)

        # Schedule shutdown in 30s, then tick countdown
        subprocess.Popen(["shutdown", "/r", "/t", "30", "/c",
                          f"Restarting to apply computer name: {new_name}"],
                         creationflags=subprocess.CREATE_NO_WINDOW)

        remaining = [30]

        def tick():
            if cancelled[0] or not dlg.winfo_exists():
                return
            remaining[0] -= 1
            if remaining[0] <= 0:
                dlg.destroy()
                return
            countdown_var.set(f"Restarting in {remaining[0]} seconds...")
            dlg.after(1000, tick)

        dlg.after(1000, tick)

    def _get_details_row(self):
        return {
            "computer_name": self.sys_computer_name_entry.get().strip(),
            "operator":      self.op_user_entry.get().strip(),
            "email":         self.op_email_box.get("1.0", "end").strip().replace("\n", " | "),
            "brand":         self.sys_brand_entry.get().strip(),
            "model":         self.sys_model_entry.get().strip(),
            "serial":        self.sys_serial_entry.get().strip(),
            "processor":     self.sys_cpu_entry.get().strip(),
            "ram":           self.sys_ram_entry.get().strip(),
            "disk":          self.sys_disk_entry.get().strip(),
            "display":       self.sys_display_entry.get().strip(),
            "windows":       self.sys_winver_entry.get().strip(),
            "last_update":   self.sys_lastupdate_entry.get().strip(),
            "monitors":      self.sys_monitor_box.get("1.0", "end").strip().replace("\n", " | "),
        }

    def _sync_to_sheet(self):
        self._sync_sheet_btn.configure(text="Syncing...", state="disabled")
        data = self._get_details_row()

        def task():
            ok, msg = sheets_sync.append_row(data)

            def done():
                self._sync_sheet_btn.configure(text="Send to Google Sheet", state="normal")
                self._append_output(f"Sheet sync: {msg}")
                if ok:
                    msgbox.showinfo("Google Sheets", f"Row added successfully.\n\n{msg}")
                else:
                    msgbox.showerror("Google Sheets Sync Failed", msg)
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _export_csv(self):
        data = self._get_details_row()
        default_name = f"{data.get('computer_name', 'system_info') or 'system_info'}.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
            title="Export System Info to CSV",
        )
        if not path:
            return
        headers = [
            "Computer Name", "Operator Username", "Operator Email",
            "Brand Name", "System Model", "System Serial No.",
            "Processor", "RAM", "Disk Size", "Display / GPU",
            "Windows Version", "Last Windows Update", "Monitor Details",
        ]
        row = [
            data["computer_name"], data["operator"], data["email"],
            data["brand"], data["model"], data["serial"],
            data["processor"], data["ram"], data["disk"], data["display"],
            data["windows"], data["last_update"], data["monitors"],
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerow(row)
            self._append_output(f"Exported to {path}")
            log(f"System info exported to CSV: {path}", "success")
        except Exception as e:
            self._append_output(f"ERROR: CSV export failed — {e}")
            msgbox.showerror("Export Failed", str(e))

    def _browse_ous(self):
        domain = self.domain_name_entry.get().strip()
        server_ip = self.dc_ip_entry.get().strip()
        username = self.join_user_entry.get().strip()
        password = self.join_pass_entry.get()

        missing = []
        if not domain:    missing.append("Domain Name")
        if not username:  missing.append("Domain Username")
        if not password:  missing.append("Domain Password")
        if missing:
            msgbox.showerror("Missing Fields",
                             f"Please fill in: {', '.join(missing)}")
            return

        target = server_ip if server_ip else domain
        self._browse_btn.configure(text="Fetching...", state="disabled")
        self._append_output(f"Pinging {target}...")

        def fetch():
            import socket
            try:
                sock = socket.create_connection((target, 389), timeout=5)
                sock.close()
            except OSError:
                self.after(0, lambda: self._browse_error(
                    f"Cannot reach {target} on port 389 (LDAP).\n\n"
                    "Possible causes:\n"
                    "  • Wrong DC Server IP\n"
                    "  • LDAP port 389 is blocked by firewall\n"
                    "  • Domain controller is offline"))
                return

            self._append_output(f"Port 389 open on {target}, querying OUs...")
            args = ["-DomainName", domain, "-Username", username]
            if server_ip:
                args.extend(["-ServerIP", server_ip])

            rc, out = run_powershell_with_secret("get_ous.ps1", args, password)

            errors = [l for l in out.splitlines() if l.startswith("ERROR")]
            if rc != 0 or errors:
                msg = errors[0] if errors else out
                self.after(0, lambda: self._browse_error(
                    f"LDAP query failed:\n\n{msg}\n\nCheck credentials and that the account has read access to AD."))
                return

            ous = [l.strip() for l in out.splitlines() if l.strip() and not l.startswith("ERROR")]
            if not ous:
                self.after(0, lambda: self._browse_error("No OUs found in the directory."))
                return

            self._append_output(f"Found {len(ous)} OUs.")
            self.after(0, lambda: OUPickerDialog(self, ous, self._on_ou_selected))
            self.after(0, self._browse_btn_reset)

        threading.Thread(target=fetch, daemon=True).start()

    def _browse_error(self, message: str):
        self._browse_btn_reset()
        self._append_output(f"Browse failed: {message.splitlines()[0]}")
        msgbox.showerror("Browse OUs Failed", message)

    def _browse_btn_reset(self):
        self._browse_btn.configure(text="Browse...", state="normal")

    def _on_ou_selected(self, ou_path: str):
        self.ou_entry.delete(0, "end")
        self.ou_entry.insert(0, ou_path)

    def _join_domain(self):
        domain = self.domain_name_entry.get().strip()
        server_ip = self.dc_ip_entry.get().strip()
        ou = self.ou_entry.get().strip()
        username = self.join_user_entry.get().strip()
        password = self.join_pass_entry.get()

        if not domain or not username or not password:
            self._append_output("ERROR: Domain name, username and password are required.")
            return

        self._append_output(f"Joining domain {domain}...")
        log(f"Joining domain {domain} as {username}")

        args = ["-DomainName", domain, "-Username", username]
        if ou:
            args.extend(["-OUPath", ou])
        if server_ip:
            args.extend(["-ServerIP", server_ip])

        def task():
            rc, out = run_powershell_with_secret("join_domain.ps1", args, password,
                                                  callback=self._safe_append)
            if rc == 0:
                log(f"Joined domain {domain}", "success")
            else:
                log(f"Domain join failed: {out}", "error")

        threading.Thread(target=task, daemon=True).start()


class OUPickerDialog(ctk.CTkToplevel):
    def __init__(self, master, ous: list, on_select):
        super().__init__(master)
        self.ous = ous
        self.on_select = on_select

        self.title("Select OU")
        self.geometry("560x440")
        self.resizable(False, True)
        self.grab_set()
        self._build()
        self._center()

    def _center(self):
        self.update_idletasks()
        x = self.master.winfo_rootx() + (self.master.winfo_width() - 560) // 2
        y = self.master.winfo_rooty() + (self.master.winfo_height() - 440) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Select an Organisational Unit",
                      font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._filter)
        ctk.CTkEntry(self, placeholder_text="Filter OUs...",
                      textvariable=self.search_var, height=36).grid(
            row=1, column=0, padx=20, pady=(0, 8), sticky="ew")

        self.scroll = ctk.CTkScrollableFrame(self, height=280)
        self.scroll.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)
        self._render_ous(self.ous)

        ctk.CTkButton(self, text="Cancel", width=120, fg_color="transparent",
                       border_width=1, command=self.destroy).grid(
            row=3, column=0, padx=20, pady=(0, 20), sticky="e")

    def _render_ous(self, ous):
        for w in self.scroll.winfo_children():
            w.destroy()
        for i, ou in enumerate(ous):
            ctk.CTkButton(self.scroll, text=ou, anchor="w",
                           fg_color="transparent", hover_color=T.PANEL_3,
                           command=lambda o=ou: self._pick(o)).grid(
                row=i, column=0, sticky="ew", padx=4, pady=2)

    def _filter(self, *_):
        term = self.search_var.get().lower()
        self._render_ous([ou for ou in self.ous if term in ou.lower()])

    def _pick(self, ou: str):
        self.grab_release()
        self.destroy()
        self.on_select(ou)
