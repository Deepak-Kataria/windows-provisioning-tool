import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import customtkinter as ctk

from modules import security_checks as sc
from modules.logger import log, log_change
from modules.runner import run_encoded_powershell
from modules.security_report import build_html, build_text, machine_meta, ordered_checks
from modules.utils import writable_path

CHECKS = sc.CHECKS  # kept for any external imports

_SEV_COLOR    = {"HIGH": "#c0392b", "MEDIUM": "#d35400", "LOW": "#7f8c8d"}
_STATUS_COLOR = {"PASS": "#27ae60", "FAIL": "#e74c3c", "WARN": "#e67e22", "UNKNOWN": "gray"}
_STATUS_ICON  = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "UNKNOWN": "?"}
_LEVEL_COLOR  = {"CLEAN": "#27ae60", "LOW": "#2874a6", "MEDIUM": "#d35400",
                 "HIGH": "#c0392b", "CRITICAL": "#7b241c"}
_CAT_HDR_BG   = ("gray82", "gray24")

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

        top = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=("gray90", "gray17"))
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(4, weight=1)
        top.grid_propagate(False)

        self._scan_btn = ctk.CTkButton(
            top, text="Run Vulnerability Scan", width=190,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._run_scan)
        self._scan_btn.grid(row=0, column=0, padx=(14, 8), pady=10)

        self._export_btn = ctk.CTkButton(
            top, text="Export Report", width=120, fg_color="transparent", border_width=1,
            state="disabled", command=self._export_report)
        self._export_btn.grid(row=0, column=1, padx=6, pady=10)

        self._copy_btn = ctk.CTkButton(
            top, text="Copy Report", width=110, fg_color="transparent", border_width=1,
            state="disabled", command=self._copy_report)
        self._copy_btn.grid(row=0, column=2, padx=6, pady=10)

        self._status_lbl = ctk.CTkLabel(
            top, text=f"Click 'Run Vulnerability Scan' to start ({len(CHECKS)} checks).",
            text_color="gray", font=ctk.CTkFont(size=11))
        self._status_lbl.grid(row=0, column=4, padx=12, sticky="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._scroll, text="No scan results yet.\nRun a scan to see the security report.",
            text_color="gray", font=ctk.CTkFont(size=13), justify="center"
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

        self._summary = ctk.CTkFrame(self._scroll, corner_radius=8)
        self._summary.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        self._summary.grid_columnconfigure(1, weight=1)
        self._fill_summary()

        grid_row = 1
        for cat in sc.CATEGORIES:
            hdr = ctk.CTkFrame(self._scroll, fg_color=_CAT_HDR_BG, corner_radius=0, height=38)
            hdr.grid(row=grid_row, column=0, padx=12, pady=(12, 0), sticky="ew")
            hdr.grid_propagate(False)
            hdr.grid_columnconfigure(1, weight=1)
            hdr.grid_rowconfigure(0, weight=1)
            ctk.CTkLabel(hdr, text=f"  {cat}", font=ctk.CTkFont(size=13, weight="bold"),
                         anchor="w").grid(row=0, column=0, padx=6, sticky="w")
            count_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=11),
                                     text_color="gray", anchor="w")
            count_lbl.grid(row=0, column=1, padx=8, sticky="w")
            fix_all_btn = ctk.CTkButton(
                hdr, text="Fix All", width=120, height=26,
                fg_color="#2980b9", hover_color="#1a5276",
                command=lambda c=cat: self._open_fix_all(c))
            fix_all_btn.grid(row=0, column=2, padx=8)
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

        ctk.CTkLabel(
            self._summary, text=f"  {s['level']}  ", fg_color=_LEVEL_COLOR[s["level"]],
            text_color="white", corner_radius=6, height=44,
            font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, rowspan=3, padx=(14, 12), pady=12, sticky="ns")

        ctk.CTkLabel(
            self._summary, text=f"Security score  {s['score']} / 100",
            font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        ).grid(row=0, column=1, padx=0, pady=(12, 0), sticky="w")

        meta = machine_meta()
        ctk.CTkLabel(
            self._summary,
            text=f"{meta['computer']}   |   Scanned {self._scan_time or '-'}   |   {len(CHECKS)} checks",
            text_color="gray", font=ctk.CTkFont(size=11), anchor="w"
        ).grid(row=1, column=1, sticky="w")

        pills = ctk.CTkFrame(self._summary, fg_color="transparent")
        pills.grid(row=2, column=1, pady=(4, 12), sticky="w")
        items = [(f"  {c['FAIL']} FAILED  ", "#c0392b"),
                 (f"  {c['WARN']} WARNING  ", "#d35400"),
                 (f"  {c['PASS']} PASSED  ", "#27ae60")]
        if c["UNKNOWN"]:
            items.append((f"  {c['UNKNOWN']} UNKNOWN  ", "#7f8c8d"))
        for col, (label, color) in enumerate(items):
            ctk.CTkLabel(pills, text=label, fg_color=color, text_color="white", corner_radius=5,
                         font=ctk.CTkFont(size=11, weight="bold"), height=26
                         ).grid(row=0, column=col, padx=(0, 6))

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
        color = "#e74c3c" if n_fail else ("#e67e22" if n_warn else "#27ae60")
        w["count_lbl"].configure(text=f"{text}   ({len(ids)} checks)", text_color=color)

        n_fix = len(self._fix_all_candidates(cat))
        w["fix_all_btn"].configure(
            text=f"Fix All ({n_fix})" if n_fix else "Fix All",
            state="normal" if n_fix and not self._running else "disabled")

    def _add_result_row(self, parent, check, row_idx):
        bg = ("gray95", "gray18") if row_idx % 2 == 0 else ("gray90", "gray20")
        row = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0)
        row.grid(row=row_idx, column=0, sticky="ew")
        row.grid_columnconfigure(2, weight=1)

        icon_lbl = ctk.CTkLabel(row, text="", width=30, font=ctk.CTkFont(size=14, weight="bold"))
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(8, 2), pady=8)

        name_frame = ctk.CTkFrame(row, fg_color="transparent", width=210)
        name_frame.grid(row=0, column=1, rowspan=2, padx=(0, 12), pady=8, sticky="w")
        name_lbl = ctk.CTkLabel(name_frame, text=check["name"], width=210, anchor="w",
                                justify="left", wraplength=205,
                                font=ctk.CTkFont(size=12, weight="bold"))
        name_lbl.grid(row=0, column=0, sticky="w")
        sev = check["severity"]
        ctk.CTkLabel(name_frame, text=f" {sev} ", height=16, corner_radius=3,
                     fg_color=_SEV_COLOR[sev], text_color="white",
                     font=ctk.CTkFont(size=9, weight="bold")
                     ).grid(row=1, column=0, pady=(2, 0), sticky="w")

        detail_lbl = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=11), anchor="w",
                                  wraplength=400, justify="left")
        detail_lbl.grid(row=0, column=2, padx=(0, 12), pady=(8, 0), sticky="w")

        if check.get("impact"):
            ctk.CTkLabel(row, text=f"If fixed: {check['impact']}",
                         font=ctk.CTkFont(size=10, slant="italic"), text_color="gray",
                         anchor="w", wraplength=400, justify="left"
                         ).grid(row=1, column=2, padx=(0, 12), pady=(0, 8), sticky="w")

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.grid(row=0, column=3, rowspan=2, padx=(0, 10), pady=6)

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
        color = _STATUS_COLOR.get(status, "gray")
        w["icon_lbl"].configure(text=f" {_STATUS_ICON.get(status, '?')} ", text_color=color)
        w["name_lbl"].configure(text_color=color)
        w["detail_lbl"].configure(text=detail or check["description"],
                                  text_color=color if detail else "gray")

        for child in w["btn_frame"].winfo_children():
            child.destroy()
        w["fix_btn"] = w["revert_btn"] = None

        col = 0
        if status in ("FAIL", "WARN") and check.get("fix_ps"):
            w["fix_btn"] = ctk.CTkButton(
                w["btn_frame"], text=check["fix_label"], width=145, height=28,
                fg_color="#2980b9", hover_color="#1a5276",
                command=lambda c=check: self._run_fix(c))
            w["fix_btn"].grid(row=0, column=col, padx=(0, 4))
            col += 1
        if check.get("undo_ps"):
            w["revert_btn"] = ctk.CTkButton(
                w["btn_frame"], text=check.get("undo_label", "Revert"), width=160, height=28,
                fg_color="#7f8c8d", hover_color="#5d6d7e",
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
        color = "#e74c3c" if c["FAIL"] else ("#e67e22" if c["WARN"] else "#27ae60")
        self._status_lbl.configure(
            text=f"{prefix}  |  {s['level']} ({s['score']}/100)  |  "
                 f"{c['FAIL']} failed  {c['WARN']} warnings  {c['PASS']} passed",
            text_color=color)

    # ── Scan ───────────────────────────────────────────────────────

    def _run_scan(self):
        if self._running:
            return
        self._fixed.clear()
        self._results.clear()
        self._export_btn.configure(state="disabled")
        self._copy_btn.configure(state="disabled")
        self._clear_report()
        self._set_busy(True, "Scanning...")
        self._status_lbl.configure(text="Running checks...", text_color="gray")

        prog = ctk.CTkLabel(self._scroll, text=f"Scanning...  0 / {len(CHECKS)}",
                            text_color="gray", font=ctk.CTkFont(size=13))
        prog.grid(row=0, column=0, pady=60)
        log("Security: scan started")

        def run_one(check):
            _, out = run_encoded_powershell(check["check_ps"])
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
                                       text_color="gray")
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
            scroll, wraplength=560, justify="left", anchor="w", text_color="gray",
            font=ctk.CTkFont(size=11),
            text="Ticked fixes run one after another and each is re-checked. Fixes that can "
                 "interrupt how people work are unticked — tick them only if you've read the impact."
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        vars_ = {}
        for i, check in enumerate(candidates, 1):
            box = ctk.CTkFrame(scroll, fg_color=("gray92", "gray20"))
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
                         text_color="#d35400" if check["disruptive"] else "gray"
                         ).grid(row=1, column=0, padx=(38, 10), pady=(0, 8), sticky="w")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.grid(row=2, column=0, padx=16, pady=(4, 14), sticky="e")

        def selected():
            return [c for c in candidates if vars_[c["id"]].get()]

        apply_btn = ctk.CTkButton(btns, width=150, fg_color="#2980b9", hover_color="#1a5276")

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
                    self.after(0, lambda m=msg: self._status_lbl.configure(text=m, text_color="gray"))
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
        self._status_lbl.configure(text="Report copied to clipboard.", text_color="gray")

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
            self._status_lbl.configure(text=f"Export failed: {e}", text_color="#e74c3c")
            return
        log(f"Security report exported: {html_path} / {txt_path}")
        self._status_lbl.configure(text=f"Report saved: {html_path} (+ .txt)", text_color="gray")
        try:
            os.startfile(html_path)
        except OSError:
            pass
