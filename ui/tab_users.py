"""Users — accounts that can sign in to this tool."""
import customtkinter as ctk

from modules.auth import add_user, change_password, delete_user, list_users
from ui import theme as T
from ui.widgets import confirm_run, section_header, tile_row, tip

_COLS = (36, 150, 190, 64, 96)   # avatar, username, display name, role, created (px, unscaled)
MIN_PASSWORD = 8


class UsersTab(ctk.CTkFrame):
    def __init__(self, master, role):
        super().__init__(master, fg_color="transparent")
        self.role = role
        self._me = None   # signed-in username, from the dashboard
        self._build()

    def attach_shell(self, shell):
        self._me = shell.username
        self._refresh_list()

    # ── Build ──────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._tiles_host = ctk.CTkFrame(self, fg_color="transparent")
        self._tiles_host.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self._tiles_host.grid_columnconfigure(0, weight=1)

        # Accounts table
        hdr, col = section_header(self, "Accounts")
        hdr.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self._count_lbl = ctk.CTkLabel(hdr, text="", font=T.mono(11), text_color=T.MUTED)
        self._count_lbl.grid(row=0, column=col, padx=4, sticky="w")

        table = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0)
        table.grid(row=2, column=0, sticky="nsew", padx=(0, 6))
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        self._rows = ctk.CTkScrollableFrame(table, fg_color="transparent", corner_radius=0)
        self._rows.grid(row=0, column=0, sticky="nsew")
        self._rows.grid_columnconfigure(0, weight=1)

        self._build_add_form()

        self._status = ctk.CTkLabel(self, text="", font=T.ui(12), anchor="w")
        self._status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self._refresh_list()

    @staticmethod
    def _layout_cols(frame):
        # grid minsize is in raw pixels while CTk widget sizes are DPI-scaled, so scale it too
        scale = ctk.ScalingTracker.get_widget_scaling(frame)
        for i, w in enumerate(_COLS):
            frame.grid_columnconfigure(i, minsize=round(w * scale))
        frame.grid_columnconfigure(len(_COLS), weight=1)   # actions column stretches

    def _build_add_form(self):
        hdr, _ = section_header(self, "Add user")
        hdr.grid(row=1, column=1, sticky="ew", padx=(6, 0))
        card = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0)
        card.grid(row=2, column=1, sticky="new", padx=(6, 0))
        card.grid_columnconfigure(1, weight=1)

        fields = [("USERNAME", "new_username", False, "e.g. jsmith"),
                  ("DISPLAY NAME", "new_display", False, "e.g. John Smith"),
                  ("PASSWORD", "new_password", True, f"at least {MIN_PASSWORD} characters"),
                  ("CONFIRM", "new_confirm", True, "repeat password")]
        for i, (label, attr, secret, ph) in enumerate(fields):
            ctk.CTkLabel(card, text=label, font=T.mono(10), text_color=T.MUTED, width=100,
                         anchor="w").grid(row=i, column=0, sticky="w", padx=(14, 6),
                                          pady=(14 if i == 0 else 4, 4))
            entry = ctk.CTkEntry(card, height=30, placeholder_text=ph, show="*" if secret else "")
            entry.grid(row=i, column=1, sticky="ew", padx=(0, 14), pady=(14 if i == 0 else 4, 4))
            entry.bind("<Return>", lambda e: self._add_user())
            setattr(self, attr, entry)

        ctk.CTkLabel(card, text="ROLE", font=T.mono(10), text_color=T.MUTED, anchor="w").grid(
            row=4, column=0, sticky="w", padx=(14, 6), pady=4)
        self.role_var = ctk.StringVar(value="User")
        ctk.CTkSegmentedButton(card, values=["User", "Admin"], variable=self.role_var,
                               command=lambda v: self._role_hint()).grid(
            row=4, column=1, sticky="w", pady=4)
        self._hint = ctk.CTkLabel(card, text="", font=T.ui(11), text_color=T.MUTED, anchor="w",
                                  justify="left", wraplength=300)
        self._hint.grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 0))
        self._role_hint()

        self.add_error = ctk.CTkLabel(card, text="", text_color=T.FAIL, font=T.ui(12), anchor="w")
        self.add_error.grid(row=6, column=0, columnspan=2, sticky="w", padx=14)
        ctk.CTkButton(card, text="Add user", width=120, command=self._add_user).grid(
            row=7, column=1, sticky="e", padx=14, pady=(4, 14))

    def _role_hint(self):
        self._hint.configure(text="Admins see every page and can manage accounts."
                             if self.role_var.get() == "Admin"
                             else "Users can only see the Apps page.")

    # ── List ───────────────────────────────────────────────────────

    def _refresh_list(self):
        for w in self._rows.winfo_children():
            w.destroy()
        users = list_users()
        admins = sum(1 for u in users if u["role"] == "admin")

        for w in self._tiles_host.winfo_children():
            w.destroy()
        row, _ = tile_row(self._tiles_host, [
            ("Accounts", len(users), T.ACCENT, "can sign in to this tool"),
            ("Admins", admins, T.OK, "full access"),
            ("Users", len(users) - admins, T.INFO, "Apps page only"),
        ])
        row.grid(row=0, column=0, sticky="ew")
        self._count_lbl.configure(text=f"[{len(users)}]")

        # Column headings live in the same scroll frame as the rows so the columns line up.
        head = ctk.CTkFrame(self._rows, fg_color=T.PANEL_2, corner_radius=0, height=26)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_propagate(False)
        head.grid_rowconfigure(0, weight=1)
        self._layout_cols(head)
        for i, text in enumerate(["", "USERNAME", "DISPLAY NAME", "ROLE", "CREATED"]):
            ctk.CTkLabel(head, text=text, font=T.mono(9, "bold"), text_color=T.DIM,
                         anchor="w").grid(row=0, column=i, sticky="w")

        for i, user in enumerate(users):
            self._add_row(i, user, admins)

    def _add_row(self, i, user, admins):
        uname, is_admin = user["username"], user["role"] == "admin"
        r = ctk.CTkFrame(self._rows, fg_color=T.PANEL if i % 2 == 0 else T.PANEL_2,
                         corner_radius=0, height=38)
        r.grid(row=i + 1, column=0, sticky="ew")
        r.grid_propagate(False)
        r.grid_rowconfigure(0, weight=1)
        self._layout_cols(r)

        initials = "".join(p[0] for p in user["display_name"].split()[:2]).upper() or uname[:2].upper()
        ctk.CTkLabel(r, text=initials, width=26, height=26, corner_radius=13, fg_color=T.ACCENT_DIM,
                     text_color=T.ACCENT, font=T.mono(10, "bold")).grid(row=0, column=0, padx=(10, 0))

        name = ctk.CTkFrame(r, fg_color="transparent")
        name.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(name, text=uname, font=T.mono(12), text_color=T.TEXT_BRIGHT).grid(row=0, column=0)
        me = uname == self._me
        if me:
            ctk.CTkLabel(name, text=" YOU ", font=T.mono(9, "bold"), text_color=T.ACCENT,
                         fg_color=T.ACCENT_DIM, corner_radius=3, height=16).grid(row=0, column=1, padx=6)

        ctk.CTkLabel(r, text=user["display_name"], font=T.ui(12), anchor="w").grid(
            row=0, column=2, sticky="w")
        ctk.CTkLabel(r, text="ADMIN" if is_admin else "USER", font=T.mono(10, "bold"),
                     text_color=T.OK if is_admin else T.INFO).grid(row=0, column=3, sticky="w")
        ctk.CTkLabel(r, text=user.get("created") or "—", font=T.mono(11), text_color=T.MUTED).grid(
            row=0, column=4, sticky="w")

        acts = ctk.CTkFrame(r, fg_color="transparent")
        acts.grid(row=0, column=5, sticky="e", padx=10)
        tip(T.outline_button(acts, text="Reset password", width=110, height=24,
                             command=lambda u=uname: self._reset_password(u)),
            f"Set a new password for {uname}").grid(row=0, column=0)
        last_admin = is_admin and admins <= 1
        if not me and not last_admin:
            tip(T.outline_button(acts, text="Delete", width=64, height=24, text_color=T.FAIL,
                                 command=lambda u=user: self._delete_user(u)),
                f"Remove {uname} (asks first)").grid(row=0, column=1, padx=(6, 0))
        else:
            ctk.CTkLabel(acts, text="", width=70).grid(row=0, column=1)

    # ── Actions ────────────────────────────────────────────────────

    def _delete_user(self, user):
        uname = user["username"]
        if not confirm_run(self, "Delete user", "This account will no longer be able to sign in:",
                           [f"{uname}  ({user['display_name']}, {user['role']})"],
                           action_text="Delete user", danger=True):
            return
        delete_user(uname)
        self._set_status(f"Deleted user: {uname}")
        self._refresh_list()

    def _reset_password(self, username):
        ResetPasswordDialog(self, username,
                            on_complete=lambda: self._set_status(f"Password reset for {username}"))

    def _add_user(self):
        username = self.new_username.get().strip()
        display = self.new_display.get().strip()
        password = self.new_password.get()
        confirm = self.new_confirm.get()
        role = self.role_var.get().lower()

        if not username or not display:
            self.add_error.configure(text="Username and display name are required.")
            return
        if len(password) < MIN_PASSWORD:
            self.add_error.configure(text=f"Password must be at least {MIN_PASSWORD} characters.")
            return
        if password != confirm:
            self.add_error.configure(text="Passwords do not match.")
            self.new_confirm.delete(0, "end")
            return
        if username in {u["username"] for u in list_users()}:
            self.add_error.configure(text="Username already exists.")
            return

        add_user(username, password, role, display)
        self.add_error.configure(text="")
        for entry in (self.new_username, self.new_display, self.new_password, self.new_confirm):
            entry.delete(0, "end")
        self._set_status(f"Added user: {username}")
        self._refresh_list()

    def _set_status(self, message, error=False):
        self._status.configure(text=message, text_color=T.FAIL if error else T.OK)
        self.after(4000, lambda: self._status.winfo_exists() and self._status.configure(text=""))


class ResetPasswordDialog(ctk.CTkToplevel):
    def __init__(self, master, username: str, on_complete):
        super().__init__(master)
        self.username = username
        self.on_complete = on_complete
        self.title("Reset password")
        self.geometry("380x250")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self._build()
        self._center()
        self.after(60, lambda: self.winfo_exists() and self.grab_set())
        self.after(80, lambda: self.winfo_exists() and self.pw.focus_set())

    def _center(self):
        self.update_idletasks()
        x = self.master.winfo_rootx() + (self.master.winfo_width() - 380) // 2
        y = self.master.winfo_rooty() + (self.master.winfo_height() - 250) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=f"▸  RESET PASSWORD · {self.username}", font=T.mono(13, "bold"),
                     text_color=T.ACCENT, anchor="w").grid(row=0, column=0, columnspan=2, padx=20,
                                                           pady=(20, 14), sticky="w")
        self.pw = self._field(1, "NEW", f"at least {MIN_PASSWORD} characters")
        self.confirm = self._field(2, "CONFIRM", "repeat password")
        self.error = ctk.CTkLabel(self, text="", text_color=T.FAIL, font=T.ui(12))
        self.error.grid(row=3, column=0, columnspan=2, padx=20, sticky="w")
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=4, column=0, columnspan=2, padx=20, pady=(6, 18), sticky="e")
        T.outline_button(btns, text="Cancel", width=90, command=self._close).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(btns, text="Reset password", width=130, command=self._submit).grid(row=0, column=1)
        self.bind("<Return>", lambda e: self._submit())
        self.bind("<Escape>", lambda e: self._close())

    def _field(self, row, label, ph):
        ctk.CTkLabel(self, text=label, font=T.mono(10), text_color=T.MUTED, width=80, anchor="w").grid(
            row=row, column=0, padx=(20, 6), pady=4, sticky="w")
        e = ctk.CTkEntry(self, height=30, show="*", placeholder_text=ph)
        e.grid(row=row, column=1, padx=(0, 20), pady=4, sticky="ew")
        return e

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _submit(self):
        pw, confirm = self.pw.get(), self.confirm.get()
        if len(pw) < MIN_PASSWORD:
            self.error.configure(text=f"Password must be at least {MIN_PASSWORD} characters.")
            return
        if pw != confirm:
            self.error.configure(text="Passwords do not match.")
            self.confirm.delete(0, "end")
            return
        change_password(self.username, pw)
        self._close()
        self.on_complete()
