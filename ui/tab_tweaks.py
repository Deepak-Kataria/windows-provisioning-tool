import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_inline_powershell
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class TweaksTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._tweak_vars = {}     # id -> BooleanVar (checkboxes)
        self._pref_vars = {}      # id -> BooleanVar (toggles)
        self._pref_data = {}      # id -> pref dict
        self._tweak_data = {}     # id -> tweak dict
        self._load_config()
        self._build()
        self._load_pref_states()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "tweaks.json"), encoding="utf-8") as f:
            self._config = json.load(f)

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=6)
        self.grid_columnconfigure(1, weight=4)

        # ── Left: Tweaks ───────────────────────────────────────────
        left = ctk.CTkScrollableFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, padx=(12, 4), pady=(12, 4), sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        # Essential
        self._section_label(left, "Essential Tweaks", 0)
        row = 1
        for tweak in self._config["essential"]:
            row = self._add_tweak_row(left, tweak, row)

        # Advanced
        self._section_label(left, "Advanced Tweaks  —  CAUTION", row, color="#FF8F00")
        row += 1
        for tweak in self._config["advanced"]:
            row = self._add_tweak_row(left, tweak, row)

        # Privacy
        self._section_label(left, "Privacy & Tracking", row, color="#CE93D8")
        row += 1
        for tweak in self._config.get("privacy", []):
            row = self._add_tweak_row(left, tweak, row)

        # Org Settings
        self._section_label(left, "Org Settings", row, color="#4FC3F7")
        row += 1
        for tweak in self._config.get("org", []):
            row = self._add_tweak_row(left, tweak, row)

        # Select All / None buttons
        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=row, column=0, sticky="w", padx=8, pady=(10, 4))
        ctk.CTkButton(btn_row, text="Select All", width=100,
                       command=lambda: [v.set(True) for v in self._tweak_vars.values()]).grid(
            row=0, column=0, padx=(0, 6))
        ctk.CTkButton(btn_row, text="Deselect All", width=100,
                       command=lambda: [v.set(False) for v in self._tweak_vars.values()]).grid(
            row=0, column=1)

        # ── Right: Preferences + Performance ──────────────────────
        right = ctk.CTkScrollableFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, padx=(4, 12), pady=(12, 4), sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        self._section_label(right, "Customize Preferences", 0)
        prow = 1
        for pref in self._config["preferences"]:
            prow = self._add_pref_row(right, pref, prow)

        self._section_label(right, "Performance Plans", prow, color="#4FC3F7")
        prow += 1
        perf = self._config["performance"]

        ctk.CTkButton(right, text="Enable Ultimate Performance",
                       fg_color="#2e7d32", hover_color="#1b5e20",
                       command=lambda: self._run_perf(perf["enable_cmd"], "Enable Ultimate Performance")).grid(
            row=prow, column=0, padx=12, pady=(6, 3), sticky="ew")
        prow += 1
        ctk.CTkButton(right, text="Disable / Use Balanced Plan",
                       fg_color="#555555", hover_color="#333333",
                       command=lambda: self._run_perf(perf["disable_cmd"], "Set Balanced Plan")).grid(
            row=prow, column=0, padx=12, pady=(3, 8), sticky="ew")

        # ── Bottom: Description ────────────────────────────────────
        desc_frame = ctk.CTkFrame(self, height=56)
        desc_frame.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 4), sticky="ew")
        desc_frame.grid_columnconfigure(0, weight=1)
        desc_frame.grid_propagate(False)
        self._desc_label = ctk.CTkLabel(
            desc_frame, text="Hover over any tweak to see its description.",
            text_color="gray", font=ctk.CTkFont(size=11), anchor="w", wraplength=900)
        self._desc_label.grid(row=0, column=0, padx=12, pady=8, sticky="w")

        # ── Bottom: Buttons ────────────────────────────────────────
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=2, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")
        action_frame.grid_columnconfigure(2, weight=1)

        self._apply_btn = ctk.CTkButton(action_frame, text="Apply Selected Tweaks",
                                         width=180, command=self._apply_tweaks)
        self._apply_btn.grid(row=0, column=0, padx=(0, 8))

        self._undo_btn = ctk.CTkButton(action_frame, text="Undo Selected Tweaks",
                                        width=180, fg_color="#FF8F00", hover_color="#E65100",
                                        command=self._undo_tweaks)
        self._undo_btn.grid(row=0, column=1)

        self._status_label = ctk.CTkLabel(action_frame, text="",
                                           font=ctk.CTkFont(size=11), text_color="gray", anchor="w")
        self._status_label.grid(row=0, column=3, padx=16, sticky="w")

    def _section_label(self, parent, text, row, color="white"):
        ctk.CTkLabel(parent, text=text,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      text_color=color, anchor="w").grid(
            row=row, column=0, sticky="w", padx=8, pady=(12, 4))
        return row + 1

    def _add_tweak_row(self, parent, tweak, row):
        var = ctk.BooleanVar(value=False)
        self._tweak_vars[tweak["id"]] = var
        self._tweak_data[tweak["id"]] = tweak

        cb = ctk.CTkCheckBox(parent, text=tweak["name"], variable=var,
                              font=ctk.CTkFont(size=12))
        cb.grid(row=row, column=0, sticky="w", padx=16, pady=2)

        desc = tweak["description"]
        cb.bind("<Enter>", lambda e, d=desc: self._desc_label.configure(text=d))
        cb.bind("<Leave>", lambda e: self._desc_label.configure(
            text="Hover over any tweak to see its description."))
        return row + 1

    def _add_pref_row(self, parent, pref, row):
        var = ctk.BooleanVar(value=False)
        self._pref_vars[pref["id"]] = var
        self._pref_data[pref["id"]] = pref

        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
        row_frame.grid_columnconfigure(1, weight=1)

        toggle = ctk.CTkSwitch(row_frame, text=pref["name"], variable=var,
                                font=ctk.CTkFont(size=12),
                                command=lambda p=pref, v=var: self._apply_pref(p, v.get()))
        toggle.grid(row=0, column=0, columnspan=2, sticky="w")

        desc = pref["description"]
        toggle.bind("<Enter>", lambda e, d=desc: self._desc_label.configure(text=d))
        toggle.bind("<Leave>", lambda e: self._desc_label.configure(
            text="Hover over any tweak to see its description."))
        return row + 1

    # ── Preference state loading ───────────────────────────────────

    def _load_pref_states(self):
        def task():
            for pid, pref in self._pref_data.items():
                try:
                    cmd = f"(Get-ItemProperty -Path '{pref['reg_path']}' -Name '{pref['reg_name']}' -ErrorAction SilentlyContinue).'{pref['reg_name']}'"
                    rc, out = run_inline_powershell(cmd)
                    val = out.strip()
                    if val.lstrip('-').isdigit():
                        is_on = int(val) == pref["on_value"]
                        self.after(0, lambda v=self._pref_vars[pid], s=is_on: v.set(s))
                except Exception:
                    pass
        threading.Thread(target=task, daemon=True).start()

    # ── Preference toggle apply ────────────────────────────────────

    def _apply_pref(self, pref, is_on):
        value = pref["on_value"] if is_on else pref["off_value"]
        cmd = f"If (!(Test-Path '{pref['reg_path']}')) {{ New-Item -Path '{pref['reg_path']}' -Force | Out-Null }}; Set-ItemProperty -Path '{pref['reg_path']}' -Name '{pref['reg_name']}' -Value {value} -Force"

        def task():
            rc, out = run_inline_powershell(cmd)
            state = "ON" if is_on else "OFF"
            if rc == 0:
                log(f"Pref {pref['name']} → {state}", "success")
                self.after(0, lambda: self._status_label.configure(
                    text=f"{pref['name']} set {state}"))
            else:
                log(f"Pref {pref['name']} failed: {out}", "error")
                self.after(0, lambda: self._status_label.configure(
                    text=f"Failed: {pref['name']}"))

        threading.Thread(target=task, daemon=True).start()

    # ── Tweak apply / undo ─────────────────────────────────────────

    def _apply_tweaks(self):
        selected = [(tid, self._tweak_data[tid]) for tid, var in self._tweak_vars.items()
                    if var.get()]
        if not selected:
            self._status_label.configure(text="No tweaks selected.")
            return
        self._run_tweaks(selected, mode="apply")

    def _undo_tweaks(self):
        selected = [(tid, self._tweak_data[tid]) for tid, var in self._tweak_vars.items()
                    if var.get()]
        if not selected:
            self._status_label.configure(text="No tweaks selected.")
            return
        self._run_tweaks(selected, mode="undo")

    def _run_tweaks(self, selected, mode):
        if self._running:
            return
        self._running = True
        self._apply_btn.configure(state="disabled")
        self._undo_btn.configure(state="disabled")
        total = len(selected)
        self._status_label.configure(text=f"Running {total} tweak(s)...")
        log(f"Tweaks: {mode} {total} items")

        def task():
            results = []  # list of (name, ok, error_msg)
            log_lines = []  # full log for the dialog
            for tid, tweak in selected:
                cmd = tweak.get("apply") if mode == "apply" else tweak.get("undo")
                log_lines.append(f"\n>>> {tweak['name']}")
                if not cmd:
                    results.append((tweak["name"], None, "No undo command defined", ""))
                    log_lines.append("  [SKIP] No undo command defined.")
                    continue

                rc, out = run_inline_powershell(cmd)
                if out.strip():
                    for line in out.strip().splitlines():
                        log_lines.append(f"  {line}")
                if rc == 0:
                    results.append((tweak["name"], True, "", ""))
                    log_lines.append(f"  [OK]")
                    log(f"Tweak OK: {tweak['name']}", "success")
                else:
                    err_msg = out.strip() or f"exit code {rc}"
                    results.append((tweak["name"], False, err_msg, cmd))
                    log_lines.append(f"  [FAILED] exit {rc}")
                    log(f"Tweak FAIL: {tweak['name']} — {out}", "error")

            succeeded = sum(1 for _, ok, *_ in results if ok is True)
            failed = sum(1 for _, ok, *_ in results if ok is False)

            def finish():
                self._running = False
                self._apply_btn.configure(state="normal")
                self._undo_btn.configure(state="normal")
                if failed:
                    self._status_label.configure(
                        text=f"Done: {succeeded} ok, {failed} failed — see details")
                else:
                    self._status_label.configure(
                        text=f"Done: {succeeded} tweak(s) applied successfully.")
                self._show_done(results, mode, "\n".join(log_lines))

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _run_perf(self, cmd, label):
        if self._running:
            return
        self._running = True
        self._apply_btn.configure(state="disabled")
        self._undo_btn.configure(state="disabled")
        self._status_label.configure(text=f"Running: {label}...")
        log(f"Performance: {label}")

        def task():
            rc, out = run_inline_powershell(cmd)

            def finish():
                self._running = False
                self._apply_btn.configure(state="normal")
                self._undo_btn.configure(state="normal")
                if rc == 0:
                    self._status_label.configure(text=f"Done: {label}")
                    log(f"Performance OK: {label}", "success")
                else:
                    self._status_label.configure(text=f"Failed: {label} (exit {rc})")
                    log(f"Performance FAIL: {label} — {out}", "error")

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _show_done(self, results, mode, log_text=""):
        succeeded = sum(1 for _, ok, *_ in results if ok is True)
        failed = sum(1 for _, ok, *_ in results if ok is False)
        skipped = sum(1 for _, ok, *_ in results if ok is None)
        total = len(results)
        action = "applied" if mode == "apply" else "undone"

        dialog = ctk.CTkToplevel(self)
        dialog.title("Tweaks Complete")
        dialog.geometry("620x600")
        dialog.resizable(True, True)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        dialog.grid_rowconfigure(1, weight=2)
        dialog.grid_rowconfigure(3, weight=1)
        dialog.grid_columnconfigure(0, weight=1)

        # Summary header
        summary_color = "#4CAF50" if failed == 0 else "#FF8F00"
        summary_text = f"Done — {succeeded} ok"
        if failed:
            summary_text += f", {failed} failed"
        if skipped:
            summary_text += f", {skipped} skipped"
        ctk.CTkLabel(dialog, text=summary_text,
                      font=ctk.CTkFont(size=15, weight="bold"),
                      text_color=summary_color).grid(
            row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        # Scrollable results list
        scroll = ctk.CTkScrollableFrame(dialog)
        scroll.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        for idx, (name, ok, err, cmd) in enumerate(results):
            if ok is True:
                icon, color = "✓", "#4CAF50"
                detail = ""
            elif ok is False:
                icon, color = "✗", "#f44336"
                detail = err
            else:
                icon, color = "—", "#888888"
                detail = err

            row_frame = ctk.CTkFrame(scroll, fg_color=("gray90", "gray20"), corner_radius=6)
            row_frame.grid(row=idx, column=0, sticky="ew", pady=2, padx=2)
            row_frame.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row_frame, text=icon, text_color=color,
                          font=ctk.CTkFont(size=13, weight="bold"), width=24).grid(
                row=0, column=0, padx=(8, 4), pady=6)
            ctk.CTkLabel(row_frame, text=name, anchor="w",
                          font=ctk.CTkFont(size=12)).grid(
                row=0, column=1, sticky="w", pady=6)

            if detail:
                ctk.CTkLabel(row_frame, text=detail, anchor="w",
                              text_color="#ff8a80" if ok is False else "#aaaaaa",
                              font=ctk.CTkFont(size=10),
                              wraplength=440).grid(
                    row=1, column=1, sticky="w", padx=4, pady=(0, 2))
            if ok is False and cmd:
                short_cmd = cmd[:120] + "..." if len(cmd) > 120 else cmd
                ctk.CTkLabel(row_frame, text=f"CMD: {short_cmd}", anchor="w",
                              text_color="#555555", font=ctk.CTkFont(size=9, family="Courier New"),
                              wraplength=440).grid(
                    row=2, column=1, sticky="w", padx=4, pady=(0, 6))

        # Log section
        ctk.CTkLabel(dialog, text="Full Log",
                      font=ctk.CTkFont(size=12, weight="bold"), anchor="w").grid(
            row=2, column=0, padx=16, pady=(4, 2), sticky="w")
        log_box = ctk.CTkTextbox(dialog, font=ctk.CTkFont(family="Courier New", size=11),
                                  state="normal")
        log_box.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="nsew")
        log_box.insert("1.0", log_text.strip() if log_text.strip() else "No output captured.")
        log_box.configure(state="disabled")

        ctk.CTkButton(dialog, text="Close", width=100,
                       command=dialog.destroy).grid(row=4, column=0, pady=(0, 16))
