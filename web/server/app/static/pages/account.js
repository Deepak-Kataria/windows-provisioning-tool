import { api, toast, toastError } from "/static/app.js";

const form = document.getElementById("pw-form");
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (form.new_password.value !== form.repeat.value) { toastError("New passwords do not match"); return; }
  try {
    await api("/api/auth/password", {
      method: "POST",
      json: { current_password: form.current_password.value, new_password: form.new_password.value },
    });
    toast("Password changed. Other sessions were signed out.", "ok");
    form.reset();
    setTimeout(() => { location.href = "/"; }, 1200);
  } catch (err) { toastError(err); }
});
