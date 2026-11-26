import {
  ACTIVE, api, badge, can, clear, confirmDialog, fmtTime, formDialog, h, runAction, table, timeEl, toast, toastError,
} from "/static/app.js";
import { renderCleanup, renderDebloat, renderTweaks } from "/static/pages/machine2.js";

const root = document.getElementById("machine");
const MID = root.dataset.id;
const panels = Object.fromEntries([...root.querySelectorAll(".tab-panel")].map((p) => [p.dataset.panel, p]));
let machine = null;
const loaded = {};

// ---------------------------------------------------------------- header

async function loadMachine() {
  try {
    machine = await api(`/api/machines/${MID}`);
  } catch (e) {
    document.getElementById("m-title").textContent = e.status === 404 ? "Machine not found" : "Error";
    toastError(e);
    return false;
  }
  document.title = `${machine.hostname} - IT Provisioning`;
  document.getElementById("m-title").textContent = machine.hostname;
  const status = machine.revoked_at
    ? badge("revoked")
    : h("span", {}, h("span", { class: `dot ${machine.online ? "on" : ""}` }), machine.online ? "online" : "offline");
  clear(document.getElementById("m-sub")).append(
    status,
    machine.label ? ` · ${machine.label}` : "",
    machine.tags?.length ? [" · ", machine.tags.map((t) => h("a", { class: "tag", href: `/machines?tag=${encodeURIComponent(t)}` }, t))] : "",
    ` · last seen `, machine.online ? "now" : timeEl(machine.last_seen_at),
    machine.agent_version ? ` · agent ${machine.agent_version}` : "",
    machine.last_ip ? ` · ${machine.last_ip}` : "",
  );
  const acts = clear(document.getElementById("m-actions"));
  if (machine.revoked_at) {
    if (can("admin")) acts.append(h("button", { class: "btn danger", onclick: deleteMachine }, "Delete"));
    return true;
  }
  if (can("technician")) {
    acts.append(
      h("button", { class: "btn", onclick: editLabel }, "Edit"),
      h("button", { class: "btn", onclick: () => runAction(MID, "agent.ping", { message: "from web" }, "Ping agent") }, "Ping"),
    );
  }
  if (can("admin")) {
    acts.append(
      h("button", { class: "btn", onclick: uninstallAgent, disabled: !machine.online, title: machine.online ? null : "Machine must be online" }, "Uninstall agent"),
      h("button", { class: "btn danger", onclick: revoke }, "Revoke"));
  }
  return true;
}

async function uninstallAgent() {
  const ok = await confirmDialog("Uninstall agent",
    `Removes the agent service and its files from ${machine.hostname}, then revokes the machine here. `
    + `To manage it again you need a new install command.`, { okText: "Uninstall", danger: true });
  if (!ok) return;
  try {
    const j = await runAction(MID, "agent.uninstall", {}, "Uninstall agent");
    if (j?.status === "succeeded") toast("Agent removed and machine revoked", "ok");
    loadMachine();
  } catch (e) { toastError(e); }
}

async function editLabel() {
  const v = await formDialog(`Edit ${machine.hostname}`, [
    { name: "label", label: "Label", value: machine.label, maxlength: 128 },
    { name: "tags", label: "Tags", value: (machine.tags || []).join(", "), maxlength: 400,
      help: "Comma separated, e.g. sales, floor2. Use tags to run an action on a group of PCs." },
  ]);
  if (!v) return;
  const tags = v.tags.split(",").map((t) => t.trim()).filter(Boolean);
  try { await api(`/api/machines/${MID}`, { method: "PATCH", json: { label: v.label, tags } }); loadMachine(); }
  catch (e) { toastError(e); }
}

async function revoke() {
  const ok = await confirmDialog("Revoke machine",
    `${machine.hostname} will be disconnected now and its agent can never connect again (it would need a new enrollment code). Running jobs are cancelled.`,
    { okText: "Revoke", danger: true });
  if (!ok) return;
  try { await api(`/api/machines/${MID}/revoke`, { method: "POST" }); toast("Machine revoked"); loadMachine(); }
  catch (e) { toastError(e); }
}

async function deleteMachine() {
  if (!await confirmDialog("Delete machine", `Delete ${machine.hostname} and all of its job history?`, { okText: "Delete", danger: true })) return;
  try { await api(`/api/machines/${MID}`, { method: "DELETE" }); location.href = "/machines"; }
  catch (e) { toastError(e); }
}

const canRun = () => can("technician") && machine && !machine.revoked_at;
const latest = (action) => api(`/api/machines/${MID}/latest`, { query: { action } });

// ---------------------------------------------------------------- overview

const SYSINFO_LABELS = {
  user: "Logged-in user", brand: "Manufacturer", model: "Model", serial: "Serial number",
  processor: "Processor", ram: "Memory", disk: "Disk", display: "Graphics",
  win_version: "Windows", win_last_update: "Last update", emails: "Email accounts", monitor_count: "Monitors",
};

async function renderOverview() {
  const p = clear(panels.overview);
  const job = await latest("system.info");
  const info = job?.result || {};
  const rows = Object.entries(info).filter(([k]) => k !== "error").map(([k, v]) => {
    const label = SYSINFO_LABELS[k] || k.replace(/_/g, " ").replace(/^monitor (\d+)$/, "Monitor $1");
    const value = k === "emails" ? v.split("|").filter(Boolean).join(", ") : v;
    return [h("dt", {}, label), h("dd", {}, value || "-")];
  });
  p.append(
    h("div", { class: "grid2" },
      h("section", { class: "card" },
        h("div", { class: "card-head" }, h("h2", {}, "System info"),
          canRun() ? h("button", { class: "btn small", onclick: async () => { await runAction(MID, "system.info", {}, "System info"); renderOverview(); } }, job ? "Refresh" : "Collect") : null),
        job ? h("p", { class: "muted small" }, `Collected ${fmtTime(job.finished_at)}`) : null,
        rows.length ? h("dl", { class: "kv" }, rows) : h("div", { class: "empty" }, "Not collected yet."),
        info.error ? h("p", { class: "error" }, info.error) : null),
      h("section", { class: "card" },
        h("h2", {}, "Agent"),
        h("dl", { class: "kv" },
          h("dt", {}, "Machine id"), h("dd", { class: "mono" }, machine.id),
          h("dt", {}, "Enrolled"), h("dd", {}, fmtTime(machine.enrolled_at)),
          h("dt", {}, "Agent version"), h("dd", {}, machine.agent_version || "-"),
          h("dt", {}, "OS"), h("dd", {}, [machine.os_info?.system, machine.os_info?.release, machine.os_info?.version].filter(Boolean).join(" ") || "-"),
          h("dt", {}, "Last IP"), h("dd", {}, machine.last_ip || "-"),
          machine.revoked_at ? [h("dt", {}, "Revoked"), h("dd", {}, fmtTime(machine.revoked_at))] : null))),
  );
}

// ---------------------------------------------------------------- security

let scan = null;
let problemsOnly = false;

async function renderSecurity() {
  const p = clear(panels.security);
  scan = scan || await latest("security.scan");
  const head = h("section", { class: "card" });
  const runBtn = canRun() ? h("button", {
    class: "btn primary",
    onclick: async () => {
      const j = await runAction(MID, "security.scan", {}, "Security scan");
      if (j?.status === "succeeded") { scan = j; renderSecurity(); }
    },
  }, scan ? "Run scan again" : "Run security scan") : null;
  if (!scan) {
    head.append(h("div", { class: "card-head" }, h("h2", {}, "Security"), runBtn),
      h("div", { class: "empty" }, "No scan yet. A scan is read-only and takes 1-3 minutes."));
    p.append(head);
    return;
  }
  const s = scan.result.summary;
  head.append(
    h("div", { class: "card-head" }, h("h2", {}, "Security"),
      h("div", { class: "row" },
        h("a", { class: "btn", href: `/api/jobs/${scan.id}/report.csv` }, "Export CSV"), runBtn)),
    h("div", { class: "score" },
      h("div", { class: "big" }, String(s.score), h("small", {}, " / 100")),
      h("div", {}, "Risk ", badge(s.level), h("div", { class: "muted small" }, `Scanned ${fmtTime(scan.finished_at)}`)),
      h("div", { class: "row" }, ["FAIL", "WARN", "PASS", "INFO", "UNKNOWN"]
        .filter((k) => s.counts?.[k]).map((k) => h("span", {}, badge(`${s.counts[k]} ${k}`, k))))),
    h("label", { class: "check" },
      h("input", { type: "checkbox", checked: problemsOnly, onchange: (e) => { problemsOnly = e.target.checked; renderSecurity(); } }),
      "Show only problems"),
  );
  const rows = scan.result.checks.filter((c) => !problemsOnly || ["FAIL", "WARN", "UNKNOWN"].includes(c.status));
  p.append(head, h("section", { class: "card flush" }, table([
    { label: "Severity", render: (c) => badge(c.severity) },
    { label: "Status", render: (c) => badge(c.status) },
    {
      label: "Check", render: (c) => h("div", {},
        h("div", { class: "check-name" }, c.name, c.category ? h("span", { class: "muted small" }, `  ${c.category}`) : null),
        c.detail ? h("div", { class: "check-detail" }, c.detail) : null,
        c.impact && c.can_fix ? h("div", { class: "check-impact" }, `If fixed: ${c.impact}`) : null),
    },
    { label: "", render: (c) => h("div", { class: "row" }, fixButtons(c)) },
  ], rows, { empty: "No problems found." })));
}

function fixButtons(c) {
  if (!canRun()) return [];
  const out = [];
  if (c.can_fix && ["FAIL", "WARN"].includes(c.status)) {
    out.push(h("button", { class: "btn small primary", onclick: () => fix(c, "fix") }, c.fix_label || "Fix"));
  }
  if (c.can_undo && c.status === "PASS") {
    out.push(h("button", { class: "btn small ghost", onclick: () => fix(c, "undo") }, "Revert"));
  }
  return out;
}

async function fix(c, mode) {
  const msg = mode === "fix"
    ? `${c.fix_label || "Fix"} on ${machine.hostname}.${c.impact ? `\n\nIf fixed: ${c.impact}` : ""}${c.disruptive ? "\n\nThis change can interrupt how people use this PC." : ""}`
    : `Revert the fix for "${c.name}" on ${machine.hostname}? This makes the PC less secure.`;
  if (!await confirmDialog(mode === "fix" ? "Apply fix" : "Revert fix", msg, { okText: mode === "fix" ? "Apply" : "Revert", danger: c.disruptive || mode === "undo" })) return;
  try {
    const j = await runAction(MID, "security.fix", { check_id: c.id, mode }, `${mode === "fix" ? "Fix" : "Revert"}: ${c.name}`);
    if (j?.result) {
      c.status = j.result.status;
      c.detail = j.result.detail;
      toast(`${c.name}: now ${c.status}`, c.status === "PASS" ? "ok" : "");
      renderSecurity();
    }
  } catch (e) { toastError(e); }
}

// ---------------------------------------------------------------- apps

const selected = new Set();

async function renderApps() {
  const p = clear(panels.apps);
  const cat = await api("/api/catalog/apps");
  const names = {};
  const group = (title, apps) => {
    apps.forEach((a) => { names[a.winget_id] = a.name; });
    const boxes = apps.map((a) => h("label", { class: "check" },
      h("input", {
        type: "checkbox", value: a.winget_id, checked: selected.has(a.winget_id), disabled: !canRun(),
        onchange: (e) => { if (e.target.checked) selected.add(a.winget_id); else selected.delete(a.winget_id); sync(); },
      }), a.name));
    const all = h("button", {
      class: "btn small ghost", disabled: !canRun(),
      onclick: () => {
        const on = !apps.every((a) => selected.has(a.winget_id));
        apps.forEach((a) => (on ? selected.add(a.winget_id) : selected.delete(a.winget_id)));
        sync();
      },
    }, "All");
    return h("div", { class: "app-group" }, h("h3", {}, title, all), boxes);
  };
  const count = h("span", {});
  const installBtn = h("button", { class: "btn primary" }, "Install");
  const uninstallBtn = h("button", { class: "btn" }, "Uninstall");
  function sync() {
    p.querySelectorAll("input[type=checkbox]").forEach((cb) => { cb.checked = selected.has(cb.value); });
    count.textContent = `${selected.size} selected`;
    installBtn.disabled = uninstallBtn.disabled = !selected.size;
  }
  async function go(action) {
    const ids = [...selected];
    if (action === "apps.uninstall" &&
      !await confirmDialog("Uninstall apps", `Uninstall from ${machine.hostname}: ${ids.map((i) => names[i]).join(", ")}?`, { okText: "Uninstall", danger: true })) return;
    try {
      const j = await runAction(MID, action, { ids }, action === "apps.install" ? "Install apps" : "Uninstall apps");
      if (j?.result?.apps) {
        const bad = j.result.apps.filter((a) => !a.ok);
        toast(bad.length ? `${bad.length} app(s) failed: ${bad.map((a) => a.name).join(", ")}` : "All done", bad.length ? "error" : "ok");
      }
      if (j && !ACTIVE.has(j.status)) { selected.clear(); sync(); }
    } catch (e) { toastError(e); }
  }
  installBtn.addEventListener("click", () => go("apps.install"));
  uninstallBtn.addEventListener("click", () => go("apps.uninstall"));
  p.append(
    h("p", { class: "muted" }, "Installs with winget, one app after another. Only apps in the catalog can be installed."),
    h("div", { class: "app-groups" },
      group("Common apps", cat.common),
      Object.entries(cat.teams).map(([team, apps]) => group(team, apps))),
    canRun() ? h("div", { class: "sticky-bar" }, count, h("div", { class: "row" }, uninstallBtn, installBtn)) : null,
  );
  sync();
}

// ---------------------------------------------------------------- history

async function renderHistory() {
  const p = clear(panels.history);
  const jobs = await api("/api/jobs", { query: { machine_id: MID, limit: 100 } });
  p.append(h("section", { class: "card flush" }, table([
    { label: "When", render: (j) => timeEl(j.created_at) },
    { label: "Action", key: "action_id" },
    { label: "Status", render: (j) => badge(j.status) },
    { label: "Exit", key: "exit_code", num: true },
    { label: "Error", render: (j) => h("span", { class: "muted small" }, j.error || "") },
  ], jobs, { empty: "No jobs on this machine yet.", onRow: (j) => { location.href = `/jobs/${j.id}`; } })));
}

// ---------------------------------------------------------------- tabs

const ctx = () => ({ id: MID, hostname: machine.hostname, canRun: canRun() });
const RENDER = {
  overview: renderOverview,
  security: renderSecurity,
  apps: renderApps,
  debloat: () => renderDebloat(panels.debloat, ctx()),
  tweaks: () => renderTweaks(panels.tweaks, ctx()),
  cleanup: () => renderCleanup(panels.cleanup, ctx()),
  history: renderHistory,
};

async function show(tab) {
  root.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  for (const [k, el] of Object.entries(panels)) el.hidden = k !== tab;
  history.replaceState(null, "", `#${tab}`);
  if (!loaded[tab] || tab === "history") {
    loaded[tab] = true;
    try { await RENDER[tab](); } catch (e) { toastError(e); }
  }
}

root.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));

(async () => {
  if (!await loadMachine()) return;
  const tab = location.hash.slice(1);
  show(RENDER[tab] ? tab : "overview");
  setInterval(loadMachine, 15000);
})();
