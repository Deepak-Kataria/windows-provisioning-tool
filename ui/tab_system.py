import customtkinter as ctk
import json
import os
import threading
import tkinter.messagebox as msgbox
from modules.runner import run_powershell, run_powershell_with_secret
from modules.logger import log
from modules import sheets_sync

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class SystemTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.device_type = ctk.StringVar(value="Desktop")
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "domain_config.json")) as f:
            self.domain_config = json.load(f)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # --- Rename Section ---
        rename_frame = ctk.CTkFrame(scroll)
        rename_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        rename_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(rename_frame, text="Rename Computer",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(16, 8))

        ctk.CTkLabel(rename_frame, text="Device Type:").grid(
            row=1, column=0, padx=20, pady=8, sticky="w")
        radio_frame = ctk.CTkFrame(rename_frame, fg_color="transparent")
        radio_frame.grid(row=1, column=1, columnspan=2, padx=8, pady=8, sticky="w")
        ctk.CTkRadioButton(radio_frame, text="Desktop", variable=self.device_type,
                            value="Desktop", command=self._update_preview).grid(
            row=0, column=0, padx=(0, 16))
        ctk.CTkRadioButton(radio_frame, text="Laptop", variable=self.device_type,
                            value="Laptop", command=self._update_preview).grid(
            row=0, column=1)

        ctk.CTkLabel(rename_frame, text="Company Prefix:").grid(
            row=2, column=0, padx=20, pady=8, sticky="w")
        self.prefix_entry = ctk.CTkEntry(rename_frame, width=140,
                                          placeholder_text="e.g. ACME")
        prefix = self.domain_config.get("company_prefix", "")
        if prefix:
            self.prefix_entry.insert(0, prefix)
        self.prefix_entry.grid(row=2, column=1, columnspan=2, padx=8, pady=8, sticky="w")
        self.prefix_entry.bind("<KeyRelease>", lambda e: self._update_preview())

        ctk.CTkLabel(rename_frame, text="Number / ID:").grid(
            row=3, column=0, padx=20, pady=8, sticky="w")
        number_row = ctk.CTkFrame(rename_frame, fg_color="transparent")
        number_row.grid(row=3, column=1, columnspan=2, padx=8, pady=8, sticky="w")
        self.number_entry = ctk.CTkEntry(number_row, width=120,
                                          placeholder_text="e.g. 001")
        self.number_entry.grid(row=0, column=0)
        self.number_entry.bind("<KeyRelease>", lambda e: self._update_preview())
        self._autogen_btn = ctk.CTkButton(number_row, text="Auto-Generate from Hardware",
                                           width=200, command=self._auto_generate_name)
        self._autogen_btn.grid(row=0, column=1, padx=(10, 0))

        ctk.CTkLabel(rename_frame, text="Preview:").grid(
            row=4, column=0, padx=20, pady=8, sticky="w")
        self.preview_label = ctk.CTkLabel(rename_frame, text="---",
                                           font=ctk.CTkFont(size=14, weight="bold"),
                                           text_color="#4FC3F7")
        self.preview_label.grid(row=4, column=1, columnspan=2, padx=8, pady=8, sticky="w")

        rename_btn = ctk.CTkButton(rename_frame, text="Apply Rename",
                                    command=self._apply_rename)
        rename_btn.grid(row=5, column=0, columnspan=3, padx=20, pady=(8, 16), sticky="w")

        # --- Operator & System Details Section ---
        details_frame = ctk.CTkFrame(scroll)
        details_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        details_frame.grid_columnconfigure(1, weight=1)
        details_frame.grid_columnconfigure(3, weight=1)

        header_row = ctk.CTkFrame(details_frame, fg_color="transparent")
        header_row.grid(row=0, column=0, columnspan=4, sticky="ew", padx=20, pady=(16, 8))
        header_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header_row, text="Operator & System Details",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w")
        self._fetch_details_btn = ctk.CTkButton(header_row, text="Fetch Details",
                                                 width=130, command=self._fetch_system_details)
        self._fetch_details_btn.grid(row=0, column=1, sticky="e")

        # Left column — Operator info
        ctk.CTkLabel(details_frame, text="Operator Username:").grid(
            row=1, column=0, padx=(20, 4), pady=5, sticky="w")
        self.op_user_entry = ctk.CTkEntry(details_frame, width=220,
                                           placeholder_text="Windows username")
        self.op_user_entry.grid(row=1, column=1, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="Operator Email(s):").grid(
            row=2, column=0, padx=(20, 4), pady=5, sticky="nw")
        self.op_email_box = ctk.CTkTextbox(details_frame, width=220, height=58,
                                            font=ctk.CTkFont(size=12))
        self.op_email_box.grid(row=2, column=1, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="System Model:").grid(
            row=3, column=0, padx=(20, 4), pady=5, sticky="w")
        self.sys_model_entry = ctk.CTkEntry(details_frame, width=220,
                                             placeholder_text="e.g. Dell Latitude 5420")
        self.sys_model_entry.grid(row=3, column=1, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="System Serial No.:").grid(
            row=4, column=0, padx=(20, 4), pady=5, sticky="w")
        self.sys_serial_entry = ctk.CTkEntry(details_frame, width=220,
                                              placeholder_text="BIOS serial number")
        self.sys_serial_entry.grid(row=4, column=1, padx=(0, 20), pady=5, sticky="w")

        # Right column — Hardware & OS
        ctk.CTkLabel(details_frame, text="Processor:").grid(
            row=1, column=2, padx=(20, 4), pady=5, sticky="w")
        self.sys_cpu_entry = ctk.CTkEntry(details_frame, width=220,
                                           placeholder_text="CPU model")
        self.sys_cpu_entry.grid(row=1, column=3, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="RAM:").grid(
            row=2, column=2, padx=(20, 4), pady=5, sticky="w")
        self.sys_ram_entry = ctk.CTkEntry(details_frame, width=220,
                                           placeholder_text="Total RAM")
        self.sys_ram_entry.grid(row=2, column=3, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="Disk Size:").grid(
            row=3, column=2, padx=(20, 4), pady=5, sticky="w")
        self.sys_disk_entry = ctk.CTkEntry(details_frame, width=220,
                                            placeholder_text="Primary disk")
        self.sys_disk_entry.grid(row=3, column=3, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="Display / GPU:").grid(
            row=4, column=2, padx=(20, 4), pady=5, sticky="w")
        self.sys_display_entry = ctk.CTkEntry(details_frame, width=220,
                                               placeholder_text="GPU / display adapter")
        self.sys_display_entry.grid(row=4, column=3, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="Windows Version:").grid(
            row=5, column=0, padx=(20, 4), pady=5, sticky="w")
        self.sys_winver_entry = ctk.CTkEntry(details_frame, width=220,
                                              placeholder_text="e.g. Windows 11 Pro")
        self.sys_winver_entry.grid(row=5, column=1, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="Last Windows Update:").grid(
            row=5, column=2, padx=(20, 4), pady=5, sticky="w")
        self.sys_lastupdate_entry = ctk.CTkEntry(details_frame, width=220,
                                                  placeholder_text="Date of last installed update")
        self.sys_lastupdate_entry.grid(row=5, column=3, padx=(0, 20), pady=5, sticky="w")

        ctk.CTkLabel(details_frame, text="Monitor Details:").grid(
            row=6, column=0, padx=(20, 4), pady=5, sticky="nw")
        self.sys_monitor_box = ctk.CTkTextbox(details_frame, width=500, height=58,
                                               font=ctk.CTkFont(size=12))
        self.sys_monitor_box.grid(row=6, column=1, columnspan=3, padx=(0, 20), pady=5, sticky="w")

        self._sync_sheet_btn = ctk.CTkButton(details_frame, text="Sync to Google Sheet",
                                              width=180, command=self._sync_to_sheet)
        self._sync_sheet_btn.grid(row=7, column=0, columnspan=2, padx=20, pady=(8, 16), sticky="w")

        # --- Domain Join Section ---
        domain_frame = ctk.CTkFrame(scroll)
        domain_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        domain_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(domain_frame, text="Join Domain",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 8))

        # Domain Name
        ctk.CTkLabel(domain_frame, text="Domain Name:").grid(
            row=1, column=0, padx=20, pady=6, sticky="w")
        self.domain_name_entry = ctk.CTkEntry(domain_frame, width=280,
                                               placeholder_text="e.g. company.local")
        default_domain = self.domain_config.get("domain_name", "")
        if default_domain:
            self.domain_name_entry.insert(0, default_domain)
        self.domain_name_entry.grid(row=1, column=1, padx=20, pady=6, sticky="w")

        # DC Server IP
        ctk.CTkLabel(domain_frame, text="DC Server IP:").grid(
            row=2, column=0, padx=20, pady=6, sticky="w")
        self.dc_ip_entry = ctk.CTkEntry(domain_frame, width=280,
                                         placeholder_text="e.g. 192.168.1.10  (optional)")
        default_dns = self.domain_config.get("dns_server", "")
        if default_dns:
            self.dc_ip_entry.insert(0, default_dns)
        self.dc_ip_entry.grid(row=2, column=1, padx=20, pady=6, sticky="w")

        # OU Path with Browse button
        ctk.CTkLabel(domain_frame, text="OU Path (optional):").grid(
            row=3, column=0, padx=20, pady=6, sticky="w")
        ou_row = ctk.CTkFrame(domain_frame, fg_color="transparent")
        ou_row.grid(row=3, column=1, padx=20, pady=6, sticky="w")
        self.ou_entry = ctk.CTkEntry(ou_row, width=210,
                                      placeholder_text="e.g. OU=Computers,DC=company,DC=local")
        default_ou = self.domain_config.get("ou_path", "")
        if default_ou:
            self.ou_entry.insert(0, default_ou)
        self.ou_entry.grid(row=0, column=0)
        self._browse_btn = ctk.CTkButton(ou_row, text="Browse...", width=80,
                                          command=self._browse_ous)
        self._browse_btn.grid(row=0, column=1, padx=(8, 0))

        # Domain Username
        ctk.CTkLabel(domain_frame, text="Domain Username:").grid(
            row=4, column=0, padx=20, pady=6, sticky="w")
        self.domain_user_entry = ctk.CTkEntry(domain_frame, width=280,
                                               placeholder_text="Admin username")
        self.domain_user_entry.grid(row=4, column=1, padx=20, pady=6, sticky="w")

        # Domain Password
        ctk.CTkLabel(domain_frame, text="Domain Password:").grid(
            row=5, column=0, padx=20, pady=6, sticky="w")
        self.domain_pass_entry = ctk.CTkEntry(domain_frame, width=280,
                                               placeholder_text="Admin password", show="*")
        self.domain_pass_entry.grid(row=5, column=1, padx=20, pady=6, sticky="w")

        join_btn = ctk.CTkButton(domain_frame, text="Join Domain",
                                  command=self._join_domain)
        join_btn.grid(row=6, column=0, columnspan=2, padx=20, pady=(8, 16), sticky="w")

        # Output log
        ctk.CTkLabel(scroll, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=3, column=0, padx=20, pady=(10, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(scroll, height=140, state="disabled")
        self.output_box.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _fetch_system_details(self):
        self._fetch_details_btn.configure(text="Fetching...", state="disabled")

        def task():
            rc, out = run_powershell("get_system_info.ps1", [], callback=None)

            def apply():
                self._fetch_details_btn.configure(text="Fetch Details", state="normal")
                if rc != 0:
                    first_err = next((l for l in out.splitlines() if l.startswith("ERROR")), out)
                    self._append_output(f"Fetch details failed: {first_err}")
                    return

                data = {}
                for line in out.splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        data[k.strip()] = v.strip()

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

                self._append_output("System details fetched.")

            self.after(0, apply)

        threading.Thread(target=task, daemon=True).start()

    def _auto_generate_name(self):
        self._autogen_btn.configure(text="Reading hardware...", state="disabled")

        def task():
            rc, out = run_powershell("get_hardware_id.ps1", [], callback=None)
            hw_id = out.strip().splitlines()[-1].strip() if out.strip() else ""

            def apply():
                self._autogen_btn.configure(text="Auto-Generate from Hardware", state="normal")
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
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _safe_append(self, text):
        self.after(0, self._append_output, text)

    def _apply_rename(self):
        prefix = self.prefix_entry.get().strip().upper()
        number = self.number_entry.get().strip().zfill(3)
        dtype = "DT" if self.device_type.get() == "Desktop" else "LT"

        if not prefix or not number:
            self._append_output("ERROR: Please enter company prefix and number.")
            return

        new_name = f"{prefix}-{dtype}-{number}"
        self._append_output(f"Renaming computer to {new_name}...")

        details = self._get_details_row(new_name)
        log(f"Renaming computer to {new_name} | operator={details.get('operator')} serial={details.get('serial')}")

        def task():
            rc, out = run_powershell("rename_computer.ps1", ["-NewName", new_name],
                                      callback=self._safe_append)
            if rc == 0:
                log(f"Computer renamed to {new_name}", "success")
                if sheets_sync.is_configured():
                    ok, msg = sheets_sync.append_row(self._get_details_row(new_name))
                    self._safe_append(f"Sheet sync: {msg}")
            else:
                log(f"Rename failed: {out}", "error")

        threading.Thread(target=task, daemon=True).start()

    def _get_details_row(self, computer_name=""):
        return {
            "computer_name": computer_name,
            "operator":      self.op_user_entry.get().strip(),
            "email":         self.op_email_box.get("1.0", "end").strip().replace("\n", " | "),
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

    def _sync_to_sheet(self, computer_name=""):
        self._sync_sheet_btn.configure(text="Syncing...", state="disabled")
        data = self._get_details_row(computer_name)

        def task():
            ok, msg = sheets_sync.append_row(data)

            def done():
                self._sync_sheet_btn.configure(text="Sync to Google Sheet", state="normal")
                self._append_output(f"Sheet sync: {msg}")
                if ok:
                    msgbox.showinfo("Google Sheets", f"Row added successfully.\n\n{msg}")
                else:
                    msgbox.showerror("Google Sheets Sync Failed", msg)
            self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    def _browse_ous(self):
        domain = self.domain_name_entry.get().strip()
        server_ip = self.dc_ip_entry.get().strip()
        username = self.domain_user_entry.get().strip()
        password = self.domain_pass_entry.get()

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
        username = self.domain_user_entry.get().strip()
        password = self.domain_pass_entry.get()

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
                           fg_color="transparent", hover_color=("#3a3a3a", "#2a2a2a"),
                           command=lambda o=ou: self._pick(o)).grid(
                row=i, column=0, sticky="ew", padx=4, pady=2)

    def _filter(self, *_):
        term = self.search_var.get().lower()
        self._render_ous([ou for ou in self.ous if term in ou.lower()])

    def _pick(self, ou: str):
        self.grab_release()
        self.destroy()
        self.on_select(ou)
