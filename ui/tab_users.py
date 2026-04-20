import customtkinter as ctk
from modules.auth import list_users, add_user, delete_user, change_password


class UsersTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- User List ---
        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=0, column=0, rowspan=2, padx=(20, 10), pady=20, sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(list_frame, text="Users",
                      font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        self.user_scroll = ctk.CTkScrollableFrame(list_frame)
        self.user_scroll.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="nsew")
        self.user_scroll.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(list_frame, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=10, pady=(0, 14), sticky="w")
        ctk.CTkButton(btn_row, text="Reset Password", width=140,
                       command=self._reset_password).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(btn_row, text="Delete User", width=120,
                       fg_color="#E53935", hover_color="#B71C1C",
                       command=self._delete_user).grid(row=0, column=1)

        # --- Add User ---
        add_frame = ctk.CTkFrame(self)
        add_frame.grid(row=0, column=1, padx=(10, 20), pady=20, sticky="new")
        add_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(add_frame, text="Add User",
                      font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 12))

        fields = [
            ("Username", "new_username", False, "e.g. jsmith"),
            ("Display Name", "new_display", False, "e.g. John Smith"),
            ("Password", "new_password", True, "At least 8 characters"),
            ("Confirm Password", "new_confirm", True, "Repeat password"),
        ]
        for i, (label, attr, secret, placeholder) in enumerate(fields):
            ctk.CTkLabel(add_frame, text=label,
                          font=ctk.CTkFont(size=13)).grid(
                row=i * 2 + 1, column=0, sticky="w", padx=16, pady=(0, 2))
            entry = ctk.CTkEntry(add_frame, width=280, height=36,
                                  placeholder_text=placeholder,
                                  show="*" if secret else "")
            entry.grid(row=i * 2 + 2, column=0, padx=16, pady=(0, 10), sticky="w")
            setattr(self, attr, entry)

        ctk.CTkLabel(add_frame, text="Role",
                      font=ctk.CTkFont(size=13)).grid(
            row=9, column=0, sticky="w", padx=16, pady=(0, 2))
        self.role_var = ctk.StringVar(value="user")
        role_menu = ctk.CTkOptionMenu(add_frame, values=["user", "admin"],
                                       variable=self.role_var, width=280)
        role_menu.grid(row=10, column=0, padx=16, pady=(0, 12), sticky="w")

        self.add_error = ctk.CTkLabel(add_frame, text="", text_color="#FF5555",
                                       font=ctk.CTkFont(size=12))
        self.add_error.grid(row=11, column=0, pady=(0, 4))

        ctk.CTkButton(add_frame, text="Add User", width=280, height=40,
                       font=ctk.CTkFont(size=13, weight="bold"),
                       command=self._add_user).grid(row=12, column=0, padx=16, pady=(0, 20))

        # --- Status ---
        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self.status_label.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="w")

        self._refresh_list()

    def _refresh_list(self):
        for w in self.user_scroll.winfo_children():
            w.destroy()
        self.selected_username = None
        self._row_buttons = {}

        for i, user in enumerate(list_users()):
            row = ctk.CTkFrame(self.user_scroll, corner_radius=6)
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            row.grid_columnconfigure(1, weight=1)

            badge_color = "#4CAF50" if user["role"] == "admin" else "#2196F3"
            ctk.CTkLabel(row, text=f"  {user['role'].upper()}  ",
                          fg_color=badge_color, corner_radius=4,
                          font=ctk.CTkFont(size=10), text_color="white").grid(
                row=0, column=0, padx=(8, 6), pady=8)

            ctk.CTkLabel(row, text=f"{user['display_name']}  ({user['username']})",
                          font=ctk.CTkFont(size=13), anchor="w").grid(
                row=0, column=1, sticky="w", pady=8)

            btn = ctk.CTkButton(row, text="Select", width=70, height=28,
                                  fg_color="transparent", border_width=1,
                                  command=lambda u=user["username"]: self._select(u))
            btn.grid(row=0, column=2, padx=8, pady=6)
            self._row_buttons[user["username"]] = (row, btn)

    def _select(self, username):
        self.selected_username = username
        for uname, (row, btn) in self._row_buttons.items():
            if uname == username:
                row.configure(fg_color=("#3a3a3a", "#2a2a2a"))
                btn.configure(text="Selected", fg_color="#4CAF50", border_width=0)
            else:
                row.configure(fg_color="transparent")
                btn.configure(text="Select", fg_color="transparent", border_width=1)

    def _delete_user(self):
        if not self.selected_username:
            self._set_status("Select a user first.", error=True)
            return
        if self.selected_username == "admin":
            self._set_status("Cannot delete the admin account.", error=True)
            return
        delete_user(self.selected_username)
        self._set_status(f"Deleted user: {self.selected_username}")
        self.selected_username = None
        self._refresh_list()

    def _reset_password(self):
        if not self.selected_username:
            self._set_status("Select a user first.", error=True)
            return
        ResetPasswordDialog(self, self.selected_username,
                             on_complete=lambda: self._set_status(
                                 f"Password reset for {self.selected_username}"))

    def _add_user(self):
        username = self.new_username.get().strip()
        display = self.new_display.get().strip()
        password = self.new_password.get()
        confirm = self.new_confirm.get()
        role = self.role_var.get()

        if not username or not display:
            self.add_error.configure(text="Username and display name are required.")
            return
        if len(password) < 8:
            self.add_error.configure(text="Password must be at least 8 characters.")
            return
        if password != confirm:
            self.add_error.configure(text="Passwords do not match.")
            self.new_confirm.delete(0, "end")
            return

        existing = [u["username"] for u in list_users()]
        if username in existing:
            self.add_error.configure(text="Username already exists.")
            return

        add_user(username, password, role, display)
        self.add_error.configure(text="")
        for entry in (self.new_username, self.new_display, self.new_password, self.new_confirm):
            entry.delete(0, "end")
        self._set_status(f"Added user: {username}")
        self._refresh_list()

    def _set_status(self, message, error=False):
        color = "#FF5555" if error else "#4CAF50"
        self.status_label.configure(text=message, text_color=color)
        self.after(4000, lambda: self.status_label.configure(text=""))


class ResetPasswordDialog(ctk.CTkToplevel):
    def __init__(self, master, username: str, on_complete):
        super().__init__(master)
        self.username = username
        self.on_complete = on_complete

        self.title("Reset Password")
        self.geometry("380x280")
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self._center()

    def _center(self):
        self.update_idletasks()
        x = self.master.winfo_rootx() + (self.master.winfo_width() - 380) // 2
        y = self.master.winfo_rooty() + (self.master.winfo_height() - 280) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text=f"Reset password for: {self.username}",
                      font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=24, pady=(24, 16), sticky="w")

        ctk.CTkLabel(self, text="New Password", font=ctk.CTkFont(size=13)).grid(
            row=1, column=0, padx=24, sticky="w")
        self.pw = ctk.CTkEntry(self, width=330, height=38, show="*",
                                placeholder_text="At least 8 characters")
        self.pw.grid(row=2, column=0, padx=24, pady=(4, 10))

        ctk.CTkLabel(self, text="Confirm Password", font=ctk.CTkFont(size=13)).grid(
            row=3, column=0, padx=24, sticky="w")
        self.confirm = ctk.CTkEntry(self, width=330, height=38, show="*",
                                     placeholder_text="Repeat password")
        self.confirm.grid(row=4, column=0, padx=24, pady=(4, 6))

        self.error = ctk.CTkLabel(self, text="", text_color="#FF5555",
                                   font=ctk.CTkFont(size=12))
        self.error.grid(row=5, column=0, pady=(0, 4))

        ctk.CTkButton(self, text="Reset Password", width=330, height=40,
                       font=ctk.CTkFont(size=13, weight="bold"),
                       command=self._submit).grid(row=6, column=0, padx=24, pady=(0, 24))

    def _submit(self):
        pw = self.pw.get()
        confirm = self.confirm.get()
        if len(pw) < 8:
            self.error.configure(text="Password must be at least 8 characters.")
            return
        if pw != confirm:
            self.error.configure(text="Passwords do not match.")
            self.confirm.delete(0, "end")
            return
        change_password(self.username, pw)
        self.grab_release()
        self.destroy()
        self.on_complete()
