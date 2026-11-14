"""Shared UI helpers: tooltips, confirm-before-run dialog, tab keyboard shortcuts."""
import tkinter as tk

import customtkinter as ctk

# ── Tooltip ─────────────────────────────────────────────────────────

_TIP_DELAY_MS = 500
_TIP_BG = ("#ffffe1", "#2b2b2b")
_TIP_FG = ("#1a1a1a", "#e6e6e6")


class Tooltip:
    """Hover tooltip for any Tk/CTk widget. CTk widgets forward bind() to their inner parts."""

    def __init__(self, widget, text, wraplength=320):
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(_TIP_DELAY_MS, self._show)

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        if self._tip or not self.text or not self.widget.winfo_exists():
            return
        dark = ctk.get_appearance_mode() == "Dark"
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tk.Label(tw, text=self.text, justify="left", wraplength=self.wraplength,
                 bg=_TIP_BG[dark], fg=_TIP_FG[dark], relief="solid", borderwidth=1,
                 font=("Segoe UI", 9), padx=6, pady=3).pack()
        tw.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event=None):
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


def tip(widget, text):
    """Attach a tooltip and return the widget, so it can wrap a constructor call."""
    Tooltip(widget, text)
    return widget


# ── Confirm before run ──────────────────────────────────────────────

def confirm_run(parent, title, intro, items, action_text="Run", danger=False, footer=None):
    """Modal "here's what will run" dialog. Returns True if the user confirms.

    items: list of str, or (str, highlighted) tuples — highlighted items are shown in red.
    """
    norm = [(i, False) if isinstance(i, str) else (i[0], bool(i[1])) for i in items]
    result = {"ok": False}

    dlg = ctk.CTkToplevel(parent)
    dlg.title(title)
    height = min(220 + 26 * len(norm), 560)
    dlg.geometry(f"520x{height}")
    dlg.minsize(420, 240)
    dlg.resizable(True, True)
    dlg.transient(parent.winfo_toplevel())
    dlg.grid_columnconfigure(0, weight=1)
    dlg.grid_rowconfigure(2, weight=1)

    ctk.CTkLabel(dlg, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").grid(
        row=0, column=0, padx=16, pady=(14, 2), sticky="w")
    ctk.CTkLabel(dlg, text=intro, font=ctk.CTkFont(size=12), text_color="gray",
                 wraplength=480, justify="left", anchor="w").grid(
        row=1, column=0, padx=16, pady=(0, 6), sticky="w")

    box = ctk.CTkScrollableFrame(dlg)
    box.grid(row=2, column=0, padx=16, pady=4, sticky="nsew")
    box.grid_columnconfigure(0, weight=1)
    for i, (text, hot) in enumerate(norm):
        ctk.CTkLabel(box, text=f"•  {text}", anchor="w", justify="left", wraplength=440,
                     font=ctk.CTkFont(size=12),
                     text_color=("#c0392b", "#ff7675") if hot else None).grid(
            row=i, column=0, padx=6, pady=1, sticky="w")

    row = 3
    if footer:
        ctk.CTkLabel(dlg, text=footer, font=ctk.CTkFont(size=11, slant="italic"),
                     text_color=("#c0392b", "#ff7675") if danger else "gray",
                     wraplength=480, justify="left", anchor="w").grid(
            row=row, column=0, padx=16, pady=(6, 0), sticky="w")
        row += 1

    def close(ok):
        result["ok"] = ok
        try:
            dlg.grab_release()
        except Exception:
            pass
        dlg.destroy()

    btns = ctk.CTkFrame(dlg, fg_color="transparent")
    btns.grid(row=row, column=0, padx=16, pady=(10, 14), sticky="e")
    ctk.CTkButton(btns, text="Cancel", width=100, fg_color="transparent", border_width=1,
                  command=lambda: close(False)).grid(row=0, column=0, padx=(0, 8))
    kw = {"fg_color": "#c0392b", "hover_color": "#922b21"} if danger else {}
    ctk.CTkButton(btns, text=action_text, width=150, command=lambda: close(True), **kw).grid(
        row=0, column=1)

    dlg.bind("<Return>", lambda e: close(True))
    dlg.bind("<KP_Enter>", lambda e: close(True))
    dlg.bind("<Escape>", lambda e: close(False))
    dlg.protocol("WM_DELETE_WINDOW", lambda: close(False))
    dlg.lift()
    dlg.after(50, dlg.focus_force)
    dlg.after(60, lambda: dlg.winfo_exists() and dlg.grab_set())
    parent.wait_window(dlg)
    return result["ok"]


# ── Keyboard shortcuts ──────────────────────────────────────────────
# Tabs opt in by defining any of:
#   shortcut_select_all()    Ctrl+A
#   shortcut_deselect_all()  Ctrl+Shift+A
#   shortcut_apply()         Ctrl+Enter   (main action of the tab: apply / clean / scan)
# A tab that hosts sub-sections can define shortcut_target() returning the active one.

SHORTCUTS = {
    "<Control-a>": "shortcut_select_all",
    "<Control-A>": "shortcut_deselect_all",   # Shift makes the keysym uppercase
    "<Control-Return>": "shortcut_apply",
    "<Control-KP_Enter>": "shortcut_apply",
}

_TEXT_CLASSES = {"Entry", "Text", "TEntry", "Spinbox", "TCombobox"}


def _resolve(target):
    seen = 0
    while target is not None and hasattr(target, "shortcut_target") and seen < 5:
        nxt = target.shortcut_target()
        if nxt is None or nxt is target:
            break
        target, seen = nxt, seen + 1
    return target


def install_shortcuts(owner, get_active):
    """Bind tab shortcuts on owner's toplevel; get_active() returns the visible tab widget.

    Bindings are removed when owner is destroyed (e.g. on logout).
    """
    root = owner.winfo_toplevel()
    bound = []

    def make_handler(method):
        def handler(event):
            # In text fields, let Ctrl+A select text as usual.
            if event.widget.winfo_class() in _TEXT_CLASSES:
                return None
            target = _resolve(get_active())
            fn = getattr(target, method, None) if target is not None else None
            if callable(fn):
                fn()
                return "break"
            return None
        return handler

    for seq, method in SHORTCUTS.items():
        bound.append((seq, root.bind(seq, make_handler(method), add="+")))

    def cleanup(event):
        if event.widget is not owner:
            return
        for seq, funcid in bound:
            try:
                root.unbind(seq, funcid)
            except Exception:
                pass
        bound.clear()

    # tk.Misc.bind directly: CTk widgets redirect .bind() to their inner canvas,
    # whose <Destroy> event would never have owner as event.widget.
    tk.Misc.bind(owner, "<Destroy>", cleanup, "+")
