import {
  api, badge, can, checkbox, clear, confirmDialog, dialog, fmtTime, formDialog, h, table, timeEl, toast, toastError,
} from "/static/app.js";

const q = document.getElementById("q");
const online = document.getElementById("online");
const revoked = document.getElementById("revoked");
const tagSel = document.getElementById("tag");
const bulkBtn = document.getElementById("bulk");
const selected = new Set();
let rows = [];
let timer;

const params = new URLSearchParams(location.search);
if (params.get("tag")) tagSel.append(h("option", { value: params.get("tag"), selected: true }, params.get("tag")));

function syncBulk() {
  if (!bulkBtn) return;
  bulkBtn.disabled = !selected.size && !tagSel.value;
  bulkBtn.textContent = selected.size ? `Run on ${selected.size} selected`
    : tagSel.value ? `Run on tag "${tagSel.value}"` : "Run on selected";
}

async function loadTags() {
  try {
    const keep = tagSel.value;
    const tags = await api("/api/tags");
    clear(tagSel).append(h("option", { value: "" }, "Any tag"),
      tags.map((t) => h("option", { value: t.tag, selected: t.tag === keep }, `${t.tag} (${t.machines})`)));
  } catch (e) { toastError(e); }
}

async function loadMachines() {
  try {
    rows = await api("/api/machines", {
      query: { q: q.value.trim(), tag: tagSel.value, online: online.value, include_revoked: revoked.checked || undefined, limit: 1000 },
    });
    for (const id of [...selected]) if (!rows.some((m) => m.id === id && !m.revoked_at)) selected.delete(id);
    document.getElementById("count").textContent = `${rows.length} machine${rows.length === 1 ? "" : "s"}`;
    const pickable = rows.filter((m) => !m.revoked_at);
    const allBox = checkbox(pickable.length > 0 && pickable.every((m) => selected.has(m.id)), (on) => {
      pickable.forEach((m) => (on ? selected.add(m.id) : selected.delete(m.id)));
      loadMachines();
    }, { "aria-label": "Select all" });
    const cols = [
      { label: "Status", render: (m) => (m.revoked_at ? badge("revoked") : h("span", {}, h("span", { class: `dot ${m.online ? "on" : ""}` }), m.online ? "online" : "offline")) },
      { label: "Hostname", render: (m) => h("a", { href: `/machines/${m.id}` }, m.hostname) },
      { label: "Label", key: "label" },
      { label: "Tags", render: (m) => (m.tags || []).map((t) => h("span", { class: "tag" }, t)) },
      { label: "Windows", render: (m) => [m.os_info?.release, m.os_info?.version].filter(Boolean).join(" ") || "-" },
      { label: "Agent", key: "agent_version" },
      { label: "Last seen", render: (m) => (m.online ? "now" : timeEl(m.last_seen_at)) },
    ];
    if (can("technician")) {
      cols.unshift({
        label: "", render: (m) => (m.revoked_at ? "" : checkbox(selected.has(m.id), (on) => { on ? selected.add(m.id) : selected.delete(m.id); syncBulk(); }, { "aria-label": `Select ${m.hostname}` })),
      });
    }
    const t = table(cols, rows, {
      empty: q.value || online.value || tagSel.value ? "No machines match." : "No machines yet. Use 'Add machine' to enroll the first PC.",
      onRow: (m) => { location.href = `/machines/${m.id}`; },
    });
    const th = t.querySelector?.("thead th");
    if (th && can("technician")) th.append(allBox);
    clear(document.getElementById("machine-table")).append(t);
    syncBulk();
  } catch (e) { toastError(e); }
}

// ---------------------------------------------------------------- bulk run

const BULK_ACTIONS = [
  { id: "agent.ping", label: "Ping agent" },
  { id: "system.info", label: "Collect system info" },
  { id: "security.scan", label: "Security scan" },
  { id: "apps.install", label: "Install apps" },
  { id: "debloat.remove", label: "Remove Store apps (debloat)" },
  { id: "tweaks.apply", label: "Apply tweaks" },
  { id: "tweaks.power", label: "Set power plan" },
];

async function pickerFor(action) {
  // returns {el, params(): object | null}
  const pick = new Set();
  const list = (items, key, label, groupKey) => {
    const groups = {};
    for (const it of items) (groups[it[groupKey] || ""] ||= []).push(it);
    return h("div", { class: "stack", style: "max-height:46vh;overflow:auto" }, Object.entries(groups).map(([g, its]) => h("div", {},
      g ? h("div", { class: "muted small", style: "margin-top:6px" }, g) : null,
      h("div", { class: "list-grid" }, its.map((it) => h("label", { class: "check" },
        checkbox(false, (on) => (on ? pick.add(it[key]) : pick.delete(it[key]))), it[label]))))));
  };
  if (action === "apps.install") {
    const cat = await api("/api/catalog/apps");
    const items = [...cat.common.map((a) => ({ ...a, g: "Common apps" })),
      ...Object.entries(cat.teams).flatMap(([t, apps]) => apps.map((a) => ({ ...a, g: t })))];
    const seen = new Set();
    const uniq = items.filter((a) => !seen.has(a.winget_id) && seen.add(a.winget_id));
    return { el: list(uniq, "winget_id", "name", "g"), params: () => (pick.size ? { ids: [...pick] } : null) };
  }
  if (action === "debloat.remove") {
    const cat = await api("/api/catalog/debloat");
    return { el: list(cat, "package", "name", "category"), params: () => (pick.size ? { packages: [...pick] } : null) };
  }
  if (action === "tweaks.apply") {
    const cat = await api("/api/catalog/tweaks");
    const mode = h("select", {}, h("option", { value: "apply" }, "Apply"), h("option", { value: "undo" }, "Undo"));
    return {
      el: h("div", { class: "stack" }, h("label", {}, "Mode", mode), list(cat, "id", "name", "section")),
      params: () => (pick.size ? { ids: [...pick], mode: mode.value } : null),
    };
  }
  if (action === "tweaks.power") {
    const plan = h("select", {}, h("option", { value: "ultimate" }, "Ultimate Performance"), h("option", { value: "balanced" }, "Balanced"));
    return { el: h("label", {}, "Plan", plan), params: () => ({ plan: plan.value }) };
  }
  return { el: h("p", { class: "muted" }, "No options."), params: () => ({}) };
}

async function openBulk() {
  const byIds = selected.size > 0;
  const target = byIds ? `${selected.size} selected machine(s)` : `every machine tagged "${tagSel.value}"`;
  const actionSel = h("select", {}, BULK_ACTIONS.map((a) => h("option", { value: a.id }, a.label)));
  const optsBox = h("div", {});
  let picker = null;
  const load = async () => {
    clear(optsBox).append(h("p", { class: "muted" }, "Loading..."));
    try { picker = await pickerFor(actionSel.value); clear(optsBox).append(picker.el); } catch (e) { toastError(e); }
  };
  actionSel.addEventListener("change", load);
  const runBtn = h("button", { class: "btn primary" }, "Run");
  const d = dialog("Run on many machines", h("div", { class: "stack" },
    h("p", {}, "Target: ", h("b", {}, target),
      h("span", { class: "muted small" }, ". Offline machines get the job when their agent connects.")),
    h("label", {}, "Action", actionSel), optsBox), {
    wide: true,
    buttons: [h("button", { class: "btn ghost", onclick: () => d.close() }, "Cancel"), runBtn],
  });
  runBtn.addEventListener("click", async () => {
    const p = picker?.params();
    if (!p) { toastError("Pick at least one item"); return; }
    const label = actionSel.selectedOptions[0].textContent;
    if (!await confirmDialog("Run on many machines", `${label} on ${target}?`, { okText: "Run" })) return;
    try {
      const body = { action: actionSel.value, params: p };
      if (byIds) body.machine_ids = [...selected]; else body.tag = tagSel.value;
      const r = await api("/api/bulk-jobs", { method: "POST", json: body });
      d.close();
      location.href = `/batches/${r.batch_id}`;
    } catch (e) { toastError(e); }
  });
  load();
}

// ---------------------------------------------------------------- enrollment

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
    const [c, pkg] = await Promise.all([
      api("/api/enrollment-codes", { method: "POST", json: { label: v.label } }),
      api("/api/agent/package"),
    ]);
    const copy = (text) => navigator.clipboard?.writeText(text).then(() => toast("Copied"), () => toast("Copy failed", "error"));
    dialog("Install the agent", h("div", { class: "stack" },
      pkg.available ? null : h("div", { class: "banner warn" },
        "The agent build is not on the server yet, so this command will fail. Build it with web\\agent\\build.ps1 and upload it first."),
      h("ol", { class: "steps" },
        h("li", {}, "On the new PC, open ", h("b", {}, "PowerShell as Administrator"), "."),
        h("li", {}, "Paste this command and press Enter:")),
      h("pre", { class: "json wrap" }, c.install_command),
      h("p", { class: "muted small" },
        "It downloads the agent from this server, installs it as a Windows service and enrolls the PC. "
        + `Works once, until ${fmtTime(c.expires_at)}. Shown only now.`),
      h("details", {}, h("summary", { class: "muted small" }, "Enrollment code only"), h("div", { class: "code-box" }, c.code)),
    ), {
      wide: true,
      buttons: [
        h("button", { class: "btn primary", onclick: () => copy(c.install_command) }, "Copy command"),
        h("button", { class: "btn", onclick: (e) => e.target.closest("dialog").close() }, "Done"),
      ],
    });
    loadCodes();
  } catch (e) { toastError(e); }
}

q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(loadMachines, 250); });
online.addEventListener("change", loadMachines);
revoked.addEventListener("change", loadMachines);
tagSel.addEventListener("change", () => { selected.clear(); loadMachines(); });
bulkBtn?.addEventListener("click", openBulk);
if (can("admin")) document.getElementById("add-machine")?.addEventListener("click", addMachine);

loadTags().then(loadMachines);
loadCodes();
setInterval(loadMachines, 10000);
