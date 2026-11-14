"""Ops-console theme: palette, fonts and the CustomTkinter theme override.

Call apply_theme() once, before any widget is created. Tabs import the tokens
(e.g. `from ui import theme as T`, then `T.MUTED`, `T.mono(11)`).
"""
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

# ── Palette (dark only — the app forces dark mode) ───────────────────
BG          = "#0a0f15"   # window background
SIDEBAR     = "#0d131b"   # sidebar + status bar
PANEL       = "#111923"   # cards / frames
PANEL_2     = "#16212e"   # nested frames, row backgrounds, group headers
PANEL_3     = "#1c2a3a"   # hover / selected rows
BORDER      = "#223144"
INPUT_BG    = "#0c131b"

TEXT        = "#d5e1ec"
TEXT_BRIGHT = "#f1f6fb"
MUTED       = "#7b8da3"
DIM         = "#4d5f73"

ACCENT      = "#00b4d8"   # cyan
ACCENT_HOVER = "#0094b3"
ACCENT_DIM  = "#0b3442"   # selected nav background
ACCENT_TEXT = "#04131a"   # text on a filled accent button

OK          = "#2ecc71"
WARN        = "#f0a020"
FAIL        = "#ef4c4c"
INFO        = "#3d9be9"
DANGER      = "#c0392b"
DANGER_HOVER = "#922b21"

# Level colours shared by Security + Threat reports
LEVEL = {"CLEAN": OK, "LOW": INFO, "MEDIUM": WARN, "HIGH": FAIL, "CRITICAL": "#ff2e63"}

# ── Fonts ────────────────────────────────────────────────────────────
UI_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"          # replaced by Cascadia Mono if installed
ICON_FAMILY = "Segoe MDL2 Assets"  # present on Windows 10 and 11

# Segoe MDL2 Assets glyphs used in the shell
ICONS = {
    "System": "", "Debloat": "", "Apps": "", "Tweaks": "",
    "Config": "", "Cleanup": "", "Security": "",
    "Threat Report": "", "Users": "",
    "info": "", "power": "", "refresh": "",
}


def mono(size=12, weight="normal"):
    return ctk.CTkFont(family=MONO_FAMILY, size=size, weight=weight)


def ui(size=13, weight="normal"):
    return ctk.CTkFont(family=UI_FAMILY, size=size, weight=weight)


def icon(size=16):
    return ctk.CTkFont(family=ICON_FAMILY, size=size)


def _pair(c):
    return [c, c]


def apply_theme():
    """Override the built-in CustomTkinter theme with the ops-console palette."""
    global MONO_FAMILY, ICON_FAMILY
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")   # load a complete theme, then override it

    # Pick the best installed fonts (needs a Tk root, so use a throwaway one if needed)
    root = tk._default_root
    tmp = None
    if root is None:
        tmp = root = tk.Tk()
        root.withdraw()
    try:
        fams = set(tkfont.families(root))
    finally:
        if tmp is not None:
            tmp.destroy()
    for f in ("Cascadia Mono", "Cascadia Code", "Consolas"):
        if f in fams:
            MONO_FAMILY = f
            break
    if "Segoe MDL2 Assets" not in fams and "Segoe Fluent Icons" in fams:
        ICON_FAMILY = "Segoe Fluent Icons"

    t = ctk.ThemeManager.theme
    t["CTk"]["fg_color"] = _pair(BG)
    t["CTkToplevel"]["fg_color"] = _pair(BG)
    t["CTkFrame"].update(corner_radius=4, fg_color=_pair(PANEL), top_fg_color=_pair(PANEL_2),
                         border_color=_pair(BORDER))
    t["CTkButton"].update(corner_radius=3, fg_color=_pair(ACCENT), hover_color=_pair(ACCENT_HOVER),
                          border_color=_pair(BORDER), text_color=_pair(ACCENT_TEXT),
                          text_color_disabled=_pair(DIM))
    t["CTkLabel"]["text_color"] = _pair(TEXT)
    t["CTkEntry"].update(corner_radius=3, border_width=1, fg_color=_pair(INPUT_BG),
                         border_color=_pair(BORDER), text_color=_pair(TEXT_BRIGHT),
                         placeholder_text_color=_pair(DIM))
    t["CTkCheckBox"].update(corner_radius=3, border_width=2, fg_color=_pair(ACCENT),
                            border_color=_pair(MUTED), hover_color=_pair(ACCENT_HOVER),
                            checkmark_color=_pair(ACCENT_TEXT), text_color=_pair(TEXT),
                            text_color_disabled=_pair(DIM))
    t["CTkSwitch"].update(fg_color=_pair(PANEL_3), progress_color=_pair(ACCENT),
                          button_color=_pair(TEXT), button_hover_color=_pair(TEXT_BRIGHT),
                          text_color=_pair(TEXT), text_color_disabled=_pair(DIM))
    t["CTkRadioButton"].update(fg_color=_pair(ACCENT), border_color=_pair(MUTED),
                               hover_color=_pair(ACCENT_HOVER), text_color=_pair(TEXT),
                               text_color_disabled=_pair(DIM))
    t["CTkProgressBar"].update(corner_radius=2, fg_color=_pair(PANEL_3), progress_color=_pair(ACCENT))
    t["CTkSlider"].update(fg_color=_pair(PANEL_3), progress_color=_pair(ACCENT),
                          button_color=_pair(ACCENT), button_hover_color=_pair(ACCENT_HOVER))
    t["CTkOptionMenu"].update(corner_radius=3, fg_color=_pair(PANEL_2), button_color=_pair(PANEL_3),
                              button_hover_color=_pair(BORDER), text_color=_pair(TEXT),
                              text_color_disabled=_pair(DIM))
    t["CTkComboBox"].update(corner_radius=3, border_width=1, fg_color=_pair(INPUT_BG),
                            border_color=_pair(BORDER), button_color=_pair(PANEL_3),
                            button_hover_color=_pair(BORDER), text_color=_pair(TEXT),
                            text_color_disabled=_pair(DIM))
    t["CTkScrollbar"].update(button_color=_pair(PANEL_3), button_hover_color=_pair(BORDER))
    t["CTkSegmentedButton"].update(corner_radius=3, border_width=1, fg_color=_pair(PANEL_2),
                                   selected_color=_pair(ACCENT_DIM), selected_hover_color=_pair(ACCENT_DIM),
                                   unselected_color=_pair(PANEL_2), unselected_hover_color=_pair(PANEL_3),
                                   text_color=_pair(TEXT), text_color_disabled=_pair(DIM))
    t["CTkTextbox"].update(corner_radius=3, border_width=1, fg_color=_pair(INPUT_BG),
                           border_color=_pair(BORDER), text_color=_pair("#9fd8b0"),
                           scrollbar_button_color=_pair(PANEL_3),
                           scrollbar_button_hover_color=_pair(BORDER))
    t["CTkScrollableFrame"]["label_fg_color"] = _pair(PANEL_2)
    t["DropdownMenu"].update(fg_color=_pair(PANEL_2), hover_color=_pair(PANEL_3), text_color=_pair(TEXT))
    # After loading, CTk flattens the per-OS font entry into CTkFont itself.
    font = t["CTkFont"].get("Windows", t["CTkFont"])
    font.update(family=UI_FAMILY, size=13)
    _patch_button_text()


def _patch_button_text():
    """Dark text only suits the default cyan button. Any button given its own fg_color
    (transparent/outline, red, orange, grey...) gets light text unless it sets one."""
    if getattr(ctk.CTkButton, "_ops_patched", False):
        return
    orig = ctk.CTkButton.__init__

    def __init__(self, *args, **kw):
        if "fg_color" in kw and "text_color" not in kw:
            kw["text_color"] = TEXT if kw["fg_color"] == "transparent" else TEXT_BRIGHT
        if kw.get("fg_color") == "transparent" and kw.get("border_width") and "border_color" not in kw:
            kw["border_color"] = BORDER
        if kw.get("fg_color") == "transparent" and "hover_color" not in kw:
            kw["hover_color"] = PANEL_3
        orig(self, *args, **kw)

    ctk.CTkButton.__init__ = __init__
    ctk.CTkButton._ops_patched = True


def outline_button(master, **kw):
    """Secondary action: transparent with a thin border."""
    kw.setdefault("fg_color", "transparent")
    kw.setdefault("border_width", 1)
    return ctk.CTkButton(master, **kw)
