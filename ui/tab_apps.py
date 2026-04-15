import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_winget
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class AppsTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.common_checkboxes = {}
        self.team_checkboxes = {}
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "apps_common.json")) as f:
            self.common_data = json.load(f)
        with open(os.path.join(CONFIG_DIR, "apps_teams.json")) as f:
            self.teams_data = json.load(f)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- Common Apps ---
        common_frame = ctk.CTkFrame(self)
        common_frame.grid(row=0, column=0, padx=(20, 10), pady=20, sticky="nsew")
        common_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(common_frame, text="Common Apps",
                      font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 4))
        ctk.CTkLabel(common_frame, text="Installed on all machines",
                      text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        scroll_common = ctk.CTkScrollableFrame(common_frame, height=220)
        scroll_common.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")

        for i, app in enumerate(self.common_data["common_apps"]):
            var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(scroll_common, text=app["name"], variable=var).grid(
                row=i, column=0, sticky="w", padx=8, pady=4)
            self.common_checkboxes[app["winget_id"]] = (var, app["name"])

        ctk.CTkButton(common_frame, text="Install Common Apps",
                       command=self._install_common).grid(
            row=3, column=0, padx=16, pady=(4, 16), sticky="w")

        # --- Team Apps ---
        team_frame = ctk.CTkFrame(self)
        team_frame.grid(row=0, column=1, padx=(10, 20), pady=20, sticky="nsew")
        team_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(team_frame, text="Team / Role Apps",
                      font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(team_frame, text="Select Team:",
                      font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 4))

        self.team_var = ctk.StringVar(value=list(self.teams_data["teams"].keys())[0])
        team_menu = ctk.CTkOptionMenu(team_frame,
                                       values=list(self.teams_data["teams"].keys()),
                                       variable=self.team_var,
                                       command=self._on_team_change)
        team_menu.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="w")

        self.scroll_team = ctk.CTkScrollableFrame(team_frame, height=220)
        self.scroll_team.grid(row=3, column=0, padx=10, pady=(0, 8), sticky="ew")

        self._populate_team_apps(self.team_var.get())

        ctk.CTkButton(team_frame, text="Install Team Apps",
                       command=self._install_team).grid(
            row=4, column=0, padx=16, pady=(4, 16), sticky="w")

        # Output
        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=1, column=0, columnspan=2, padx=20, pady=(0, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=130, state="disabled")
        self.output_box.grid(row=2, column=0, columnspan=2, padx=20,
                              pady=(0, 20), sticky="ew")

    def _populate_team_apps(self, team_name):
        for widget in self.scroll_team.winfo_children():
            widget.destroy()
        self.team_checkboxes.clear()

        apps = self.teams_data["teams"].get(team_name, [])
        for i, app in enumerate(apps):
            var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(self.scroll_team, text=app["name"], variable=var).grid(
                row=i, column=0, sticky="w", padx=8, pady=4)
            self.team_checkboxes[app["winget_id"]] = (var, app["name"])

    def _on_team_change(self, team_name):
        self._populate_team_apps(team_name)

    def _append_output(self, text):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _install_common(self):
        selected = [(wid, name) for wid, (var, name) in self.common_checkboxes.items()
                    if var.get()]
        if not selected:
            self._append_output("No apps selected.")
            return
        threading.Thread(target=self._run_installs, args=(selected,), daemon=True).start()

    def _install_team(self):
        selected = [(wid, name) for wid, (var, name) in self.team_checkboxes.items()
                    if var.get()]
        if not selected:
            self._append_output("No apps selected.")
            return
        threading.Thread(target=self._run_installs, args=(selected,), daemon=True).start()

    def _run_installs(self, apps):
        for winget_id, name in apps:
            self._append_output(f"Installing {name}...")
            log(f"Installing {name} ({winget_id})")
            rc, out = run_winget(winget_id, callback=None)
            if rc == 0:
                self._append_output(f"  Done: {name}")
                log(f"Installed {name}", "success")
            else:
                self._append_output(f"  Failed: {name}")
                log(f"Failed to install {name}: {out}", "error")
        self._append_output("Installation complete.")
