import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_powershell
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class OrgSettingsTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.checkboxes = {}
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "org_settings.json")) as f:
            self.settings_data = json.load(f)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Org Settings",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(header, text="Apply organisation-standard Windows configuration.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 12))

        scroll = ctk.CTkScrollableFrame(self, height=300)
        scroll.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=2)

        for i, tweak in enumerate(self.settings_data["registry_tweaks"]):
            var = ctk.BooleanVar(value=True)
            row_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            row_frame.grid(row=i, column=0, columnspan=2, sticky="ew", pady=4, padx=4)
            row_frame.grid_columnconfigure(1, weight=1)

            ctk.CTkCheckBox(row_frame, text=tweak["name"], variable=var, width=220).grid(
                row=0, column=0, sticky="w")
            ctk.CTkLabel(row_frame, text=tweak["description"], text_color="gray",
                          font=ctk.CTkFont(size=11), wraplength=300).grid(
                row=0, column=1, sticky="w", padx=12)
            self.checkboxes[i] = (var, tweak)

        apply_btn = ctk.CTkButton(self, text="Apply Selected Settings",
                                   command=self._apply)
        apply_btn.grid(row=2, column=0, padx=20, pady=(8, 4), sticky="w")

        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=3, column=0, padx=20, pady=(12, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=130, state="disabled")
        self.output_box.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _append_output(self, text):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _apply(self):
        selected = [tweak for _, (var, tweak) in self.checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No settings selected.")
            return

        self._append_output(f"Applying {len(selected)} settings...")
        log(f"Applying {len(selected)} org settings")

        settings_json = json.dumps(selected)

        def task():
            rc, out = run_powershell("apply_org_settings.ps1",
                                      ["-SettingsJson", settings_json],
                                      callback=self._append_output)
            log(f"Org settings applied. Return code: {rc}")

        threading.Thread(target=task, daemon=True).start()
