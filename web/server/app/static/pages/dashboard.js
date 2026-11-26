import { api, badge, clear, h, parseTime, table, timeEl, toastError } from "/static/app.js";

const tile = (num, lbl, cls) => h("div", { class: "tile" }, h("div", { class: `num ${cls || ""}` }, num), h("div", { class: "lbl" }, lbl));

async function load() {
  try {
    const [summary, machines, active, failed, recent] = await Promise.all([
      api("/api/machines/summary"),
      api("/api/machines", { query: { limit: 1000 } }),
      Promise.all(["queued", "sent", "running"].map((s) => api("/api/jobs", { query: { status: s, limit: 500 } }))),
      api("/api/jobs", { query: { status: "failed", limit: 200 } }),
      api("/api/jobs", { query: { limit: 10 } }),
    ]);
    const names = Object.fromEntries(machines.map((m) => [m.id, m.hostname]));
    const dayAgo = Date.now() - 86400e3;
    const failed24 = failed.filter((j) => parseTime(j.created_at) > dayAgo).length;
    clear(document.getElementById("tiles")).append(
      tile(summary.total, "Machines"),
      tile(summary.online, "Online now"),
      tile(summary.total - summary.online, "Offline"),
      tile(active.flat().length, "Jobs in progress"),
      tile(failed24, "Failed jobs (24h)"),
    );
    clear(document.getElementById("recent-jobs")).append(table([
      { label: "When", render: (j) => timeEl(j.created_at) },
      { label: "Machine", render: (j) => h("a", { href: `/machines/${j.machine_id}` }, names[j.machine_id] || "?") },
      { label: "Action", key: "action_id" },
      { label: "Status", render: (j) => badge(j.status) },
    ], recent, { empty: "No jobs yet.", onRow: (j) => { location.href = `/jobs/${j.id}`; } }));
    const offline = machines.filter((m) => !m.online).slice(0, 10);
    clear(document.getElementById("offline")).append(table([
      { label: "Machine", render: (m) => h("a", { href: `/machines/${m.id}` }, m.hostname) },
      { label: "Label", key: "label" },
      { label: "Last seen", render: (m) => timeEl(m.last_seen_at) },
    ], offline, { empty: "All machines are online." }));
  } catch (e) { toastError(e); }
}

load();
setInterval(load, 15000);
