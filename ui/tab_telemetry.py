import customtkinter as ctk
import threading
from modules.runner import run_powershell
from modules.logger import log

TELEMETRY_OPTIONS = [
    ("disable_telemetry",   "Disable Windows Telemetry",      "Re-enable Windows Telemetry",
     "Sets AllowTelemetry = 0 via registry",                   "-DisableTelemetry"),
    ("disable_diagnostics", "Disable Diagnostic Services",     "Re-enable Diagnostic Services",
     "Stops and disables DiagTrack and dmwappushservice",       "-DisableDiagnostics"),
    ("disable_activity",    "Disable Activity History",        "Re-enable Activity History",
     "Disables activity feed and user activity publishing",     "-DisableActivityHistory"),
    ("disable_location",    "Disable Location Tracking",       "Re-enable Location Tracking",
     "Prevents Windows from tracking your location",           "-DisableLocationTracking"),
    ("disable_adid",        "Disable Advertising ID",          "Re-enable Advertising ID",
     "Stops personalized ads based on app usage",              "-DisableAdvertisingId"),
    ("disable_feedback",    "Disable Feedback Notifications",  "Re-enable Feedback Notifications",
     "Removes Windows feedback/survey prompts",                 "-DisableFeedback"),
]


class TelemetryTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.apply_vars = {}
        self.rollback_vars = {}
        self._running = False
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # ── Apply section ──────────────────────────────────────────
        apply_card = ctk.CTkFrame(self)
        apply_card.grid(row=0, column=0, padx=20, pady=(20, 6), sticky="ew")
        apply_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(apply_card, text="Disable Telemetry & Tracking",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(apply_card, text="Apply registry and service changes to improve privacy.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        options_frame = ctk.CTkFrame(apply_card, fg_color="transparent")
        options_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        options_frame.grid_columnconfigure(0, weight=1)

        for i, (key, label, _, desc, _flag) in enumerate(TELEMETRY_OPTIONS):
            var = ctk.BooleanVar(value=True)
            row_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
            row_frame.grid(row=i, column=0, sticky="ew", padx=10, pady=3)
            row_frame.grid_columnconfigure(1, weight=1)
            ctk.CTkCheckBox(row_frame, text=label, variable=var, width=240).grid(
                row=0, column=0, sticky="w")
            ctk.CTkLabel(row_frame, text=desc, text_color="gray",
                          font=ctk.CTkFont(size=11)).grid(
                row=0, column=1, sticky="w", padx=16)
            self.apply_vars[key] = var

        self.apply_btn = ctk.CTkButton(apply_card, text="Apply Privacy Settings",
                                        command=self._apply)
        self.apply_btn.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="w")

        # Progress
        prog_frame = ctk.CTkFrame(apply_card, fg_color="transparent")
        prog_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        prog_frame.grid_columnconfigure(0, weight=1)
        self.apply_bar = ctk.CTkProgressBar(prog_frame, height=14)
        self.apply_bar.grid(row=0, column=0, sticky="ew")
        self.apply_bar.set(0)
        self.apply_status = ctk.CTkLabel(prog_frame, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.apply_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # ── Rollback section ───────────────────────────────────────
        rollback_card = ctk.CTkFrame(self)
        rollback_card.grid(row=1, column=0, padx=20, pady=(6, 6), sticky="ew")
        rollback_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(rollback_card, text="Rollback / Restore Settings",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(14, 4))
        ctk.CTkLabel(rollback_card, text="Select individual settings to re-enable.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        rb_options_frame = ctk.CTkFrame(rollback_card, fg_color="transparent")
        rb_options_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        rb_options_frame.grid_columnconfigure(0, weight=1)

        for i, (key, _label, rb_label, _desc, _flag) in enumerate(TELEMETRY_OPTIONS):
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(rb_options_frame, text=rb_label, variable=var).grid(
                row=i, column=0, sticky="w", padx=10, pady=3)
            self.rollback_vars[key] = var

        rb_btn_row = ctk.CTkFrame(rollback_card, fg_color="transparent")
        rb_btn_row.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="w")
        self.rollback_btn = ctk.CTkButton(rb_btn_row, text="Restore Selected",
                                           fg_color="#FF8F00", hover_color="#E65100",
                                           command=self._rollback)
        self.rollback_btn.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(rb_btn_row, text="Select All", width=90,
                       command=lambda: [v.set(True) for v in self.rollback_vars.values()]).grid(
            row=0, column=1, padx=4)
        ctk.CTkButton(rb_btn_row, text="Deselect All", width=90,
                       command=lambda: [v.set(False) for v in self.rollback_vars.values()]).grid(
            row=0, column=2, padx=4)

        # Progress for rollback
        rb_prog_frame = ctk.CTkFrame(rollback_card, fg_color="transparent")
        rb_prog_frame.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        rb_prog_frame.grid_columnconfigure(0, weight=1)
        self.rollback_bar = ctk.CTkProgressBar(rb_prog_frame, height=14)
        self.rollback_bar.grid(row=0, column=0, sticky="ew")
        self.rollback_bar.set(0)
        self.rollback_status = ctk.CTkLabel(rb_prog_frame, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.rollback_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # ── Output ─────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=2, column=0, padx=20, pady=(8, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=110, state="disabled")
        self.output_box.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")

    # ── Helpers ────────────────────────────────────────────────────

    def _append_output(self, text):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _show_done_dialog(self, title, body):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("340x160")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        ctk.CTkLabel(dialog, text=title,
                      font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(22, 8))
        ctk.CTkLabel(dialog, text=body, font=ctk.CTkFont(size=13)).pack(pady=(0, 14))
        ctk.CTkButton(dialog, text="OK", width=90, command=dialog.destroy).pack()

    def _build_args(self, var_dict, mode):
        flag_map = {opt[0]: opt[4] for opt in TELEMETRY_OPTIONS}
        args = ["-Mode", mode]
        for key, flag in flag_map.items():
            val = "1" if var_dict[key].get() else "0"
            args.extend([flag, val])
        return args

    def _run_task(self, mode, var_dict, bar, status_label, apply_btn, rollback_btn):
        selected_count = sum(1 for v in var_dict.values() if v.get())
        if selected_count == 0:
            self._append_output("Nothing selected.")
            return

        self._running = True
        apply_btn.configure(state="disabled")
        rollback_btn.configure(state="disabled")
        bar.set(0)
        status_label.configure(text=f"Starting {selected_count} settings...")
        self._append_output(f"{'Applying' if mode == 'disable' else 'Restoring'} {selected_count} settings...")
        log(f"Telemetry mode={mode} count={selected_count}")

        args = self._build_args(var_dict, mode)
        done = [0]

        def on_line(line):
            if line.startswith("DONE:"):
                done[0] += 1
                frac = done[0] / selected_count
                self.after(0, bar.set, frac)
                _t = f"Done {done[0]} / {selected_count}"
                self.after(0, lambda t=_t: status_label.configure(text=t))
            self.after(0, self._append_output, line)

        def task():
            rc, _ = run_powershell("disable_telemetry.ps1", args, callback=on_line)
            log(f"Telemetry mode={mode} rc={rc}")

            def finish():
                bar.set(1.0)
                status_label.configure(text="Complete.")
                apply_btn.configure(state="normal")
                rollback_btn.configure(state="normal")
                self._running = False
                verb = "applied" if mode == "disable" else "restored"
                self._show_done_dialog(
                    "Complete",
                    f"{done[0]} of {selected_count} settings {verb}."
                )
            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _apply(self):
        if self._running:
            return
        self._run_task("disable", self.apply_vars,
                        self.apply_bar, self.apply_status,
                        self.apply_btn, self.rollback_btn)

    def _rollback(self):
        if self._running:
            return
        self._run_task("restore", self.rollback_vars,
                        self.rollback_bar, self.rollback_status,
                        self.apply_btn, self.rollback_btn)
