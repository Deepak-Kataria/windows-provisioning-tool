// Login: password -> (MFA code | MFA setup with QR) -> dashboard.
const err = document.getElementById("login-error");
const steps = {
  password: document.getElementById("step-password"),
  mfa: document.getElementById("step-mfa"),
  setup: document.getElementById("step-setup"),
};
let csrf = "";

function show(name) {
  for (const [k, el] of Object.entries(steps)) el.hidden = k !== name;
  steps[name].querySelector("input")?.focus();
}
function fail(msg) { err.textContent = msg; err.hidden = false; }

async function post(url, data) {
  const r = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: data ? JSON.stringify(data) : undefined,
  });
  let d = null;
  try { d = await r.json(); } catch { /* empty */ }
  if (!r.ok) throw new Error(d?.detail && typeof d.detail === "string" ? d.detail : `Error ${r.status}`);
  return d;
}

function busy(form, on) { form.querySelectorAll("button, input").forEach((el) => { el.disabled = on; }); }

async function next(step) {
  if (step === "done") { location.href = "/"; return; }
  if (step === "mfa") { show("mfa"); return; }
  const s = await post("/api/auth/mfa/setup");
  document.getElementById("qr").src = s.qr_svg;
  document.getElementById("secret").textContent = s.secret.replace(/(.{4})/g, "$1 ").trim();
  show("setup");
}

steps.password.addEventListener("submit", async (e) => {
  e.preventDefault();
  err.hidden = true;
  const f = e.target;
  busy(f, true);
  try {
    const r = await post("/api/auth/login", { username: f.username.value.trim(), password: f.password.value });
    csrf = r.csrf_token;
    f.password.value = "";
    await next(r.next);
  } catch (ex) {
    fail(ex.message);
  } finally { busy(f, false); }
});

for (const [name, url] of [["mfa", "/api/auth/mfa"], ["setup", "/api/auth/mfa/confirm"]]) {
  steps[name].addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    const f = e.target;
    busy(f, true);
    try {
      const r = await post(url, { code: f.code.value.replace(/\s/g, "") });
      await next(r.next);
    } catch (ex) {
      f.code.value = "";
      if (ex.message === "Not logged in" || ex.message === "MFA required") { show("password"); fail("Sign-in timed out, start again."); }
      else fail(ex.message);
    } finally { busy(f, false); f.code.focus(); }
  });
}
