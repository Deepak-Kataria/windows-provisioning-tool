import { api, badge, clear, h, table, timeEl, toastError } from "/static/app.js";

const statusSel = document.getElementById("status");
const actionSel = document.getElementById("action");
const more = document.getElementById("more");
const PAGE = 50;
let rows = [];
let names = {};

async function load(append = false) {
  try {
    const page = await api("/api/jobs", {
      query: { status: statusSel.value, action: actionSel.value, limit: PAGE, offset: append ? rows.length : 0 },
    });
    rows = append ? rows.concat(page) : page;
    more.hidden = page.length < PAGE;
    clear(document.getElementById("job-table")).append(table([
      { label: "Created", render: (j) => timeEl(j.created_at) },
      { label: "Machine", render: (j) => h("a", { href: `/machines/${j.machine_id}` }, names[j.machine_id] || j.machine_id.slice(0, 8)) },
      { label: "Action", key: "action_id" },
      { label: "Status", render: (j) => badge(j.status) },
      { label: "Exit", key: "exit_code", num: true },
      { label: "Error", render: (j) => h("span", { class: "muted small" }, j.error || "") },
    ], rows, { empty: "No jobs match.", onRow: (j) => { location.href = `/jobs/${j.id}`; } }));
  } catch (e) { toastError(e); }
}

async function loadBatches() {
  try {
    const b = await api("/api/batches", { query: { limit: 10 } });
    if (!b.length) return;
    document.getElementById("batches-card").hidden = false;
    clear(document.getElementById("batches")).append(table([
      { label: "Started", render: (x) => timeEl(x.created_at) },
      { label: "Action", key: "action" },
      { label: "Machines", key: "total", num: true },
    ], b, { onRow: (x) => { location.href = `/batches/${x.batch_id}`; } }));
  } catch (e) { toastError(e); }
}

(async () => {
  loadBatches();
  try {
    const [machines, actions] = await Promise.all([
      api("/api/machines", { query: { limit: 1000, include_revoked: true } }),
      api("/api/actions"),
    ]);
    names = Object.fromEntries(machines.map((m) => [m.id, m.hostname]));
    for (const a of actions) actionSel.append(h("option", { value: a.id }, a.title));
  } catch (e) { toastError(e); }
  load();
})();
statusSel.addEventListener("change", () => load());
actionSel.addEventListener("change", () => load());
more.addEventListener("click", () => load(true));
