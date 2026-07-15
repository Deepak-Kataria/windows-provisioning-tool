import customtkinter as ctk
from ui.cleanup_profiles import ProfilesSection
from ui.cleanup_windows import WindowsCleanupSection
from ui.cleanup_disk import DiskAnalysisSection


class CleanupTab(ctk.CTkFrame):
    """Cleanup Hub: User Profiles, Windows Cleanup, Disk Analysis."""

    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._build()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        tabs = ctk.CTkTabview(self)
        tabs.grid(row=0, column=0, sticky="nsew")

        sections = [
            ("User Profiles", ProfilesSection),
            ("Windows Cleanup", WindowsCleanupSection),
            ("Disk Analysis", DiskAnalysisSection),
        ]

        for name, SectionClass in sections:
            page = tabs.add(name)
            page.grid_rowconfigure(0, weight=1)
            page.grid_columnconfigure(0, weight=1)
            widget = SectionClass(page, self.role)
            widget.grid(row=0, column=0, sticky="nsew")
