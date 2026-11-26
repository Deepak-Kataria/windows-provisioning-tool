import { api, badge, clear, confirmDialog, formDialog, h, me, table, timeEl, toast, toastError } from "/static/app.js";

const ROLES = ["viewer", "technician", "admin"];

async function load() {
  try {
    const users = await api("/api/users");
    clear(document.getElementById("user-table")).append(table([
      { label: "User", render: (u) => h("div", {}, h("b", {}, u.display_name || u.username), h("div", { class: "muted small" }, u.username)) },
      { label: "Role", render: (u) => badge(u.role, "info") },
      {
        label: "Status", render: (u) => h("div", { class: "row" },
          u.is_active ? badge("active", "ok") : badge("disabled", "muted"),
          u.totp_confirmed ? null : badge("no MFA yet", "warn"),
          u.must_change_password ? badge("must change password", "warn") : null,
          u.locked_until && new Date(u.locked_until + "Z") > new Date() ? badge("locked", "fail") : null),
      },
      { label: "Last login", render: (u) => timeEl(u.last_login_at) },
      { label: "", render: (u) => h("div", { class: "row" }, actions(u)) },
    ], users));
  } catch (e) { toastError(e); }
}

function actions(u) {
  const self = u.id === me.id;
  const act = (label, fn) => h("button", { class: "btn small ghost", onclick: fn }, label);
  const out = [act("Edit", () => edit(u)), act("Reset password", () => resetPassword(u))];
  if (!self) {
    out.push(act("Reset MFA", () => simple(u, "reset-mfa", "Reset MFA",
      `${u.username} will have to set up their authenticator again at next login. They are signed out now.`)));
  }
  if (u.locked_until) out.push(act("Unlock", () => simple(u, "unlock")));
  return out;
}

async function simple(u, path, title, message) {
  if (title && !await confirmDialog(title, message, { okText: title })) return;
  try { await api(`/api/users/${u.id}/${path}`, { method: "POST" }); toast("Done", "ok"); load(); }
  catch (e) { toastError(e); }
}

async function edit(u) {
  const v = await formDialog(`Edit ${u.username}`, [
    { name: "display_name", label: "Display name", value: u.display_name, maxlength: 128 },
    { name: "role", label: "Role", type: "select", value: u.role, options: ROLES },
    { name: "is_active", label: "Account active (unticking signs the user out)", type: "checkbox", value: u.is_active },
  ]);
  if (!v) return;
  try { await api(`/api/users/${u.id}`, { method: "PATCH", json: v }); toast("Saved", "ok"); load(); }
  catch (e) { toastError(e); }
}

async function resetPassword(u) {
  const v = await formDialog(`Reset password for ${u.username}`, [
    {
      name: "password", label: "New temporary password", type: "password", required: true, minlength: 12,
      autocomplete: "new-password", help: "12+ characters, upper and lower case, a digit. The user must change it at next login.",
    },
  ], { okText: "Reset" });
  if (!v) return;
  try { await api(`/api/users/${u.id}/password`, { method: "POST", json: v }); toast("Password reset, user signed out", "ok"); load(); }
  catch (e) { toastError(e); }
}

document.getElementById("add-user").addEventListener("click", async () => {
  const v = await formDialog("Add user", [
    { name: "username", label: "Username", required: true, pattern: "[a-zA-Z0-9._\\-]{3,64}", help: "Letters, digits, . _ -" },
    { name: "display_name", label: "Display name", maxlength: 128 },
    { name: "role", label: "Role", type: "select", value: "technician", options: ROLES },
    {
      name: "password", label: "Temporary password", type: "password", required: true, minlength: 12,
      autocomplete: "new-password", help: "Give it to the user privately. They change it and set up MFA at first login.",
    },
  ], { okText: "Create user" });
  if (!v) return;
  try { await api("/api/users", { method: "POST", json: v }); toast(`User ${v.username} created`, "ok"); load(); }
  catch (e) { toastError(e); }
});

load();
