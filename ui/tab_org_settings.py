import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_powershell
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class OrgSettingsTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.apply_checkboxes = {}
        self.rollback_checkboxes = {}
        self._running = False
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "org_settings.json")) as f:
            self.settings_data = json.load(f)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # ── Apply section ──────────────────────────────────────────
        apply_card = ctk.CTkFrame(self)
        apply_card.grid(row=0, column=0, padx=20, pady=(20, 6), sticky="ew")
        apply_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(apply_card, text="Org Settings",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(apply_card, text="Apply organisation-standard Windows configuration.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        apply_scroll = ctk.CTkScrollableFrame(apply_card, height=200)
        apply_scroll.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")
        apply_scroll.grid_columnconfigure(0, weight=1)
        apply_scroll.grid_columnconfigure(1, weight=2)

        for i, tweak in enumerate(self.settings_data["registry_tweaks"]):
            var = ctk.BooleanVar(value=True)
            row_frame = ctk.CTkFrame(apply_scroll, fg_color="transparent")
            row_frame.grid(row=i, column=0, columnspan=2, sticky="ew", pady=3, padx=4)
            row_frame.grid_columnconfigure(1, weight=1)
            ctk.CTkCheckBox(row_frame, text=tweak["name"], variable=var, width=220).grid(
                row=0, column=0, sticky="w")
            ctk.CTkLabel(row_frame, text=tweak["description"], text_color="gray",
                          font=ctk.CTkFont(size=11), wraplength=300).grid(
                row=0, column=1, sticky="w", padx=12)
            self.apply_checkboxes[i] = (var, tweak)

        self.apply_btn = ctk.CTkButton(apply_card, text="Apply Selected Settings",
                                        command=self._apply)
        self.apply_btn.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="w")

        apply_prog = ctk.CTkFrame(apply_card, fg_color="transparent")
        apply_prog.grid(row=4, column=0, padx=20, pady=(0, 12), sticky="ew")
        apply_prog.grid_columnconfigure(0, weight=1)
        self.apply_bar = ctk.CTkProgressBar(apply_prog, height=14)
        self.apply_bar.grid(row=0, column=0, sticky="ew")
        self.apply_bar.set(0)
        self.apply_status = ctk.CTkLabel(apply_prog, text="", font=ctk.CTkFont(size=11), anchor="w")
        self.apply_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # ── Rollback section ───────────────────────────────────────
        rollback_card = ctk.CTkFrame(self)
        rollback_card.grid(row=1, column=0, padx=20, pady=(0, 6), sticky="ew")
        rollback_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(rollback_card, text="Rollback / Restore Settings",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(14, 4))
        ctk.CTkLabel(rollback_card, text="Restore selected settings to Windows defaults.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        rb_scroll = ctk.CTkScrollableFrame(rollback_card, height=160)
        rb_scroll.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")
        rb_scroll.grid_columnconfigure(0, weight=1)

        for i, tweak in enumerate(self.settings_data["registry_tweaks"]):
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(rb_scroll, text=f"Restore: {tweak['name']}", variable=var).grid(
                row=i, column=0, sticky="w", padx=10, pady=3)
            self.rollback_checkboxes[i] = (var, tweak)

        rb_btn_row = ctk.CTkFrame(rollback_card, fg_color="transparent")
        rb_btn_row.grid(row=3, column=0, padx=20, pady=(0, 8), sticky="w")

        self.rollback_btn = ctk.CTkButton(rb_btn_row, text="Restore Selected",
                                           fg_color="#FF8F00", hover_color="#E65100",
                                           command=self._rollback)
        self.rollback_btn.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(rb_btn_row, text="Select All", width=90,
                       command=lambda: [v.set(True) for v, _ in self.rollback_checkboxes.values()]).grid(
            row=0, column=1, padx=4)
        ctk.CTkButton(rb_btn_row, text="Deselect All", width=90,
                       command=lambda: [v.set(False) for v, _ in self.rollback_checkboxes.values()]).grid(
            row=0, column=2, padx=4)

        rb_prog = ctk.CTkFrame(rollback_card, fg_color="transparent")
        rb_prog.grid(row=4, column=0, padx=20, pady=(0, 12), sticky="ew")
        rb_prog.grid_columnconfigure(0, weight=1)
        self.rollback_bar = ctk.CTkProgressBar(rb_prog, height=14)
        self.rollback_bar.grid(row=0, column=0, sticky="ew")
        self.rollback_bar.set(0)
        self.rollback_status = ctk.CTkLabel(rb_prog, text="", font=ctk.CTkFont(size=11), anchor="w")
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

    def _show_done_dialog(self, done, errors, total, verb):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Complete")
        dialog.geometry("320x165")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        ctk.CTkLabel(dialog, text="Complete",
                      font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(22, 8))
        ctk.CTkLabel(dialog, text=f"{done} {verb}, {errors} errors, {total} total.",
                      font=ctk.CTkFont(size=13)).pack(pady=(0, 14))
        ctk.CTkButton(dialog, text="OK", width=90, command=dialog.destroy).pack()

    def _run_task(self, mode, checkbox_dict, bar, status_label, verb):
        selected = [tweak for _, (var, tweak) in checkbox_dict.items() if var.get()]
        if not selected:
            self._append_output("Nothing selected.")
            return

        self._running = True
        self.apply_btn.configure(state="disabled")
        self.rollback_btn.configure(state="disabled")
        total = len(selected)
        bar.set(0)
        status_label.configure(text=f"Starting {total} settings...")
        self._append_output(f"{verb.capitalize()} {total} setting(s)...")
        log(f"OrgSettings mode={mode} count={total}")

        settings_json = json.dumps(selected)
        done = [0]
        errors = [0]

        def on_line(line):
            if line.startswith("APPLIED:") or line.startswith("RESTORED:"):
                done[0] += 1
                self.after(0, bar.set, done[0] / total)
                _t = f"Done {done[0]} / {total}"
                self.after(0, lambda t=_t: status_label.configure(text=t))
            elif line.startswith("ERROR:"):
                errors[0] += 1
                done[0] += 1
                self.after(0, bar.set, done[0] / total)
            self.after(0, self._append_output, line)


        def task():
            rc, _ = run_powershell("apply_org_settings.ps1",
                                    ["-SettingsJson", settings_json, "-Mode", mode],
                                    callback=on_line)
            log(f"OrgSettings mode={mode} rc={rc}")

            def finish():
                bar.set(1.0)
                status_label.configure(text="Complete.")
                self.apply_btn.configure(state="normal")
                self.rollback_btn.configure(state="normal")
                self._running = False
                self._show_done_dialog(done[0] - errors[0], errors[0], total, verb)

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def _apply(self):
        if self._running:
            return
        self._run_task("apply", self.apply_checkboxes, self.apply_bar, self.apply_status, "applied")

    def _rollback(self):
        if self._running:
            return
        self._run_task("restore", self.rollback_checkboxes, self.rollback_bar, self.rollback_status, "restored")
