"""Threat Report tab — "has this machine been compromised, and what could let it be?"."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import customtkinter as ctk

from modules import security_checks as sc
from modules import threat_report as tr
from modules.logger import log
from modules.runner import run_encoded_powershell
from modules.security_report import machine_meta, ordered
from modules.threat_checks import APPROVED_ADMINS_FILE, COMPROMISE_CHECKS
from modules.utils import writable_path
from ui.widgets import tip

_SEV_COLOR    = {"HIGH": "#c0392b", "MEDIUM": "#d35400", "LOW": "#7f8c8d"}
_STATUS_COLOR = {"PASS": "#27ae60", "FAIL": "#e74c3c", "WARN": "#e67e22",
                 "UNKNOWN": "gray", "INFO": "#2e86c1"}
_STATUS_ICON  = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "UNKNOWN": "?", "INFO": "i"}
_LEVEL_COLOR  = {"CLEAN": "#27ae60", "LOW": "#2874a6", "MEDIUM": "#d35400",
                 "HIGH": "#c0392b", "CRITICAL": "#7b241c"}
_HDR_BG       = ("gray82", "gray24")
_PART_BG      = ("gray75", "gray28")

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

        top = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=("gray90", "gray17"))
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
            text_color="gray", font=ctk.CTkFont(size=11))
        self._status_lbl.grid(row=0, column=4, padx=12, sticky="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._scroll, justify="center", text_color="gray", font=ctk.CTkFont(size=13),
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
        self._status_lbl.configure(text="Running checks...", text_color="gray")
        for w in self._scroll.winfo_children():
            w.destroy()
        prog = ctk.CTkLabel(self._scroll, text=f"Scanning...  0 / {len(tr.ALL_CHECKS)}",
                            text_color="gray", font=ctk.CTkFont(size=13))
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

        # Summary card
        card = ctk.CTkFrame(self._scroll, corner_radius=8)
        card.grid(row=row, column=0, padx=12, pady=(12, 6), sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text=f"  {t['overall']}  ", fg_color=_LEVEL_COLOR[t["overall"]],
                     text_color="white", corner_radius=6, height=50,
                     font=ctk.CTkFont(size=19, weight="bold")
                     ).grid(row=0, column=0, rowspan=3, padx=(14, 14), pady=12, sticky="ns")
        meta = machine_meta()
        ctk.CTkLabel(card, text=f"Threat Report — {meta['computer']}   |   Scanned {self._scan_time}",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
                     ).grid(row=0, column=1, pady=(12, 0), sticky="w")
        exp = t["exposure"]
        for r, (label, level, text) in enumerate([
            ("Signs of compromise", t["compromise_level"], t["compromise_verdict"]),
            ("Vulnerability exposure", exp["level"], f"security score {exp['score']}/100"),
        ], 1):
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.grid(row=r, column=1, sticky="w", pady=(2, 10 if r == 2 else 0))
            ctk.CTkLabel(line, text=f"{label}:", width=160, anchor="w",
                         font=ctk.CTkFont(size=12)).grid(row=0, column=0)
            ctk.CTkLabel(line, text=f" {level} ", fg_color=_LEVEL_COLOR[level], text_color="white",
                         corner_radius=4, height=20, font=ctk.CTkFont(size=11, weight="bold")
                         ).grid(row=0, column=1, padx=(0, 8))
            ctk.CTkLabel(line, text=text, text_color="gray", font=ctk.CTkFont(size=12)
                         ).grid(row=0, column=2)
        row += 1

        # Part 1 — compromise
        row = self._part_header(row, "Signs of Compromise", "was it hacked?")
        row = self._group(row, "Compromise indicators", COMPROMISE_CHECKS, compromise=True)
        if any(self._results.get("unapproved_admins", ("",))[0] == s for s in ("WARN", "UNKNOWN")):
            ctk.CTkLabel(self._scroll, text=f"Approved admin list: {APPROVED_ADMINS_FILE}",
                         text_color="gray", font=ctk.CTkFont(size=10), anchor="w"
                         ).grid(row=row, column=0, padx=16, sticky="w")
            row += 1

        # Part 2 — exposure
        row = self._part_header(row, "Vulnerability Exposure",
                                "can it be hacked?  —  apply fixes from the Security tab")
        for cat in sc.CATEGORIES:
            row = self._group(row, cat, [c for c in sc.CHECKS if c["category"] == cat])

    def _part_header(self, row, title, subtitle):
        hdr = ctk.CTkFrame(self._scroll, fg_color=_PART_BG, corner_radius=6)
        hdr.grid(row=row, column=0, padx=12, pady=(18, 0), sticky="ew")
        ctk.CTkLabel(hdr, text=f"  {title}", font=ctk.CTkFont(size=15, weight="bold"),
                     anchor="w").grid(row=0, column=0, padx=6, pady=8, sticky="w")
        ctk.CTkLabel(hdr, text=subtitle, text_color="gray", font=ctk.CTkFont(size=11),
                     anchor="w").grid(row=0, column=1, padx=6, sticky="w")
        return row + 1

    def _group(self, row, title, checks, compromise=False):
        statuses = [self._results.get(c["id"], ("UNKNOWN",))[0] for c in checks]
        parts = [f"{statuses.count(s)} {w}" for s, w in
                 (("FAIL", "failed"), ("WARN", "to check"), ("INFO", "to review"))
                 if statuses.count(s)]
        color = ("#e74c3c" if "FAIL" in statuses else
                 "#e67e22" if "WARN" in statuses else "#27ae60")

        hdr = ctk.CTkFrame(self._scroll, fg_color=_HDR_BG, corner_radius=0, height=32)
        hdr.grid(row=row, column=0, padx=12, pady=(10, 0), sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text=f"  {title}", font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=0, padx=6, sticky="w")
        ctk.CTkLabel(hdr, text=" · ".join(parts) or f"all {len(checks)} passed",
                     text_color=color, font=ctk.CTkFont(size=11)
                     ).grid(row=0, column=1, padx=8, sticky="w")
        row += 1

        grp = ctk.CTkFrame(self._scroll, corner_radius=0)
        grp.grid(row=row, column=0, padx=12, pady=(0, 4), sticky="ew")
        grp.grid_columnconfigure(0, weight=1)
        for i, check in enumerate(ordered(checks, self._results)):
            self._row(grp, i, check, compromise)
        return row + 1

    def _row(self, parent, idx, check, compromise):
        status, detail = self._results.get(check["id"], ("UNKNOWN", ""))
        color = _STATUS_COLOR.get(status, "gray")
        bg = ("gray95", "gray18") if idx % 2 == 0 else ("gray90", "gray20")
        r = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0)
        r.grid(row=idx, column=0, sticky="ew")
        r.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(r, text=f" {_STATUS_ICON.get(status, '?')} ", width=30, text_color=color,
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=0, column=0, rowspan=2, padx=(8, 2), pady=6)

        nf = ctk.CTkFrame(r, fg_color="transparent")
        nf.grid(row=0, column=1, rowspan=2, padx=(0, 12), pady=6, sticky="w")
        ctk.CTkLabel(nf, text=check["name"], width=210, anchor="w", justify="left",
                     wraplength=205, text_color=color, font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(nf, text=f" {check['severity']} ", height=16, corner_radius=3,
                     fg_color=_SEV_COLOR[check["severity"]], text_color="white",
                     font=ctk.CTkFont(size=9, weight="bold")
                     ).grid(row=1, column=0, pady=(2, 0), sticky="w")

        ctk.CTkLabel(r, text=detail or check["description"], anchor="w", justify="left",
                     wraplength=430, font=ctk.CTkFont(size=11),
                     text_color=color if detail else "gray"
                     ).grid(row=0, column=2, padx=(0, 12), pady=(6, 0), sticky="w")

        flagged = status in ("FAIL", "WARN", "INFO")
        note = None
        if flagged and compromise and check.get("action"):
            note = f"Action: {check['action']}"
        elif status in ("FAIL", "WARN") and not compromise and check.get("impact"):
            note = f"If fixed: {check['impact']}"
        if note:
            ctk.CTkLabel(r, text=note, anchor="w", justify="left", wraplength=430,
                         text_color="gray", font=ctk.CTkFont(size=10, slant="italic")
                         ).grid(row=1, column=2, padx=(0, 12), pady=(0, 6), sticky="w")

        if flagged and compromise and check.get("review_ps"):
            ctk.CTkButton(r, text=check["review_label"], width=150, height=28,
                          fg_color="#7f8c8d", hover_color="#5d6d7e",
                          command=lambda c=check: self._open_review(c)
                          ).grid(row=0, column=3, rowspan=2, padx=(0, 10), pady=6)

    def _open_review(self, check):
        threading.Thread(target=run_encoded_powershell, args=(check["review_ps"],),
                         daemon=True).start()
        self._status_lbl.configure(text=f"{check['review_label']}...", text_color="gray")

    # ── Copy / export ─────────────────────────────────────────────

    def _copy_report(self):
        if not self._results:
            return
        self.clipboard_clear()
        self.clipboard_append(tr.build_text(self._results))
        self._status_lbl.configure(text="Report copied to clipboard.", text_color="gray")

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
            self._status_lbl.configure(text=f"Export failed: {e}", text_color="#e74c3c")
            return
        log(f"Threat report exported: {html_path} / {txt_path}")
        self._status_lbl.configure(text=f"Report saved: {html_path} (+ .txt)", text_color="gray")
        try:
            os.startfile(html_path)
        except OSError:
            pass
