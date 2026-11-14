"""Home — Command Center: the whole machine at a glance, one card per area.

Cheap facts (disk, uptime, pending restart, scan results already in memory, recent changes)
refresh every time the page is shown. Slower facts (installed bloatware, user profiles) are
gathered with PowerShell in the background on first show and on Refresh.
"""
import ctypes
import json
import os
import platform
import shutil
import socket
import threading
import winreg
from datetime import datetime, timedelta

import customtkinter as ctk

from modules import security_checks as sc
from modules import threat_report as tr
from modules.appx import installed_appx_names
from modules.logger import CHANGES_LOG, log
from modules.runner import run_encoded_powershell
from ui import theme as T
from ui.widgets import meta_line, section_header, tip

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
STALE_PROFILE_DAYS = 90
FEED_LINES = 8

_PROFILES_PS = r"""
Get-CimInstance Win32_UserProfile | Where-Object { -not $_.Special } | ForEach-Object {
    $t = if ($_.LastUseTime) { $_.LastUseTime.ToString('s') } else { '' }
    "$($_.LocalPath)|$t|$($_.Loaded)"
}
"""

_REBOOT_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
]


# ── Data helpers (no UI) ─────────────────────────────────────────────

def _uptime():
    secs = ctypes.windll.kernel32.GetTickCount64() // 1000
    d, rem = divmod(secs, 86400)
    return f"{d}d {rem // 3600}h" if d else f"{rem // 3600}h {(rem % 3600) // 60}m"


def _uptime_days():
    return ctypes.windll.kernel32.GetTickCount64() / 86_400_000


def _os_label():
    """platform.release() says '10' on Windows 11 too, so go by the build number."""
    try:
        build = int(platform.version().split(".")[-1])
    except ValueError:
        return platform.platform()
    return f"Windows {'11' if build >= 22000 else '10'} · build {build}"


def _pending_restart():
    """Reasons a restart is pending (empty list = none). Registry only, so it's instant."""
    reasons = []
    for key in _REBOOT_KEYS:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key))
            reasons.append("Windows Update" if "WindowsUpdate" in key else "servicing")
        except OSError:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\Session Manager") as k:
            val, _ = winreg.QueryValueEx(k, "PendingFileRenameOperations")
            if val:
                reasons.append("file renames")
    except OSError:
        pass
    return reasons


def _disk(drive="C:\\"):
    try:
        u = shutil.disk_usage(drive)
        return u.total, u.free
    except OSError:
        return None


def _gb(n):
    return f"{n / 1024 ** 3:,.1f} GB"


def _recent_changes(n=FEED_LINES):
    """Last n entries of changes.log as (when, category, action), newest first."""
    try:
        with open(CHANGES_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 64 * 1024))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) < 3:
            continue
        out.append((parts[0], parts[1], parts[2]))
        if len(out) >= n:
            break
    return out


def _when(ts):
    """'2026-11-14 12:04:01' -> '12:04' today, 'Yesterday 12:04', or '11-02 12:04'."""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts[:16]
    today = datetime.now().date()
    if dt.date() == today:
        return dt.strftime("%H:%M")
    if dt.date() == today - timedelta(days=1):
        return dt.strftime("Yest %H:%M")
    return dt.strftime("%m-%d %H:%M")


# ── Card widget ──────────────────────────────────────────────────────

class HomeCard(ctk.CTkFrame):
    """Clickable summary card: coloured top strip, label + 'open ▸', big value, meter, subline."""

    def __init__(self, master, label, on_click, hint=None, meter=False):
        super().__init__(master, fg_color=T.PANEL, corner_radius=4, border_width=1,
                         border_color=T.BORDER, cursor="hand2")
        self.grid_columnconfigure(0, weight=1)
        self._strip = ctk.CTkFrame(self, height=2, width=1, corner_radius=0, fg_color=T.BORDER)
        self._strip.grid(row=0, column=0, columnspan=2, sticky="ew", padx=1, pady=(1, 0))
        ctk.CTkLabel(self, text=label.upper(), font=T.mono(10, "bold"), text_color=T.MUTED,
                     anchor="w", height=16).grid(row=1, column=0, padx=14, pady=(10, 0), sticky="w")
        self._open = ctk.CTkLabel(self, text="open ▸", font=T.mono(10), text_color=T.DIM, height=16)
        self._open.grid(row=1, column=1, padx=14, pady=(10, 0), sticky="e")
        self._value = ctk.CTkLabel(self, text="…", font=T.mono(26, "bold"), anchor="w", height=36,
                                   text_color=T.MUTED)
        self._value.grid(row=2, column=0, columnspan=2, padx=14, sticky="w")
        self._meter = None
        if meter:
            self._meter = ctk.CTkProgressBar(self, height=6, corner_radius=2)
            self._meter.set(0)
            self._meter.grid(row=3, column=0, columnspan=2, padx=14, pady=(2, 4), sticky="ew")
        self._sub = ctk.CTkLabel(self, text="", font=T.ui(11), text_color=T.MUTED, anchor="w",
                                 justify="left", wraplength=300, height=18)
        self._sub.grid(row=4, column=0, columnspan=2, padx=14, pady=(0, 12), sticky="w")

        self._bind_all(self, on_click)
        if hint:
            tip(self, hint)

    def _bind_all(self, widget, on_click):
        widget.bind("<Button-1>", lambda e: on_click(), add="+")
        widget.bind("<Enter>", lambda e: self._hover(True), add="+")
        widget.bind("<Leave>", lambda e: self._hover(False), add="+")
        for child in widget.winfo_children():
            self._bind_all(child, on_click)

    def _hover(self, on):
        self.configure(border_color=T.ACCENT if on else T.BORDER)
        self._open.configure(text_color=T.ACCENT if on else T.DIM)

    def set(self, value, color=None, sub="", meter=None):
        color = color or T.TEXT_BRIGHT
        self._strip.configure(fg_color=color)
        self._value.configure(text=str(value), text_color=color)
        self._sub.configure(text=sub or " ")
        if self._meter is not None and meter is not None:
            self._meter.configure(progress_color=color)
            self._meter.set(max(0.0, min(1.0, meter)))


# ── Page ─────────────────────────────────────────────────────────────

class HomeTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._shell = None          # Dashboard, set by attach_shell()
        self._loaded_slow = False
        self._busy = False
        self._bloat_list = self._load_bloat_list()
        self._build()

    # Dashboard hands itself over so cards can open pages and read their scan results.
    def attach_shell(self, shell):
        self._shell = shell

    def _go(self, page):
        if self._shell:
            self._shell.show(page)

    def _page(self, name):
        if not self._shell or name not in self._shell._pages:
            return None
        return self._shell._pages[name][1]

    @staticmethod
    def _load_bloat_list():
        try:
            with open(os.path.join(CONFIG_DIR, "debloat_list.json"), encoding="utf-8") as f:
                return {a["package"]: a["name"] for a in json.load(f)["appx_packages"]}
        except (OSError, ValueError, KeyError):
            return {}

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top.grid_columnconfigure(0, weight=1)
        self._meta = ctk.CTkFrame(top, fg_color="transparent")
        self._meta.grid(row=0, column=0, sticky="w")
        self._refresh_btn = T.outline_button(top, text="Refresh", width=100, height=28,
                                             command=lambda: self.refresh(slow=True))
        self._refresh_btn.grid(row=0, column=1, sticky="e")
        tip(self._refresh_btn, "Re-read everything, including installed apps and user profiles")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew")
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="card")

        cards = [
            ("security", "Security", "Security", "Vulnerability scan results (opens the Security page)", True),
            ("threat", "Threats", "Threat Report", "Signs of compromise (opens the Threat Report page)", False),
            ("disk", "Disk C:", "Cleanup", "Free space on the system drive (opens Cleanup)", True),
            ("bloat", "Bloatware", "Debloat", "Apps from the debloat list that are still installed", False),
            ("profiles", "Profiles", "Cleanup", f"Local user profiles; stale = unused for {STALE_PROFILE_DAYS}+ days", False),
            ("system", "System", "System", "Uptime and pending restarts (opens System)", False),
        ]
        self._cards = {}
        for i, (key, label, page, hint, meter) in enumerate(cards):
            card = HomeCard(grid, label, lambda p=page: self._go(p), hint=hint, meter=meter)
            card.grid(row=i // 3, column=i % 3, sticky="nsew",
                      padx=(0 if i % 3 == 0 else 5, 0 if i % 3 == 2 else 5), pady=5)
            self._cards[key] = card

        hdr, col = section_header(self, "Recent actions", height=30, accent=T.BORDER)
        hdr.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self._feed_count = ctk.CTkLabel(hdr, text="", font=T.mono(10), text_color=T.DIM)
        self._feed_count.grid(row=0, column=col, padx=4, sticky="w")

        self._feed = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0)
        self._feed.grid(row=3, column=0, sticky="new")
        self._feed.grid_columnconfigure(2, weight=1)

    # ── Refresh ────────────────────────────────────────────────────

    def on_show(self):
        """Called by the dashboard each time Home becomes visible."""
        self.refresh(slow=not self._loaded_slow)

    def shortcut_apply(self):
        self.refresh(slow=True)

    def refresh(self, slow=False):
        self._fill_meta()
        self._fill_security()
        self._fill_threat()
        self._fill_disk()
        self._fill_system()
        self._fill_feed()
        if slow and not self._busy:
            self._loaded_slow = True
            self._busy = True
            self._refresh_btn.configure(state="disabled", text="Refreshing…")
            for key in ("bloat", "profiles"):
                self._cards[key].set("…", T.MUTED, "checking…")
            threading.Thread(target=self._gather_slow, daemon=True).start()

    def _fill_meta(self):
        for w in self._meta.winfo_children():
            w.destroy()
        meta_line(self._meta, [("host", socket.gethostname().upper()),
                               ("os", _os_label()),
                               ("updated", datetime.now().strftime("%H:%M:%S"))]
                  ).grid(row=0, column=0, sticky="w")

    def _fill_security(self):
        tab = self._page("Security")
        res = getattr(tab, "_results", None)
        card = self._cards["security"]
        if not res:
            card.set("NOT SCANNED", T.MUTED, f"{len(sc.CHECKS)} checks · click to open and run a scan", 0)
            return
        s = sc.risk_summary(res)
        c = s["counts"]
        fixable = sum(1 for chk in sc.CHECKS if sc.is_auto_fixable(chk)
                      and res.get(chk["id"], ("UNKNOWN",))[0] in ("FAIL", "WARN"))
        card.set(f"{s['level']} · {s['score']}", T.LEVEL[s["level"]],
                 f"{c['FAIL']} failed · {c['WARN']} warnings · {fixable} auto-fixable",
                 s["score"] / 100)

    def _fill_threat(self):
        tab = self._page("Threat Report")
        res = getattr(tab, "_results", None)
        card = self._cards["threat"]
        if not res:
            card.set("NOT SCANNED", T.MUTED, "Click to open and run a threat scan")
            return
        t = tr.threat_summary(res)
        flagged = sum(t["compromise_counts"].get(k, 0) for k in ("FAIL", "WARN", "INFO"))
        card.set(t["compromise_level"], T.LEVEL[t["compromise_level"]],
                 f"{flagged} indicator{'s' if flagged != 1 else ''} flagged · overall {t['overall']}")

    def _fill_disk(self):
        d = _disk()
        card = self._cards["disk"]
        if not d:
            card.set("N/A", T.MUTED, "Could not read drive C:", 0)
            return
        total, free = d
        pct_free = 100 * free / total if total else 0
        color = T.FAIL if pct_free < 10 else (T.WARN if pct_free < 20 else T.OK)
        card.set(f"{pct_free:.0f}% free", color,
                 f"{_gb(free)} free of {_gb(total)}", 1 - free / total if total else 0)

    def _fill_system(self):
        reasons = _pending_restart()
        days = _uptime_days()
        card = self._cards["system"]
        if reasons:
            card.set("RESTART", T.WARN, f"Pending ({', '.join(reasons)}) · up {_uptime()}")
        else:
            color = T.WARN if days >= 14 else T.OK
            card.set(f"UP {_uptime()}", color,
                     "No restart pending" + (" · long uptime, consider a restart" if days >= 14 else ""))

    def _fill_feed(self):
        for w in self._feed.winfo_children():
            w.destroy()
        items = _recent_changes()
        self._feed_count.configure(text=f"last {len(items)} from changes.log" if items else "")
        if not items:
            ctk.CTkLabel(self._feed, text="No changes recorded yet. Fixes, removals and clean-ups appear here.",
                         font=T.ui(11), text_color=T.MUTED).grid(row=0, column=0, padx=14, pady=10, sticky="w")
            return
        for i, (ts, cat, action) in enumerate(items):
            bg = T.PANEL if i % 2 == 0 else T.PANEL_2
            row = ctk.CTkFrame(self._feed, fg_color=bg, corner_radius=0, height=26)
            row.grid(row=i, column=0, columnspan=3, sticky="ew")
            row.grid_columnconfigure(2, weight=1)
            ctk.CTkLabel(row, text=_when(ts), width=96, anchor="w", font=T.mono(11),
                         text_color=T.TEXT).grid(row=0, column=0, padx=(14, 6))
            ctk.CTkLabel(row, text=cat.upper()[:18], width=150, anchor="w", font=T.mono(10, "bold"),
                         text_color=T.ACCENT).grid(row=0, column=1, padx=(0, 6))
            text = action if len(action) <= 110 else action[:107] + "…"
            ctk.CTkLabel(row, text=text, anchor="w", font=T.ui(12), text_color=T.TEXT
                         ).grid(row=0, column=2, sticky="w", padx=(0, 14))

    # ── Slow facts (worker thread) ───────────────────────────────────

    def _gather_slow(self):
        bloat = profiles = None
        try:
            installed = installed_appx_names()
            bloat = sorted(name for pkg, name in self._bloat_list.items() if pkg in installed)
        except Exception as e:
            log(f"Home: bloatware check failed: {e}", "warning")
        try:
            _, out = run_encoded_powershell(_PROFILES_PS, timeout=60)
            profiles = []
            for line in out.splitlines():
                parts = line.strip().split("|")
                if len(parts) == 3 and parts[0]:
                    profiles.append((parts[0], parts[1], parts[2].lower() == "true"))
        except Exception as e:
            log(f"Home: profile check failed: {e}", "warning")
        try:
            self.after(0, self._apply_slow, bloat, profiles)
        except RuntimeError:
            pass   # window closed meanwhile

    def _apply_slow(self, bloat, profiles):
        if not self.winfo_exists():
            return
        self._busy = False
        self._refresh_btn.configure(state="normal", text="Refresh")

        card = self._cards["bloat"]
        if bloat is None:
            card.set("N/A", T.MUTED, "Could not list installed apps")
        elif not bloat:
            card.set("CLEAN", T.OK, f"None of the {len(self._bloat_list)} listed apps are installed")
        else:
            names = ", ".join(bloat[:3]) + ("…" if len(bloat) > 3 else "")
            card.set(len(bloat), T.WARN, f"still installed: {names}")

        card = self._cards["profiles"]
        if profiles is None:
            card.set("N/A", T.MUTED, "Could not list user profiles")
            return
        cutoff = datetime.now() - timedelta(days=STALE_PROFILE_DAYS)
        stale = 0
        for _, last, loaded in profiles:
            try:
                if not loaded and last and datetime.fromisoformat(last) < cutoff:
                    stale += 1
            except ValueError:
                pass
        card.set(len(profiles), T.WARN if stale else T.OK,
                 f"{stale} not used for {STALE_PROFILE_DAYS}+ days" if stale else "none stale")
