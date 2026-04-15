import customtkinter as ctk
from ui.tab_system import SystemTab
from ui.tab_debloat import DebloatTab
from ui.tab_telemetry import TelemetryTab
from ui.tab_apps import AppsTab
from ui.tab_org_settings import OrgSettingsTab


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

        ctk.CTkLabel(topbar, text="IT Provisioning Tool",
                      font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=20, pady=14, sticky="w")

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
        ]

        # Admin-only tabs
        admin_only = {"System", "Debloat", "Privacy", "Org Settings"}

        for tab_name, TabClass in tab_definitions:
            if tab_name in admin_only and self.role != "admin":
                continue
            tab = tabs.add(tab_name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            widget = TabClass(tab, self.role)
            widget.grid(row=0, column=0, sticky="nsew")
