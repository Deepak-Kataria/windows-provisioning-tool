import os
import customtkinter as ctk
from modules.paths import get_base_dir
from ui.tab_system import SystemTab
from ui.tab_debloat import DebloatTab
from ui.tab_telemetry import TelemetryTab
from ui.tab_apps import AppsTab
from ui.tab_org_settings import OrgSettingsTab
from ui.tab_users import UsersTab

APP_VERSION = "v1.3.0"


class Dashboard(ctk.CTkFrame):
    def __init__(self, master, username, role, display_name, on_logout):
        super().__init__(master, fg_color="transparent")
        self.username = username
        self.role = role
        self.display_name = display_name
        self.on_logout = on_logout
        self._build()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top bar
        topbar = ctk.CTkFrame(self, height=56, corner_radius=0)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)

        title_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=20, pady=8, sticky="w")
        ctk.CTkLabel(title_frame, text="IT Provisioning Tool",
                      font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w")

        # Clickable version badge - opens changelog
        ver_btn = ctk.CTkButton(
            title_frame, text=APP_VERSION,
            font=ctk.CTkFont(size=11),
            text_color="#4FC3F7",
            fg_color="transparent",
            hover_color=("#2a2a2a", "#1a1a1a"),
            width=60, height=22,
            command=self._show_changelog)
        ver_btn.grid(row=0, column=1, padx=(6, 0), sticky="w")

        role_badge = "ADMIN" if self.role == "admin" else "USER"
        badge_color = "#4CAF50" if self.role == "admin" else "#2196F3"
        ctk.CTkLabel(topbar,
                      text=f"  {self.display_name}  [{role_badge}]  ",
                      font=ctk.CTkFont(size=12),
                      fg_color=badge_color,
                      corner_radius=6,
                      text_color="white").grid(row=0, column=1, padx=8, sticky="e")

        ctk.CTkButton(topbar, text="Logout", width=80, height=30,
                       fg_color="transparent", border_width=1,
                       command=self.on_logout).grid(
            row=0, column=2, padx=16, pady=10)

        # Tabs
        tabs = ctk.CTkTabview(self)
        tabs.grid(row=1, column=0, padx=12, pady=12, sticky="nsew")

        tab_definitions = [
            ("System", SystemTab),
            ("Debloat", DebloatTab),
            ("Privacy", TelemetryTab),
            ("Apps", AppsTab),
            ("Org Settings", OrgSettingsTab),
            ("Users", UsersTab),
        ]

        admin_only = {"System", "Debloat", "Privacy", "Org Settings", "Users"}

        for tab_name, TabClass in tab_definitions:
            if tab_name in admin_only and self.role != "admin":
                continue
            tab = tabs.add(tab_name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            widget = TabClass(tab, self.role)
            widget.grid(row=0, column=0, sticky="nsew")

    def _show_changelog(self):
        changelog_path = os.path.join(get_base_dir(), "CHANGELOG.md")
        try:
            with open(changelog_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"Could not load CHANGELOG.md\nPath: {changelog_path}\nError: {e}"

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Changelog  {APP_VERSION}")
        dialog.geometry("700x560")
        dialog.resizable(True, True)
        dialog.grid_rowconfigure(0, weight=1)
        dialog.grid_columnconfigure(0, weight=1)
        dialog.after(100, dialog.lift)
        dialog.after(150, dialog.focus_force)

        box = ctk.CTkTextbox(dialog, wrap="word",
                              font=ctk.CTkFont(family="Courier New", size=12))
        box.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="nsew")
        box.insert("1.0", content)
        box.configure(state="disabled")

        ctk.CTkButton(dialog, text="Close", width=100,
                       command=dialog.destroy).grid(row=1, column=0, pady=(0, 16))
