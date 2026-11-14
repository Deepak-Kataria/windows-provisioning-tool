"""Debloat: remove pre-installed Store apps, or reinstall them.

Each app shows whether it is on this PC (read with Get-AppxPackage in the background).
"""
import json
import os
import threading
from collections import defaultdict

import customtkinter as ctk

from modules.appx import installed_appx_names
from modules.logger import log
from modules.runner import run_powershell
from ui import theme as T
from ui.widgets import ActionBar, LogDrawer, confirm_run, section_header, tile_row, tip

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
COLS = 3


class DebloatTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._mode = "remove"            # or "reinstall"
        self._only_relevant = True       # remove: installed only / reinstall: removed only
        self._installed = None           # set of package names; None = not checked yet / failed
        self._scan_failed = False
        self._load_config()
        self.app_names = {a["package"]: a["name"] for a in self.debloat_data["appx_packages"]}
        self._vars = {}                  # package -> BooleanVar
        for pkg in self.app_names:
            var = ctk.BooleanVar(value=False)
            var.trace_add("write", lambda *_: self._update_counts())
            self._vars[pkg] = var
        self._build()
        self._scan_installed()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "debloat_list.json"), encoding="utf-8") as f:
            self.debloat_data = json.load(f)

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        tiles_host = ctk.CTkFrame(self, fg_color="transparent")
        tiles_host.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tiles_host.grid_columnconfigure(0, weight=1)
        row, self._tiles = tile_row(tiles_host, [
            ("Installed now", "…", T.MUTED, "checking this PC…"),
            ("Selected", "0", T.ACCENT, ""),
            ("Not present", "…", T.MUTED, ""),
        ])
        row.grid(row=0, column=0, sticky="ew")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(3, weight=1)
        self._mode_btn = ctk.CTkSegmentedButton(bar, values=["Remove", "Reinstall"],
                                                command=self._set_mode)
        self._mode_btn.set("Remove")
        self._mode_btn.grid(row=0, column=0)
        tip(self._mode_btn, "Remove apps from this PC, or reinstall apps that were removed")
        self._filter_btn = ctk.CTkSegmentedButton(bar, values=["Installed only", "All"],
                                                  command=self._set_filter)
        self._filter_btn.set("Installed only")
        self._filter_btn.grid(row=0, column=1, padx=(12, 0))
        self._rescan_btn = T.outline_button(bar, text="Re-check", width=90, height=28,
                                            command=self._scan_installed)
        self._rescan_btn.grid(row=0, column=2, padx=(12, 0))
        tip(self._rescan_btn, "Read the installed apps from this PC again")
        self._search = ctk.CTkEntry(bar, width=220, height=28, placeholder_text="Search apps…")
        self._search.grid(row=0, column=4, sticky="e")
        self._search.bind("<KeyRelease>", lambda e: self._render())

        self._list = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self._list.grid(row=2, column=0, sticky="nsew")
        for c in range(COLS):
            self._list.grid_columnconfigure(c, weight=1, uniform="app")

        self._log = LogDrawer(self)
        self._log.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        self._action = ActionBar(self)
        self._action.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self._action.button("Select all", self._select_all, outline=True, width=96,
                            tip_text="Tick every app that can be ticked (Ctrl+A)")
        self._action.button("Select none", self._deselect_all, outline=True, width=96,
                            tip_text="Untick every app (Ctrl+Shift+A)")
        self._main_btn = self._action.button("Remove", self._run_main, danger=True, width=170,
                                             tip_text="Run on the ticked apps (Ctrl+Enter). "
                                                      "You'll see the list before anything runs.")
        self._render()

    # ── State ──────────────────────────────────────────────────────

    def _is_installed(self, pkg):
        return None if self._installed is None else pkg in self._installed

    def _selectable(self, pkg):
        """Remove: installed apps only. Reinstall: missing apps only. Anything when unknown."""
        inst = self._is_installed(pkg)
        if inst is None:
            return True
        return inst if self._mode == "remove" else not inst

    def _default_selection(self):
        for pkg, var in self._vars.items():
            var.set(self._mode == "remove" and self._is_installed(pkg) is True)

    def _set_mode(self, value):
        self._mode = "remove" if value == "Remove" else "reinstall"
        first = "Installed only" if self._mode == "remove" else "Removed only"
        self._filter_btn.configure(values=[first, "All"])
        self._filter_btn.set(first if self._only_relevant else "All")
        self._default_selection()
        self._render()

    def _set_filter(self, value):
        self._only_relevant = value != "All"
        self._render()

    def _scan_installed(self):
        self._rescan_btn.configure(state="disabled", text="Checking…")

        def task():
            try:
                names, failed = installed_appx_names(), False
            except Exception as e:
                log(f"Debloat: could not list installed apps: {e}", "warning")
                names, failed = None, True
            try:
                self.after(0, self._apply_scan, names, failed)
            except RuntimeError:
                pass   # window closed meanwhile

        threading.Thread(target=task, daemon=True).start()

    def _apply_scan(self, names, failed):
        if not self.winfo_exists():
            return
        self._installed, self._scan_failed = names, failed
        self._rescan_btn.configure(state="normal" if not self._running else "disabled", text="Re-check")
        self._default_selection()
        self._render()

    # ── Render ─────────────────────────────────────────────────────

    def _render(self):
        for w in self._list.winfo_children():
            w.destroy()
        query = self._search.get().strip().lower()
        grouped = defaultdict(list)
        for app in self.debloat_data["appx_packages"]:
            grouped[app.get("category", "Other")].append(app)

        r = 0
        for category, apps in grouped.items():
            shown = [a for a in apps
                     if (not self._only_relevant or self._selectable(a["package"]))
                     and (not query or query in a["name"].lower() or query in a["package"].lower())]
            if not shown:
                continue
            hdr, col = section_header(self._list, category, height=28, accent=T.BORDER)
            hdr.grid(row=r, column=0, columnspan=COLS, sticky="ew", pady=(10 if r else 0, 0))
            n_inst = sum(1 for a in apps if self._is_installed(a["package"]))
            known = self._installed is not None
            ctk.CTkLabel(hdr, text=(f"{n_inst} installed · " if known else "") + f"{len(apps)} listed",
                         font=T.mono(10), text_color=T.MUTED).grid(row=0, column=col, padx=4, sticky="w")
            tick = T.outline_button(hdr, text="tick all", width=64, height=20, font=T.mono(10),
                                    command=lambda s=shown: self._tick_group(s))
            tick.grid(row=0, column=col + 1, padx=8)
            tip(tick, f"Tick or untick every {category} app shown")
            r += 1
            for i, app in enumerate(shown):
                self._app_cell(app, r + i // COLS, i % COLS, (i // COLS) % 2)
            r += (len(shown) + COLS - 1) // COLS

        if r == 0:
            if self._installed is None and not self._scan_failed:
                msg = "Checking which apps are installed on this PC…"
            elif query:
                msg = f"No apps match “{query}”."
            elif self._mode == "remove":
                msg = "None of the listed apps are installed. Nothing to remove."
            else:
                msg = "Every listed app is still installed. Nothing to reinstall."
            ctk.CTkLabel(self._list, text=msg, font=T.ui(12), text_color=T.MUTED).grid(
                row=0, column=0, columnspan=COLS, pady=40)
        self._update_counts()

    def _app_cell(self, app, row, col, band):
        pkg = app["package"]
        cell = ctk.CTkFrame(self._list, fg_color=T.PANEL if band == 0 else T.PANEL_2,
                            corner_radius=0, height=32)
        cell.grid(row=row, column=col, sticky="ew")
        cell.grid_propagate(False)
        cell.grid_columnconfigure(0, weight=1)
        cell.grid_rowconfigure(0, weight=1)
        cb = ctk.CTkCheckBox(cell, text=app["name"], variable=self._vars[pkg], font=T.ui(12),
                             checkbox_width=16, checkbox_height=16,
                             state="normal" if self._selectable(pkg) else "disabled")
        cb.grid(row=0, column=0, sticky="w", padx=(10, 4))
        tip(cb, pkg)
        inst = self._is_installed(pkg)
        if inst:
            text, color = "INSTALLED", T.WARN
        elif inst is False:
            text, color = "NOT PRESENT", T.DIM
        else:
            text, color = "", T.DIM
        ctk.CTkLabel(cell, text=text, font=T.mono(9, "bold"), text_color=color).grid(
            row=0, column=1, padx=(0, 10))

    def _tick_group(self, apps):
        targets = [a["package"] for a in apps if self._selectable(a["package"])]
        new = not all(self._vars[p].get() for p in targets)
        for p in targets:
            self._vars[p].set(new)

    def _selected(self):
        return [p for p, v in self._vars.items() if v.get() and self._selectable(p)]

    def _update_counts(self):
        if not hasattr(self, "_main_btn") or not self.winfo_exists():
            return
        total = len(self.app_names)
        if self._installed is None:
            if self._scan_failed:
                self._tiles["Installed now"].set("?", T.MUTED, "could not check: tick apps manually")
                self._tiles["Not present"].set("?", T.MUTED, "")
            else:
                self._tiles["Installed now"].set("…", T.MUTED, "checking this PC…")
                self._tiles["Not present"].set("…", T.MUTED, "")
        else:
            n = sum(1 for p in self.app_names if p in self._installed)
            self._tiles["Installed now"].set(n, T.WARN if n else T.OK, f"of {total} apps on the list")
            self._tiles["Not present"].set(total - n, T.OK, "already removed or never installed")
        sel = len(self._selected())
        rem = self._mode == "remove"
        self._tiles["Selected"].set(sel, T.FAIL if rem and sel else T.ACCENT,
                                    "will be removed" if rem else "will be reinstalled")
        if self._running:
            return
        noun = "app" if sel == 1 else "apps"
        self._main_btn.configure(
            text=f"Remove {sel} {noun}" if rem else f"Reinstall {sel} {noun}",
            fg_color=T.DANGER if rem else T.ACCENT,
            hover_color=T.DANGER_HOVER if rem else T.ACCENT_HOVER,
            text_color=T.ON_COLOR if rem else T.ACCENT_TEXT,
            state="normal" if sel else "disabled")
        if sel:
            self._action.set_summary(f"{sel} {noun} selected for {'removal' if rem else 'reinstall'}")
        else:
            self._action.set_summary("Tick the apps to remove" if rem
                                     else "Tick removed apps to reinstall them")

    # ── Helpers ────────────────────────────────────────────────────

    def _select_all(self):
        for p, v in self._vars.items():
            if self._selectable(p):
                v.set(True)

    def _deselect_all(self):
        for v in self._vars.values():
            v.set(False)

    # Keyboard shortcuts (see ui/widgets.py)
    shortcut_select_all = _select_all
    shortcut_deselect_all = _deselect_all

    def shortcut_apply(self):
        self._run_main()

    def _run_main(self):
        if self._mode == "remove":
            self._remove_apps()
        else:
            self._reinstall_apps()

    def _append_output(self, text):
        self._log.append(text)

    def _set_running(self, running):
        self._running = running
        state = "disabled" if running else "normal"
        for w in (self._main_btn, self._mode_btn, self._rescan_btn):
            w.configure(state=state)
        if not running:
            self._action.progress(None)
            self._update_counts()

    def _show_done_dialog(self, title, summary):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("360x240")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        dialog.after(60, lambda: dialog.winfo_exists() and dialog.grab_set())
        dialog.lift()
        dialog.focus_force()
        ctk.CTkLabel(dialog, text="▸  " + title.upper(), font=T.mono(13, "bold"),
                     text_color=T.ACCENT).pack(pady=(22, 10))
        ctk.CTkLabel(dialog, text=summary, font=T.mono(12), justify="left").pack(pady=(0, 12))
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(pady=(0, 16))
        ctk.CTkButton(btn_row, text="OK", width=100, command=dialog.destroy).grid(row=0, column=0, padx=6)
        T.outline_button(btn_row, text="Copy", width=80,
                         command=lambda: (dialog.clipboard_clear(),
                                          dialog.clipboard_append(f"{title}\n\n{summary}"))
                         ).grid(row=0, column=1, padx=6)
        dialog.bind("<Return>", lambda e: dialog.destroy())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    # ── Remove ─────────────────────────────────────────────────────

    def _remove_apps(self):
        if self._running:
            return
        selected = self._selected()
        if not selected:
            self._append_output("No apps selected.")
            return
        if not confirm_run(self, "Remove apps?",
                           f"These {len(selected)} app(s) will be uninstalled for all users:",
                           [self.app_names.get(p, p) for p in selected],
                           action_text=f"Remove {len(selected)} app(s)", danger=True,
                           footer="You can reinstall them later with the Reinstall switch."):
            return

        self._set_running(True)
        total = len(selected)
        self._action.progress(0, f"Removing {total} apps…")
        self._append_output(f"Removing {total} apps...")
        log(f"Debloat: removing {total} apps")

        counts = {"removed": 0, "not_found": 0, "errors": 0, "done": 0}
        state = {"log_file": ""}

        def on_line(line):
            if line.startswith("REMOVED:"):
                counts["removed"] += 1
                counts["done"] += 1
            elif line.startswith("NOT_FOUND:"):
                counts["not_found"] += 1
                counts["done"] += 1
            elif line.startswith("ERROR:"):
                counts["errors"] += 1
                counts["done"] += 1
            elif line.startswith("LOG:"):
                state["log_file"] = line[4:].strip()
            self.after(0, self._append_output, line)
            done = counts["done"]
            self.after(0, self._action.progress, done / total, f"Removing {done} / {total}")

        def task():
            rc, _ = run_powershell("debloat.ps1", ["-Packages", ",".join(selected)], callback=on_line)
            log(f"Debloat rc={rc} removed={counts['removed']} "
                f"not_found={counts['not_found']} errors={counts['errors']}")

            def finish():
                self._set_running(False)
                self._scan_installed()
                log_note = f"\n\nLog saved to:\n{state['log_file']}" if state["log_file"] else ""
                self._show_done_dialog("Debloat complete",
                                       f"Removed:   {counts['removed']}\n"
                                       f"Not found: {counts['not_found']}\n"
                                       f"Errors:    {counts['errors']}\n"
                                       f"Total:     {total}{log_note}")
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── Reinstall ──────────────────────────────────────────────────

    def _reinstall_apps(self):
        if self._running:
            return
        selected = [{"name": self.app_names[p], "package": p} for p in self._selected()]
        if not selected:
            self._append_output("No apps selected for reinstall.")
            return
        if not confirm_run(self, "Reinstall apps?",
                           f"These {len(selected)} app(s) will be reinstalled via winget:",
                           [a["name"] for a in selected],
                           action_text=f"Reinstall {len(selected)} app(s)"):
            return

        self._set_running(True)
        total = len(selected)
        self._action.progress(0, f"Reinstalling {total} apps…")
        self._append_output(f"Reinstalling {total} app(s) via winget...")
        log(f"Debloat rollback: reinstalling {total} apps")

        counts = {"ok": 0, "failed": 0, "done": 0}

        def on_line(line):
            if line.startswith("REINSTALLED:"):
                counts["ok"] += 1
                counts["done"] += 1
            elif line.startswith("FAILED:") or line.startswith("ERROR:"):
                counts["failed"] += 1
                counts["done"] += 1
            self.after(0, self._append_output, line)
            done = counts["done"]
            self.after(0, self._action.progress, done / total, f"Reinstalling {done} / {total}")

        def task():
            rc, _ = run_powershell("reinstall_apps.ps1", ["-AppsJson", json.dumps(selected)],
                                   callback=on_line)
            log(f"Reinstall rc={rc} ok={counts['ok']} failed={counts['failed']}")

            def finish():
                self._set_running(False)
                self._scan_installed()
                self._show_done_dialog("Reinstall complete",
                                       f"Reinstalled: {counts['ok']}\n"
                                       f"Failed:      {counts['failed']}\n"
                                       f"Total:       {total}\n\n"
                                       f"For failed apps, install manually from Microsoft Store.")
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()
