"""App shell: sidebar navigation, page header, live system status bar."""
import ctypes
import getpass
import os
import socket
import threading
import time

import customtkinter as ctk

from modules.paths import get_base_dir
from ui import theme as T
from ui.tab_apps import AppsTab
from ui.tab_cleanup import CleanupTab
from ui.tab_config import ConfigTab
from ui.tab_debloat import DebloatTab
from ui.tab_home import HomeTab
from ui.tab_security import SecurityTab
from ui.tab_system import SystemTab
from ui.tab_threat import ThreatTab
from ui.tab_tweaks import TweaksTab
from ui.tab_users import UsersTab
from ui.widgets import bind_root, install_shortcuts, tip

APP_VERSION = "v1.3.0"

# (group, [(page name, class, subtitle)]) — order here is sidebar order and Ctrl+N order.
# Home is Ctrl+0; the pages after it are Ctrl+1..9 in this order.
NAV = [
    ("OVERVIEW", [
        ("Home", HomeTab, "Everything about this machine at a glance"),
    ]),
    ("PROVISION", [
        ("System", SystemTab, "Hardware info, rename computer, domain join"),
        ("Apps", AppsTab, "Install standard and team software"),
        ("Config", ConfigTab, "Windows features, legacy panels, Google Sheets sync"),
    ]),
    ("OPTIMIZE", [
        ("Debloat", DebloatTab, "Remove preinstalled Store apps, or reinstall them"),
        ("Tweaks", TweaksTab, "System tweaks, privacy, preferences, power plans"),
        ("Cleanup", CleanupTab, "User profiles, Windows junk, disk usage"),
    ]),
    ("DEFENSE", [
        ("Security", SecurityTab, "Vulnerability scan, risk score, one-click fixes"),
        ("Threat Report", ThreatTab, "Signs of compromise and vulnerability exposure"),
    ]),
    ("ADMIN", [
        ("Users", UsersTab, "Accounts that can sign in to this tool"),
    ]),
]

USER_PAGES = {"Apps"}   # pages a non-admin may see
HOME = "Home"

SIDEBAR_W = 216


# ── Live machine info for the status bar ─────────────────────────────

def _local_ip():
    try:
        # UDP connect sends no packets; it just picks the outbound interface.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        return ip if not ip.startswith("127.") else None
    except OSError:
        try:
            ip = socket.gethostbyname(socket.gethostname())
            return ip if not ip.startswith("127.") else None
        except OSError:
            return None


def _os_string():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            def get(name, default=""):
                try:
                    return winreg.QueryValueEx(k, name)[0]
                except OSError:
                    return default
            name, build = get("ProductName", "Windows"), get("CurrentBuild", "?")
            ver = get("DisplayVersion") or get("ReleaseId")
        if str(build).isdigit() and int(build) >= 22000:
            name = name.replace("Windows 10", "Windows 11")   # registry still says 10 on 11
        return f"{name.replace('Windows ', 'Win')} {ver} ({build})".replace("  ", " ")
    except Exception:
        return "Windows"


def _domain():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters") as k:
            dom = winreg.QueryValueEx(k, "Domain")[0]
        return dom.upper() if dom else "WORKGROUP"
    except Exception:
        return os.environ.get("USERDNSDOMAIN", "WORKGROUP").upper()


def _elevated():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _uptime():
    try:
        secs = ctypes.windll.kernel32.GetTickCount64() // 1000
    except Exception:
        return "?"
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    return f"{d}d {h:02d}h {rem // 60:02d}m"


# ── Sidebar nav item ─────────────────────────────────────────────────

class NavItem(ctk.CTkFrame):
    def __init__(self, master, name, index, on_click):
        super().__init__(master, fg_color="transparent", corner_radius=3, height=36, cursor="hand2")
        self.name = name
        self._active = False
        self.grid_columnconfigure(2, weight=1)
        self.grid_propagate(False)

        self._bar = ctk.CTkFrame(self, width=3, height=20, corner_radius=1, fg_color="transparent")
        self._bar.grid(row=0, column=0, padx=(0, 10), pady=8, sticky="ns")
        self._icon = ctk.CTkLabel(self, text=T.ICONS.get(name, ""), font=T.icon(15),
                                  text_color=T.MUTED, width=20)
        self._icon.grid(row=0, column=1, padx=(0, 12))
        self._text = ctk.CTkLabel(self, text=name, font=T.ui(13), text_color=T.TEXT, anchor="w")
        self._text.grid(row=0, column=2, sticky="w")
        self._key = ctk.CTkLabel(self, text=f"^{index}" if index <= 9 else "", font=T.mono(10),
                                 text_color=T.DIM)
        self._key.grid(row=0, column=3, padx=(0, 10))
        self.grid_rowconfigure(0, weight=1)

        for w in (self, self._bar, self._icon, self._text, self._key):
            w.bind("<Button-1>", lambda e: on_click(name))
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))

    def _hover(self, on):
        if not self._active:
            self.configure(fg_color=T.PANEL_2 if on else "transparent")

    def set_active(self, active):
        self._active = active
        self.configure(fg_color=T.ACCENT_DIM if active else "transparent")
        self._bar.configure(fg_color=T.ACCENT if active else "transparent")
        self._icon.configure(text_color=T.ACCENT if active else T.MUTED)
        self._text.configure(text_color=T.TEXT_BRIGHT if active else T.TEXT,
                             font=T.ui(13, "bold") if active else T.ui(13))


# ── Dashboard ────────────────────────────────────────────────────────

class Dashboard(ctk.CTkFrame):
    def __init__(self, master, username, role, display_name, on_logout):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        self.username = username
        self.role = role
        self.display_name = display_name
        self.on_logout = on_logout
        self._pages = {}      # name -> tab widget
        self._page_meta = {}  # name -> (group, subtitle)
        self._nav = {}        # name -> NavItem
        self._current = None
        self._build()

    def _visible(self, name):
        return self.role == "admin" or name in USER_PAGES

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_sidebar()

        main = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)
        self._build_header(main)

        self._content = ctk.CTkFrame(main, fg_color=T.BG, corner_radius=0)
        self._content.grid(row=1, column=0, sticky="nsew", padx=14, pady=(10, 10))
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._build_statusbar()

        order = []
        for group, pages in NAV:
            for name, cls, subtitle in pages:
                if not self._visible(name):
                    continue
                self._page_meta[name] = (group, subtitle)
                page = ctk.CTkFrame(self._content, fg_color="transparent", corner_radius=0)
                page.grid_rowconfigure(0, weight=1)
                page.grid_columnconfigure(0, weight=1)
                widget = cls(page, self.role)
                widget.grid(row=0, column=0, sticky="nsew")
                if hasattr(widget, "attach_shell"):
                    widget.attach_shell(self)
                self._pages[name] = (page, widget)
                order.append(name)

        if order:
            self.show(order[0])

        # Ctrl+A / Ctrl+Shift+A / Ctrl+Enter go to the visible page; Ctrl+1..9 switch pages
        install_shortcuts(self, lambda: self._pages[self._current][1] if self._current else None)
        numbered = [n for n in order if n != HOME]
        keys = {f"<Control-Key-{i}>": (lambda e, n=n: self.show(n))
                for i, n in enumerate(numbered[:9], 1)}
        if HOME in self._pages:
            keys["<Control-Key-0>"] = lambda e: self.show(HOME)
        bind_root(self, keys)

        self._refresh_status()
        self._tick()

    # ── Sidebar ──────────────────────────────────────────────────────

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=SIDEBAR_W, fg_color=T.SIDEBAR, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 4))
        ctk.CTkLabel(brand, text="◆", font=T.ui(18, "bold"), text_color=T.ACCENT).grid(
            row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(brand, text="PROVISION", font=T.mono(16, "bold"),
                     text_color=T.TEXT_BRIGHT).grid(row=0, column=1, sticky="w")
        ver = ctk.CTkLabel(brand, text=f"IT TOOLKIT · {APP_VERSION}", font=T.mono(10),
                           text_color=T.MUTED, cursor="hand2")
        ver.grid(row=1, column=1, sticky="w")
        ver.bind("<Button-1>", lambda e: self._show_changelog())
        tip(ver, "Show the changelog")

        ctk.CTkFrame(side, height=1, fg_color=T.BORDER).grid(
            row=1, column=0, sticky="ew", padx=12, pady=(14, 6))

        nav = ctk.CTkFrame(side, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="new", padx=8)
        nav.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(2, weight=1)

        r, idx = 0, 1
        for group, pages in NAV:
            names = [p[0] for p in pages if self._visible(p[0])]
            if not names:
                continue
            ctk.CTkLabel(nav, text=group, font=T.mono(10, "bold"), text_color=T.DIM,
                         anchor="w").grid(row=r, column=0, sticky="w", padx=12, pady=(12, 2))
            r += 1
            for name in names:
                if name == HOME:
                    item = NavItem(nav, name, 0, self.show)
                else:
                    item = NavItem(nav, name, idx, self.show)
                    idx += 1
                item.grid(row=r, column=0, sticky="ew", pady=1)
                self._nav[name] = item
                r += 1

        # Signed-in user + logout
        ctk.CTkFrame(side, height=1, fg_color=T.BORDER).grid(
            row=3, column=0, sticky="ew", padx=12, pady=(6, 0))
        user = ctk.CTkFrame(side, fg_color="transparent")
        user.grid(row=4, column=0, sticky="ew", padx=14, pady=12)
        user.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(user, text=self.display_name, font=T.ui(12, "bold"),
                     text_color=T.TEXT_BRIGHT, anchor="w").grid(row=0, column=0, sticky="w")
        role_color = T.OK if self.role == "admin" else T.INFO
        ctk.CTkLabel(user, text=f"● {self.role.upper()}", font=T.mono(10, "bold"),
                     text_color=role_color, anchor="w").grid(row=1, column=0, sticky="w")
        tip(ctk.CTkButton(user, text=T.ICONS["power"], font=T.icon(14), width=32, height=32,
                          fg_color="transparent", border_width=1, text_color=T.MUTED,
                          hover_color=T.DANGER, command=self.on_logout),
            "Log out").grid(row=0, column=1, rowspan=2, sticky="e")

    # ── Header ───────────────────────────────────────────────────────

    def _build_header(self, main):
        hdr = ctk.CTkFrame(main, fg_color=T.BG, corner_radius=0, height=64)
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 12))
        hdr.grid_columnconfigure(0, weight=1)

        crumb = ctk.CTkFrame(hdr, fg_color="transparent")
        crumb.grid(row=0, column=0, sticky="w")
        self._crumb_group = ctk.CTkLabel(crumb, text="", font=T.mono(11, "bold"),
                                         text_color=T.ACCENT)
        self._crumb_group.grid(row=0, column=0)
        ctk.CTkLabel(crumb, text="  ▸  ", font=T.mono(11), text_color=T.DIM).grid(row=0, column=1)
        self._crumb_page = ctk.CTkLabel(crumb, text="", font=T.mono(11), text_color=T.MUTED)
        self._crumb_page.grid(row=0, column=2)

        self._title = ctk.CTkLabel(hdr, text="", font=T.ui(22, "bold"),
                                   text_color=T.TEXT_BRIGHT, anchor="w")
        self._title.grid(row=1, column=0, sticky="w")
        self._subtitle = ctk.CTkLabel(hdr, text="", font=T.ui(12), text_color=T.MUTED, anchor="w")
        self._subtitle.grid(row=2, column=0, sticky="w")

        keys = ctk.CTkLabel(hdr, text="^A all   ^⇧A none   ^↵ run   ^0 home   ^1-9 nav",
                            font=T.mono(10), text_color=T.DIM)
        keys.grid(row=0, column=1, rowspan=3, sticky="se", pady=(0, 4))
        tip(keys, "Keyboard shortcuts\n"
                  "Ctrl+A  select all\nCtrl+Shift+A  select none\n"
                  "Ctrl+Enter  run the page's main action (asks first)\n"
                  "Ctrl+0  Home\n"
                  "Ctrl+1 … Ctrl+9  jump to a page")

        ctk.CTkFrame(main, height=1, fg_color=T.BORDER).grid(
            row=0, column=0, sticky="sew", padx=20)

    # ── Status bar ───────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0, height=28)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(0, weight=1)
        ctk.CTkFrame(bar, height=1, fg_color=T.BORDER).place(x=0, y=0, relwidth=1)

        self._net_dot = ctk.CTkLabel(bar, text="●", font=T.mono(11), text_color=T.DIM)
        self._net_dot.grid(row=0, column=0, padx=(14, 4))
        self._status = {}
        fields = [("net", None), ("HOST", "Computer name"), ("IP", "Primary IPv4 address"),
                  ("OS", "Windows edition, version and build"), ("DOMAIN", "Joined domain"),
                  ("USER", "Signed-in Windows account"), ("PRIV", "Process elevation")]
        col = 1
        for key, hint in fields:
            if key != "net":
                ctk.CTkLabel(bar, text=key, font=T.mono(10), text_color=T.DIM).grid(
                    row=0, column=col, padx=(14, 5))
                col += 1
            lbl = ctk.CTkLabel(bar, text="…", font=T.mono(11), text_color=T.TEXT)
            lbl.grid(row=0, column=col)
            if hint:
                tip(lbl, hint)
            self._status[key] = lbl
            col += 1

        bar.grid_columnconfigure(col, weight=1)
        self._uptime_lbl = ctk.CTkLabel(bar, text="", font=T.mono(10), text_color=T.DIM)
        self._uptime_lbl.grid(row=0, column=col + 1, padx=(0, 14))
        tip(self._uptime_lbl, "Time since Windows last started")
        self._clock = ctk.CTkLabel(bar, text="", font=T.mono(11), text_color=T.TEXT)
        self._clock.grid(row=0, column=col + 2, padx=(0, 14))

    def _refresh_status(self):
        """Gather machine info off the UI thread; re-run every 30 s (IP / domain can change)."""
        def task():
            info = {
                "HOST": socket.gethostname().upper(),
                "IP": _local_ip(),
                "OS": _os_string(),
                "DOMAIN": _domain(),
                "USER": getpass.getuser(),
                "PRIV": "ELEVATED" if _elevated() else "STANDARD",
            }
            try:
                self.after(0, self._apply_status, info)
            except RuntimeError:
                pass   # window closed meanwhile
        if not self.winfo_exists():
            return
        threading.Thread(target=task, daemon=True).start()
        self.after(30_000, self._refresh_status)

    def _apply_status(self, info):
        if not self.winfo_exists():
            return
        online = info["IP"] is not None
        self._net_dot.configure(text_color=T.OK if online else T.FAIL)
        self._status["net"].configure(text="ONLINE" if online else "OFFLINE",
                                      text_color=T.OK if online else T.FAIL)
        for key in ("HOST", "OS", "DOMAIN", "USER"):
            self._status[key].configure(text=info[key])
        self._status["IP"].configure(text=info["IP"] or "—")
        elevated = info["PRIV"] == "ELEVATED"
        self._status["PRIV"].configure(text=info["PRIV"], text_color=T.OK if elevated else T.WARN)
        self._status["DOMAIN"].configure(
            text_color=T.TEXT if info["DOMAIN"] != "WORKGROUP" else T.MUTED)

    def _tick(self):
        if not self.winfo_exists():
            return
        self._clock.configure(text=time.strftime("%H:%M:%S"))
        self._uptime_lbl.configure(text=f"UP {_uptime()}")
        self.after(1000, self._tick)

    # ── Navigation ───────────────────────────────────────────────────

    def show(self, name):
        if name not in self._pages or name == self._current:
            return
        if self._current:
            self._pages[self._current][0].grid_remove()
            self._nav[self._current].set_active(False)
        self._current = name
        self._pages[name][0].grid(row=0, column=0, sticky="nsew")
        self._nav[name].set_active(True)
        group, subtitle = self._page_meta[name]
        self._crumb_group.configure(text=group)
        self._crumb_page.configure(text=name.upper())
        self._title.configure(text=name)
        self._subtitle.configure(text=subtitle)
        on_show = getattr(self._pages[name][1], "on_show", None)
        if callable(on_show):
            on_show()

    # ── Changelog ────────────────────────────────────────────────────

    def _show_changelog(self):
        changelog_path = os.path.join(get_base_dir(), "CHANGELOG.md")
        try:
            with open(changelog_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"Could not load CHANGELOG.md\nPath: {changelog_path}\nError: {e}"

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Changelog  {APP_VERSION}")
        dialog.geometry("760x580")
        dialog.resizable(True, True)
        dialog.grid_rowconfigure(1, weight=1)
        dialog.grid_columnconfigure(0, weight=1)
        dialog.after(100, dialog.lift)
        dialog.after(150, dialog.focus_force)

        ctk.CTkLabel(dialog, text=f"CHANGELOG  ·  {APP_VERSION}", font=T.mono(13, "bold"),
                     text_color=T.ACCENT, anchor="w").grid(
            row=0, column=0, padx=16, pady=(14, 6), sticky="w")
        box = ctk.CTkTextbox(dialog, wrap="word", font=T.mono(12), text_color=T.TEXT)
        box.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="nsew")
        box.insert("1.0", content)
        box.configure(state="disabled")

        ctk.CTkButton(dialog, text="Close", width=100,
                      command=dialog.destroy).grid(row=2, column=0, pady=(0, 16))
