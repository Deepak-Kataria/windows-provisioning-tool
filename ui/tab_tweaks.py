"""Tweaks: system tweaks, preferences and power plans.

Each tweak shows whether it's already applied (read from the registry where possible).
"""
import json
import os
import threading

import customtkinter as ctk

from modules.logger import log
from modules.reg_state import active_power_plan, pref_on, tweak_applied
from modules.runner import run_inline_powershell
from ui import theme as T
from ui.widgets import ActionBar, confirm_run, section_header, tile_row, tip

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

# (config key, header, accent, caution?)
SECTIONS = [
    ("essential", "Essential tweaks", None, False),
    ("advanced", "Advanced tweaks", "WARN", True),
    ("privacy", "Privacy & tracking", None, False),
    ("org", "Org settings", None, False),
]
ULTIMATE = "Ultimate Performance"


class TweaksTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._tweak_vars = {}     # id -> BooleanVar (checkboxes)
        self._tweak_data = {}     # id -> tweak dict
        self._status = {}         # id -> True / False / None (applied?)
        self._status_lbls = {}    # id -> status label
        self._pref_vars = {}      # id -> BooleanVar (switches)
        self._pref_data = {}      # id -> pref dict
        self._pref_lbls = {}      # id -> ON/OFF label
        self._plan = None
        self._load_config()
        self._advanced = {t["id"] for t in self._config.get("advanced", [])}
        self._build()
        self._refresh_state()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "tweaks.json"), encoding="utf-8") as f:
            self._config = json.load(f)

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        tiles_host = ctk.CTkFrame(self, fg_color="transparent")
        tiles_host.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        tiles_host.grid_columnconfigure(0, weight=1)
        row, self._tiles = tile_row(tiles_host, [
            ("Applied", "…", T.MUTED, "reading this PC…"),
            ("Selected", "0", T.ACCENT, "will be applied"),
            ("Preferences on", "…", T.INFO, "switches apply instantly"),
            ("Power plan", "…", T.TEXT, ""),
        ])
        row.grid(row=0, column=0, sticky="ew")

        # Left: tweaks
        left = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        left.grid_columnconfigure(0, weight=1)
        r = 0
        self._section_counts = {}
        for key, title, accent, caution in SECTIONS:
            tweaks = self._config.get(key, [])
            if not tweaks:
                continue
            color = getattr(T, accent) if accent else None
            hdr, col = section_header(left, title, height=30, accent=color)
            hdr.grid(row=r, column=0, sticky="ew", pady=(10 if r else 0, 0))
            cnt = ctk.CTkLabel(hdr, text="", font=T.mono(10), text_color=color or T.MUTED)
            cnt.grid(row=0, column=col, padx=4, sticky="w")
            self._section_counts[key] = cnt
            tick = T.outline_button(hdr, text="tick all", width=64, height=20, font=T.mono(10),
                                    command=lambda k=key: self._tick_section(k))
            tick.grid(row=0, column=col + 1, padx=8)
            tip(tick, f"Tick or untick every {title.lower()} tweak")
            r += 1
            box = ctk.CTkFrame(left, fg_color=T.PANEL, corner_radius=0)
            box.grid(row=r, column=0, sticky="ew")
            box.grid_columnconfigure(0, weight=1)
            for i, tweak in enumerate(tweaks):
                self._add_tweak_row(box, tweak, i, caution)
            r += 1

        # Right: preferences + power plan
        right = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)
        hdr, col = section_header(right, "Preferences", height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text="apply instantly", font=T.mono(10), text_color=T.MUTED).grid(
            row=0, column=col, padx=4, sticky="w")
        pbox = ctk.CTkFrame(right, fg_color=T.PANEL, corner_radius=0)
        pbox.grid(row=1, column=0, sticky="ew")
        pbox.grid_columnconfigure(0, weight=1)
        for i, pref in enumerate(self._config.get("preferences", [])):
            self._add_pref_row(pbox, pref, i)

        hdr, _ = section_header(right, "Power plan", height=30)
        hdr.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        plan = ctk.CTkFrame(right, fg_color=T.PANEL, corner_radius=0)
        plan.grid(row=3, column=0, sticky="ew")
        plan.grid_columnconfigure(1, weight=1)
        self._plan_btn = ctk.CTkSegmentedButton(plan, values=["Balanced", ULTIMATE],
                                                command=self._choose_plan)
        self._plan_btn.grid(row=0, column=0, padx=12, pady=10, sticky="w")
        tip(self._plan_btn, "Balanced is the Windows default. Ultimate Performance uses more "
                            "power; best for desktops.")
        self._plan_lbl = ctk.CTkLabel(plan, text="", font=T.mono(10), text_color=T.MUTED)
        self._plan_lbl.grid(row=0, column=1, padx=12, sticky="e")

        # Bottom action bar
        self._action = ActionBar(self)
        self._action.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._action.button("Select all", self.shortcut_select_all, outline=True, width=96,
                            tip_text="Tick every tweak, including Advanced ones (Ctrl+A)")
        self._action.button("Select none", self.shortcut_deselect_all, outline=True, width=96,
                            tip_text="Untick every tweak (Ctrl+Shift+A)")
        self._undo_btn = self._action.button("Undo selected", self._undo_tweaks, outline=True,
                                             width=120, text_color=T.WARN, border_color=T.WARN,
                                             tip_text="Revert the ticked tweaks to Windows defaults")
        self._apply_btn = self._action.button("Apply", self._apply_tweaks, width=150,
                                              tip_text="Apply the ticked tweaks (Ctrl+Enter). "
                                                       "You'll see the list before anything runs.")
        self._update_summary()

    def _add_tweak_row(self, parent, tweak, i, caution):
        tid = tweak["id"]
        var = ctk.BooleanVar(value=False)
        var.trace_add("write", lambda *_: self._update_summary())
        self._tweak_vars[tid] = var
        self._tweak_data[tid] = tweak

        row = ctk.CTkFrame(parent, fg_color=T.PANEL if i % 2 == 0 else T.PANEL_2, corner_radius=0)
        row.grid(row=i, column=0, sticky="ew")
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkCheckBox(row, text="", variable=var, width=20, checkbox_width=16,
                        checkbox_height=16).grid(row=0, column=0, rowspan=2, padx=(10, 6), pady=6, sticky="n")
        name = ctk.CTkFrame(row, fg_color="transparent")
        name.grid(row=0, column=1, sticky="w", pady=(5, 0))
        ctk.CTkLabel(name, text=tweak["name"], font=T.ui(12, "bold"), text_color=T.TEXT_BRIGHT,
                     height=18).grid(row=0, column=0, sticky="w")
        if caution:
            ctk.CTkLabel(name, text=" CAUTION ", font=T.mono(8, "bold"), text_color=T.WARN,
                         fg_color=T.PANEL_3, corner_radius=2, height=14).grid(row=0, column=1, padx=6)
        ctk.CTkLabel(row, text=tweak.get("description", ""), font=T.ui(11), text_color=T.MUTED,
                     anchor="w", justify="left", wraplength=560, height=16).grid(
            row=1, column=1, sticky="w", pady=(0, 6))
        lbl = ctk.CTkLabel(row, text="…", font=T.mono(9, "bold"), text_color=T.DIM, width=70)
        lbl.grid(row=0, column=2, rowspan=2, padx=(6, 12))
        self._status_lbls[tid] = lbl

    def _add_pref_row(self, parent, pref, i):
        pid = pref["id"]
        var = ctk.BooleanVar(value=False)
        self._pref_vars[pid] = var
        self._pref_data[pid] = pref
        row = ctk.CTkFrame(parent, fg_color=T.PANEL if i % 2 == 0 else T.PANEL_2, corner_radius=0,
                           height=34)
        row.grid(row=i, column=0, sticky="ew")
        row.grid_propagate(False)
        row.grid_rowconfigure(0, weight=1)
        row.grid_columnconfigure(0, weight=1)
        name = ctk.CTkLabel(row, text=pref["name"], font=T.ui(12), anchor="w")
        name.grid(row=0, column=0, sticky="w", padx=12)
        tip(name, pref.get("description", ""))
        lbl = ctk.CTkLabel(row, text="", font=T.mono(10, "bold"), width=34, text_color=T.DIM)
        lbl.grid(row=0, column=1)
        self._pref_lbls[pid] = lbl
        sw = ctk.CTkSwitch(row, text="", variable=var, width=44, switch_width=34, switch_height=16,
                           command=lambda p=pref, v=var: self._apply_pref(p, v.get()))
        sw.grid(row=0, column=2, padx=(4, 10))
        tip(sw, pref.get("description", ""))

    # ── State ──────────────────────────────────────────────────────

    def on_show(self):
        if not self._running:
            self._refresh_state()

    def _refresh_state(self):
        """Read tweak / preference / power plan state off the UI thread (fast: registry only)."""
        def task():
            status = {tid: tweak_applied(t) for tid, t in self._tweak_data.items()}
            prefs = {pid: pref_on(p) for pid, p in self._pref_data.items()}
            plan = active_power_plan()
            try:
                self.after(0, self._apply_state, status, prefs, plan)
            except RuntimeError:
                pass
        threading.Thread(target=task, daemon=True).start()

    def _apply_state(self, status, prefs, plan):
        if not self.winfo_exists():
            return
        self._status, self._plan = status, plan
        for tid, st in status.items():
            text, color = ("APPLIED", T.OK) if st else ("NOT SET", T.DIM) if st is False else ("—", T.DIM)
            self._status_lbls[tid].configure(text=text, text_color=color)
        for key, _, _, _ in SECTIONS:
            if key in self._section_counts:
                ids = [t["id"] for t in self._config.get(key, [])]
                known = [i for i in ids if status.get(i) is not None]
                n = sum(1 for i in known if status[i])
                self._section_counts[key].configure(
                    text=f"{len(ids)} · {n} applied" if known else f"{len(ids)}")
        for pid, on in prefs.items():
            if on is not None:
                self._pref_vars[pid].set(on)
            self._pref_lbls[pid].configure(text="ON" if on else "OFF" if on is False else "—",
                                           text_color=T.OK if on else T.MUTED)
        self._plan_btn.set(ULTIMATE if plan and "ultimate" in plan.lower() else
                           "Balanced" if plan and "balanced" in plan.lower() else "")
        self._plan_lbl.configure(text=f"active: {plan}" if plan else "active plan unknown")
        self._update_summary()

    def _update_summary(self):
        if not hasattr(self, "_apply_btn"):
            return
        known = [s for s in self._status.values() if s is not None]
        n_app = sum(1 for s in known if s)
        if self._status:
            self._tiles["Applied"].set(f"{n_app} / {len(known)}", T.OK if n_app else T.MUTED,
                                       f"in place · {len(self._tweak_data) - len(known)} not checkable")
        n_on = sum(1 for v in self._pref_vars.values() if v.get())
        self._tiles["Preferences on"].set(f"{n_on} / {len(self._pref_vars)}", T.INFO,
                                          "switches apply instantly")
        plan = self._plan or "unknown"
        self._tiles["Power plan"].set(plan if len(plan) <= 14 else plan[:13] + "…",
                                      T.WARN if "ultimate" in plan.lower() else T.TEXT,
                                      "max performance" if "ultimate" in plan.lower() else "active scheme")
        sel = [tid for tid, v in self._tweak_vars.items() if v.get()]
        already = sum(1 for tid in sel if self._status.get(tid))
        adv = sum(1 for tid in sel if tid in self._advanced)
        self._tiles["Selected"].set(len(sel), T.WARN if adv else T.ACCENT,
                                    f"{adv} advanced" if adv else "will be applied")
        if self._running:
            return
        noun = "tweak" if len(sel) == 1 else "tweaks"
        self._apply_btn.configure(text=f"Apply {len(sel)} {noun}", state="normal" if sel else "disabled")
        self._undo_btn.configure(state="normal" if sel else "disabled")
        if sel:
            extra = f" · {already} already applied" if already else ""
            self._action.set_summary(f"{len(sel)} {noun} selected{extra}")
        else:
            self._action.set_summary("Tick the tweaks to apply or undo")

    def _tick_section(self, key):
        ids = [t["id"] for t in self._config.get(key, [])]
        new = not all(self._tweak_vars[i].get() for i in ids)
        for i in ids:
            self._tweak_vars[i].set(new)

    # Keyboard shortcuts (see ui/widgets.py)
    def shortcut_select_all(self):
        for v in self._tweak_vars.values():
            v.set(True)

    def shortcut_deselect_all(self):
        for v in self._tweak_vars.values():
            v.set(False)

    def shortcut_apply(self):
        self._apply_tweaks()

    def _set_status(self, text, color=None):
        self._action.set_summary(text, color)

    # ── Preferences / power plan ───────────────────────────────────

    def _apply_pref(self, pref, is_on):
        value = pref["on_value"] if is_on else pref["off_value"]
        cmd = (f"If (!(Test-Path '{pref['reg_path']}')) {{ New-Item -Path '{pref['reg_path']}' -Force | Out-Null }}; "
               f"Set-ItemProperty -Path '{pref['reg_path']}' -Name '{pref['reg_name']}' -Value {value} -Force")
        self._pref_lbls[pref["id"]].configure(text="ON" if is_on else "OFF",
                                              text_color=T.OK if is_on else T.MUTED)
        self._update_summary()

        def task():
            rc, out = run_inline_powershell(cmd)
            state = "ON" if is_on else "OFF"
            if rc == 0:
                log(f"Pref {pref['name']} → {state}", "success")
                self.after(0, self._set_status, f"{pref['name']} set {state}", T.OK)
            else:
                log(f"Pref {pref['name']} failed: {out}", "error")
                self.after(0, self._set_status, f"Failed: {pref['name']}", T.FAIL)
                self.after(0, self._refresh_state)

        threading.Thread(target=task, daemon=True).start()

    def _choose_plan(self, value):
        perf = self._config["performance"]
        if value == ULTIMATE:
            self._run_perf(perf["enable_cmd"], "Enable Ultimate Performance")
        else:
            self._run_perf(perf["disable_cmd"], "Set Balanced plan")

    def _run_perf(self, cmd, label):
        if self._running:
            return
        self._running = True
        self._apply_btn.configure(state="disabled")
        self._undo_btn.configure(state="disabled")
        self._plan_btn.configure(state="disabled")
        self._set_status(f"Running: {label}…", T.TEXT)
        log(f"Performance: {label}")

        def task():
            rc, out = run_inline_powershell(cmd)

            def finish():
                self._running = False
                self._plan_btn.configure(state="normal")
                if rc == 0:
                    log(f"Performance OK: {label}", "success")
                else:
                    log(f"Performance FAIL: {label} — {out}", "error")
                self._refresh_state()
                self.after(300, lambda: self._set_status(
                    f"Done: {label}" if rc == 0 else f"Failed: {label} (exit {rc})",
                    T.OK if rc == 0 else T.FAIL))
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── Tweak apply / undo ─────────────────────────────────────────

    def _selected(self):
        return [(tid, self._tweak_data[tid]) for tid, var in self._tweak_vars.items() if var.get()]

    def _apply_tweaks(self):
        selected = self._selected()
        if not selected:
            self._set_status("No tweaks selected.", T.WARN)
            return
        self._run_tweaks(selected, mode="apply")

    def _undo_tweaks(self):
        selected = self._selected()
        if not selected:
            self._set_status("No tweaks selected.", T.WARN)
            return
        self._run_tweaks(selected, mode="undo")

    def _run_tweaks(self, selected, mode):
        if self._running:
            return
        has_adv = any(tid in self._advanced for tid, _ in selected)
        verb = "applied" if mode == "apply" else "reverted"
        if not confirm_run(
                self, "Apply tweaks?" if mode == "apply" else "Undo tweaks?",
                f"These {len(selected)} tweak(s) will be {verb}:",
                [(t["name"] + ("  (Advanced)" if tid in self._advanced else ""), tid in self._advanced)
                 for tid, t in selected],
                action_text=f"{'Apply' if mode == 'apply' else 'Undo'} {len(selected)} tweak(s)",
                danger=has_adv,
                footer="Advanced tweaks are shown in red. Make sure you've read their descriptions."
                       if has_adv else None):
            return
        self._running = True
        self._apply_btn.configure(state="disabled")
        self._undo_btn.configure(state="disabled")
        total = len(selected)
        self._action.progress(0, f"Running {total} tweak(s)…")
        log(f"Tweaks: {mode} {total} items")

        def task():
            results = []    # (name, ok, error_msg, cmd)
            log_lines = []  # full log for the dialog
            for n, (tid, tweak) in enumerate(selected, 1):
                self.after(0, self._action.progress, (n - 1) / total, f"{n} / {total}  {tweak['name']}")
                cmd = tweak.get("apply") if mode == "apply" else tweak.get("undo")
                log_lines.append(f"\n>>> {tweak['name']}")
                if not cmd:
                    results.append((tweak["name"], None, "No undo command defined", ""))
                    log_lines.append("  [SKIP] No undo command defined.")
                    continue
                rc, out = run_inline_powershell(cmd)
                for line in out.strip().splitlines():
                    log_lines.append(f"  {line}")
                if rc == 0:
                    results.append((tweak["name"], True, "", ""))
                    log_lines.append("  [OK]")
                    log(f"Tweak OK: {tweak['name']}", "success")
                else:
                    results.append((tweak["name"], False, out.strip() or f"exit code {rc}", cmd))
                    log_lines.append(f"  [FAILED] exit {rc}")
                    log(f"Tweak FAIL: {tweak['name']} — {out}", "error")

            succeeded = sum(1 for _, ok, *_ in results if ok is True)
            failed = sum(1 for _, ok, *_ in results if ok is False)

            def finish():
                self._running = False
                self._action.progress(None)
                self._refresh_state()
                self.after(300, lambda: self._set_status(
                    f"Done: {succeeded} ok, {failed} failed (see details)" if failed
                    else f"Done: {succeeded} tweak(s) {verb}.", T.WARN if failed else T.OK))
                self._show_done(results, mode, "\n".join(log_lines))

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
        dialog.transient(self.winfo_toplevel())
        dialog.after(60, lambda: dialog.winfo_exists() and dialog.grab_set())
        dialog.lift()
        dialog.focus_force()
        dialog.grid_rowconfigure(1, weight=2)
        dialog.grid_rowconfigure(3, weight=1)
        dialog.grid_columnconfigure(0, weight=1)

        # Summary header
        summary_color = T.OK if failed == 0 else T.WARN
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
                icon, color = "✓", T.OK
                detail = ""
            elif ok is False:
                icon, color = "✗", T.FAIL
                detail = err
            else:
                icon, color = "—", T.MUTED
                detail = err

            row_frame = ctk.CTkFrame(scroll, fg_color=T.PANEL_2, corner_radius=6)
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
                              text_color=T.FAIL if ok is False else T.MUTED,
                              font=ctk.CTkFont(size=10),
                              wraplength=440).grid(
                    row=1, column=1, sticky="w", padx=4, pady=(0, 2))
            if ok is False and cmd:
                short_cmd = cmd[:120] + "..." if len(cmd) > 120 else cmd
                ctk.CTkLabel(row_frame, text=f"CMD: {short_cmd}", anchor="w",
                              text_color=T.DIM, font=ctk.CTkFont(size=9, family=T.MONO_FAMILY),
                              wraplength=440).grid(
                    row=2, column=1, sticky="w", padx=4, pady=(0, 6))

        # Log section
        ctk.CTkLabel(dialog, text="Full Log",
                      font=ctk.CTkFont(size=12, weight="bold"), anchor="w").grid(
            row=2, column=0, padx=16, pady=(4, 2), sticky="w")
        log_box = ctk.CTkTextbox(dialog, font=ctk.CTkFont(family=T.MONO_FAMILY, size=11),
                                  state="normal")
        log_box.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="nsew")
        log_box.insert("1.0", log_text.strip() if log_text.strip() else "No output captured.")
        log_box.configure(state="disabled")

        close_row = ctk.CTkFrame(dialog, fg_color="transparent")
        close_row.grid(row=4, column=0, pady=(0, 16))

        def _copy_results():
            lines = [f"Tweaks {action.capitalize()} — {succeeded} ok, {failed} failed, {skipped} skipped"]
            for name, ok, err, _ in results:
                icon = "OK" if ok is True else ("FAIL" if ok is False else "SKIP")
                lines.append(f"  [{icon}] {name}" + (f" — {err}" if err else ""))
            dialog.clipboard_clear()
            dialog.clipboard_append("\n".join(lines))

        ctk.CTkButton(close_row, text="Close", width=100,
                      command=dialog.destroy).grid(row=0, column=0, padx=6)
        T.outline_button(close_row, text="Copy results", width=110,
                         command=_copy_results).grid(row=0, column=1, padx=6)
