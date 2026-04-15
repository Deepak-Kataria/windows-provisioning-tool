import customtkinter as ctk
from ui.login_screen import LoginScreen
from ui.dashboard import Dashboard

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("IT Provisioning Tool")
        self.geometry("1000x700")
        self.minsize(860, 600)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._show_login()

    def _show_login(self):
        self._clear()
        login = LoginScreen(self, on_login_success=self._on_login)
        login.grid(row=0, column=0, sticky="nsew")

    def _on_login(self, username, role, display_name):
        self._clear()
        dashboard = Dashboard(self, username, role, display_name,
                               on_logout=self._show_login)
        dashboard.grid(row=0, column=0, sticky="nsew")

    def _clear(self):
        for widget in self.winfo_children():
            widget.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
