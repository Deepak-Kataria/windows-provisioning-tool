import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import customtkinter as ctk

from ui import theme as T

from modules import security_checks as sc
from modules.logger import log, log_change
from modules.runner import run_encoded_powershell
from modules.security_report import build_html, build_text, machine_meta, ordered_checks
from modules.utils import writable_path
from ui.widgets import meta_line, section_header, tile_row, tip

CHECKS = sc.CHECKS  # kept for any external imports

_STATUS_COLOR = T.STATUS
_LEVEL_COLOR  = T.LEVEL
_ROW_BG       = (T.PANEL, T.PANEL_2)   # alternating rows

_SCAN_WORKERS = 6


class SecurityTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._results = {}       # id → (status, detail)
        self._fixed = set()      # ids where a fix was applied this session
        self._row_widgets = {}   # id → widgets of that row
        self._cat_widgets = {}   # category → {"count_lbl", "fix_all_btn"}
        self._summary = None
        self._scan_time = None
        self._build()

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=T.PANEL)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(4, weight=1)
        top.grid_propagate(False)

        self._scan_btn = ctk.CTkButton(
            top, text="Run Vulnerability Scan", width=190,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._run_scan)
        self._scan_btn.grid(row=0, column=0, padx=(14, 8), pady=10)
        tip(self._scan_btn, "Run all vulnerability checks (Ctrl+Enter). Read-only, nothing is changed.")

        self._export_btn = ctk.CTkButton(
            top, text="Export Report", width=120, fg_color="transparent", border_width=1,
            state="disabled", command=self._export_report)
        self._export_btn.grid(row=0, column=1, padx=6, pady=10)
        tip(self._export_btn, "Save the report as HTML and TXT in the logs folder")

        self._copy_btn = ctk.CTkButton(
            top, text="Copy Report", width=110, fg_color="transparent", border_width=1,
            state="disabled", command=self._copy_report)
        self._copy_btn.grid(row=0, column=2, padx=6, pady=10)
        tip(self._copy_btn, "Copy the plain-text report to the clipboard (for tickets)")

        self._status_lbl = ctk.CTkLabel(
            top, text=f"Click 'Run Vulnerability Scan' to start ({len(CHECKS)} checks).",
            text_color=T.MUTED, font=ctk.CTkFont(size=11))
        self._status_lbl.grid(row=0, column=4, padx=12, sticky="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._scroll, text="No scan results yet.\nRun a scan to see the security report.",
            text_color=T.MUTED, font=ctk.CTkFont(size=13), justify="center"
        ).grid(row=0, column=0, pady=60)

    def _set_busy(self, busy, scan_text=None):
        self._running = busy
        state = "disabled" if busy else "normal"
        self._scan_btn.configure(state=state, text=scan_text or "Run Vulnerability Scan")
        if self._results:
            self._export_btn.configure(state=state)
            self._copy_btn.configure(state=state)
        for cat in self._cat_widgets:
            self._refresh_category(cat)

    # ── Report rendering ───────────────────────────────────────────

    def _clear_report(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._row_widgets.clear()
        self._cat_widgets.clear()
        self._summary = None

    def _render_report(self):
        self._clear_report()

        self._summary = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._summary.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")
        self._summary.grid_columnconfigure(0, weight=1)
        self._fill_summary()

        grid_row = 1
        for cat in sc.CATEGORIES:
            hdr, col = section_header(self._scroll, cat)
            hdr.grid(row=grid_row, column=0, padx=12, pady=(12, 0), sticky="ew")
            count_lbl = ctk.CTkLabel(hdr, text="", font=T.mono(11),
                                     text_color=T.MUTED, anchor="w")
            count_lbl.grid(row=0, column=col, padx=4, sticky="w")
            fix_all_btn = ctk.CTkButton(
                hdr, text="Fix All", width=110, height=24,
                command=lambda c=cat: self._open_fix_all(c))
            fix_all_btn.grid(row=0, column=col + 1, padx=8)
            tip(fix_all_btn, f"Pick and apply the automatic fixes for {cat} (asks first)")
            self._cat_widgets[cat] = {"count_lbl": count_lbl, "fix_all_btn": fix_all_btn}
            grid_row += 1

            grp = ctk.CTkFrame(self._scroll, corner_radius=0)
            grp.grid(row=grid_row, column=0, padx=12, pady=(0, 4), sticky="ew")
            grp.grid_columnconfigure(0, weight=1)
            grid_row += 1

            for r_idx, check in enumerate(ordered_checks(cat, self._results)):
                self._add_result_row(grp, check, r_idx)
            self._refresh_category(cat)

        self._export_btn.configure(state="normal")
        self._copy_btn.configure(state="normal")

    def _fill_summary(self):
        if not self._summary:
            return
        for w in self._summary.winfo_children():
            w.destroy()
        s = sc.risk_summary(self._results)
        c = s["counts"]
        level_color = _LEVEL_COLOR[s["level"]]
        score_color = T.OK if s["score"] >= 80 else (T.WARN if s["score"] >= 50 else T.FAIL)
        n_fixable = sum(len(self._fix_all_candidates(cat)) for cat in sc.CATEGORIES)

        tiles = [
            ("Risk level", s["level"], level_color, "overall exposure"),
            ("Score", f"{s['score']}/100", score_color, "higher is better"),
            ("Failed", c["FAIL"], T.FAIL if c["FAIL"] else T.DIM,
             f"{n_fixable} auto-fixable" if n_fixable else "none auto-fixable"),
            ("Warnings", c["WARN"], T.WARN if c["WARN"] else T.DIM, "review recommended"),
            ("Passed", c["PASS"], T.OK, f"of {len(CHECKS)} checks"),
        ]
        if c["UNKNOWN"]:
            tiles.append(("Unknown", c["UNKNOWN"], T.MUTED, "check could not run"))
        row, _ = tile_row(self._summary, tiles)
        row.grid(row=0, column=0, sticky="ew")

        meta = machine_meta()
        meta_line(self._summary, [("host", meta["computer"]),
                                  ("scanned", self._scan_time or "-"),
                                  ("checks", len(CHECKS)),
                                  ("fixed this session", len(self._fixed))]
                  ).grid(row=1, column=0, pady=(8, 0), sticky="w")

    def _fix_all_candidates(self, cat):
        return [c for c in ordered_checks(cat, self._results)
                if sc.is_auto_fixable(c)
                and self._results.get(c["id"], ("UNKNOWN",))[0] in ("FAIL", "WARN")]

    def _refresh_category(self, cat):
        w = self._cat_widgets.get(cat)
        if not w:
            return
        ids = [c["id"] for c in CHECKS if c["category"] == cat]
        statuses = [self._results.get(i, ("UNKNOWN",))[0] for i in ids]
        n_fail, n_warn = statuses.count("FAIL"), statuses.count("WARN")
        parts = []
        if n_fail:
            parts.append(f"{n_fail} failed")
        if n_warn:
            parts.append(f"{n_warn} warning{'s' if n_warn != 1 else ''}")
        text = " · ".join(parts) if parts else f"all {len(ids)} passed"
        color = T.FAIL if n_fail else (T.WARN if n_warn else T.OK)
        w["count_lbl"].configure(text=f"{text}   [{len(ids)}]", text_color=color)

        n_fix = len(self._fix_all_candidates(cat))
        w["fix_all_btn"].configure(
            text=f"Fix All ({n_fix})" if n_fix else "Fix All",
            state="normal" if n_fix and not self._running else "disabled")

    def _add_result_row(self, parent, check, row_idx):
        row = ctk.CTkFrame(parent, fg_color=_ROW_BG[row_idx % 2], corner_radius=0)
        row.grid(row=row_idx, column=0, sticky="ew")
        row.grid_columnconfigure(3, weight=1)

        icon_lbl = ctk.CTkLabel(row, text="", width=44, font=T.mono(11, "bold"))
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=4, sticky="n")

        sev = check["severity"]
        ctk.CTkLabel(row, text=T.SEV_TAG.get(sev, sev), width=36, font=T.mono(10, "bold"),
                     text_color=T.SEV[sev]).grid(row=0, column=1, padx=(0, 6), pady=4, sticky="n")

        name_lbl = ctk.CTkLabel(row, text=check["name"], width=230, anchor="w",
                                justify="left", wraplength=225,
                                font=ctk.CTkFont(size=12, weight="bold"))
        name_lbl.grid(row=0, column=2, rowspan=2, padx=(0, 12), pady=4, sticky="nw")

        detail_lbl = ctk.CTkLabel(row, text="", font=T.mono(11), anchor="w",
                                  wraplength=460, justify="left")
        detail_lbl.grid(row=0, column=3, padx=(0, 12), pady=(4, 0), sticky="w")

        if check.get("impact"):
            ctk.CTkLabel(row, text=f"if fixed: {check['impact']}",
                         font=ctk.CTkFont(size=10, slant="italic"), text_color=T.DIM,
                         anchor="w", wraplength=460, justify="left", height=16
                         ).grid(row=1, column=3, padx=(0, 12), pady=(0, 4), sticky="w")

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.grid(row=0, column=4, rowspan=2, padx=(0, 10), pady=4)

        self._row_widgets[check["id"]] = {
            "icon_lbl": icon_lbl, "name_lbl": name_lbl, "detail_lbl": detail_lbl,
            "btn_frame": btn_frame, "fix_btn": None, "revert_btn": None,
        }
        status, detail = self._results.get(check["id"], ("UNKNOWN", ""))
        self._update_row(check["id"], status, detail)

    def _update_row(self, check_id, status, detail):
        check = sc.CHECKS_BY_ID[check_id]
        w = self._row_widgets.get(check_id)
        if not w:
            return
        color = _STATUS_COLOR.get(status, T.MUTED)
        w["icon_lbl"].configure(text=T.STATUS_TAG.get(status, " ?? "), text_color=color)
        w["name_lbl"].configure(text_color=T.TEXT_BRIGHT if status != "PASS" else T.TEXT)
        w["detail_lbl"].configure(text=detail or check["description"],
                                  text_color=color if detail and status != "PASS" else T.MUTED)

        for child in w["btn_frame"].winfo_children():
            child.destroy()
        w["fix_btn"] = w["revert_btn"] = None

        col = 0
        if status in ("FAIL", "WARN") and check.get("fix_ps"):
            w["fix_btn"] = ctk.CTkButton(
                w["btn_frame"], text=check["fix_label"], width=145, height=24,
                command=lambda c=check: self._run_fix(c))
            w["fix_btn"].grid(row=0, column=col, padx=(0, 4))
            col += 1
        if check.get("undo_ps"):
            w["revert_btn"] = T.outline_button(
                w["btn_frame"], text=check.get("undo_label", "Revert"), width=185, height=24,
                command=lambda c=check: self._run_revert(c))
            w["revert_btn"].grid(row=0, column=col, padx=(4, 0))

    def _after_result_change(self, check_id):
        status, detail = self._results[check_id]
        self._update_row(check_id, status, detail)
        self._refresh_category(sc.CHECKS_BY_ID[check_id]["category"])
        self._fill_summary()
        self._update_status_line()

    def _update_status_line(self, prefix="Scan complete"):
        s = sc.risk_summary(self._results)
        c = s["counts"]
        color = T.FAIL if c["FAIL"] else (T.WARN if c["WARN"] else T.OK)
        self._status_lbl.configure(
            text=f"{prefix}  |  {s['level']} ({s['score']}/100)  |  "
                 f"{c['FAIL']} failed  {c['WARN']} warnings  {c['PASS']} passed",
            text_color=color)

    # ── Scan ───────────────────────────────────────────────────────

    def shortcut_apply(self):
        self._run_scan()

    def _run_scan(self):
        if self._running:
            return
        self._fixed.clear()
        self._results.clear()
        self._export_btn.configure(state="disabled")
        self._copy_btn.configure(state="disabled")
        self._clear_report()
        self._set_busy(True, "Scanning...")
        self._status_lbl.configure(text="Running checks...", text_color=T.MUTED)

        prog = ctk.CTkLabel(self._scroll, text=f"Scanning...  0 / {len(CHECKS)}",
                            text_color=T.MUTED, font=ctk.CTkFont(size=13))
        prog.grid(row=0, column=0, pady=60)
        log("Security: scan started")

        def run_one(check):
            _, out = run_encoded_powershell(check["check_ps"], timeout=check.get("timeout", 120))
            return check, sc.evaluate(check, out)

        def task():
            results, total = {}, len(CHECKS)
            try:
                with ThreadPoolExecutor(max_workers=_SCAN_WORKERS) as pool:
                    futures = [pool.submit(run_one, c) for c in CHECKS]
                    for done, fut in enumerate(as_completed(futures), 1):
                        try:
                            check, (status, detail) = fut.result()
                        except Exception as e:  # keep scanning the rest
                            log(f"Security check crashed: {e}", "error")
                            continue
                        results[check["id"]] = (status, detail)
                        log(f"Security {check['id']}: {status} {detail}")
                        msg = f"Scanning...  {done} / {total}  —  {check['name']}"
                        self.after(0, lambda m=msg: prog.winfo_exists() and prog.configure(text=m))
            finally:
                self.after(0, self._finish_scan, results)

        threading.Thread(target=task, daemon=True).start()

    def _finish_scan(self, results):
        self._results = results
        self._scan_time = datetime.now().strftime("%Y-%m-%d  %H:%M")
        self._running = False
        self._render_report()
        self._set_busy(False)
        self._update_status_line()
        log(f"Security: scan finished — {sc.risk_summary(results)['level']}")

    # ── Fix / revert ──────────────────────────────────────────────

    def _apply(self, check, mode):
        """Run fix ('fix') or undo ('revert') for one check and re-verify. Worker thread only."""
        before = self._results.get(check["id"], ("?", ""))
        before_str = f"{before[0]}: {before[1]}" if before[1] else before[0]
        script = check["fix_ps"] if mode == "fix" else check["undo_ps"]
        _, fix_out = run_encoded_powershell(script)
        _, out = run_encoded_powershell(check["check_ps"])
        status, detail = sc.evaluate(check, out)
        self._results[check["id"]] = (status, detail)
        after_str = f"{status}: {detail}" if detail else status
        if mode == "fix":
            self._fixed.add(check["id"])
            action = f"{check['name']} — {check['fix_label']}"
        else:
            self._fixed.discard(check["id"])
            action = f"{check['name']} — REVERTED ({check.get('undo_label', '')})"
        log_change("Security", action, before=before_str, after=after_str)
        log(f"Security {mode} {check['id']}: {status} | {fix_out}")
        return status

    def _run_fix(self, check):
        if self._running:
            return
        # "Open X" style fixes just launch a console for manual review — nothing to verify.
        if not sc.is_auto_fixable(check):
            threading.Thread(target=run_encoded_powershell, args=(check["fix_ps"],),
                             daemon=True).start()
            self._status_lbl.configure(text=f"{check['fix_label']}: opened for manual review.",
                                       text_color=T.MUTED)
            return
        self._row_action(check, "fix", "Fixing...")

    def _run_revert(self, check):
        if self._running:
            return
        self._row_action(check, "revert", "Reverting...")

    def _row_action(self, check, mode, busy_text):
        self._set_busy(True)
        w = self._row_widgets.get(check["id"])
        btn = w and w["fix_btn" if mode == "fix" else "revert_btn"]
        if btn:
            btn.configure(state="disabled", text=busy_text)

        def task():
            try:
                self._apply(check, mode)
            finally:
                self.after(0, self._after_result_change, check["id"])
                self.after(0, self._set_busy, False)
                self.after(0, self._update_status_line,
                           "Fix applied" if mode == "fix" else "Reverted")

        threading.Thread(target=task, daemon=True).start()

    # ── Fix All (per category) ────────────────────────────────────

    def _open_fix_all(self, cat):
        if self._running:
            return
        candidates = self._fix_all_candidates(cat)
        if not candidates:
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Fix All — {cat}")
        dlg.geometry("640x520")
        dlg.resizable(True, True)
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()
        dlg.grid_columnconfigure(0, weight=1)
        dlg.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            dlg, text=f"Apply {cat} fixes",
            font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        ).grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")

        scroll = ctk.CTkScrollableFrame(dlg)
        scroll.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            scroll, wraplength=560, justify="left", anchor="w", text_color=T.MUTED,
            font=ctk.CTkFont(size=11),
            text="Ticked fixes run one after another and each is re-checked. Fixes that can "
                 "interrupt how people work are unticked — tick them only if you've read the impact."
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        vars_ = {}
        for i, check in enumerate(candidates, 1):
            box = ctk.CTkFrame(scroll, fg_color=T.PANEL_2)
            box.grid(row=i, column=0, sticky="ew", pady=3)
            box.grid_columnconfigure(0, weight=1)
            var = ctk.BooleanVar(value=not check["disruptive"])
            vars_[check["id"]] = var
            label = f"{check['fix_label']}  —  {check['name']}  [{check['severity']}]"
            ctk.CTkCheckBox(box, text=label, variable=var,
                            font=ctk.CTkFont(size=12, weight="bold")
                            ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")
            note = ("⚠ May interrupt users. " if check["disruptive"] else "") + check.get("impact", "")
            ctk.CTkLabel(box, text=note, wraplength=540, justify="left", anchor="w",
                         font=ctk.CTkFont(size=10, slant="italic"),
                         text_color=T.WARN if check["disruptive"] else T.MUTED
                         ).grid(row=1, column=0, padx=(38, 10), pady=(0, 8), sticky="w")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.grid(row=2, column=0, padx=16, pady=(4, 14), sticky="e")

        def selected():
            return [c for c in candidates if vars_[c["id"]].get()]

        apply_btn = ctk.CTkButton(btns, width=150)

        def refresh_apply(*_):
            n = len(selected())
            apply_btn.configure(text=f"Apply {n} fix{'es' if n != 1 else ''}",
                                state="normal" if n else "disabled")

        def do_apply():
            chosen = selected()
            dlg.grab_release()
            dlg.destroy()
            if chosen:
                self._run_fix_all(cat, chosen)

        for v in vars_.values():
            v.trace_add("write", refresh_apply)
        apply_btn.configure(command=do_apply)
        ctk.CTkButton(btns, text="Cancel", width=100, fg_color="transparent", border_width=1,
                      command=lambda: (dlg.grab_release(), dlg.destroy())
                      ).grid(row=0, column=0, padx=(0, 8))
        apply_btn.grid(row=0, column=1)
        refresh_apply()

    def _run_fix_all(self, cat, checks):
        self._set_busy(True)
        log(f"Security: Fix All {cat} — {', '.join(c['id'] for c in checks)}")

        def task():
            fixed = 0
            try:
                for i, check in enumerate(checks, 1):
                    msg = f"Fix All {cat}: {i} / {len(checks)}  —  {check['name']}"
                    self.after(0, lambda m=msg: self._status_lbl.configure(text=m, text_color=T.MUTED))
                    if self._apply(check, "fix") == "PASS":
                        fixed += 1
                    self.after(0, self._after_result_change, check["id"])
            finally:
                def done():
                    self._set_busy(False)
                    self._update_status_line(f"Fix All {cat}: {fixed}/{len(checks)} now passing")
                self.after(0, done)

        threading.Thread(target=task, daemon=True).start()

    # ── Copy / export ─────────────────────────────────────────────

    def _copy_report(self):
        if not self._results:
            return
        self.clipboard_clear()
        self.clipboard_append(build_text(self._results, self._fixed))
        self._status_lbl.configure(text="Report copied to clipboard.", text_color=T.MUTED)

    def _export_report(self):
        if not self._results:
            return
        meta = machine_meta()
        stem = f"security_scan_{meta['computer']}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}"
        log_dir = writable_path("logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
            html_path = os.path.join(log_dir, stem + ".html")
            txt_path = os.path.join(log_dir, stem + ".txt")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(build_html(self._results, self._fixed, meta))
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(build_text(self._results, self._fixed, meta))
        except Exception as e:
            self._status_lbl.configure(text=f"Export failed: {e}", text_color=T.FAIL)
            return
        log(f"Security report exported: {html_path} / {txt_path}")
        self._status_lbl.configure(text=f"Report saved: {html_path} (+ .txt)", text_color=T.MUTED)
        try:
            os.startfile(html_path)
        except OSError:
            pass
