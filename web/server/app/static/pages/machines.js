import { api, badge, can, clear, confirmDialog, dialog, fmtTime, formDialog, h, table, timeEl, toast, toastError } from "/static/app.js";

const q = document.getElementById("q");
const online = document.getElementById("online");
const revoked = document.getElementById("revoked");
let timer;

async function loadMachines() {
  try {
    const rows = await api("/api/machines", {
      query: { q: q.value.trim(), online: online.value, include_revoked: revoked.checked || undefined, limit: 1000 },
    });
    document.getElementById("count").textContent = `${rows.length} machine${rows.length === 1 ? "" : "s"}`;
    clear(document.getElementById("machine-table")).append(table([
      { label: "Status", render: (m) => m.revoked_at ? badge("revoked") : h("span", {}, h("span", { class: `dot ${m.online ? "on" : ""}` }), m.online ? "online" : "offline") },
      { label: "Hostname", render: (m) => h("a", { href: `/machines/${m.id}` }, m.hostname) },
      { label: "Label", key: "label" },
      { label: "Windows", render: (m) => [m.os_info?.release, m.os_info?.version].filter(Boolean).join(" ") || "-" },
      { label: "Agent", key: "agent_version" },
      { label: "Last IP", render: (m) => h("span", { class: "mono" }, m.last_ip || "-") },
      { label: "Last seen", render: (m) => m.online ? "now" : timeEl(m.last_seen_at) },
    ], rows, {
      empty: q.value || online.value ? "No machines match." : "No machines yet. Use 'Add machine' to enroll the first PC.",
      onRow: (m) => { location.href = `/machines/${m.id}`; },
    }));
  } catch (e) { toastError(e); }
}

async function loadCodes() {
  const box = document.getElementById("codes");
  if (!box) return;
  try {
    const codes = await api("/api/enrollment-codes");
    clear(box).append(table([
      { label: "Label", render: (c) => c.label || h("span", { class: "muted" }, "(none)") },
      { label: "Created", render: (c) => timeEl(c.created_at) },
      { label: "Expires", render: (c) => fmtTime(c.expires_at) },
      {
        label: "", render: (c) => h("button", {
          class: "btn small ghost",
          onclick: async () => {
            if (!await confirmDialog("Delete code", "The code will stop working. Continue?", { okText: "Delete", danger: true })) return;
            try { await api(`/api/enrollment-codes/${c.id}`, { method: "DELETE" }); loadCodes(); } catch (e) { toastError(e); }
          },
        }, "Delete"),
      },
    ], codes, { empty: "No unused codes." }));
  } catch (e) { toastError(e); }
}

async function addMachine() {
  const v = await formDialog("Add machine", [
    { name: "label", label: "Label (optional)", help: "e.g. the user or desk this PC is for", maxlength: 128 },
  ], { okText: "Create code", intro: "Creates a one-time enrollment code, valid for 24 hours." });
  if (!v) return;
  try {
    const c = await api("/api/enrollment-codes", { method: "POST", json: { label: v.label } });
    const server = location.origin;
    const cmd = `itops-agent enroll --server ${server} --code ${c.code}`;
    const copy = (text) => navigator.clipboard?.writeText(text).then(() => toast("Copied"), () => toast("Copy failed", "error"));
    dialog("Enrollment code", h("div", { class: "stack" },
      h("div", { class: "code-box" }, c.code),
      h("p", { class: "muted small" }, `Single use. Expires ${fmtTime(c.expires_at)}. It is shown only once.`),
      h("p", {}, "On the PC, as administrator, run the agent setup and enter this code, or run:"),
      h("pre", { class: "json wrap" }, cmd),
    ), {
      buttons: [
        h("button", { class: "btn", onclick: () => copy(c.code) }, "Copy code"),
        h("button", { class: "btn", onclick: () => copy(cmd) }, "Copy command"),
        h("button", { class: "btn primary", onclick: (e) => e.target.closest("dialog").close() }, "Done"),
      ],
    });
    loadCodes();
  } catch (e) { toastError(e); }
}

q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(loadMachines, 250); });
online.addEventListener("change", loadMachines);
revoked.addEventListener("change", loadMachines);
if (can("admin")) document.getElementById("add-machine")?.addEventListener("click", addMachine);

loadMachines();
loadCodes();
setInterval(loadMachines, 10000);
