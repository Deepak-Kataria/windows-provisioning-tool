import customtkinter as ctk
from modules.auth import change_password


class FirstRunDialog(ctk.CTkToplevel):
    """Mandatory password-change dialog shown on first login. Cannot be dismissed."""

    def __init__(self, master, username: str, on_complete):
        super().__init__(master)
        self.username = username
        self.on_complete = on_complete

        self.title("Set Your Password")
        self.geometry("420x380")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # block close button

        self._build()
        self._center()

    def _center(self):
        self.update_idletasks()
        x = self.master.winfo_x() + (self.master.winfo_width() - 420) // 2
        y = self.master.winfo_y() + (self.master.winfo_height() - 380) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Welcome — First Login",
                      font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(30, 4), sticky="w")

        ctk.CTkLabel(self,
                      text="You must set a new password before continuing.\nThis dialog cannot be skipped.",
                      text_color="gray", font=ctk.CTkFont(size=12),
                      justify="left").grid(
            row=1, column=0, padx=30, pady=(0, 24), sticky="w")

        ctk.CTkLabel(self, text="New Password",
                      font=ctk.CTkFont(size=13)).grid(
            row=2, column=0, padx=30, pady=(0, 4), sticky="w")
        self.new_pw = ctk.CTkEntry(self, width=360, height=40,
                                    placeholder_text="At least 8 characters",
                                    show="*")
        self.new_pw.grid(row=3, column=0, padx=30, pady=(0, 14))

        ctk.CTkLabel(self, text="Confirm Password",
                      font=ctk.CTkFont(size=13)).grid(
            row=4, column=0, padx=30, pady=(0, 4), sticky="w")
        self.confirm_pw = ctk.CTkEntry(self, width=360, height=40,
                                        placeholder_text="Repeat password",
                                        show="*")
        self.confirm_pw.grid(row=5, column=0, padx=30, pady=(0, 8))

        self.error_label = ctk.CTkLabel(self, text="", text_color="#FF5555",
                                         font=ctk.CTkFont(size=12))
        self.error_label.grid(row=6, column=0, pady=(0, 4))

        ctk.CTkButton(self, text="Set Password & Continue", width=360, height=44,
                       font=ctk.CTkFont(size=14, weight="bold"),
                       command=self._submit).grid(row=7, column=0, padx=30, pady=(4, 30))

        self.new_pw.bind("<Return>", lambda e: self._submit())
        self.confirm_pw.bind("<Return>", lambda e: self._submit())

    def _submit(self):
        pw = self.new_pw.get()
        confirm = self.confirm_pw.get()

        if len(pw) < 8:
            self.error_label.configure(text="Password must be at least 8 characters.")
            return
        if pw != confirm:
            self.error_label.configure(text="Passwords do not match.")
            self.confirm_pw.delete(0, "end")
            return

        change_password(self.username, pw)
        self.grab_release()
        self.destroy()
        self.on_complete()
