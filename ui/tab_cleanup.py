"""Cleanup Hub: User Profiles, Windows Cleanup, Disk Analysis, with summary tiles on top."""
import shutil
from datetime import datetime

import customtkinter as ctk

from modules.utils import format_size
from ui import theme as T
from ui.cleanup_disk import DiskAnalysisSection
from ui.cleanup_profiles import STALE_DAYS, ProfilesSection
from ui.cleanup_windows import LOCATIONS, WindowsCleanupSection
from ui.widgets import tile_row, tip

SECTIONS = [
    ("User profiles", ProfilesSection),
    ("Windows cleanup", WindowsCleanupSection),
    ("Disk analysis", DiskAnalysisSection),
]
_POLL_MS = 1500


class CleanupTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._sections = {}
        self._current = None
        self._polling = False
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        tiles_host = ctk.CTkFrame(self, fg_color="transparent")
        tiles_host.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tiles_host.grid_columnconfigure(0, weight=1)
        row, self._tiles = tile_row(tiles_host, [
            ("Reclaimable", "—", T.MUTED, "scan sizes to measure"),
            ("Disk C:", "…", T.MUTED, ""),
            ("Profiles", "…", T.MUTED, "loading…"),
            ("Selected", "—", T.ACCENT, "will be freed"),
        ])
        row.grid(row=0, column=0, sticky="ew")

        self._switch = ctk.CTkSegmentedButton(self, values=[n for n, _ in SECTIONS], command=self._show)
        self._switch.grid(row=1, column=0, sticky="w", pady=(0, 8))
        tip(self._switch, "Profiles: per-user cache and temp · Windows: system junk · Disk: what uses the space")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        for name, cls in SECTIONS:
            widget = cls(content, self.role)
            self._sections[name] = widget
        self._show(SECTIONS[0][0])

    def _show(self, name):
        if self._current:
            self._sections[self._current].grid_remove()
        self._current = name
        self._switch.set(name)
        self._sections[name].grid(row=0, column=0, sticky="nsew")
        self._refresh_tiles()

    def shortcut_target(self):
        return self._sections.get(self._current)

    # ── Tiles ──────────────────────────────────────────────────────

    def on_show(self):
        self._refresh_tiles()
        if not self._polling:
            self._polling = True
            self.after(_POLL_MS, self._poll)

    def _poll(self):
        if not self.winfo_exists() or not self.winfo_ismapped():
            self._polling = False
            return
        self._refresh_tiles()
        self.after(_POLL_MS, self._poll)

    def _refresh_tiles(self):
        prof = self._sections["User profiles"]
        win = self._sections["Windows cleanup"]

        p_sizes = [v for v in getattr(prof, "_sizes", {}).values() if v is not None]
        w_sizes = [v for v in getattr(win, "_sizes", {}).values() if v is not None]
        if p_sizes or w_sizes:
            total = sum(p_sizes) + sum(w_sizes)
            parts = []
            if p_sizes:
                parts.append(f"profiles {format_size(sum(p_sizes))}")
            if w_sizes:
                parts.append(f"Windows {format_size(sum(w_sizes))}")
            self._tiles["Reclaimable"].set(format_size(total), T.WARN if total else T.OK, " · ".join(parts))
        else:
            self._tiles["Reclaimable"].set("—", T.MUTED, "scan sizes to measure")

        try:
            u = shutil.disk_usage("C:\\")
            pct = 100 * u.free / u.total
            self._tiles["Disk C:"].set(f"{pct:.0f}% free", T.FAIL if pct < 10 else T.WARN if pct < 20 else T.OK,
                                       f"{format_size(u.free)} free of {format_size(u.total)}")
        except OSError:
            self._tiles["Disk C:"].set("?", T.MUTED, "could not read drive C:")

        profiles = getattr(prof, "_profiles", {})
        if profiles:
            stale = 0
            for p in profiles.values():
                try:
                    if (datetime.now() - datetime.strptime(p["last_use"], "%Y-%m-%d")).days >= STALE_DAYS:
                        stale += 1
                except (ValueError, TypeError, KeyError):
                    pass
            self._tiles["Profiles"].set(len(profiles), T.WARN if stale else T.OK,
                                        f"{stale} stale ({STALE_DAYS}+ days)" if stale else "none stale")

        sec = self._sections[self._current]
        sizes = getattr(sec, "_sizes", None)
        vars_ = getattr(sec, "_vars", None)
        if sizes is None or vars_ is None:
            self._tiles["Selected"].set("—", T.DIM, "pick a folder to scan")
            return
        picked = [k for k, v in vars_.items() if v.get()]
        known = [sizes.get(k) for k in picked if sizes.get(k) is not None]
        if not picked:
            self._tiles["Selected"].set("0", T.DIM, "nothing ticked")
        elif len(known) < len(picked):
            self._tiles["Selected"].set(len(picked), T.ACCENT, "scan sizes to see the space")
        else:
            self._tiles["Selected"].set(format_size(sum(known)), T.ACCENT, f"{len(picked)} ticked · will be freed")
