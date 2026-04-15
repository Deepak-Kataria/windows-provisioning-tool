import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_powershell
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class DebloatTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.checkboxes = {}
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "debloat_list.json")) as f:
            self.debloat_data = json.load(f)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Debloat Windows",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(header, text="Select apps to remove. This cannot be undone easily.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")
        ctk.CTkButton(btn_frame, text="Select All", width=110,
                       command=self._select_all).grid(row=0, column=0, padx=4)
        ctk.CTkButton(btn_frame, text="Deselect All", width=110,
                       command=self._deselect_all).grid(row=0, column=1, padx=4)

        # Scrollable app list
        scroll = ctk.CTkScrollableFrame(self, height=280)
        scroll.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        scroll.grid_columnconfigure(0, weight=1)

        for i, app in enumerate(self.debloat_data["appx_packages"]):
            var = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(scroll, text=app["name"], variable=var)
            cb.grid(row=i, column=0, sticky="w", padx=10, pady=4)
            self.checkboxes[app["package"]] = var

        remove_btn = ctk.CTkButton(self, text="Remove Selected Apps",
                                    fg_color="#E53935", hover_color="#B71C1C",
                                    command=self._remove_apps)
        remove_btn.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="w")

        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=3, column=0, padx=20, pady=(8, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=130, state="disabled")
        self.output_box.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _select_all(self):
        for var in self.checkboxes.values():
            var.set(True)

    def _deselect_all(self):
        for var in self.checkboxes.values():
            var.set(False)

    def _append_output(self, text):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _remove_apps(self):
        selected = [pkg for pkg, var in self.checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No apps selected.")
            return

        self._append_output(f"Removing {len(selected)} apps...")
        log(f"Debloat: removing {len(selected)} apps")

        def task():
            rc, out = run_powershell("debloat.ps1",
                                      ["-Packages", ",".join(selected)],
                                      callback=self._append_output)
            log(f"Debloat complete. Return code: {rc}")

        threading.Thread(target=task, daemon=True).start()
