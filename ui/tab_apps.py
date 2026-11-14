"""Apps: install standard, team and local software in one table.

Each app shows whether it's already installed: a fast registry check first, then
`winget export` in the background for exact IDs and versions.
"""
import json
import os
import re
import threading
import tkinter as tk

import customtkinter as ctk

from modules.installed_apps import match_registry, registry_programs, winget_installed
from modules.logger import log
from modules.runner import run_local_installer, run_winget, run_winget_uninstall
from modules.utils import resolve_installer_path
from ui import theme as T
from ui.widgets import ActionBar, LogDrawer, confirm_run, tile_row, tip

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

_DL_RE = re.compile(
    r'([\d,]+\.?\d*)\s*(B|KB|MB|GB)\s*/\s*([\d,]+\.?\d*)\s*(B|KB|MB|GB)',
    re.IGNORECASE
)
_UNITS = {'B': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3}
_COLS = (30, 230, 260, 70, 150)   # tick, app, source, list, status (px, unscaled); menu stretches
_LIST_COLOR = {"COMMON": "MUTED", "TEAM": "INFO", "LOCAL": "WARN"}


def _to_bytes(val_str, unit):
    return float(val_str.replace(',', '')) * _UNITS[unit.upper()]


class AppsTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._stop_requested = False
        self._current_process = None
        self._vars = {}           # key -> BooleanVar (kept across filter / team changes)
        self._entries = []        # [{"key", "app", "list"}] for common + current team + local
        self._reg = None          # registry programs [(name, ver)]
        self._wg = None           # {winget_id_lower: version} once winget export finishes
        self._wg_state = "idle"   # idle / running / done / failed
        self._filter = "All"
        self._load_config()
        self.team_var = ctk.StringVar(value=list(self.teams_data["teams"].keys())[0])
        self._build()
        self._rebuild_entries()
        self._check_installed()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "apps_common.json"), encoding="utf-8") as f:
            self.common_data = json.load(f)
        with open(os.path.join(CONFIG_DIR, "apps_teams.json"), encoding="utf-8") as f:
            self.teams_data = json.load(f)
        local_path = os.path.join(CONFIG_DIR, "apps_local.json")
        if os.path.exists(local_path):
            with open(local_path, encoding="utf-8") as f:
                self.local_data = json.load(f)
        else:
            self.local_data = {"local_apps": []}

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        tiles_host = ctk.CTkFrame(self, fg_color="transparent")
        tiles_host.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tiles_host.grid_columnconfigure(0, weight=1)
        row, self._tiles = tile_row(tiles_host, [
            ("Selected", "0", T.ACCENT, "will be installed"),
            ("Already installed", "…", T.MUTED, "checking this PC…"),
            ("Team", self.team_var.get(), T.INFO, ""),
            ("Local installers", "0", T.DIM, ""),
        ])
        row.grid(row=0, column=0, sticky="ew")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(3, weight=1)
        self._filter_btn = ctk.CTkSegmentedButton(bar, values=["All", "Common", "Team", "Local"],
                                                  command=self._set_filter)
        self._filter_btn.set("All")
        self._filter_btn.grid(row=0, column=0)
        tip(self._filter_btn, "Show all apps, or only one list")
        ctk.CTkLabel(bar, text="TEAM", font=T.mono(10), text_color=T.MUTED).grid(
            row=0, column=1, padx=(16, 6))
        self._team_btn = ctk.CTkSegmentedButton(bar, values=list(self.teams_data["teams"].keys()),
                                                variable=self.team_var, command=self._on_team_change)
        self._team_btn.grid(row=0, column=2, sticky="w")
        tip(self._team_btn, "Team preset: which role apps are listed")
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=4, sticky="e")
        self._recheck_btn = T.outline_button(right, text="Re-check", width=86, height=28,
                                             command=self._check_installed)
        self._recheck_btn.grid(row=0, column=0)
        tip(self._recheck_btn, "Check again which apps are installed")
        if self.role == "admin":
            tip(T.outline_button(right, text="+ Local installer", width=130, height=28,
                                 command=self._add_local_app_dialog),
                "Add an .exe / .msi from this PC or a network share").grid(row=0, column=1, padx=(8, 0))

        table = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0)
        table.grid(row=2, column=0, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        self._rows = ctk.CTkScrollableFrame(table, fg_color="transparent", corner_radius=0)
        self._rows.grid(row=0, column=0, sticky="nsew")
        self._rows.grid_columnconfigure(0, weight=1)

        # Download line (hidden until a winget download reports progress)
        self.dl_frame = ctk.CTkFrame(self, fg_color=T.PANEL_2, corner_radius=0)
        self.dl_frame.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.dl_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.dl_frame, text="DOWNLOADING", font=T.mono(9, "bold"), text_color=T.DIM).grid(
            row=0, column=0, padx=(12, 8), pady=6)
        self.dl_app_label = ctk.CTkLabel(self.dl_frame, text="", font=T.ui(12), anchor="w")
        self.dl_app_label.grid(row=0, column=1, sticky="w")
        self.dl_size_label = ctk.CTkLabel(self.dl_frame, text="", font=T.mono(11), text_color=T.MUTED)
        self.dl_size_label.grid(row=0, column=2, padx=12)
        self.dl_bar = ctk.CTkProgressBar(self.dl_frame, height=4, corner_radius=0)
        self.dl_bar.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.dl_bar.set(0)
        self.dl_frame.grid_remove()

        self._log = LogDrawer(self)
        self._log.grid(row=4, column=0, sticky="ew", pady=(6, 0))

        self._action = ActionBar(self)
        self._action.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        self._action.button("Select all", self._select_all, outline=True, width=96,
                            tip_text="Tick every app shown (Ctrl+A)")
        self._action.button("Select none", self._deselect_all, outline=True, width=96,
                            tip_text="Untick every app (Ctrl+Shift+A)")
        self.stop_btn = self._action.button("Stop", self._stop_install, danger=True, width=70,
                                            state="disabled",
                                            tip_text="Cancel after the current app finishes")
        self._install_btn = self._action.button("Install", self._install_selected, width=160,
                                                tip_text="Install the ticked apps (Ctrl+Enter). "
                                                         "You'll see the list first.")

    @staticmethod
    def _layout_cols(frame):
        scale = ctk.ScalingTracker.get_widget_scaling(frame)
        for i, w in enumerate(_COLS):
            frame.grid_columnconfigure(i, minsize=round(w * scale))
        frame.grid_columnconfigure(len(_COLS), weight=1)

    # ── Entries / state ────────────────────────────────────────────

    def _rebuild_entries(self):
        team = self.team_var.get()
        entries = [{"key": f"common:{a.get('winget_id', a['name'])}", "app": a, "list": "COMMON"}
                   for a in self.common_data["common_apps"]]
        entries += [{"key": f"team:{a.get('winget_id', a['name'])}", "app": a, "list": "TEAM"}
                    for a in self.teams_data["teams"].get(team, [])]
        entries += [{"key": f"local:{a['name']}", "app": a, "list": "LOCAL"}
                    for a in self.local_data.get("local_apps", [])]
        self._entries = entries
        for e in entries:
            if e["key"] not in self._vars:
                var = ctk.BooleanVar(value=self._installed_version(e) is None and self._known())
                var.trace_add("write", lambda *_: self._update_counts())
                self._vars[e["key"]] = var
        self._render()

    def _known(self):
        return self._reg is not None

    def _installed_version(self, entry):
        """Version string ('' if unknown) when installed, None when not (or not checked yet)."""
        app = entry["app"]
        if self._wg is not None and app.get("winget_id"):
            v = self._wg.get(app["winget_id"].lower())
            if v is not None:
                return v
        if self._reg is not None:
            return match_registry(app, self._reg)
        return None

    def _check_installed(self):
        """Registry now (instant), winget export in the background."""
        self._reg = registry_programs()
        for e in self._entries:   # default: tick apps that aren't installed yet
            self._vars[e["key"]].set(self._installed_version(e) is None)
        already_running = self._wg_state == "running"
        self._wg_state = "running"
        self._recheck_btn.configure(state="disabled", text="Checking…")
        self._render()
        if already_running:
            return

        def task():
            res = winget_installed()
            try:
                self.after(0, self._apply_winget, res)
            except RuntimeError:
                pass
        threading.Thread(target=task, daemon=True).start()

    def _apply_winget(self, res):
        if not self.winfo_exists():
            return
        self._wg = res if res is not None else self._wg
        self._wg_state = "done" if res is not None else "failed"
        self._recheck_btn.configure(state="normal", text="Re-check")
        for e in self._entries:   # untick anything winget found that the registry missed
            if self._installed_version(e) is not None and self._vars[e["key"]].get():
                self._vars[e["key"]].set(False)
        self._render()

    def _set_filter(self, value):
        self._filter = value
        self._render()

    def _on_team_change(self, team_name):
        self._rebuild_entries()

    def _visible(self):
        f = self._filter.upper()
        return [e for e in self._entries if f == "ALL" or e["list"] == f]

    # ── Render ─────────────────────────────────────────────────────

    def _render(self):
        for w in self._rows.winfo_children():
            w.destroy()
        head = ctk.CTkFrame(self._rows, fg_color=T.PANEL_2, corner_radius=0, height=26)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_propagate(False)
        head.grid_rowconfigure(0, weight=1)
        self._layout_cols(head)
        for i, text in enumerate(["", "APP", "SOURCE", "LIST", "STATUS"]):
            ctk.CTkLabel(head, text=text, font=T.mono(9, "bold"), text_color=T.DIM,
                         anchor="w").grid(row=0, column=i, sticky="w", padx=(10 if i == 0 else 0, 0))

        visible = self._visible()
        for i, e in enumerate(visible):
            self._add_row(i + 1, e)
        if not visible:
            msg = ("No local installers yet." + (" Click “+ Local installer” to add one."
                                                 if self.role == "admin" else "")
                   if self._filter == "Local" else "No apps in this list.")
            ctk.CTkLabel(self._rows, text=msg, font=T.ui(12), text_color=T.MUTED).grid(
                row=1, column=0, pady=30)
        self._update_counts()

    def _add_row(self, r, entry):
        app, lst = entry["app"], entry["list"]
        ver = self._installed_version(entry)
        installed = ver is not None
        row = ctk.CTkFrame(self._rows, fg_color=T.PANEL if r % 2 else T.PANEL_2, corner_radius=0,
                           height=32)
        row.grid(row=r, column=0, sticky="ew")
        row.grid_propagate(False)
        row.grid_rowconfigure(0, weight=1)
        self._layout_cols(row)
        ctk.CTkCheckBox(row, text="", variable=self._vars[entry["key"]], width=20,
                        checkbox_width=16, checkbox_height=16).grid(row=0, column=0, padx=(10, 0), sticky="w")
        ctk.CTkLabel(row, text=app["name"], font=T.ui(12, "bold"),
                     text_color=T.MUTED if installed else T.TEXT_BRIGHT, anchor="w").grid(
            row=0, column=1, sticky="w")
        source = app.get("winget_id") or app.get("installer", "")
        src_lbl = ctk.CTkLabel(row, text=source if len(source) <= 34 else "…" + source[-33:],
                               font=T.mono(10), text_color=T.MUTED, anchor="w")
        src_lbl.grid(row=0, column=2, sticky="w")
        tip(src_lbl, source)
        ctk.CTkLabel(row, text=lst, font=T.mono(9, "bold"),
                     text_color=getattr(T, _LIST_COLOR[lst])).grid(row=0, column=3, sticky="w")
        if installed:
            text, color = (f"INSTALLED {ver}" if ver else "INSTALLED"), T.OK
        elif self._reg is None:
            text, color = "…", T.DIM
        else:
            text, color = "NOT INSTALLED", T.DIM
        ctk.CTkLabel(row, text=text[:22], font=T.mono(9, "bold"), text_color=color, anchor="w").grid(
            row=0, column=4, sticky="w")
        more = T.outline_button(row, text="⋯", width=30, height=22, border_width=0,
                                command=lambda e=entry: None)
        more.configure(command=lambda e=entry, b=more: self._row_menu(e, b))
        more.grid(row=0, column=5, sticky="e", padx=10)
        tip(more, "More actions")

    def _row_menu(self, entry, button):
        app = entry["app"]
        menu = tk.Menu(self, tearoff=0, bg=T.PANEL_2, fg=T.TEXT, activebackground=T.PANEL_3,
                       activeforeground=T.TEXT_BRIGHT, bd=0)
        if app.get("winget_id"):
            menu.add_command(label=f"Uninstall {app['name']}…",
                             command=lambda: self._uninstall_single(app["winget_id"], app["name"]))
        if entry["list"] == "LOCAL" and self.role == "admin":
            menu.add_command(label="Remove from local list", command=lambda: self._remove_local_app(app))
        if menu.index("end") is None:
            menu.add_command(label="No actions", state="disabled")
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

    def _selected(self):
        return [e for e in self._entries if self._vars[e["key"]].get()]

    def _update_counts(self):
        if not hasattr(self, "_install_btn") or not self.winfo_exists():
            return
        sel = self._selected()
        listed = [e for e in self._entries if e["list"] != "LOCAL"]
        inst = [e for e in listed if self._installed_version(e) is not None]
        reinstall = sum(1 for e in sel if self._installed_version(e) is not None)
        self._tiles["Selected"].set(len(sel), T.ACCENT,
                                    f"{reinstall} already installed" if reinstall else "will be installed")
        if self._reg is None:
            self._tiles["Already installed"].set("…", T.MUTED, "checking this PC…")
        else:
            note = {"running": " · refining with winget…", "failed": " · winget unavailable"}.get(self._wg_state, "")
            self._tiles["Already installed"].set(len(inst), T.OK if inst else T.MUTED,
                                                 f"of {len(listed)} listed apps{note}")
        team = self.team_var.get()
        self._tiles["Team"].set(team if len(team) <= 14 else team[:13] + "…", T.INFO,
                                f"{len(self.teams_data['teams'].get(team, []))} apps in this preset")
        n_local = len(self.local_data.get("local_apps", []))
        self._tiles["Local installers"].set(n_local, T.WARN if n_local else T.DIM,
                                            "configured" if n_local else "none configured")
        if self._running:
            return
        noun = "app" if len(sel) == 1 else "apps"
        self._install_btn.configure(text=f"Install {len(sel)} {noun}", state="normal" if sel else "disabled")
        hidden = len(sel) - len([e for e in sel if e in self._visible()])
        if sel:
            extra = f" · {reinstall} already installed (will reinstall)" if reinstall else ""
            extra += f" · {hidden} in other lists" if hidden else ""
            self._action.set_summary(f"{len(sel)} {noun} selected{extra}")
        else:
            self._action.set_summary("Tick the apps to install")

    # ── Helpers ────────────────────────────────────────────────────

    def _select_all(self):
        for e in self._visible():
            self._vars[e["key"]].set(True)

    def _deselect_all(self):
        for v in self._vars.values():
            v.set(False)

    # Keyboard shortcuts (see ui/widgets.py)
    shortcut_select_all = _select_all
    shortcut_deselect_all = _deselect_all

    def shortcut_apply(self):
        self._install_selected()

    def _show_dl_frame(self, app_name):
        self.dl_app_label.configure(text=app_name)
        self.dl_bar.set(0)
        self.dl_size_label.configure(text="")
        self.dl_frame.grid()

    def _hide_dl_frame(self):
        self.dl_frame.grid_remove()

    def _update_dl_bar(self, pct, size_text):
        self.dl_bar.set(pct)
        self.dl_size_label.configure(text=size_text)

    def _make_dl_callback(self, name):
        def cb(line):
            m = _DL_RE.search(line)
            if m:
                try:
                    cur = _to_bytes(m.group(1), m.group(2))
                    tot = _to_bytes(m.group(3), m.group(4))
                    pct = min(cur / tot, 1.0) if tot > 0 else 0
                    size_text = f"{m.group(1)} {m.group(2)} / {m.group(3)} {m.group(4)}"
                    self.after(0, self._update_dl_bar, pct, size_text)
                except Exception:
                    pass
            else:
                self._safe_append(line)
        return cb

    def _append_output(self, text):
        self._log.append(text)

    def _safe_append(self, text):
        self.after(0, self._append_output, text)

    def _set_running(self, running):
        self._running = running
        self._install_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self._team_btn.configure(state="disabled" if running else "normal")
        if not running:
            self._action.progress(None)
            self._update_counts()

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
        dialog.geometry("320x190")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        dialog.after(60, lambda: dialog.winfo_exists() and dialog.grab_set())
        dialog.lift()
        dialog.focus_force()
        ctk.CTkLabel(dialog, text="▸  " + action.upper(), font=T.mono(13, "bold"),
                     text_color=T.ACCENT).pack(pady=(22, 8))
        body = f"Succeeded: {succeeded}\nFailed:    {failed}\nTotal:     {total}"
        ctk.CTkLabel(dialog, text=body, font=T.mono(12), justify="left").pack(pady=(0, 14))
        ctk.CTkButton(dialog, text="OK", width=90, command=dialog.destroy).pack()
        dialog.bind("<Return>", lambda e: dialog.destroy())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    # ── Local app management (admin only) ─────────────────────────

    def _refresh_local_apps(self):
        self._rebuild_entries()

    def _add_local_app_dialog(self):
        from tkinter import filedialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Local App")
        dialog.geometry("500x230")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        dialog.after(60, lambda: dialog.winfo_exists() and dialog.grab_set())
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

        err_label = ctk.CTkLabel(dialog, text="", text_color=T.FAIL, font=ctk.CTkFont(size=11))
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
        T.outline_button(btn_row, text="Cancel", width=100, command=dialog.destroy).grid(row=0, column=1, padx=8)

    def _remove_local_app(self, app):
        self.local_data["local_apps"] = [
            a for a in self.local_data.get("local_apps", []) if a["name"] != app["name"]]
        self._save_local_apps()
        self._refresh_local_apps()

    def _save_local_apps(self):
        path = os.path.join(CONFIG_DIR, "apps_local.json")
        with open(path, "w") as f:
            json.dump(self.local_data, f, indent=4)

    def _remove_local_app(self, app):
        if not confirm_run(self, "Remove local installer", "This entry will be removed from the list "
                           "(the installer file itself is not deleted):", [app["name"]],
                           action_text="Remove"):
            return
        self.local_data["local_apps"] = [
            a for a in self.local_data.get("local_apps", []) if a["name"] != app["name"]]
        self._save_local_apps()
        self._refresh_local_apps()

    # ── Install ────────────────────────────────────────────────────

    def _install_selected(self):
        if self._running:
            return
        entries = self._selected()
        if not entries:
            self._append_output("No apps selected.")
            return
        items = []
        for e in entries:
            ver = self._installed_version(e)
            items.append((e["app"]["name"] + (f"  (already installed {ver})".rstrip() if ver is not None else ""),
                          False))
        if not confirm_run(self, "Install apps?", f"These {len(entries)} app(s) will be installed:",
                           items, action_text=f"Install {len(entries)} app(s)",
                           footer="Local installers may open their own setup window."
                           if any(e["list"] == "LOCAL" for e in entries) else None):
            return
        self._run_installs([e["app"] for e in entries])

    def _run_installs(self, apps):
        self._set_running(True)
        total = len(apps)
        self._action.progress(0, f"Starting {total} installs…")
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
                self.after(0, self._action.progress, i / total, f"Installing {i + 1} / {total}: {name}")
                self._safe_append(f"Installing {name}...")

                holder = []
                if app.get("installer"):
                    path = resolve_installer_path(app["installer"])
                    if not path:
                        self._safe_append(f"  ERROR: Installer not found: {app['installer']}")
                        self._safe_append("  Check the path exists on this machine or network share.")
                        log(f"Installer not found: {app['installer']}", "error")
                        failed += 1
                        continue
                    self._safe_append("  Launching installer — complete setup in popup window...")
                    log(f"Installing {name} (local: {path})")
                    rc, _ = run_local_installer(path, app.get("installer_args"),
                                                callback=self._safe_append, process_holder=holder)
                else:
                    self.after(0, self._show_dl_frame, name)
                    log(f"Installing {name} ({app['winget_id']})")
                    rc, _ = run_winget(app["winget_id"], callback=self._make_dl_callback(name),
                                       process_holder=holder)
                    self.after(0, self._hide_dl_frame)
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

            def finish():
                self._hide_dl_frame()
                self._stop_requested = False
                self._current_process = None
                self._set_running(False)
                self._action.set_summary(f"Done: {succeeded} ok, {failed} failed.",
                                         T.WARN if failed else T.OK)
                self._check_installed()
                self._show_done_dialog(succeeded, failed, total, "installed")

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── Uninstall (from the ⋯ menu) ────────────────────────────────

    def _uninstall_single(self, winget_id, name):
        if self._running:
            self._append_output("Wait for current operation to finish.")
            return
        if not confirm_run(self, "Uninstall app?", "This app will be uninstalled with winget:",
                           [(f"{name}  ({winget_id})", True)], action_text="Uninstall", danger=True):
            return
        self._set_running(True)
        self._action.progress(0.5, f"Uninstalling {name}…")
        self._append_output(f"Uninstalling {name}...")
        log(f"Uninstalling {name} ({winget_id})")

        def task():
            rc, _ = run_winget_uninstall(winget_id, callback=self._safe_append)
            if rc == 0:
                self._safe_append(f"  OK: {name} uninstalled.")
                log(f"Uninstalled {name}", "success")
            else:
                self._safe_append(f"  FAILED: {name} (exit {rc})")
                log(f"Uninstall failed {name}", "error")

            def finish():
                self._set_running(False)
                self._action.set_summary(f"{name} uninstalled." if rc == 0 else f"Uninstall failed: {name} (exit {rc})",
                                         T.OK if rc == 0 else T.FAIL)
                self._check_installed()
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()
