import customtkinter as ctk

from ui import theme as T
import threading
import os
import tkinter.messagebox as msgbox
from modules.runner import run_powershell, run_inline_powershell
from modules.logger import log, log_change
from modules.utils import format_size
from datetime import datetime

from ui.widgets import ActionBar, LogDrawer, confirm_run, tip

STALE_DAYS = 90


from modules.cleanup_locations import junk_categories as _junk_categories  # noqa: E402


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
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Junk = reclaimable AppData cache and temp files only, not the whole profile. "
                                "Profiles in use are protected and need extra confirmation.",
                     font=T.ui(11), text_color=T.MUTED, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))

        self._list_card = ctk.CTkScrollableFrame(self, fg_color=T.PANEL, corner_radius=0)
        self._list_card.grid(row=1, column=0, sticky="nsew")
        self._list_card.grid_columnconfigure(5, weight=1)

        self._log = LogDrawer(self)
        self._log.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        self._action = ActionBar(self)
        self._action.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self._refresh_btn = self._action.button("Refresh list", self._refresh_list, outline=True, width=100,
                                                tip_text="Reload the list of user profiles on this PC")
        self._scan_btn = self._action.button("Scan sizes", self._scan, outline=True, width=100,
                                             tip_text="Measure reclaimable cache/temp space per profile. "
                                                      "Nothing is deleted.")
        self._action.button("Select all", self._select_all, outline=True, width=90,
                            tip_text="Tick every profile (Ctrl+A)")
        self._action.button("Select none", self._select_none, outline=True, width=96,
                            tip_text="Untick every profile (Ctrl+Shift+A)")
        self._clean_btn = self._action.button("Clean selected", self._clean, danger=True, width=130,
                                              tip_text="Delete cache/temp junk from the ticked profiles "
                                                       "(Ctrl+Enter). Documents and settings are not touched.")
        self._total_label = self._action._summary
        self._total_label.configure(text="Total selected: ---")

    # ── Helpers ────────────────────────────────────────────────────────

    def _append(self, text):
        self._log.append(text)

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

    # Keyboard shortcuts (see ui/widgets.py)
    def shortcut_select_all(self):
        self._select_all()

    def shortcut_deselect_all(self):
        self._select_none()

    def shortcut_apply(self):
        self._clean()

    def _update_size_label(self, sid, val):
        lbl = self._size_labels.get(sid)
        if not lbl:
            return
        color = T.TEXT_BRIGHT if val > 0 else T.MUTED
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

    def _status(self, sid):
        """(text, colour) for the STATUS column."""
        p = self._profiles[sid]
        if self._is_guarded(sid):
            return "IN USE", T.INFO
        try:
            days = (datetime.now() - datetime.strptime(p["last_use"], "%Y-%m-%d")).days
        except (ValueError, TypeError):
            return "UNKNOWN", T.DIM
        if days >= STALE_DAYS:
            return f"STALE {days}d", T.WARN
        return "ACTIVE", T.MUTED

    def _render_rows(self):
        for w in self._list_card.winfo_children():
            w.destroy()
        self._row_frames = {}

        heads = ["", "USER", "PATH", "LAST USED", "JUNK", "STATUS", "", ""]
        for c, text in enumerate(heads):
            ctk.CTkLabel(self._list_card, text=text, font=T.mono(9, "bold"), text_color=T.DIM,
                         anchor="w").grid(row=0, column=c, sticky="w", padx=(12 if c == 0 else 0, 12), pady=(6, 2))
        ctk.CTkFrame(self._list_card, height=1, fg_color=T.BORDER).grid(
            row=1, column=0, columnspan=len(heads), sticky="ew")

        if not self._profiles:
            ctk.CTkLabel(self._list_card, text="No profiles found.", text_color=T.MUTED).grid(
                row=2, column=0, columnspan=len(heads), padx=14, pady=14, sticky="w")
            return

        row = 2
        for sid, p in self._profiles.items():
            guarded = self._is_guarded(sid)
            ctk.CTkCheckBox(self._list_card, text="", variable=self._vars[sid], width=20,
                            checkbox_width=16, checkbox_height=16).grid(row=row, column=0, padx=(12, 4), pady=4, sticky="w")
            ctk.CTkLabel(self._list_card, text=p["username"], font=T.ui(12, "bold"),
                         text_color=T.TEXT_BRIGHT, anchor="w").grid(row=row, column=1, padx=(0, 12), sticky="w")
            path = p["local_path"]
            ctk.CTkLabel(self._list_card, text=path if len(path) <= 40 else "…" + path[-39:],
                         font=T.mono(10), text_color=T.MUTED, anchor="w").grid(row=row, column=2, padx=(0, 12), sticky="w")
            ctk.CTkLabel(self._list_card, text=p["last_use"] or "—", font=T.mono(11),
                         text_color=T.TEXT, anchor="w").grid(row=row, column=3, padx=(0, 12), sticky="w")
            sz = self._sizes.get(sid)
            size_lbl = ctk.CTkLabel(self._list_card, text="---" if sz is None else format_size(sz),
                                    font=T.mono(11), text_color=T.MUTED if not sz else T.TEXT_BRIGHT, anchor="w")
            size_lbl.grid(row=row, column=4, padx=(0, 12), sticky="w")
            self._size_labels[sid] = size_lbl
            text, color = self._status(sid)
            ctk.CTkLabel(self._list_card, text=text, font=T.mono(9, "bold"), text_color=color,
                         anchor="w").grid(row=row, column=5, padx=(0, 12), sticky="w")

            expanded = sid in self._expanded
            T.outline_button(self._list_card, text="Details ▾" if expanded else "Details ▸", width=78, height=24,
                             font=T.ui(11), command=lambda s=sid: self._toggle_details(s)).grid(
                row=row, column=6, padx=(0, 6), pady=4, sticky="e")
            del_btn = T.outline_button(self._list_card, text="Delete profile", width=104, height=24, font=T.ui(11),
                                       text_color=T.FAIL, state="disabled" if guarded else "normal",
                                       command=lambda s=sid: self._delete_profile(s))
            del_btn.grid(row=row, column=7, padx=(0, 12), pady=4, sticky="e")
            if guarded:
                tip(del_btn, "This profile is in use and can't be deleted")
            row += 1
            if expanded:
                row = self._render_detail_row(sid, row)

    def _render_detail_row(self, sid, row):
        detail = ctk.CTkFrame(self._list_card, fg_color=T.PANEL_2, corner_radius=0)
        detail.grid(row=row, column=1, columnspan=7, padx=(0, 12), pady=(0, 6), sticky="ew")
        detail.grid_columnconfigure(0, weight=1)

        breakdown = self._breakdown.get(sid)
        if breakdown is None:
            ctk.CTkLabel(detail, text="Click \"Scan Sizes\" to see a category breakdown for this profile.",
                         text_color=T.MUTED, font=ctk.CTkFont(size=11)).grid(
                row=0, column=0, columnspan=3, padx=12, pady=8, sticky="w")
            return row + 1

        nonzero = [c for c in breakdown if c[2] > 0]
        if not nonzero:
            ctk.CTkLabel(detail, text="No junk found in any category.",
                         text_color=T.MUTED, font=ctk.CTkFont(size=11)).grid(
                row=0, column=0, columnspan=3, padx=12, pady=8, sticky="w")
            return row + 1

        for j, (cat_id, label, size) in enumerate(sorted(nonzero, key=lambda c: c[2], reverse=True)):
            ctk.CTkLabel(detail, text=label, font=ctk.CTkFont(size=11), anchor="w").grid(
                row=j, column=0, padx=(12, 6), pady=3, sticky="w")
            ctk.CTkLabel(detail, text=format_size(size), font=ctk.CTkFont(size=11),
                         text_color=T.MUTED).grid(row=j, column=1, padx=(0, 14), pady=3, sticky="e")
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

        def describe(sid):
            p = self._profiles[sid]
            sz = self._sizes.get(sid)
            size = f"  ({format_size(sz)})" if sz is not None else ""
            guarded = self._is_guarded(sid)
            return (p["username"] + size + ("  [in use]" if guarded else ""), guarded)

        if not confirm_run(self, "Clean these profiles?",
                           f"Cache/temp junk will be deleted from {len(selected)} profile(s):",
                           [describe(sid) for sid in selected],
                           action_text=f"Clean {len(selected)} profile(s)", danger=True,
                           footer="Profiles marked [in use] will ask for confirmation again."
                                  if any(self._is_guarded(s) for s in selected) else None):
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
