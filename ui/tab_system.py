import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_powershell
from modules.logger import log

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

        # --- Rename Section ---
        rename_frame = ctk.CTkFrame(self)
        rename_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        rename_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(rename_frame, text="Rename Computer",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(16, 8))

        ctk.CTkLabel(rename_frame, text="Device Type:").grid(
            row=1, column=0, padx=20, pady=8, sticky="w")
        ctk.CTkRadioButton(rename_frame, text="Desktop", variable=self.device_type,
                            value="Desktop", command=self._update_preview).grid(
            row=1, column=1, padx=8, sticky="w")
        ctk.CTkRadioButton(rename_frame, text="Laptop", variable=self.device_type,
                            value="Laptop", command=self._update_preview).grid(
            row=1, column=2, padx=8, sticky="w")

        ctk.CTkLabel(rename_frame, text="Company Prefix:").grid(
            row=2, column=0, padx=20, pady=8, sticky="w")
        self.prefix_entry = ctk.CTkEntry(rename_frame, width=140,
                                          placeholder_text="e.g. ACME")
        prefix = self.domain_config.get("company_prefix", "")
        if prefix:
            self.prefix_entry.insert(0, prefix)
        self.prefix_entry.grid(row=2, column=1, columnspan=2, padx=8, pady=8, sticky="w")
        self.prefix_entry.bind("<KeyRelease>", lambda e: self._update_preview())

        ctk.CTkLabel(rename_frame, text="Number:").grid(
            row=3, column=0, padx=20, pady=8, sticky="w")
        self.number_entry = ctk.CTkEntry(rename_frame, width=100,
                                          placeholder_text="e.g. 001")
        self.number_entry.grid(row=3, column=1, columnspan=2, padx=8, pady=8, sticky="w")
        self.number_entry.bind("<KeyRelease>", lambda e: self._update_preview())

        ctk.CTkLabel(rename_frame, text="Preview:").grid(
            row=4, column=0, padx=20, pady=8, sticky="w")
        self.preview_label = ctk.CTkLabel(rename_frame, text="---",
                                           font=ctk.CTkFont(size=14, weight="bold"),
                                           text_color="#4FC3F7")
        self.preview_label.grid(row=4, column=1, columnspan=2, padx=8, pady=8, sticky="w")

        rename_btn = ctk.CTkButton(rename_frame, text="Apply Rename",
                                    command=self._apply_rename)
        rename_btn.grid(row=5, column=0, columnspan=3, padx=20, pady=(8, 16), sticky="w")

        # --- Domain Join Section ---
        domain_frame = ctk.CTkFrame(self)
        domain_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        domain_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(domain_frame, text="Join Domain",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(16, 8))

        fields = [
            ("Domain Name:", "domain_name_entry", self.domain_config.get("domain_name", ""), "e.g. company.local"),
            ("OU Path (optional):", "ou_entry", self.domain_config.get("ou_path", ""), "e.g. OU=Computers,DC=company,DC=local"),
            ("Domain Username:", "domain_user_entry", "", "Admin username"),
            ("Domain Password:", "domain_pass_entry", "", "Admin password"),
        ]

        for i, (label, attr, default, placeholder) in enumerate(fields):
            ctk.CTkLabel(domain_frame, text=label).grid(
                row=i + 1, column=0, padx=20, pady=6, sticky="w")
            entry = ctk.CTkEntry(domain_frame, width=280, placeholder_text=placeholder,
                                  show="*" if "Password" in label else "")
            if default:
                entry.insert(0, default)
            entry.grid(row=i + 1, column=1, padx=20, pady=6, sticky="w")
            setattr(self, attr, entry)

        join_btn = ctk.CTkButton(domain_frame, text="Join Domain",
                                  command=self._join_domain)
        join_btn.grid(row=len(fields) + 1, column=0, columnspan=2,
                       padx=20, pady=(8, 16), sticky="w")

        # Output log
        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=2, column=0, padx=20, pady=(10, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=140, state="disabled")
        self.output_box.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")

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

        def task():
            rc, out = run_powershell("rename_computer.ps1", ["-NewName", new_name],
                                      callback=self._append_output)
            if rc == 0:
                log(f"Computer renamed to {new_name}", "success")
            else:
                log(f"Rename failed: {out}", "error")

        threading.Thread(target=task, daemon=True).start()

    def _join_domain(self):
        domain = self.domain_name_entry.get().strip()
        ou = self.ou_entry.get().strip()
        username = self.domain_user_entry.get().strip()
        password = self.domain_pass_entry.get()

        if not domain or not username or not password:
            self._append_output("ERROR: Domain name, username and password are required.")
            return

        self._append_output(f"Joining domain {domain}...")
        log(f"Joining domain {domain} as {username}")

        args = ["-DomainName", domain, "-Username", username, "-Password", password]
        if ou:
            args.extend(["-OUPath", ou])

        def task():
            rc, out = run_powershell("join_domain.ps1", args, callback=self._append_output)
            if rc == 0:
                log(f"Joined domain {domain}", "success")
            else:
                log(f"Domain join failed: {out}", "error")

        threading.Thread(target=task, daemon=True).start()
