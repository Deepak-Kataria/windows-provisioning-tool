import customtkinter as ctk

from ui import theme as T
import threading
import tkinter.messagebox as msgbox
from modules.runner import run_inline_powershell
from modules.logger import log
from modules.utils import format_size
from ui.widgets import ActionBar, LogDrawer, confirm_run, section_header, tip


from modules.cleanup_locations import GROUPS, LOCATIONS  # noqa: E402  (data lives in modules/)


class WindowsCleanupSection(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._running = False
        self._vars = {}
        self._size_labels = {}
        self._sizes = {loc["id"]: None for loc in LOCATIONS}
        self._build()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Scan sizes first, then tick and clean. Items marked CAN'T UNDO ask again before running.",
                     font=T.ui(11), text_color=T.MUTED, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))

        wrap = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)

        grid_row = 0
        for grp in GROUPS:
            hdr, col = section_header(wrap, grp["label"], height=28, accent=T.BORDER)
            hdr.grid(row=grid_row, column=0, sticky="ew", pady=(10 if grid_row else 0, 0))
            T.outline_button(hdr, text="all", width=36, height=20, font=T.mono(10),
                             command=lambda g=grp: self._group_select(g, True)).grid(row=0, column=col + 1, padx=(4, 2))
            T.outline_button(hdr, text="none", width=44, height=20, font=T.mono(10),
                             command=lambda g=grp: self._group_select(g, False)).grid(row=0, column=col + 2, padx=(2, 8))
            grid_row += 1

            items_card = ctk.CTkFrame(wrap, fg_color=T.PANEL, corner_radius=0)
            items_card.grid(row=grid_row, column=0, sticky="ew")
            items_card.grid_columnconfigure(0, weight=1)
            for i, loc in enumerate(grp["items"]):
                var = ctk.BooleanVar(value=loc["default"])
                var.trace_add("write", lambda *a: self._update_total())
                self._vars[loc["id"]] = var
                row = ctk.CTkFrame(items_card, fg_color=T.PANEL if i % 2 == 0 else T.PANEL_2,
                                   corner_radius=0, height=32)
                row.grid(row=i, column=0, sticky="ew")
                row.grid_propagate(False)
                row.grid_rowconfigure(0, weight=1)
                row.grid_columnconfigure(1, weight=1)
                ctk.CTkCheckBox(row, text=loc["label"], variable=var, font=T.ui(12),
                                checkbox_width=16, checkbox_height=16).grid(row=0, column=0, padx=(12, 6), sticky="w")
                if loc.get("confirm"):
                    ctk.CTkLabel(row, text=" CAN'T UNDO ", font=T.mono(8, "bold"), text_color=T.WARN,
                                 fg_color=T.PANEL_3, corner_radius=2, height=14).grid(row=0, column=1, sticky="w")
                size_lbl = ctk.CTkLabel(row, text="---", text_color=T.MUTED, font=T.mono(11), width=90, anchor="e")
                size_lbl.grid(row=0, column=2, padx=(0, 14), sticky="e")
                self._size_labels[loc["id"]] = size_lbl
            grid_row += 1

        self._log = LogDrawer(self)
        self._log.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        self._action = ActionBar(self)
        self._action.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self._scan_btn = self._action.button("Scan sizes", self._scan, outline=True, width=100,
                                             tip_text="Measure how much space each location uses. Nothing is deleted.")
        self._action.button("Select all", self._select_all, outline=True, width=90,
                            tip_text="Tick every location (Ctrl+A)")
        self._action.button("Select none", self._select_none, outline=True, width=96,
                            tip_text="Untick every location (Ctrl+Shift+A)")
        self._clean_btn = self._action.button("Clean selected", self._clean, danger=True, width=130,
                                              tip_text="Delete the contents of the ticked locations (Ctrl+Enter). "
                                                       "You'll see the list before anything runs.")
        self._total_label = self._action._summary
        self._update_total()

    # ── Helpers ────────────────────────────────────────────────────────

    def _append(self, text):
        self._log.append(text)

    def _safe_append(self, text):
        self.after(0, self._append, text)

    def _set_btn_state(self, enabled):
        state = "normal" if enabled else "disabled"
        self._scan_btn.configure(state=state)
        self._clean_btn.configure(state=state)

    def _update_total(self):
        total = 0
        any_unknown = False
        for loc in LOCATIONS:
            if self._vars[loc["id"]].get():
                sz = self._sizes[loc["id"]]
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

    def _select_none(self):
        for var in self._vars.values():
            var.set(False)

    # Keyboard shortcuts (see ui/widgets.py)
    def shortcut_select_all(self):
        self._select_all()

    def shortcut_deselect_all(self):
        self._select_none()

    def shortcut_apply(self):
        self._clean()

    def _group_select(self, grp, value):
        for loc in grp["items"]:
            self._vars[loc["id"]].set(value)

    def _parse_size(self, out):
        lines = [l.strip() for l in out.splitlines()
                 if l.strip() and not l.strip().startswith("ERR:")]
        try:
            return int(lines[-1]) if lines else 0
        except (ValueError, IndexError):
            return 0

    def _update_size_label(self, loc_id, val):
        lbl = self._size_labels[loc_id]
        color = T.TEXT_BRIGHT if val > 0 else T.MUTED
        lbl.configure(text=format_size(val), text_color=color)

    # ── Scan ───────────────────────────────────────────────────────────

    def _scan(self):
        if self._running:
            return
        self._running = True
        self._set_btn_state(False)
        self._append("\nScanning sizes...")
        log("Cleanup: scan started")

        def task():
            for loc in LOCATIONS:
                self._safe_append(f"  Checking {loc['label']}...")
                rc, out = run_inline_powershell(loc["size_ps"])
                val = self._parse_size(out)
                self._sizes[loc["id"]] = val
                self.after(0, self._update_size_label, loc["id"], val)

            self.after(0, self._update_total)
            self._safe_append("\nScan complete.")
            self._running = False
            self.after(0, self._set_btn_state, True)

        threading.Thread(target=task, daemon=True).start()

    # ── Clean ──────────────────────────────────────────────────────────

    def _clean(self):
        if self._running:
            return
        selected = [loc for loc in LOCATIONS if self._vars[loc["id"]].get()]
        if not selected:
            self._append("No locations selected.")
            return

        def describe(loc):
            sz = self._sizes.get(loc["id"])
            size = f"  ({format_size(sz)})" if sz is not None else ""
            return (loc["label"] + size + ("  [!]" if loc.get("confirm") else ""),
                    bool(loc.get("confirm")))

        if not confirm_run(self, "Clean these locations?",
                           f"The contents of these {len(selected)} location(s) will be deleted:",
                           [describe(loc) for loc in selected],
                           action_text=f"Clean {len(selected)} location(s)", danger=True,
                           footer="Items marked [!] will ask for confirmation again individually."
                                  if any(l.get("confirm") for l in selected) else None):
            return

        confirmed = []
        for loc in selected:
            if loc.get("confirm"):
                ok = msgbox.askyesno(
                    "Confirm Destructive Action",
                    loc["confirm_msg"],
                    icon="warning"
                )
                if ok:
                    confirmed.append(loc)
            else:
                confirmed.append(loc)

        if not confirmed:
            return

        slow_items = [loc["label"] for loc in confirmed if loc.get("slow")]
        if slow_items:
            msgbox.showinfo(
                "Slow Operations",
                "The following may take 5-15 minutes:\n\n"
                + "\n".join(f"  - {n}" for n in slow_items)
                + "\n\nPlease wait — the app will not respond during DISM."
            )

        self._running = True
        self._set_btn_state(False)
        total_before = sum(self._sizes[loc["id"]] or 0 for loc in confirmed)
        self._append(f"\nCleaning {len(confirmed)} location(s)...")
        log(f"Cleanup: clean {[l['id'] for l in confirmed]}")

        def task():
            for loc in confirmed:
                self._safe_append(f"\n  >>> {loc['label']}")
                rc, out = run_inline_powershell(loc["clean_ps"], callback=self._safe_append)
                if rc != 0:
                    self._safe_append(f"  [WARN] exit {rc}")
                log(f"Cleanup: {loc['id']} rc={rc}")

            self._safe_append("\nRescanning freed space...")
            total_after = 0
            for loc in confirmed:
                rc, out = run_inline_powershell(loc["size_ps"])
                val = self._parse_size(out)
                self._sizes[loc["id"]] = val
                total_after += val
                self.after(0, self._update_size_label, loc["id"], val)

            freed = max(0, total_before - total_after)
            self.after(0, self._update_total)
            self._safe_append(f"\nDone.  Freed: {format_size(freed)}")
            self._running = False
            self.after(0, self._set_btn_state, True)

        threading.Thread(target=task, daemon=True).start()
