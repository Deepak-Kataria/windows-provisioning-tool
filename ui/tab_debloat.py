import customtkinter as ctk
import json
import os
import threading
from collections import defaultdict
from modules.runner import run_powershell
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class DebloatTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.checkboxes = {}
        self.reinstall_checkboxes = {}
        self._running = False
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "debloat_list.json")) as f:
            self.debloat_data = json.load(f)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # ── Remove section ─────────────────────────────────────────
        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Debloat Windows",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(header, text="Select apps to remove. Use Rollback below to reinstall if needed.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")
        ctk.CTkButton(btn_frame, text="Select All", width=110,
                       command=self._select_all).grid(row=0, column=0, padx=4)
        ctk.CTkButton(btn_frame, text="Deselect All", width=110,
                       command=self._deselect_all).grid(row=0, column=1, padx=4)

        # Scrollable app list grouped by category
        scroll = ctk.CTkScrollableFrame(self, height=240)
        scroll.grid(row=1, column=0, padx=20, pady=(6, 0), sticky="ew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)
        scroll.grid_columnconfigure(2, weight=1)

        grouped = defaultdict(list)
        for app in self.debloat_data["appx_packages"]:
            grouped[app.get("category", "Other")].append(app)

        row = 0
        for category, apps in grouped.items():
            ctk.CTkLabel(scroll, text=category,
                          font=ctk.CTkFont(size=12, weight="bold"),
                          text_color="#4FC3F7").grid(
                row=row, column=0, columnspan=3, sticky="w", padx=8, pady=(10, 2))
            row += 1
            col = 0
            for app in apps:
                var = ctk.BooleanVar(value=True)
                ctk.CTkCheckBox(scroll, text=app["name"], variable=var).grid(
                    row=row, column=col, sticky="w", padx=8, pady=2)
                self.checkboxes[app["package"]] = var
                col += 1
                if col == 3:
                    col = 0
                    row += 1
            if col != 0:
                row += 1

        self.remove_btn = ctk.CTkButton(self, text="Remove Selected Apps",
                                         fg_color="#E53935", hover_color="#B71C1C",
                                         command=self._remove_apps)
        self.remove_btn.grid(row=2, column=0, padx=20, pady=(8, 2), sticky="w")

        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.grid(row=3, column=0, padx=20, pady=(0, 4), sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=12)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)
        self.progress_label = ctk.CTkLabel(progress_frame, text="",
                                            font=ctk.CTkFont(size=11), anchor="w")
        self.progress_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # ── Rollback / Reinstall section ───────────────────────────
        rb_card = ctk.CTkFrame(self)
        rb_card.grid(row=4, column=0, padx=20, pady=(8, 0), sticky="ew")
        rb_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(rb_card, text="Rollback / Reinstall Apps",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(14, 2))
        ctk.CTkLabel(rb_card, text="Select apps to reinstall via Microsoft Store (winget).",
                      text_color="gray", font=ctk.CTkFont(size=11)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        rb_scroll = ctk.CTkScrollableFrame(rb_card, height=120)
        rb_scroll.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")
        rb_scroll.grid_columnconfigure(0, weight=1)
        rb_scroll.grid_columnconfigure(1, weight=1)
        rb_scroll.grid_columnconfigure(2, weight=1)

        col = 0
        rb_row = 0
        for app in self.debloat_data["appx_packages"]:
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(rb_scroll, text=app["name"], variable=var).grid(
                row=rb_row, column=col, sticky="w", padx=8, pady=3)
            self.reinstall_checkboxes[app["package"]] = (var, app["name"])
            col += 1
            if col == 3:
                col = 0
                rb_row += 1

        rb_btn_row = ctk.CTkFrame(rb_card, fg_color="transparent")
        rb_btn_row.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="w")
        self.reinstall_btn = ctk.CTkButton(rb_btn_row, text="Reinstall Selected",
                                            fg_color="#FF8F00", hover_color="#E65100",
                                            command=self._reinstall_apps)
        self.reinstall_btn.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(rb_btn_row, text="Select All", width=90,
                       command=lambda: [v.set(True) for v, _ in self.reinstall_checkboxes.values()]).grid(
            row=0, column=1, padx=4)
        ctk.CTkButton(rb_btn_row, text="Deselect All", width=90,
                       command=lambda: [v.set(False) for v, _ in self.reinstall_checkboxes.values()]).grid(
            row=0, column=2, padx=4)

        rb_prog = ctk.CTkFrame(rb_card, fg_color="transparent")
        rb_prog.grid(row=4, column=0, padx=16, pady=(0, 12), sticky="ew")
        rb_prog.grid_columnconfigure(0, weight=1)
        self.reinstall_bar = ctk.CTkProgressBar(rb_prog, height=12)
        self.reinstall_bar.grid(row=0, column=0, sticky="ew")
        self.reinstall_bar.set(0)
        self.reinstall_status = ctk.CTkLabel(rb_prog, text="",
                                              font=ctk.CTkFont(size=11), anchor="w")
        self.reinstall_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # ── Output ─────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=5, column=0, padx=20, pady=(8, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=110, state="disabled")
        self.output_box.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="ew")

    # ── Helpers ────────────────────────────────────────────────────

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

    def _set_buttons(self, state):
        self.remove_btn.configure(state=state)
        self.reinstall_btn.configure(state=state)

    def _show_done_dialog(self, title, summary):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("360x200")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        ctk.CTkLabel(dialog, text=title,
                      font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(24, 8))
        ctk.CTkLabel(dialog, text=summary, font=ctk.CTkFont(size=13),
                      justify="left").pack(pady=(0, 16))
        ctk.CTkButton(dialog, text="OK", width=100, command=dialog.destroy).pack()

    # ── Remove ─────────────────────────────────────────────────────

    def _remove_apps(self):
        if self._running:
            return
        selected = [pkg for pkg, var in self.checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No apps selected.")
            return

        self._running = True
        self._set_buttons("disabled")
        self.progress_bar.set(0)
        self.progress_label.configure(text=f"Starting {len(selected)} apps...")
        self._append_output(f"Removing {len(selected)} apps...")
        log(f"Debloat: removing {len(selected)} apps")

        total = len(selected)
        counts = {"removed": 0, "not_found": 0, "errors": 0, "done": 0}

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
            self.after(0, self._append_output, line)
            frac = counts["done"] / total
            self.after(0, self.progress_bar.set, frac)
            _t = f"Processing {counts['done']} / {total}"
            self.after(0, lambda t=_t: self.progress_label.configure(text=t))

        def task():
            rc, _ = run_powershell("debloat.ps1",
                                    ["-Packages", ",".join(selected)],
                                    callback=on_line)
            log(f"Debloat rc={rc} removed={counts['removed']} "
                f"not_found={counts['not_found']} errors={counts['errors']}")

            def finish():
                self.progress_bar.set(1.0)
                self.progress_label.configure(text="Done.")
                self._set_buttons("normal")
                self._running = False
                self._show_done_dialog("Debloat Complete",
                    f"Removed:   {counts['removed']}\n"
                    f"Not found: {counts['not_found']}\n"
                    f"Errors:    {counts['errors']}\n"
                    f"Total:     {total}")
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── Reinstall ──────────────────────────────────────────────────

    def _reinstall_apps(self):
        if self._running:
            return
        selected = [{"name": name, "package": pkg}
                    for pkg, (var, name) in self.reinstall_checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No apps selected for reinstall.")
            return

        self._running = True
        self._set_buttons("disabled")
        self.reinstall_bar.set(0)
        self.reinstall_status.configure(text=f"Starting reinstall of {len(selected)} app(s)...")
        self._append_output(f"Reinstalling {len(selected)} app(s) via winget...")
        log(f"Debloat rollback: reinstalling {len(selected)} apps")

        total = len(selected)
        counts = {"ok": 0, "failed": 0, "done": 0}

        def on_line(line):
            if line.startswith("REINSTALLED:"):
                counts["ok"] += 1
                counts["done"] += 1
            elif line.startswith("FAILED:") or line.startswith("ERROR:"):
                counts["failed"] += 1
                counts["done"] += 1
            self.after(0, self._append_output, line)
            self.after(0, self.reinstall_bar.set, counts["done"] / total)
            _t = f"Done {counts['done']} / {total}"
            self.after(0, lambda t=_t: self.reinstall_status.configure(text=t))

        def task():
            rc, _ = run_powershell("reinstall_apps.ps1",
                                    ["-AppsJson", json.dumps(selected)],
                                    callback=on_line)
            log(f"Reinstall rc={rc} ok={counts['ok']} failed={counts['failed']}")

            def finish():
                self.reinstall_bar.set(1.0)
                self.reinstall_status.configure(text="Done.")
                self._set_buttons("normal")
                self._running = False
                self._show_done_dialog("Reinstall Complete",
                    f"Reinstalled: {counts['ok']}\n"
                    f"Failed:      {counts['failed']}\n"
                    f"Total:       {total}\n\n"
                    f"For failed apps, install manually from Microsoft Store.")
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()
