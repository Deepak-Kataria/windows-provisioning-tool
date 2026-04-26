import customtkinter as ctk
import json
import os
import threading
from modules.runner import run_powershell
from modules.logger import log

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


class DebloatTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self.checkboxes = {}
        self._running = False
        self._load_config()
        self._build()

    def _load_config(self):
        with open(os.path.join(CONFIG_DIR, "debloat_list.json")) as f:
            self.debloat_data = json.load(f)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Debloat Windows",
                      font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(header, text="Select apps to remove. This cannot be undone easily.",
                      text_color="gray", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")
        ctk.CTkButton(btn_frame, text="Select All", width=110,
                       command=self._select_all).grid(row=0, column=0, padx=4)
        ctk.CTkButton(btn_frame, text="Deselect All", width=110,
                       command=self._deselect_all).grid(row=0, column=1, padx=4)

        # Scrollable app list grouped by category
        scroll = ctk.CTkScrollableFrame(self, height=300)
        scroll.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)
        scroll.grid_columnconfigure(2, weight=1)

        # Group apps by category
        from collections import defaultdict
        grouped = defaultdict(list)
        for app in self.debloat_data["appx_packages"]:
            grouped[app.get("category", "Other")].append(app)

        row = 0
        for category, apps in grouped.items():
            ctk.CTkLabel(scroll, text=category,
                          font=ctk.CTkFont(size=12, weight="bold"),
                          text_color="#4FC3F7").grid(
                row=row, column=0, columnspan=3, sticky="w", padx=8, pady=(10, 2))
            row += 1
            col = 0
            for app in apps:
                var = ctk.BooleanVar(value=True)
                ctk.CTkCheckBox(scroll, text=app["name"], variable=var).grid(
                    row=row, column=col, sticky="w", padx=8, pady=2)
                self.checkboxes[app["package"]] = var
                col += 1
                if col == 3:
                    col = 0
                    row += 1
            if col != 0:
                row += 1

        self.remove_btn = ctk.CTkButton(self, text="Remove Selected Apps",
                                         fg_color="#E53935", hover_color="#B71C1C",
                                         command=self._remove_apps)
        self.remove_btn.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="w")

        # Progress area
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.grid(row=3, column=0, padx=20, pady=(0, 4), sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=14)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(progress_frame, text="", width=140,
                                            font=ctk.CTkFont(size=11), anchor="w")
        self.progress_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        ctk.CTkLabel(self, text="Output",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=4, column=0, padx=20, pady=(8, 4), sticky="w")
        self.output_box = ctk.CTkTextbox(self, height=130, state="disabled")
        self.output_box.grid(row=5, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _select_all(self):
        for var in self.checkboxes.values():
            var.set(True)

    def _deselect_all(self):
        for var in self.checkboxes.values():
            var.set(False)

    def _append_output(self, text):
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _set_progress(self, done, total):
        frac = done / total if total else 0
        self.progress_bar.set(frac)
        self.progress_label.configure(text=f"Processing {done} / {total}")

    def _show_done_dialog(self, removed, not_found, errors, total):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Debloat Complete")
        dialog.geometry("360x200")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()

        ctk.CTkLabel(dialog, text="Debloat Complete",
                      font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(24, 8))

        summary = (
            f"Removed:    {removed}\n"
            f"Not found:  {not_found}\n"
            f"Errors:     {errors}\n"
            f"Total:      {total}"
        )
        ctk.CTkLabel(dialog, text=summary, font=ctk.CTkFont(size=13),
                      justify="left").pack(pady=(0, 16))

        ctk.CTkButton(dialog, text="OK", width=100,
                       command=dialog.destroy).pack()

    def _remove_apps(self):
        if self._running:
            return
        selected = [pkg for pkg, var in self.checkboxes.items() if var.get()]
        if not selected:
            self._append_output("No apps selected.")
            return

        self._running = True
        self.remove_btn.configure(state="disabled", text="Running...")
        self.progress_bar.set(0)
        self.progress_label.configure(text=f"Starting {len(selected)} apps...")
        self._append_output(f"Removing {len(selected)} apps...")
        log(f"Debloat: removing {len(selected)} apps")

        total = len(selected)
        counts = {"removed": 0, "not_found": 0, "errors": 0, "done": 0}

        def on_line(line):
            if line.startswith("REMOVED:"):
                counts["removed"] += 1
                counts["done"] += 1
            elif line.startswith("NOT_FOUND:"):
                counts["not_found"] += 1
                counts["done"] += 1
            elif line.startswith("ERROR:"):
                counts["errors"] += 1
                counts["done"] += 1

            self.after(0, self._append_output, line)
            self.after(0, self._set_progress, counts["done"], total)

        def task():
            rc, _ = run_powershell("debloat.ps1",
                                    ["-Packages", ",".join(selected)],
                                    callback=on_line)
            log(f"Debloat complete. rc={rc} removed={counts['removed']} "
                f"not_found={counts['not_found']} errors={counts['errors']}")

            def finish():
                self.progress_bar.set(1.0)
                self.progress_label.configure(text="Done.")
                self.remove_btn.configure(state="normal", text="Remove Selected Apps")
                self._running = False
                self._show_done_dialog(counts["removed"], counts["not_found"],
                                        counts["errors"], total)

            self.after(0, finish)

        threading.Thread(target=task, daemon=True).start()
