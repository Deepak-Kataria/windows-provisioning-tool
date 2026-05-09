import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_winget, run_winget_uninstall, run_local_installer
from modules.utils import resolve_installer_path
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class AppsTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.common_checkboxes = {}
        self.team_checkboxes = {}
        self.local_checkboxes = {}
        self.uninstall_checkboxes = {}
        self._running = False
        self._stop_requested = False
        self._current_process = None
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "apps_common.json")) as f:
            self.common_data = json.load(f)
        with open(os.path.join(CONFIG_DIR, "apps_teams.json")) as f:
            self.teams_data = json.load(f)
        local_path = os.path.join(CONFIG_DIR, "apps_local.json")
        if os.path.exists(local_path):
            with open(local_path) as f:
                self.local_data = json.load(f)
        else:
            self.local_data = {"local_apps": []}

    # ── Build UI ───────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Scrollable wrapper so output is always reachable
        self._wrap = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._wrap.grid(row=0, column=0, sticky="nsew")
        self._wrap.grid_columnconfigure(0, weight=1)
        self._wrap.grid_columnconfigure(1, weight=1)
        w = self._wrap

        # ── Common Apps card ──────────────────────────────────────
        common_frame = ctk.CTkFrame(w)
        common_frame.grid(row=0, column=0, padx=(10, 4), pady=(10, 4), sticky="nsew")
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
            label = app["name"] + (" [Local]" if "installer" in app else "")
            ctk.CTkCheckBox(scroll_common, text=label, variable=var).grid(
                row=i, column=0, sticky="w", padx=8, pady=3)
            key = app.get("winget_id") or app["name"]
            self.common_checkboxes[key] = (var, app)

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

        # ── Team Apps card ────────────────────────────────────────
        team_frame = ctk.CTkFrame(w)
        team_frame.grid(row=0, column=1, padx=(4, 10), pady=(10, 4), sticky="nsew")
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

        # ── Local / Offline Apps card ─────────────────────────────
        local_frame = ctk.CTkFrame(w)
        local_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="ew")
        local_frame.grid_columnconfigure(0, weight=1)

        local_header = ctk.CTkFrame(local_frame, fg_color="transparent")
        local_header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 2))
        local_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(local_header, text="Local / Offline Apps",
                      font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w")
        if self.role == "admin":
            ctk.CTkButton(local_header, text="+ Add App", width=100,
                           command=self._add_local_app_dialog).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(local_frame, text="Installed from local or network path — no internet required",
                      text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 6))

        self.scroll_local = ctk.CTkScrollableFrame(local_frame, height=120)
        self.scroll_local.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="ew")
        self.scroll_local.grid_columnconfigure(0, weight=1)
        self._refresh_local_apps()

        local_btn_row = ctk.CTkFrame(local_frame, fg_color="transparent")
        local_btn_row.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="w")

        self.local_btn = ctk.CTkButton(local_btn_row, text="Install Local Apps",
                                        command=self._install_local)
        self.local_btn.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(local_btn_row, text="Select All", width=90,
                       command=lambda: [v.set(True) for v, _ in self.local_checkboxes.values()]).grid(
            row=0, column=1, padx=4)
        ctk.CTkButton(local_btn_row, text="Deselect All", width=90,
                       command=lambda: [v.set(False) for v, _ in self.local_checkboxes.values()]).grid(
            row=0, column=2, padx=4)

        local_prog = ctk.CTkFrame(local_frame, fg_color="transparent")
        local_prog.grid(row=4, column=0, padx=16, pady=(0, 12), sticky="ew")
        local_prog.grid_columnconfigure(0, weight=1)
        self.local_bar = ctk.CTkProgressBar(local_prog, height=12)
        self.local_bar.grid(row=0, column=0, sticky="ew")
        self.local_bar.set(0)
        self.local_status = ctk.CTkLabel(local_prog, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.local_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # ── Output ────────────────────────────────────────────────
        output_hdr = ctk.CTkFrame(w, fg_color="transparent")
        output_hdr.grid(row=2, column=0, columnspan=2, padx=10, pady=(4, 2), sticky="ew")
        output_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(output_hdr, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w")
        self.stop_btn = ctk.CTkButton(output_hdr, text="Stop", width=80,
                                       fg_color="#d32f2f", hover_color="#b71c1c",
                                       state="disabled", command=self._stop_install)
        self.stop_btn.grid(row=0, column=1, sticky="e")

        self.output_box = ctk.CTkTextbox(w, height=120, state="disabled")
        self.output_box.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="ew")

        # ── Rollback / Uninstall card ─────────────────────────────
        uninstall_card = ctk.CTkFrame(w)
        uninstall_card.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        uninstall_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(uninstall_card, text="Rollback / Uninstall Apps",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(uninstall_card, text="Select apps to uninstall. All common and team apps listed.",
                      text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        all_apps = {}
        for app in self.common_data["common_apps"]:
            if "winget_id" in app:
                all_apps[app["winget_id"]] = app["name"]
        for apps_list in self.teams_data["teams"].values():
            for app in apps_list:
                if "winget_id" in app:
                    all_apps[app["winget_id"]] = app["name"]

        uninstall_scroll = ctk.CTkScrollableFrame(uninstall_card, height=120)
        uninstall_scroll.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")
        uninstall_scroll.grid_columnconfigure(0, weight=1)

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
            label = app["name"] + (" [Local]" if "installer" in app else "")
            ctk.CTkCheckBox(self.scroll_team, text=label, variable=var).grid(
                row=i, column=0, sticky="w", padx=8, pady=3)
            key = app.get("winget_id") or app["name"]
            self.team_checkboxes[key] = (var, app)

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
        for btn in (self.common_btn, self.team_btn, self.local_btn, self.uninstall_btn):
            btn.configure(state=state)
        self.stop_btn.configure(state="normal" if state == "disabled" else "disabled")

    def _stop_install(self):
        self._stop_requested = True
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass
        self._safe_append("--- Stop requested — cancelling after current app ---")

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

    # ── Local app management (admin only) ─────────────────────────

    def _refresh_local_apps(self):
        for widget in self.scroll_local.winfo_children():
            widget.destroy()
        self.local_checkboxes.clear()
        local_apps = self.local_data.get("local_apps", [])
        if local_apps:
            for idx, app in enumerate(local_apps):
                var = ctk.BooleanVar(value=True)
                row_frame = ctk.CTkFrame(self.scroll_local, fg_color="transparent")
                row_frame.grid(row=idx, column=0, sticky="ew", pady=2)
                ctk.CTkCheckBox(row_frame, text=app["name"], variable=var).grid(
                    row=0, column=0, sticky="w", padx=8)
                if self.role == "admin":
                    ctk.CTkButton(row_frame, text="✕", width=28, height=24,
                                   fg_color="#555555", hover_color="#d32f2f",
                                   command=lambda a=app: self._remove_local_app(a)).grid(
                        row=0, column=1, padx=(4, 0))
                self.local_checkboxes[app["name"]] = (var, app)
        else:
            msg = "No local apps configured. Click '+ Add App' to add one." if self.role == "admin" \
                  else "No local apps configured."
            ctk.CTkLabel(self.scroll_local, text=msg,
                          text_color="gray", font=ctk.CTkFont(size=11)).grid(
                row=0, column=0, sticky="w", padx=8, pady=8)

    def _add_local_app_dialog(self):
        from tkinter import filedialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Local App")
        dialog.geometry("500x230")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        dialog.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dialog, text="App Name:").grid(row=0, column=0, padx=16, pady=(20, 6), sticky="w")
        name_entry = ctk.CTkEntry(dialog, width=300, placeholder_text="e.g. My ERP")
        name_entry.grid(row=0, column=1, columnspan=2, padx=(0, 16), pady=(20, 6), sticky="ew")

        ctk.CTkLabel(dialog, text="Installer Path:").grid(row=1, column=0, padx=16, pady=6, sticky="w")
        path_entry = ctk.CTkEntry(dialog, width=240,
                                   placeholder_text=r"C:\path\setup.exe  or  \\server\share\setup.exe")
        path_entry.grid(row=1, column=1, padx=(0, 4), pady=6, sticky="ew")

        def browse():
            f = filedialog.askopenfilename(
                title="Select Installer",
                filetypes=[("Installers", "*.exe *.msi"), ("All files", "*.*")])
            if f:
                path_entry.delete(0, "end")
                path_entry.insert(0, f)

        ctk.CTkButton(dialog, text="Browse", width=70, command=browse).grid(
            row=1, column=2, padx=(0, 16), pady=6)

        ctk.CTkLabel(dialog, text="Silent Args:").grid(row=2, column=0, padx=16, pady=6, sticky="w")
        args_entry = ctk.CTkEntry(dialog, width=300,
                                   placeholder_text="e.g. /silent  or  /S  or  /quiet /norestart")
        args_entry.grid(row=2, column=1, columnspan=2, padx=(0, 16), pady=6, sticky="ew")

        err_label = ctk.CTkLabel(dialog, text="", text_color="#ff6b6b", font=ctk.CTkFont(size=11))
        err_label.grid(row=3, column=0, columnspan=3, padx=16, pady=(0, 4), sticky="w")

        def confirm():
            name = name_entry.get().strip()
            path = path_entry.get().strip()
            if not name:
                err_label.configure(text="App name required.")
                return
            if not path:
                err_label.configure(text="Installer path required.")
                return
            app = {"name": name, "installer": path}
            raw_args = args_entry.get().strip()
            if raw_args:
                app["installer_args"] = raw_args.split()
            self.local_data.setdefault("local_apps", []).append(app)
            self._save_local_apps()
            self._refresh_local_apps()
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.grid(row=4, column=0, columnspan=3, pady=(4, 16))
        ctk.CTkButton(btn_row, text="Add App", width=100, command=confirm).grid(row=0, column=0, padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=100, fg_color="gray",
                       hover_color="#555555", command=dialog.destroy).grid(row=0, column=1, padx=8)

    def _remove_local_app(self, app):
        self.local_data["local_apps"] = [
            a for a in self.local_data.get("local_apps", []) if a["name"] != app["name"]]
        self._save_local_apps()
        self._refresh_local_apps()

    def _save_local_apps(self):
        path = os.path.join(CONFIG_DIR, "apps_local.json")
        with open(path, "w") as f:
            json.dump(self.local_data, f, indent=4)

    # ── Install (winget) ───────────────────────────────────────────

    def _install_common(self):
        if self._running:
            return
        selected = [app for _, (var, app) in self.common_checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No apps selected.")
            return
        self._run_installs(selected, self.common_bar, self.common_status)

    def _install_team(self):
        if self._running:
            return
        selected = [app for _, (var, app) in self.team_checkboxes.items() if var.get()]
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
            for i, app in enumerate(apps):
                if self._stop_requested:
                    self._safe_append("Installation stopped.")
                    break
                name = app["name"]
                _t = f"Installing {i + 1}/{total}: {name}"
                self.after(0, lambda t=_t: status_label.configure(text=t))
                self._safe_append(f"Installing {name}...")

                holder = []
                if app.get("installer"):
                    path = resolve_installer_path(app["installer"])
                    if not path:
                        self._safe_append(f"  ERROR: Installer not found: {app['installer']}")
                        log(f"Installer not found: {app['installer']}", "error")
                        failed += 1
                        self.after(0, bar.set, (i + 1) / total)
                        continue
                    self._safe_append(f"  Launching installer — complete setup in popup window...")
                    log(f"Installing {name} (local: {path})")
                    rc, _ = run_local_installer(path, app.get("installer_args"),
                                                callback=self._safe_append, process_holder=holder)
                else:
                    log(f"Installing {name} ({app['winget_id']})")
                    rc, _ = run_winget(app["winget_id"], callback=self._safe_append,
                                       process_holder=holder)
                if holder:
                    self._current_process = holder[0]

                if self._stop_requested:
                    self._safe_append("Installation stopped.")
                    break

                if rc == 0:
                    succeeded += 1
                    self._safe_append(f"  OK: {name}")
                    log(f"Installed {name}", "success")
                elif rc == 3010:
                    succeeded += 1
                    self._safe_append(f"  OK: {name} (reboot required to complete)")
                    log(f"Installed {name} — reboot needed", "success")
                else:
                    failed += 1
                    self._safe_append(f"  FAILED: {name} (exit code {rc})")
                    log(f"Failed {name} exit={rc}", "error")

                self.after(0, bar.set, (i + 1) / total)

            def finish():
                bar.set(1.0)
                status_label.configure(text=f"Done. {succeeded} ok, {failed} failed.")
                self._running = False
                self._stop_requested = False
                self._current_process = None
                self._set_all_buttons("normal")
                self._show_done_dialog(succeeded, failed, total, "installed")

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── Install (local) ────────────────────────────────────────────

    def _install_local(self):
        if self._running:
            return
        selected = [app for _, (var, app) in self.local_checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No local apps selected.")
            return

        self._running = True
        self._set_all_buttons("disabled")
        total = len(selected)
        self.local_bar.set(0)
        self.local_status.configure(text=f"Starting {total} installs...")
        self._append_output(f"Installing {total} local app(s)...")
        log(f"Apps: installing {total} local apps")

        def task():
            succeeded = 0
            failed = 0
            for i, app in enumerate(selected):
                if self._stop_requested:
                    self._safe_append("Installation stopped.")
                    break
                name = app["name"]
                _t = f"Installing {i + 1}/{total}: {name}"
                self.after(0, lambda t=_t: self.local_status.configure(text=t))
                self._safe_append(f"Installing {name}...")
                log(f"Installing {name} (local: {app['installer']})")

                path = resolve_installer_path(app["installer"])
                if not path:
                    self._safe_append(f"  ERROR: Installer not found: {app['installer']}")
                    self._safe_append(f"  Check the path exists on this machine or network share.")
                    log(f"Installer not found: {app['installer']}", "error")
                    failed += 1
                    self.after(0, self.local_bar.set, (i + 1) / total)
                    continue

                self._safe_append(f"  Path: {path}")
                self._safe_append(f"  Launching installer — complete setup in popup window...")
                holder = []
                rc, _ = run_local_installer(path, app.get("installer_args"),
                                             callback=self._safe_append, process_holder=holder)
                if holder:
                    self._current_process = holder[0]

                if self._stop_requested:
                    self._safe_append("Installation stopped.")
                    break

                if rc == 0:
                    succeeded += 1
                    self._safe_append(f"  OK: {name} installed successfully.")
                    log(f"Installed {name}", "success")
                elif rc == 3010:
                    succeeded += 1
                    self._safe_append(f"  OK: {name} installed — reboot required to complete.")
                    log(f"Installed {name} — reboot needed", "success")
                else:
                    failed += 1
                    self._safe_append(f"  FAILED: {name} (exit code {rc})")
                    self._safe_append(f"  Check installer path and silent args are correct.")
                    log(f"Failed {name} exit={rc}", "error")

                self.after(0, self.local_bar.set, (i + 1) / total)

            def finish():
                self.local_bar.set(1.0)
                self.local_status.configure(text=f"Done. {succeeded} ok, {failed} failed.")
                self._running = False
                self._stop_requested = False
                self._current_process = None
                self._set_all_buttons("normal")
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
                if self._stop_requested:
                    self._safe_append("Uninstall stopped.")
                    break
                _t = f"Uninstalling {i + 1}/{total}: {name}"
                self.after(0, lambda t=_t: self.uninstall_status.configure(text=t))
                self._safe_append(f"Uninstalling {name}...")
                log(f"Uninstalling {name} ({winget_id})")

                holder = []
                rc, _ = run_winget_uninstall(winget_id, callback=self._safe_append,
                                              process_holder=holder)
                if holder:
                    self._current_process = holder[0]

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
                self._running = False
                self._stop_requested = False
                self._current_process = None
                self._set_all_buttons("normal")
                self._show_done_dialog(succeeded, failed, total, "uninstalled")

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()
