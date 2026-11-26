import customtkinter as ctk

from ui import theme as T
import threading
import tkinter.messagebox as msgbox
from modules.runner import run_powershell, run_inline_powershell
from modules.logger import log
from modules.utils import format_size
from ui.widgets import LogDrawer, section_header, tip

HEALTH_COLORS = {
    "Healthy": T.OK,
    "Warning": T.WARN,
    "Unhealthy": T.FAIL,
    "Unknown": "gray",
}


class DiskAnalysisSection(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._drives = []
        self._current_path = None
        self._build()
        self._load_drives()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        wrap = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        hdr, col = section_header(wrap, "Drives", height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        self._refresh_drives_btn = T.outline_button(hdr, text="Refresh", width=80, height=22, font=T.ui(11),
                                                    command=self._load_drives)
        self._refresh_drives_btn.grid(row=0, column=col + 1, padx=8)
        tip(self._refresh_drives_btn, "Reload drive list and free space")
        self._drives_card = ctk.CTkFrame(wrap, fg_color=T.PANEL, corner_radius=0)
        self._drives_card.grid(row=1, column=0, sticky="ew")
        self._drives_card.grid_columnconfigure(0, weight=1)

        hdr, col = section_header(wrap, "Folder sizes", height=30)
        hdr.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkLabel(hdr, text="largest first · read-only", font=T.mono(10), text_color=T.MUTED).grid(
            row=0, column=col, padx=4, sticky="w")
        path_row = ctk.CTkFrame(wrap, fg_color=T.PANEL, corner_radius=0)
        path_row.grid(row=3, column=0, sticky="ew")
        path_row.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(path_row, text="DRIVE", font=T.mono(10), text_color=T.MUTED).grid(row=0, column=0, padx=(12, 6), pady=8)
        self._drive_menu = ctk.CTkOptionMenu(path_row, values=["---"], width=80, command=self._on_drive_selected)
        self._drive_menu.grid(row=0, column=1, padx=(0, 10))
        self._path_entry = ctk.CTkEntry(path_row, placeholder_text="Path", font=T.mono(11))
        self._path_entry.grid(row=0, column=2, padx=(0, 6), sticky="ew")
        self._path_entry.bind("<Return>", lambda e: self._go_path())
        tip(T.outline_button(path_row, text="Up", width=50, command=self._go_up),
            "Go to the parent folder").grid(row=0, column=3, padx=3)
        tip(T.outline_button(path_row, text="Go", width=50, command=self._go_path),
            "Open the path typed in the box").grid(row=0, column=4, padx=3)
        self._scan_folder_btn = ctk.CTkButton(path_row, text="Scan this folder", width=130, command=self._scan_folder)
        self._scan_folder_btn.grid(row=0, column=5, padx=(6, 12))
        tip(self._scan_folder_btn, "Size every subfolder of the current path, largest first (Ctrl+Enter). "
                                   "Large trees such as C:\\ take a while.")

        self._folder_card = ctk.CTkFrame(wrap, fg_color=T.PANEL, corner_radius=0)
        self._folder_card.grid(row=4, column=0, sticky="ew", pady=(1, 0))
        self._folder_card.grid_columnconfigure(0, weight=1)

        self._log = LogDrawer(self)
        self._log.grid(row=1, column=0, sticky="ew", pady=(6, 0))

    # ── Helpers ────────────────────────────────────────────────────────

    def _append(self, text):
        self._log.append(text)

    def _safe_append(self, text):
        self.after(0, self._append, text)

    def _set_busy(self, busy):
        state = "disabled" if busy else "normal"
        self._refresh_drives_btn.configure(state=state)
        self._scan_folder_btn.configure(state=state)

    def _parse_int(self, val, default=0):
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    # ── Drives ─────────────────────────────────────────────────────────

    def _load_drives(self):
        if self._running:
            return
        self._running = True
        self._set_busy(True)
        self._append("\nLoading drive info...")

        def task():
            rc, out = run_powershell("get_drive_health.ps1", [])
            drives = []
            errors = []
            for line in out.splitlines():
                parts = line.strip().split("|")
                if not parts or not parts[0]:
                    continue
                if parts[0] == "ERROR":
                    errors.append(line)
                    continue
                if len(parts) < 4:
                    continue
                letter, size, free, health = parts[:4]
                drives.append({
                    "letter": letter,
                    "size": self._parse_int(size),
                    "free": self._parse_int(free),
                    "health": health,
                })

            def apply():
                self._drives = drives
                self._render_drives()
                letters = [d["letter"] for d in drives] or ["---"]
                self._drive_menu.configure(values=letters)
                if drives and not self._current_path:
                    self._drive_menu.set(letters[0])
                    self._on_drive_selected(letters[0])
                if errors:
                    self._append(f"\n{errors[0]}")
                self._append(f"\nLoaded {len(drives)} drive(s).")
                self._running = False
                self._set_busy(False)

            self.after(0, apply)

        threading.Thread(target=task, daemon=True).start()

    def _render_drives(self):
        for w in self._drives_card.winfo_children():
            w.destroy()

        if not self._drives:
            ctk.CTkLabel(self._drives_card, text="No fixed drives found.",
                         text_color=T.MUTED).grid(row=0, column=0, padx=14, pady=14, sticky="w")
            return

        for i, d in enumerate(self._drives):
            row = ctk.CTkFrame(self._drives_card, fg_color="transparent")
            row.grid(row=i, column=0, padx=10, pady=6, sticky="ew")
            row.grid_columnconfigure(2, weight=1)

            ctk.CTkLabel(row, text=d["letter"], font=ctk.CTkFont(size=13, weight="bold"),
                         width=40).grid(row=0, column=0, padx=(4, 10))

            free_pct = (d["free"] / d["size"] * 100) if d["size"] else 0
            used_frac = 1 - (d["free"] / d["size"]) if d["size"] else 0

            bar_color = T.FAIL if free_pct < 10 else (T.WARN if free_pct < 20 else T.OK)
            bar = ctk.CTkProgressBar(row, width=200, progress_color=bar_color)
            bar.set(used_frac)
            bar.grid(row=0, column=1, padx=(0, 14))

            size_text = f"{format_size(d['free'])} free of {format_size(d['size'])}  ({free_pct:.0f}% free)"
            size_color = T.FAIL if free_pct < 10 else None
            size_kw = {"anchor": "w", "font": ctk.CTkFont(size=12)}
            if size_color:
                size_kw["text_color"] = size_color
            ctk.CTkLabel(row, text=size_text, **size_kw).grid(row=0, column=2, sticky="w")

            health = d["health"]
            ctk.CTkLabel(row, text=health.upper(), font=T.mono(9, "bold"),
                         text_color=HEALTH_COLORS.get(health, T.MUTED)).grid(row=0, column=3, padx=(10, 4))

    def _on_drive_selected(self, letter):
        if letter == "---":
            return
        self._current_path = f"{letter}\\"
        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, self._current_path)
        self._clear_folder_rows()

    # ── Folder browser ───────────────────────────────────────────────

    def _clear_folder_rows(self, hint=True):
        for w in self._folder_card.winfo_children():
            w.destroy()
        if not hint:
            return
        ctk.CTkLabel(self._folder_card, text="Pick a drive or type a path, then Scan this folder.",
                     font=T.ui(12), text_color=T.MUTED).grid(row=0, column=0, padx=14, pady=24, sticky="w")

    def _go_path(self):
        path = self._path_entry.get().strip()
        if not path:
            return
        self._current_path = path if path.endswith("\\") else path + "\\"
        self._clear_folder_rows()

    def shortcut_apply(self):
        self._scan_folder()

    def _go_up(self):
        if not self._current_path:
            return
        trimmed = self._current_path.rstrip("\\")
        if len(trimmed) <= 2:
            return  # already at drive root, e.g. "C:"
        parent = trimmed.rsplit("\\", 1)[0] + "\\"
        self._current_path = parent
        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, self._current_path)
        self._clear_folder_rows()

    def _scan_folder(self):
        if self._running:
            return
        path = self._path_entry.get().strip()
        if not path:
            self._append("Enter a path first.")
            return
        self._current_path = path if path.endswith("\\") else path + "\\"

        if path.rstrip("\\").upper() in ("C:", "C:\\") :
            ok = msgbox.askyesno(
                "Slow Scan Warning",
                "Scanning the entire C:\\ drive can take several minutes.\n\nContinue?"
            )
            if not ok:
                return

        self._running = True
        self._set_busy(True)
        self._clear_folder_rows()
        self._append(f"\nListing subfolders of {self._current_path}...")

        def task():
            list_ps = (
                f"Get-ChildItem \"{self._current_path}\" -Directory -Force -EA SilentlyContinue"
                " | Select-Object -ExpandProperty FullName"
            )
            rc, out = run_inline_powershell(list_ps)
            folders = [l.strip() for l in out.splitlines()
                       if l.strip() and not l.strip().startswith("ERR:")]

            if not folders:
                self._safe_append("No subfolders found (or path is inaccessible).")
                self._running = False
                self.after(0, self._set_busy, False)
                return

            results = []
            for full_path in folders:
                name = full_path.rstrip("\\").rsplit("\\", 1)[-1]
                self._safe_append(f"  Checking {name}...")
                size_ps = (
                    f"$s=(Get-ChildItem \"{full_path}\" -Recurse -Force -EA SilentlyContinue"
                    " | Measure-Object -Property Length -Sum).Sum;"
                    " if ($s) { [int64]$s } else { 0 }"
                )
                rc, size_out = run_inline_powershell(size_ps)
                size_lines = [l.strip() for l in size_out.splitlines()
                              if l.strip() and not l.strip().startswith("ERR:")]
                size = self._parse_int(size_lines[-1]) if size_lines else 0
                results.append((name, full_path, size))

            results.sort(key=lambda r: r[2], reverse=True)

            def apply():
                self._render_folder_rows(results)
                self._append("\nFolder scan complete.")
                self._running = False
                self._set_busy(False)

            self.after(0, apply)

        threading.Thread(target=task, daemon=True).start()

    def _render_folder_rows(self, results):
        self._clear_folder_rows(hint=False)
        if not results:
            ctk.CTkLabel(self._folder_card, text="No subfolders found.",
                         text_color=T.MUTED).grid(row=0, column=0, padx=14, pady=14, sticky="w")
            return

        max_size = max((r[2] for r in results), default=0) or 1
        for i, (name, full_path, size) in enumerate(results):
            row = ctk.CTkFrame(self._folder_card, fg_color="transparent")
            row.grid(row=i, column=0, padx=10, pady=3, sticky="ew")
            row.grid_columnconfigure(0, weight=1)

            btn = ctk.CTkButton(row, text=f"  {name}", anchor="w",
                                fg_color="transparent", hover_color=T.PANEL_3,
                                font=ctk.CTkFont(size=12),
                                command=lambda p=full_path: self._drill_into(p))
            btn.grid(row=0, column=0, sticky="ew")

            ctk.CTkLabel(row, text=format_size(size), font=ctk.CTkFont(size=11),
                         text_color=T.MUTED, width=90).grid(row=0, column=1, padx=(6, 14))

    def _drill_into(self, path):
        self._current_path = path if path.endswith("\\") else path + "\\"
        self._path_entry.delete(0, "end")
        self._path_entry.insert(0, self._current_path)
        self._scan_folder()
