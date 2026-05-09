import sys
import os

# .pyd extensions (bcrypt, etc.) cannot load from UNC paths — relaunch from local temp
if getattr(sys, 'frozen', False) and sys.executable.startswith('\\\\'):
    import shutil, subprocess, tempfile
    _src = os.path.dirname(sys.executable)
    _dst = os.path.join(tempfile.gettempdir(), 'IT-Provisioning-Tool-run')
    shutil.copytree(_src, _dst, dirs_exist_ok=True)
    subprocess.Popen([os.path.join(_dst, os.path.basename(sys.executable))])
    sys.exit(0)

# Source mode: self-elevate if not admin (exe handles this via --uac-admin manifest)
if not getattr(sys, 'frozen', False):
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        script = os.path.abspath(sys.argv[0])
        args = ' '.join(f'"{a}"' for a in [script] + sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
        sys.exit(0)

import customtkinter as ctk
from ui.dashboard import Dashboard

# AUTH_ENABLED = False — login bypassed during development.
# To restore: set True and uncomment the login imports below.
AUTH_ENABLED = False
# from ui.login_screen import LoginScreen
# from ui.first_run_dialog import FirstRunDialog
# from modules.auth import is_first_run

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
        self._show_dashboard("admin", "admin", "Administrator")

    def _show_dashboard(self, username, role, display_name):
        self._clear()
        dashboard = Dashboard(self, username, role, display_name,
                               on_logout=self.destroy)
        dashboard.grid(row=0, column=0, sticky="nsew")

    def _clear(self):
        for widget in self.winfo_children():
            widget.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
