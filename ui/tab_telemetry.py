import customtkinter as ctk
import threading
from modules.runner import run_powershell
from modules.logger import log


class TelemetryTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.options = {}
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Disable Telemetry & Tracking",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(header, text="Apply registry and service changes to improve privacy.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 16))

        options_frame = ctk.CTkFrame(self)
        options_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        options_frame.grid_columnconfigure(0, weight=1)

        telemetry_options = [
            ("disable_telemetry", "Disable Windows Telemetry",
             "Sets AllowTelemetry = 0 via registry"),
            ("disable_diagnostics", "Disable Diagnostic Services",
             "Stops and disables DiagTrack and dmwappushservice"),
            ("disable_activity", "Disable Activity History",
             "Disables activity feed and user activity publishing"),
            ("disable_location", "Disable Location Tracking",
             "Prevents Windows from tracking your location"),
            ("disable_adid", "Disable Advertising ID",
             "Stops personalized ads based on app usage"),
            ("disable_feedback", "Disable Feedback Notifications",
             "Removes Windows feedback/survey prompts"),
        ]

        for i, (key, label, desc) in enumerate(telemetry_options):
            var = ctk.BooleanVar(value=True)
            row_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
            row_frame.grid(row=i, column=0, sticky="ew", padx=10, pady=4)
            row_frame.grid_columnconfigure(1, weight=1)
            ctk.CTkCheckBox(row_frame, text=label, variable=var, width=240).grid(
                row=0, column=0, sticky="w")
            ctk.CTkLabel(row_frame, text=desc, text_color="gray",
                          font=ctk.CTkFont(size=11)).grid(
                row=0, column=1, sticky="w", padx=16)
            self.options[key] = var

        apply_btn = ctk.CTkButton(self, text="Apply Privacy Settings",
                                   command=self._apply)
        apply_btn.grid(row=2, column=0, padx=20, pady=(8, 4), sticky="w")

        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=3, column=0, padx=20, pady=(12, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=140, state="disabled")
        self.output_box.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _append_output(self, text):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _apply(self):
        self._append_output("Applying privacy settings...")
        log("Applying telemetry/privacy settings")

        args = []
        mapping = {
            "disable_telemetry": "-DisableTelemetry",
            "disable_diagnostics": "-DisableDiagnostics",
            "disable_activity": "-DisableActivityHistory",
            "disable_location": "-DisableLocationTracking",
            "disable_adid": "-DisableAdvertisingId",
            "disable_feedback": "-DisableFeedback",
        }

        for key, flag in mapping.items():
            val = "$true" if self.options[key].get() else "$false"
            args.extend([flag, val])

        def task():
            rc, out = run_powershell("disable_telemetry.ps1", args,
                                      callback=self._append_output)
            log(f"Telemetry settings applied. Return code: {rc}")

        threading.Thread(target=task, daemon=True).start()
