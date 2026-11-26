"""Ops-console theme: palette, fonts and the CustomTkinter theme override.

Call apply_theme() once, before any widget is created. Tabs import the tokens
(e.g. `from ui import theme as T`, then `T.MUTED`, `T.mono(11)`).
"""
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

# ── Palette presets ──────────────────────────────────────────────────
# Each preset defines every colour token. The active one is copied into the module
# globals by apply_theme(), so tabs keep using T.PANEL, T.ACCENT, ... unchanged.
# Pick one in ui_settings.json ({"theme": "Graphite"}) or with PROVTOOL_THEME=<name>.

_STATUS_DARK = dict(OK="#2ecc71", WARN="#f0a020", FAIL="#ef4c4c", INFO="#3d9be9",
                    CRITICAL="#ff2e63", DANGER="#c0392b", DANGER_HOVER="#922b21")

PRESETS = {
    # Dark navy, cyan accent: the approved default
    "Good One": dict(
        MODE="dark", BG="#0a0f15", SIDEBAR="#0d131b", PANEL="#111923", PANEL_2="#16212e",
        PANEL_3="#1c2a3a", BORDER="#223144", INPUT_BG="#0c131b",
        TEXT="#d5e1ec", TEXT_BRIGHT="#f1f6fb", MUTED="#7b8da3", DIM="#4d5f73",
        ACCENT="#00b4d8", ACCENT_HOVER="#0094b3", ACCENT_DIM="#0b3442", ACCENT_TEXT="#04131a",
        TERM_TEXT="#9fd8b0", ON_COLOR="#f1f6fb", **_STATUS_DARK),
    # Neutral charcoal, Windows-blue accent: calm, close to Windows 11 dark
    "Graphite": dict(
        MODE="dark", BG="#18181b", SIDEBAR="#1e1e22", PANEL="#232328", PANEL_2="#2a2a30",
        PANEL_3="#34343c", BORDER="#3a3a43", INPUT_BG="#1b1b1f",
        TEXT="#e4e4e7", TEXT_BRIGHT="#fafafa", MUTED="#a1a1aa", DIM="#6b6b74",
        ACCENT="#4c9eff", ACCENT_HOVER="#3484e6", ACCENT_DIM="#1d3352", ACCENT_TEXT="#06162b",
        TERM_TEXT="#b4d4ff", ON_COLOR="#fafafa", **_STATUS_DARK),
    # Near-black, phosphor green: SOC / terminal feel
    "Terminal": dict(
        MODE="dark", BG="#060a07", SIDEBAR="#091009", PANEL="#0d150f", PANEL_2="#122016",
        PANEL_3="#192b1e", BORDER="#1f3626", INPUT_BG="#070e09",
        TEXT="#c6e5cd", TEXT_BRIGHT="#eafff0", MUTED="#6e927a", DIM="#455f4d",
        ACCENT="#39d353", ACCENT_HOVER="#2cb345", ACCENT_DIM="#123d1d", ACCENT_TEXT="#03140a",
        TERM_TEXT="#7ee787", ON_COLOR="#eafff0",
        **{**_STATUS_DARK, "OK": "#7ee787"}),
    # Warm black, amber accent: classic NOC wallboard
    "Amber Ops": dict(
        MODE="dark", BG="#0e0a06", SIDEBAR="#130e08", PANEL="#19130c", PANEL_2="#211910",
        PANEL_3="#2c2115", BORDER="#3a2c1b", INPUT_BG="#110c07",
        TEXT="#ecdcc4", TEXT_BRIGHT="#fff4e3", MUTED="#a08a6c", DIM="#6b5a44",
        ACCENT="#ffb000", ACCENT_HOVER="#d99500", ACCENT_DIM="#3d2c08", ACCENT_TEXT="#1a1000",
        TERM_TEXT="#ffd27a", ON_COLOR="#fff4e3",
        **{**_STATUS_DARK, "WARN": "#ff7a1a"}),
    # Light theme for bright offices and projectors
    "Daylight": dict(
        MODE="light", BG="#eef1f5", SIDEBAR="#e3e8ee", PANEL="#ffffff", PANEL_2="#f5f7fa",
        PANEL_3="#e4e9f0", BORDER="#cfd7e0", INPUT_BG="#ffffff",
        TEXT="#1f2933", TEXT_BRIGHT="#0b1117", MUTED="#5b6b7c", DIM="#8b98a6",
        ACCENT="#0969da", ACCENT_HOVER="#0757b5", ACCENT_DIM="#d6e6fb", ACCENT_TEXT="#ffffff",
        TERM_TEXT="#1a7f37", ON_COLOR="#ffffff",
        OK="#1a7f37", WARN="#b35c00", FAIL="#cf222e", INFO="#0969da",
        CRITICAL="#a40e26", DANGER="#cf222e", DANGER_HOVER="#a40e26"),
}
DEFAULT_PRESET = "Good One"
ACTIVE_PRESET = DEFAULT_PRESET
SETTINGS_FILE = "ui_settings.json"

# Module-level tokens start as the default preset; apply_theme() swaps them.
globals().update(PRESETS[DEFAULT_PRESET])

# Level / status / severity colours shared by Security + Threat reports.
# Mutated in place by apply_theme(), so modules holding a reference see the change.
LEVEL = {}
STATUS = {}
SEV = {}
STATUS_TAG = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN", "INFO": "INFO", "UNKNOWN": " ?? "}
SEV_TAG = {"HIGH": "HIGH", "MEDIUM": "MED", "LOW": "LOW"}


def _rebuild_maps():
    LEVEL.update({"CLEAN": OK, "LOW": INFO, "MEDIUM": WARN, "HIGH": FAIL, "CRITICAL": CRITICAL})
    STATUS.update({"PASS": OK, "FAIL": FAIL, "WARN": WARN, "INFO": INFO, "UNKNOWN": MUTED})
    SEV.update({"HIGH": FAIL, "MEDIUM": WARN, "LOW": MUTED})


_rebuild_maps()


def _settings_path():
    from modules.utils import writable_path
    return writable_path(SETTINGS_FILE)


def chosen_preset():
    """Preset name from PROVTOOL_THEME, else ui_settings.json, else the default."""
    import json
    import os
    name = os.environ.get("PROVTOOL_THEME")
    if not name:
        try:
            with open(_settings_path(), encoding="utf-8") as f:
                name = json.load(f).get("theme")
        except (OSError, ValueError, AttributeError):
            name = None
    return name if name in PRESETS else DEFAULT_PRESET


def save_preset(name):
    """Remember the preset for the next launch (takes effect on restart)."""
    import json
    if name not in PRESETS:
        raise ValueError(f"Unknown theme {name!r}")
    path = _settings_path()
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["theme"] = name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── Fonts ────────────────────────────────────────────────────────────
UI_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"          # replaced by Cascadia Mono if installed
ICON_FAMILY = "Segoe MDL2 Assets"  # present on Windows 10 and 11

# Segoe MDL2 Assets glyphs used in the shell
ICONS = {
    "Home": "", "System": "", "Network": "", "Debloat": "", "Apps": "", "Tweaks": "",
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


def apply_theme(name=None):
    """Load a palette preset and override the built-in CustomTkinter theme with it.
    Must run before any widget is created and before the tab modules are imported."""
    global MONO_FAMILY, ICON_FAMILY, ACTIVE_PRESET
    ACTIVE_PRESET = name if name in PRESETS else chosen_preset()
    globals().update(PRESETS[ACTIVE_PRESET])
    _rebuild_maps()
    ctk.set_appearance_mode(MODE)
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
                           border_color=_pair(BORDER), text_color=_pair(TERM_TEXT),
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
            kw["text_color"] = TEXT if kw["fg_color"] == "transparent" else ON_COLOR
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
