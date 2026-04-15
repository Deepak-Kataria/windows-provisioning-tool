import customtkinter as ctk
from modules.auth import authenticate


class LoginScreen(ctk.CTkFrame):
    def __init__(self, master, on_login_success):
        super().__init__(master, fg_color="transparent")
        self.on_login_success = on_login_success
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # Logo / Title
        ctk.CTkLabel(self, text="IT Provisioning Tool",
                      font=ctk.CTkFont(size=28, weight="bold")).grid(
            row=0, column=0, pady=(60, 4))
        ctk.CTkLabel(self, text="Sign in to continue",
                      font=ctk.CTkFont(size=14),
                      text_color="gray").grid(row=1, column=0, pady=(0, 40))

        # Login card
        card = ctk.CTkFrame(self, width=380, corner_radius=16)
        card.grid(row=2, column=0, padx=40, pady=10, sticky="n")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="Username",
                      font=ctk.CTkFont(size=13)).grid(
            row=0, column=0, sticky="w", padx=30, pady=(30, 4))
        self.username_entry = ctk.CTkEntry(card, width=320, height=40,
                                            placeholder_text="Enter username")
        self.username_entry.grid(row=1, column=0, padx=30, pady=(0, 16))

        ctk.CTkLabel(card, text="Password",
                      font=ctk.CTkFont(size=13)).grid(
            row=2, column=0, sticky="w", padx=30, pady=(0, 4))
        self.password_entry = ctk.CTkEntry(card, width=320, height=40,
                                            placeholder_text="Enter password",
                                            show="*")
        self.password_entry.grid(row=3, column=0, padx=30, pady=(0, 8))

        self.error_label = ctk.CTkLabel(card, text="", text_color="#FF5555",
                                         font=ctk.CTkFont(size=12))
        self.error_label.grid(row=4, column=0, pady=(0, 4))

        login_btn = ctk.CTkButton(card, text="Sign In", width=320, height=44,
                                   font=ctk.CTkFont(size=14, weight="bold"),
                                   command=self._do_login)
        login_btn.grid(row=5, column=0, padx=30, pady=(8, 30))

        self.username_entry.bind("<Return>", lambda e: self._do_login())
        self.password_entry.bind("<Return>", lambda e: self._do_login())

    def _do_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if not username or not password:
            self.error_label.configure(text="Please enter username and password.")
            return

        success, role, display_name = authenticate(username, password)
        if success:
            self.error_label.configure(text="")
            self.on_login_success(username, role, display_name)
        else:
            self.error_label.configure(text="Invalid username or password.")
            self.password_entry.delete(0, "end")
