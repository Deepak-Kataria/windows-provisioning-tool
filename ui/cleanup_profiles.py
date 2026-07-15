import customtkinter as ctk
import threading
import os
import tkinter.messagebox as msgbox
from modules.runner import run_powershell, run_inline_powershell
from modules.logger import log, log_change
from modules.utils import format_size


def _junk_categories(local_path):
    """Build size/clean PowerShell for the standard junk locations, scoped to one profile."""
    lp = local_path.rstrip("\\")
    cats = []

    def add_dir(id_, label, subpath):
        full = f"{lp}\\{subpath}"
        cats.append({
            "id": id_,
            "label": label,
            "size_ps": (
                f"if (Test-Path \"{full}\") {{"
                f" $s=(Get-ChildItem \"{full}\" -Recurse -Force -EA SilentlyContinue"
                f" | Measure-Object -Property Length -Sum).Sum;"
                f" if ($s) {{ [int64]$s }} else {{ 0 }} }} else {{ 0 }}"
            ),
            "clean_ps": (
                f"if (Test-Path \"{full}\") {{"
                f" Remove-Item \"{full}\\*\" -Recurse -Force -EA SilentlyContinue }};"
                f" Write-Host '{label} cleaned.'"
            ),
        })

    def add_filtered_dir(id_, label, subpath, filter_):
        base = f"{lp}\\{subpath}"
        cats.append({
            "id": id_,
            "label": label,
            "size_ps": (
                f"$b=\"{base}\"; if (Test-Path $b) {{"
                f" $s=(Get-ChildItem $b -Filter {filter_} -Recurse -Directory -EA SilentlyContinue"
                f" | ForEach-Object {{ Get-ChildItem $_.FullName -Recurse -Force -EA SilentlyContinue }}"
                f" | Measure-Object -Property Length -Sum).Sum;"
                f" if ($s) {{ [int64]$s }} else {{ 0 }} }} else {{ 0 }}"
            ),
            "clean_ps": (
                f"$b=\"{base}\"; if (Test-Path $b) {{"
                f" Get-ChildItem $b -Filter {filter_} -Recurse -Directory -EA SilentlyContinue"
                f" | ForEach-Object {{ Remove-Item \"$($_.FullName)\\*\" -Recurse -Force -EA SilentlyContinue }} }};"
                f" Write-Host '{label} cleaned.'"
            ),
        })

    add_dir("temp", "Local Temp", r"AppData\Local\Temp")
    add_dir("inetcache", "Internet Cache", r"AppData\Local\Microsoft\Windows\INetCache")
    add_filtered_dir("chrome", "Chrome Cache", r"AppData\Local\Google\Chrome\User Data", "Cache")
    add_filtered_dir("edge", "Edge Cache", r"AppData\Local\Microsoft\Edge\User Data", "Cache")
    add_filtered_dir("firefox", "Firefox Cache", r"AppData\Local\Mozilla\Firefox\Profiles", "cache2")
    add_dir("cookies", "Cookies", r"AppData\Roaming\Microsoft\Windows\Cookies")
    add_dir("recent", "Recent Items", r"AppData\Roaming\Microsoft\Windows\Recent")
    add_dir("wer", "Crash/Error Reports", r"AppData\Local\Microsoft\Windows\WER")

    thumb_dir = f"{lp}\\AppData\\Local\\Microsoft\\Windows\\Explorer"
    cats.append({
        "id": "thumbcache",
        "label": "Thumbnail Cache",
        "size_ps": (
            f"if (Test-Path \"{thumb_dir}\") {{"
            f" $s=(Get-ChildItem \"{thumb_dir}\" -Filter 'thumbcache_*.db' -Force -EA SilentlyContinue"
            f" | Measure-Object -Property Length -Sum).Sum;"
            f" if ($s) {{ [int64]$s }} else {{ 0 }} }} else {{ 0 }}"
        ),
        "clean_ps": (
            f"if (Test-Path \"{thumb_dir}\") {{"
            f" Remove-Item \"{thumb_dir}\\thumbcache_*.db\" -Force -EA SilentlyContinue }};"
            f" Write-Host 'Thumbnail Cache cleaned.'"
        ),
    })

    icon_file = f"{lp}\\AppData\\Local\\IconCache.db"
    cats.append({
        "id": "iconcache",
        "label": "Icon Cache",
        "size_ps": (
            f"if (Test-Path \"{icon_file}\") {{"
            f" (Get-Item \"{icon_file}\" -Force -EA SilentlyContinue).Length }} else {{ 0 }}"
        ),
        "clean_ps": (
            f"if (Test-Path \"{icon_file}\") {{ Remove-Item \"{icon_file}\" -Force -EA SilentlyContinue }};"
            f" Write-Host 'Icon Cache cleaned.'"
        ),
    })

    return cats


class ProfilesSection(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._profiles = {}       # sid -> {username, local_path, last_use, loaded}
        self._vars = {}           # sid -> BooleanVar
        self._size_labels = {}    # sid -> CTkLabel
        self._sizes = {}          # sid -> int or None
        self._breakdown = {}      # sid -> list of (cat_id, label, size) or None
        self._expanded = set()    # sids currently showing category breakdown
        self._row_frames = {}
        self._current_user = os.environ.get("USERNAME", "").strip().lower()
        self._build()
        self._refresh_list()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        wrap = ctk.CTkScrollableFrame(self, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(wrap)
        hdr.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="User Profile Cleanup",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, padx=14, pady=(12, 2), sticky="w")

        ctk.CTkLabel(hdr,
                     text="Junk size shown is reclaimable AppData cache/temp only, not total profile size.\n"
                          "Active/current-user profiles are flagged and need extra confirmation.",
                     font=ctk.CTkFont(size=11), text_color="gray", justify="left").grid(
            row=1, column=0, padx=14, pady=(0, 6), sticky="w")

        btn_row = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="w")

        self._refresh_btn = ctk.CTkButton(btn_row, text="Refresh List", width=110,
                                          command=self._refresh_list)
        self._refresh_btn.grid(row=0, column=0, padx=(4, 6))

        self._scan_btn = ctk.CTkButton(btn_row, text="Scan Sizes", width=110,
                                       command=self._scan)
        self._scan_btn.grid(row=0, column=1, padx=6)

        self._clean_btn = ctk.CTkButton(btn_row, text="Clean Selected", width=130,
                                        fg_color="#c0392b", hover_color="#922b21",
                                        command=self._clean)
        self._clean_btn.grid(row=0, column=2, padx=6)

        ctk.CTkButton(btn_row, text="Select All", width=90,
                      command=self._select_all).grid(row=0, column=3, padx=6)
        ctk.CTkButton(btn_row, text="Select None", width=90,
                      command=self._select_none).grid(row=0, column=4, padx=6)

        self._total_label = ctk.CTkLabel(hdr, text="Total selected: ---",
                                         font=ctk.CTkFont(size=12), text_color="gray")
        self._total_label.grid(row=3, column=0, padx=14, pady=(0, 12), sticky="w")

        self._list_card = ctk.CTkFrame(wrap, corner_radius=6)
        self._list_card.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        self._list_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(wrap, text="Output",
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").grid(
            row=2, column=0, padx=10, pady=(12, 2), sticky="w")

        self._output = ctk.CTkTextbox(wrap, height=200, state="disabled",
                                      font=ctk.CTkFont(family="Courier New", size=11))
        self._output.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")

    # ── Helpers ────────────────────────────────────────────────────────

    def _append(self, text):
        self._output.configure(state="normal")
        self._output.insert("end", text + "\n")
        self._output.see("end")
        self._output.configure(state="disabled")

    def _safe_append(self, text):
        self.after(0, self._append, text)

    def _set_btn_state(self, enabled):
        state = "normal" if enabled else "disabled"
        self._refresh_btn.configure(state=state)
        self._scan_btn.configure(state=state)
        self._clean_btn.configure(state=state)

    def _is_guarded(self, sid):
        p = self._profiles[sid]
        return p["loaded"] or p["username"].strip().lower() == self._current_user

    def _parse_size(self, out):
        lines = [l.strip() for l in out.splitlines()
                 if l.strip() and not l.strip().startswith("ERR:")]
        try:
            return int(lines[-1]) if lines else 0
        except (ValueError, IndexError):
            return 0

    def _update_total(self):
        total = 0
        any_unknown = False
        for sid, var in self._vars.items():
            if var.get():
                sz = self._sizes.get(sid)
                if sz is None:
                    any_unknown = True
                else:
                    total += sz
        if any_unknown:
            self._total_label.configure(text="Total selected: scan first to calculate")
        else:
            self._total_label.configure(text=f"Total selected: {format_size(total)}")

    def _select_all(self):
        for var in self._vars.values():
            var.set(True)
        self._update_total()

    def _select_none(self):
        for var in self._vars.values():
            var.set(False)
        self._update_total()

    def _update_size_label(self, sid, val):
        lbl = self._size_labels.get(sid)
        if not lbl:
            return
        color = ("#1a1a1a", "white") if val > 0 else "gray"
        lbl.configure(text=format_size(val), text_color=color)

    # ── List ───────────────────────────────────────────────────────────

    def _refresh_list(self):
        if self._running:
            return
        self._running = True
        self._set_btn_state(False)
        self._append("\nLoading profiles...")

        def task():
            rc, out = run_powershell("get_user_profiles.ps1", [])
            profiles = {}
            errors = []
            for line in out.splitlines():
                parts = line.strip().split("|")
                if not parts or not parts[0]:
                    continue
                if parts[0] == "ERROR":
                    errors.append(line)
                    continue
                if len(parts) < 5:
                    continue
                sid, username, local_path, last_use, loaded = parts[:5]
                profiles[sid] = {
                    "username": username,
                    "local_path": local_path,
                    "last_use": last_use,
                    "loaded": loaded == "1",
                }

            def apply():
                self._profiles = profiles
                self._vars = {sid: ctk.BooleanVar(value=False) for sid in profiles}
                for var in self._vars.values():
                    var.trace_add("write", lambda *a: self._update_total())
                self._sizes = {sid: None for sid in profiles}
                self._breakdown = {sid: None for sid in profiles}
                self._expanded = set()
                self._size_labels = {}
                self._render_rows()
                self._update_total()
                if errors:
                    self._append(f"\n{errors[0]}")
                self._append(f"\nLoaded {len(profiles)} profile(s).")
                self._running = False
                self._set_btn_state(True)

            self.after(0, apply)

        threading.Thread(target=task, daemon=True).start()

    def _render_rows(self):
        for w in self._list_card.winfo_children():
            w.destroy()
        self._row_frames = {}

        if not self._profiles:
            ctk.CTkLabel(self._list_card, text="No profiles found.",
                         text_color="gray").grid(row=0, column=0, padx=14, pady=14, sticky="w")
            return

        row = 0
        for sid, p in self._profiles.items():
            guarded = self._is_guarded(sid)

            cb = ctk.CTkCheckBox(self._list_card, text="", variable=self._vars[sid], width=20)
            cb.grid(row=row, column=0, padx=(14, 4), pady=5, sticky="w")

            name_text = p["username"]
            if guarded:
                name_text += "  [ACTIVE / CURRENT USER]"
            name_color = ("#c0392b", "#ff7675") if guarded else None
            name_kw = {"anchor": "w", "font": ctk.CTkFont(size=12)}
            if name_color:
                name_kw["text_color"] = name_color
            ctk.CTkLabel(self._list_card, text=name_text, **name_kw).grid(
                row=row, column=1, padx=(0, 6), pady=5, sticky="w")

            ctk.CTkLabel(self._list_card, text=f"Last login: {p['last_use']}",
                         text_color="gray", font=ctk.CTkFont(size=11)).grid(
                row=row, column=2, padx=(0, 14), pady=5, sticky="w")

            size_lbl = ctk.CTkLabel(self._list_card, text="---",
                                    text_color="gray", font=ctk.CTkFont(size=11))
            size_lbl.grid(row=row, column=3, padx=(0, 14), pady=5, sticky="e")
            self._size_labels[sid] = size_lbl

            expanded = sid in self._expanded
            details_btn = ctk.CTkButton(self._list_card, text="Details ▾" if expanded else "Details ▸",
                                        width=80, height=26, font=ctk.CTkFont(size=11),
                                        fg_color="transparent", border_width=1,
                                        command=lambda s=sid: self._toggle_details(s))
            details_btn.grid(row=row, column=4, padx=(0, 6), pady=5, sticky="e")

            del_btn = ctk.CTkButton(self._list_card, text="Delete Profile", width=110, height=26,
                                    fg_color="#c0392b", hover_color="#922b21",
                                    font=ctk.CTkFont(size=11),
                                    state="disabled" if guarded else "normal",
                                    command=lambda s=sid: self._delete_profile(s))
            del_btn.grid(row=row, column=5, padx=(0, 14), pady=5, sticky="e")

            row += 1

            if expanded:
                row = self._render_detail_row(sid, row)

    def _render_detail_row(self, sid, row):
        detail = ctk.CTkFrame(self._list_card, fg_color=("gray90", "gray17"), corner_radius=6)
        detail.grid(row=row, column=0, columnspan=6, padx=(30, 14), pady=(0, 6), sticky="ew")
        detail.grid_columnconfigure(0, weight=1)

        breakdown = self._breakdown.get(sid)
        if breakdown is None:
            ctk.CTkLabel(detail, text="Click \"Scan Sizes\" to see a category breakdown for this profile.",
                         text_color="gray", font=ctk.CTkFont(size=11)).grid(
                row=0, column=0, columnspan=3, padx=12, pady=8, sticky="w")
            return row + 1

        nonzero = [c for c in breakdown if c[2] > 0]
        if not nonzero:
            ctk.CTkLabel(detail, text="No junk found in any category.",
                         text_color="gray", font=ctk.CTkFont(size=11)).grid(
                row=0, column=0, columnspan=3, padx=12, pady=8, sticky="w")
            return row + 1

        for j, (cat_id, label, size) in enumerate(sorted(nonzero, key=lambda c: c[2], reverse=True)):
            ctk.CTkLabel(detail, text=label, font=ctk.CTkFont(size=11), anchor="w").grid(
                row=j, column=0, padx=(12, 6), pady=3, sticky="w")
            ctk.CTkLabel(detail, text=format_size(size), font=ctk.CTkFont(size=11),
                         text_color="gray").grid(row=j, column=1, padx=(0, 14), pady=3, sticky="e")
            ctk.CTkButton(detail, text="Clean", width=70, height=24, font=ctk.CTkFont(size=11),
                          command=lambda s=sid, c=cat_id: self._clean_category(s, c)).grid(
                row=j, column=2, padx=(0, 12), pady=3, sticky="e")

        return row + len(nonzero)

    def _toggle_details(self, sid):
        if sid in self._expanded:
            self._expanded.discard(sid)
        else:
            self._expanded.add(sid)
        self._render_rows()

    # ── Scan ───────────────────────────────────────────────────────────

    def _scan(self):
        if self._running or not self._profiles:
            return
        self._running = True
        self._set_btn_state(False)
        self._append("\nScanning junk sizes...")

        def task():
            for sid, p in self._profiles.items():
                self._safe_append(f"  Checking {p['username']}...")
                breakdown = []
                total = 0
                for cat in _junk_categories(p["local_path"]):
                    rc, out = run_inline_powershell(cat["size_ps"])
                    size = self._parse_size(out)
                    breakdown.append((cat["id"], cat["label"], size))
                    total += size
                self._sizes[sid] = total
                self._breakdown[sid] = breakdown
                self.after(0, self._update_size_label, sid, total)

            self.after(0, self._update_total)
            self.after(0, self._render_rows)
            self._safe_append("\nScan complete.")
            self._running = False
            self.after(0, self._set_btn_state, True)

        threading.Thread(target=task, daemon=True).start()

    # ── Clean ──────────────────────────────────────────────────────────

    def _clean(self):
        if self._running:
            return
        selected = [sid for sid, var in self._vars.items() if var.get()]
        if not selected:
            self._append("No profiles selected.")
            return

        confirmed = []
        for sid in selected:
            p = self._profiles[sid]
            if self._is_guarded(sid):
                ok = msgbox.askyesno(
                    "Confirm Cleaning Active Profile",
                    f"'{p['username']}' is the active or currently logged-in profile.\n\n"
                    "Cleaning its cache/temp files while in use can cause running "
                    "applications to behave unexpectedly.\n\nContinue anyway?",
                    icon="warning"
                )
                if not ok:
                    continue
            confirmed.append(sid)

        if not confirmed:
            return

        self._running = True
        self._set_btn_state(False)
        total_before = sum(self._sizes.get(sid) or 0 for sid in confirmed)
        self._append(f"\nCleaning {len(confirmed)} profile(s)...")

        def task():
            for sid in confirmed:
                p = self._profiles[sid]
                self._safe_append(f"\n  >>> {p['username']}")
                for cat in _junk_categories(p["local_path"]):
                    rc, out = run_inline_powershell(cat["clean_ps"], callback=self._safe_append)
                    if rc != 0:
                        self._safe_append(f"    [WARN] {cat['label']} exit {rc}")
                log_change("Profile Cleanup", f"Cleaned junk for profile {p['username']}",
                           before=format_size(self._sizes.get(sid)))

            self._safe_append("\nRescanning freed space...")
            total_after = 0
            for sid in confirmed:
                p = self._profiles[sid]
                breakdown = []
                total = 0
                for cat in _junk_categories(p["local_path"]):
                    rc, out = run_inline_powershell(cat["size_ps"])
                    size = self._parse_size(out)
                    breakdown.append((cat["id"], cat["label"], size))
                    total += size
                self._sizes[sid] = total
                self._breakdown[sid] = breakdown
                total_after += total
                self.after(0, self._update_size_label, sid, total)

            freed = max(0, total_before - total_after)
            self.after(0, self._update_total)
            self.after(0, self._render_rows)
            self._safe_append(f"\nDone.  Freed: {format_size(freed)}")
            self._running = False
            self.after(0, self._set_btn_state, True)

        threading.Thread(target=task, daemon=True).start()

    def _clean_category(self, sid, cat_id):
        if self._running:
            return
        p = self._profiles.get(sid)
        if not p:
            return
        cat = next((c for c in _junk_categories(p["local_path"]) if c["id"] == cat_id), None)
        if not cat:
            return

        if self._is_guarded(sid):
            ok = msgbox.askyesno(
                "Confirm Cleaning Active Profile",
                f"'{p['username']}' is the active or currently logged-in profile.\n\n"
                f"Clean '{cat['label']}' anyway?",
                icon="warning"
            )
            if not ok:
                return

        self._running = True
        self._set_btn_state(False)
        self._append(f"\nCleaning {cat['label']} for {p['username']}...")

        def task():
            rc, out = run_inline_powershell(cat["clean_ps"], callback=self._safe_append)
            if rc != 0:
                self._safe_append(f"  [WARN] exit {rc}")
            log_change("Profile Cleanup", f"Cleaned {cat['label']} for profile {p['username']}")

            rc, out = run_inline_powershell(cat["size_ps"])
            new_size = self._parse_size(out)

            breakdown = self._breakdown.get(sid) or []
            self._breakdown[sid] = [
                (c_id, label, new_size if c_id == cat_id else size)
                for c_id, label, size in breakdown
            ]
            self._sizes[sid] = sum(size for _, _, size in self._breakdown[sid])

            self.after(0, self._update_size_label, sid, self._sizes[sid])
            self.after(0, self._update_total)
            self.after(0, self._render_rows)
            self._safe_append(f"\nDone cleaning {cat['label']}.")
            self._running = False
            self.after(0, self._set_btn_state, True)

        threading.Thread(target=task, daemon=True).start()

    # ── Delete ─────────────────────────────────────────────────────────

    def _delete_profile(self, sid):
        if self._running:
            return
        p = self._profiles.get(sid)
        if not p or self._is_guarded(sid):
            return

        ok = msgbox.askyesno(
            "Confirm Delete Profile",
            f"Permanently delete the profile '{p['username']}'?\n\n"
            f"Path: {p['local_path']}\n\n"
            "This removes the profile's registry entry and all its files "
            "(Desktop, Documents, AppData, etc). This cannot be undone.\n\n"
            "Continue?",
            icon="warning"
        )
        if not ok:
            return

        self._running = True
        self._set_btn_state(False)
        self._append(f"\nDeleting profile {p['username']}...")
        log(f"Deleting user profile {p['username']} ({sid})")

        def task():
            ps = (
                f"(Get-CimInstance Win32_UserProfile -Filter \"SID='{sid}'\").Delete();"
                " Write-Host 'Profile deleted.'"
            )
            rc, out = run_inline_powershell(ps, callback=self._safe_append)
            if rc == 0:
                log_change("Profile Cleanup", f"Deleted profile {p['username']}",
                           before=p["local_path"])
                self._safe_append(f"\nProfile {p['username']} deleted.")
            else:
                self._safe_append(f"\n[WARN] Delete failed, exit {rc}")
                log(f"Profile delete failed for {p['username']}: {out}", "error")
            self._running = False
            self.after(0, self._set_btn_state, True)
            self.after(0, self._refresh_list)

        threading.Thread(target=task, daemon=True).start()
