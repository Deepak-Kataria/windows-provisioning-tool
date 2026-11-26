"""Threat Report tab — "has this machine been compromised, and what could let it be?"."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import customtkinter as ctk

from ui import theme as T

from modules import security_checks as sc
from modules import threat_report as tr
from modules.logger import log
from modules.runner import run_encoded_powershell
from modules.security_report import machine_meta, ordered
from modules.threat_checks import APPROVED_ADMINS_FILE, COMPROMISE_CHECKS
from modules.utils import writable_path
from ui.widgets import meta_line, section_header, tile_row, tip

_STATUS_COLOR = T.STATUS
_LEVEL_COLOR  = T.LEVEL
_ROW_BG       = (T.PANEL, T.PANEL_2)   # alternating rows

_SCAN_WORKERS = 6


class ThreatTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._results = {}
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
            top, text="Run Threat Scan", width=170,
            font=ctk.CTkFont(size=13, weight="bold"), command=self._run_scan)
        self._scan_btn.grid(row=0, column=0, padx=(14, 8), pady=10)
        tip(self._scan_btn, "Look for signs of compromise and vulnerability exposure (Ctrl+Enter). Read-only, takes 1-3 minutes.")

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
            top, text=f"{len(COMPROMISE_CHECKS)} compromise indicators + {len(sc.CHECKS)} "
                      f"vulnerability checks. Takes 1–3 minutes.",
            text_color=T.MUTED, font=ctk.CTkFont(size=11))
        self._status_lbl.grid(row=0, column=4, padx=12, sticky="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._scroll, justify="center", text_color=T.MUTED, font=ctk.CTkFont(size=13),
            text="Has this machine been compromised, and what could let it be?\n\n"
                 "Run a threat scan for a report with two parts:\n"
                 "Signs of Compromise  ·  Vulnerability Exposure"
        ).grid(row=0, column=0, pady=60)

    # ── Scan ───────────────────────────────────────────────────────

    def shortcut_apply(self):
        self._run_scan()

    def _run_scan(self):
        if self._running:
            return
        self._running = True
        self._results = {}
        for b in (self._export_btn, self._copy_btn):
            b.configure(state="disabled")
        self._scan_btn.configure(state="disabled", text="Scanning...")
        self._status_lbl.configure(text="Running checks...", text_color=T.MUTED)
        for w in self._scroll.winfo_children():
            w.destroy()
        prog = ctk.CTkLabel(self._scroll, text=f"Scanning...  0 / {len(tr.ALL_CHECKS)}",
                            text_color=T.MUTED, font=ctk.CTkFont(size=13))
        prog.grid(row=0, column=0, pady=60)
        log("Threat report: scan started")

        def run_one(check):
            _, out = run_encoded_powershell(check["check_ps"], timeout=check.get("timeout", 120))
            return check, sc.evaluate(check, out)

        def task():
            results, total = {}, len(tr.ALL_CHECKS)
            try:
                with ThreadPoolExecutor(max_workers=_SCAN_WORKERS) as pool:
                    # Slowest checks first so they don't hold up the end of the scan
                    order = sorted(tr.ALL_CHECKS, key=lambda c: -c.get("timeout", 120))
                    futures = [pool.submit(run_one, c) for c in order]
                    for done, fut in enumerate(as_completed(futures), 1):
                        try:
                            check, (status, detail) = fut.result()
                        except Exception as e:
                            log(f"Threat check crashed: {e}", "error")
                            continue
                        results[check["id"]] = (status, detail)
                        log(f"Threat {check['id']}: {status} {detail}")
                        msg = f"Scanning...  {done} / {total}  —  {check['name']}"
                        self.after(0, lambda m=msg: prog.winfo_exists() and prog.configure(text=m))
            finally:
                self.after(0, self._finish_scan, results)

        threading.Thread(target=task, daemon=True).start()

    def _finish_scan(self, results):
        self._results = results
        self._scan_time = datetime.now().strftime("%Y-%m-%d  %H:%M")
        self._running = False
        self._scan_btn.configure(state="normal", text="Run Threat Scan")
        self._export_btn.configure(state="normal")
        self._copy_btn.configure(state="normal")
        self._render()
        t = tr.threat_summary(results)
        self._status_lbl.configure(
            text=f"Scan complete  |  Overall {t['overall']}  |  Compromise: {t['compromise_level']}"
                 f"  |  Exposure: {t['exposure']['level']} ({t['exposure']['score']}/100)",
            text_color=_LEVEL_COLOR[t["overall"]])
        log(f"Threat report: overall {t['overall']}")

    # ── Rendering ─────────────────────────────────────────────────

    def _render(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        t = tr.threat_summary(self._results)
        row = 0

        # Summary tiles
        exp = t["exposure"]
        comp_flagged = sum(1 for c in COMPROMISE_CHECKS
                           if self._results.get(c["id"], ("UNKNOWN",))[0] in ("FAIL", "WARN", "INFO"))
        exp_flagged = sum(1 for c in sc.CHECKS
                          if self._results.get(c["id"], ("UNKNOWN",))[0] in ("FAIL", "WARN"))
        summary = ctk.CTkFrame(self._scroll, fg_color="transparent")
        summary.grid(row=row, column=0, padx=12, pady=(12, 4), sticky="ew")
        summary.grid_columnconfigure(0, weight=1)
        tiles, _ = tile_row(summary, [
            ("Overall", t["overall"], _LEVEL_COLOR[t["overall"]], "worst of both parts"),
            ("Compromise", t["compromise_level"], _LEVEL_COLOR[t["compromise_level"]],
             t["compromise_verdict"]),
            ("Exposure", exp["level"], _LEVEL_COLOR[exp["level"]],
             f"security score {exp['score']}/100"),
            ("Indicators flagged", comp_flagged, T.WARN if comp_flagged else T.OK,
             f"of {len(COMPROMISE_CHECKS)} compromise checks"),
            ("Weaknesses", exp_flagged, T.WARN if exp_flagged else T.OK,
             f"of {len(sc.CHECKS)} vulnerability checks"),
        ])
        tiles.grid(row=0, column=0, sticky="ew")
        meta = machine_meta()
        meta_line(summary, [("host", meta["computer"]), ("scanned", self._scan_time),
                            ("checks", len(tr.ALL_CHECKS))]
                  ).grid(row=1, column=0, pady=(8, 0), sticky="w")
        row += 1

        # Part 1 — compromise
        row = self._part_header(row, "Signs of Compromise", "was it hacked?")
        row = self._group(row, "Compromise indicators", COMPROMISE_CHECKS, compromise=True)
        if any(self._results.get("unapproved_admins", ("",))[0] == s for s in ("WARN", "UNKNOWN")):
            ctk.CTkLabel(self._scroll, text=f"Approved admin list: {APPROVED_ADMINS_FILE}",
                         text_color=T.MUTED, font=ctk.CTkFont(size=10), anchor="w"
                         ).grid(row=row, column=0, padx=16, sticky="w")
            row += 1

        # Part 2 — exposure
        row = self._part_header(row, "Vulnerability Exposure",
                                "can it be hacked?  —  apply fixes from the Security tab")
        for cat in sc.CATEGORIES:
            row = self._group(row, cat, [c for c in sc.CHECKS if c["category"] == cat])

    def _part_header(self, row, title, subtitle):
        hdr, col = section_header(self._scroll, title, height=40, big=True)
        hdr.grid(row=row, column=0, padx=12, pady=(20, 0), sticky="ew")
        ctk.CTkLabel(hdr, text=subtitle, text_color=T.MUTED, font=ctk.CTkFont(size=11),
                     anchor="w").grid(row=0, column=col, padx=4, sticky="w")
        return row + 1

    def _group(self, row, title, checks, compromise=False):
        statuses = [self._results.get(c["id"], ("UNKNOWN",))[0] for c in checks]
        parts = [f"{statuses.count(s)} {w}" for s, w in
                 (("FAIL", "failed"), ("WARN", "to check"), ("INFO", "to review"))
                 if statuses.count(s)]
        color = T.FAIL if "FAIL" in statuses else (T.WARN if "WARN" in statuses else T.OK)

        hdr, col = section_header(self._scroll, title, height=30, accent=T.BORDER)
        hdr.grid(row=row, column=0, padx=12, pady=(10, 0), sticky="ew")
        ctk.CTkLabel(hdr, text=(" · ".join(parts) or f"all {len(checks)} passed") + f"   [{len(checks)}]",
                     text_color=color, font=T.mono(11)
                     ).grid(row=0, column=col, padx=4, sticky="w")
        row += 1

        grp = ctk.CTkFrame(self._scroll, corner_radius=0)
        grp.grid(row=row, column=0, padx=12, pady=(0, 4), sticky="ew")
        grp.grid_columnconfigure(0, weight=1)
        for i, check in enumerate(ordered(checks, self._results)):
            self._row(grp, i, check, compromise)
        return row + 1

    def _row(self, parent, idx, check, compromise):
        status, detail = self._results.get(check["id"], ("UNKNOWN", ""))
        color = _STATUS_COLOR.get(status, T.MUTED)
        r = ctk.CTkFrame(parent, fg_color=_ROW_BG[idx % 2], corner_radius=0)
        r.grid(row=idx, column=0, sticky="ew")
        r.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(r, text=T.STATUS_TAG.get(status, " ?? "), width=44, text_color=color,
                     font=T.mono(11, "bold")
                     ).grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=4, sticky="n")
        sev = check["severity"]
        ctk.CTkLabel(r, text=T.SEV_TAG.get(sev, sev), width=36, font=T.mono(10, "bold"), text_color=T.SEV[sev]
                     ).grid(row=0, column=1, padx=(0, 6), pady=4, sticky="n")
        ctk.CTkLabel(r, text=check["name"], width=230, anchor="w", justify="left",
                     wraplength=225, text_color=T.TEXT_BRIGHT if status != "PASS" else T.TEXT,
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=0, column=2, rowspan=2, padx=(0, 12), pady=4, sticky="nw")

        ctk.CTkLabel(r, text=detail or check["description"], anchor="w", justify="left",
                     wraplength=460, font=T.mono(11),
                     text_color=color if detail and status != "PASS" else T.MUTED
                     ).grid(row=0, column=3, padx=(0, 12), pady=(4, 0), sticky="w")

        flagged = status in ("FAIL", "WARN", "INFO")
        note = None
        if flagged and compromise and check.get("action"):
            note = f"action: {check['action']}"
        elif status in ("FAIL", "WARN") and not compromise and check.get("impact"):
            note = f"if fixed: {check['impact']}"
        if note:
            ctk.CTkLabel(r, text=note, anchor="w", justify="left", wraplength=460, height=16,
                         text_color=T.DIM, font=ctk.CTkFont(size=10, slant="italic")
                         ).grid(row=1, column=3, padx=(0, 12), pady=(0, 4), sticky="w")

        if flagged and compromise and check.get("review_ps"):
            T.outline_button(r, text=check["review_label"], width=150, height=24,
                             command=lambda c=check: self._open_review(c)
                             ).grid(row=0, column=4, rowspan=2, padx=(0, 10), pady=4)

    def _open_review(self, check):
        threading.Thread(target=run_encoded_powershell, args=(check["review_ps"],),
                         daemon=True).start()
        self._status_lbl.configure(text=f"{check['review_label']}...", text_color=T.MUTED)

    # ── Copy / export ─────────────────────────────────────────────

    def _copy_report(self):
        if not self._results:
            return
        self.clipboard_clear()
        self.clipboard_append(tr.build_text(self._results))
        self._status_lbl.configure(text="Report copied to clipboard.", text_color=T.MUTED)

    def _export_report(self):
        if not self._results:
            return
        meta = machine_meta()
        stem = f"threat_report_{meta['computer']}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}"
        log_dir = writable_path("logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
            html_path = os.path.join(log_dir, stem + ".html")
            txt_path = os.path.join(log_dir, stem + ".txt")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(tr.build_html(self._results, meta))
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(tr.build_text(self._results, meta))
        except Exception as e:
            self._status_lbl.configure(text=f"Export failed: {e}", text_color=T.FAIL)
            return
        log(f"Threat report exported: {html_path} / {txt_path}")
        self._status_lbl.configure(text=f"Report saved: {html_path} (+ .txt)", text_color=T.MUTED)
        try:
            os.startfile(html_path)
        except OSError:
            pass
