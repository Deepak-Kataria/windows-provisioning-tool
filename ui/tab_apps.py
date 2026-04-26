import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_winget, run_winget_uninstall
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class AppsTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.common_checkboxes = {}
        self.team_checkboxes = {}
        self.uninstall_checkboxes = {}
        self._running = False
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "apps_common.json")) as f:
            self.common_data = json.load(f)
        with open(os.path.join(CONFIG_DIR, "apps_teams.json")) as f:
            self.teams_data = json.load(f)

    # ── Build UI ───────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Common Apps card
        common_frame = ctk.CTkFrame(self)
        common_frame.grid(row=0, column=0, padx=(20, 6), pady=(20, 6), sticky="nsew")
        common_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(common_frame, text="Common Apps",
                      font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 2))
        ctk.CTkLabel(common_frame, text="Installed on all machines",
                      text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 6))

        scroll_common = ctk.CTkScrollableFrame(common_frame, height=180)
        scroll_common.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="ew")

        for i, app in enumerate(self.common_data["common_apps"]):
            var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(scroll_common, text=app["name"], variable=var).grid(
                row=i, column=0, sticky="w", padx=8, pady=3)
            self.common_checkboxes[app["winget_id"]] = (var, app["name"])

        self.common_btn = ctk.CTkButton(common_frame, text="Install Common Apps",
                                         command=self._install_common)
        self.common_btn.grid(row=3, column=0, padx=16, pady=(4, 8), sticky="w")

        common_prog = ctk.CTkFrame(common_frame, fg_color="transparent")
        common_prog.grid(row=4, column=0, padx=16, pady=(0, 12), sticky="ew")
        common_prog.grid_columnconfigure(0, weight=1)
        self.common_bar = ctk.CTkProgressBar(common_prog, height=12)
        self.common_bar.grid(row=0, column=0, sticky="ew")
        self.common_bar.set(0)
        self.common_status = ctk.CTkLabel(common_prog, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.common_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Team Apps card
        team_frame = ctk.CTkFrame(self)
        team_frame.grid(row=0, column=1, padx=(6, 20), pady=(20, 6), sticky="nsew")
        team_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(team_frame, text="Team / Role Apps",
                      font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 2))

        ctk.CTkLabel(team_frame, text="Select Team:",
                      font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 4))

        self.team_var = ctk.StringVar(value=list(self.teams_data["teams"].keys())[0])
        ctk.CTkOptionMenu(team_frame,
                           values=list(self.teams_data["teams"].keys()),
                           variable=self.team_var,
                           command=self._on_team_change).grid(
            row=2, column=0, padx=16, pady=(0, 6), sticky="w")

        self.scroll_team = ctk.CTkScrollableFrame(team_frame, height=180)
        self.scroll_team.grid(row=3, column=0, padx=10, pady=(0, 6), sticky="ew")
        self._populate_team_apps(self.team_var.get())

        self.team_btn = ctk.CTkButton(team_frame, text="Install Team Apps",
                                       command=self._install_team)
        self.team_btn.grid(row=4, column=0, padx=16, pady=(4, 8), sticky="w")

        team_prog = ctk.CTkFrame(team_frame, fg_color="transparent")
        team_prog.grid(row=5, column=0, padx=16, pady=(0, 12), sticky="ew")
        team_prog.grid_columnconfigure(0, weight=1)
        self.team_bar = ctk.CTkProgressBar(team_prog, height=12)
        self.team_bar.grid(row=0, column=0, sticky="ew")
        self.team_bar.set(0)
        self.team_status = ctk.CTkLabel(team_prog, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.team_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Output
        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=1, column=0, columnspan=2, padx=20, pady=(4, 2), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=100, state="disabled")
        self.output_box.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 6), sticky="ew")

        # Uninstall / Rollback card
        uninstall_card = ctk.CTkFrame(self)
        uninstall_card.grid(row=3, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        uninstall_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(uninstall_card, text="Rollback / Uninstall Apps",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(uninstall_card, text="Select apps to uninstall. All common and team apps listed.",
                      text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        # Collect all unique apps across common + all teams
        all_apps = {}
        for app in self.common_data["common_apps"]:
            all_apps[app["winget_id"]] = app["name"]
        for apps_list in self.teams_data["teams"].values():
            for app in apps_list:
                all_apps[app["winget_id"]] = app["name"]

        uninstall_scroll = ctk.CTkScrollableFrame(uninstall_card, height=120)
        uninstall_scroll.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")
        uninstall_scroll.grid_columnconfigure(0, weight=1)

        # 3-column grid for compact layout
        col_count = 3
        for idx, (wid, name) in enumerate(sorted(all_apps.items(), key=lambda x: x[1])):
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(uninstall_scroll, text=name, variable=var).grid(
                row=idx // col_count, column=idx % col_count, sticky="w", padx=8, pady=3)
            self.uninstall_checkboxes[wid] = (var, name)

        rb_btn_row = ctk.CTkFrame(uninstall_card, fg_color="transparent")
        rb_btn_row.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="w")

        self.uninstall_btn = ctk.CTkButton(rb_btn_row, text="Uninstall Selected",
                                            fg_color="#FF8F00", hover_color="#E65100",
                                            command=self._uninstall_selected)
        self.uninstall_btn.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(rb_btn_row, text="Select All", width=90,
                       command=lambda: [v.set(True) for v, _ in self.uninstall_checkboxes.values()]).grid(
            row=0, column=1, padx=4)
        ctk.CTkButton(rb_btn_row, text="Deselect All", width=90,
                       command=lambda: [v.set(False) for v, _ in self.uninstall_checkboxes.values()]).grid(
            row=0, column=2, padx=4)

        uninstall_prog = ctk.CTkFrame(uninstall_card, fg_color="transparent")
        uninstall_prog.grid(row=4, column=0, padx=16, pady=(0, 12), sticky="ew")
        uninstall_prog.grid_columnconfigure(0, weight=1)
        self.uninstall_bar = ctk.CTkProgressBar(uninstall_prog, height=12)
        self.uninstall_bar.grid(row=0, column=0, sticky="ew")
        self.uninstall_bar.set(0)
        self.uninstall_status = ctk.CTkLabel(uninstall_prog, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.uninstall_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

    # ── Helpers ────────────────────────────────────────────────────

    def _populate_team_apps(self, team_name):
        for widget in self.scroll_team.winfo_children():
            widget.destroy()
        self.team_checkboxes.clear()
        for i, app in enumerate(self.teams_data["teams"].get(team_name, [])):
            var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(self.scroll_team, text=app["name"], variable=var).grid(
                row=i, column=0, sticky="w", padx=8, pady=3)
            self.team_checkboxes[app["winget_id"]] = (var, app["name"])

    def _on_team_change(self, team_name):
        self._populate_team_apps(team_name)

    def _append_output(self, text):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _safe_append(self, text):
        self.after(0, self._append_output, text)

    def _set_all_buttons(self, state):
        for btn in (self.common_btn, self.team_btn, self.uninstall_btn):
            btn.configure(state=state)

    def _show_done_dialog(self, succeeded, failed, total, action="installed"):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Complete")
        dialog.geometry("320x170")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        ctk.CTkLabel(dialog, text="Operation Complete",
                      font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(22, 8))
        body = f"Successfully {action}: {succeeded}\nFailed: {failed}\nTotal: {total}"
        ctk.CTkLabel(dialog, text=body, font=ctk.CTkFont(size=13), justify="left").pack(pady=(0, 14))
        ctk.CTkButton(dialog, text="OK", width=90, command=dialog.destroy).pack()

    # ── Install ────────────────────────────────────────────────────

    def _install_common(self):
        if self._running:
            return
        selected = [(wid, name) for wid, (var, name) in self.common_checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No apps selected.")
            return
        self._run_installs(selected, self.common_bar, self.common_status)

    def _install_team(self):
        if self._running:
            return
        selected = [(wid, name) for wid, (var, name) in self.team_checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No apps selected.")
            return
        self._run_installs(selected, self.team_bar, self.team_status)

    def _run_installs(self, apps, bar, status_label):
        self._running = True
        self._set_all_buttons("disabled")
        total = len(apps)
        bar.set(0)
        status_label.configure(text=f"Starting {total} installs...")
        self._append_output(f"Installing {total} app(s)...")
        log(f"Apps: installing {total} apps")

        def task():
            succeeded = 0
            failed = 0
            for i, (winget_id, name) in enumerate(apps):
                _t = f"Installing {i + 1}/{total}: {name}"
                self.after(0, lambda t=_t: status_label.configure(text=t))
                self._safe_append(f"Installing {name}...")
                log(f"Installing {name} ({winget_id})")

                rc, _ = run_winget(winget_id, callback=self._safe_append)

                if rc == 0:
                    succeeded += 1
                    self._safe_append(f"  OK: {name}")
                    log(f"Installed {name}", "success")
                else:
                    failed += 1
                    self._safe_append(f"  FAILED: {name} (exit {rc})")
                    log(f"Failed {name}", "error")

                self.after(0, bar.set, (i + 1) / total)

            def finish():
                bar.set(1.0)
                status_label.configure(text=f"Done. {succeeded} ok, {failed} failed.")
                self._set_all_buttons("normal")
                self._running = False
                self._show_done_dialog(succeeded, failed, total, "installed")

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── Uninstall ──────────────────────────────────────────────────

    def _uninstall_selected(self):
        if self._running:
            return
        selected = [(wid, name) for wid, (var, name) in self.uninstall_checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No apps selected for uninstall.")
            return

        self._running = True
        self._set_all_buttons("disabled")
        total = len(selected)
        self.uninstall_bar.set(0)
        self.uninstall_status.configure(text=f"Starting uninstall of {total} app(s)...")
        self._append_output(f"Uninstalling {total} app(s)...")
        log(f"Apps: uninstalling {total} apps")

        def task():
            succeeded = 0
            failed = 0
            for i, (winget_id, name) in enumerate(selected):
                _t = f"Uninstalling {i + 1}/{total}: {name}"
                self.after(0, lambda t=_t: self.uninstall_status.configure(text=t))
                self._safe_append(f"Uninstalling {name}...")
                log(f"Uninstalling {name} ({winget_id})")

                rc, _ = run_winget_uninstall(winget_id, callback=self._safe_append)

                if rc == 0:
                    succeeded += 1
                    self._safe_append(f"  OK: {name}")
                    log(f"Uninstalled {name}", "success")
                else:
                    failed += 1
                    self._safe_append(f"  FAILED: {name} (exit {rc})")
                    log(f"Uninstall failed {name}", "error")

                self.after(0, self.uninstall_bar.set, (i + 1) / total)

            def finish():
                self.uninstall_bar.set(1.0)
                self.uninstall_status.configure(text=f"Done. {succeeded} ok, {failed} failed.")
                self._set_all_buttons("normal")
                self._running = False
                self._show_done_dialog(succeeded, failed, total, "uninstalled")

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()
