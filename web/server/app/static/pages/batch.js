import { api, badge, can, clear, confirmDialog, fmtTime, h, table, toast, toastError } from "/static/app.js";

const root = document.getElementById("batch");
const BID = root.dataset.id;
let timer = null;

const tile = (num, lbl) => h("div", { class: "tile" }, h("div", { class: "num" }, num), h("div", { class: "lbl" }, lbl));

async function load() {
  let b;
  try { b = await api(`/api/batches/${BID}`); } catch (e) {
    document.getElementById("b-title").textContent = e.status === 404 ? "Bulk run not found" : "Error";
    toastError(e);
    clearInterval(timer);
    return;
  }
  const c = b.counts;
  const active = (c.queued || 0) + (c.sent || 0) + (c.running || 0);
  document.getElementById("b-title").textContent = `Bulk run: ${b.action}`;
  clear(document.getElementById("b-sub")).append(
    `Started ${fmtTime(b.created_at)} · ${b.total} machine(s) · params `, h("span", { class: "mono" }, JSON.stringify(b.params)));
  clear(document.getElementById("b-tiles")).append(
    tile(b.total, "Machines"), tile(c.succeeded || 0, "Succeeded"), tile(c.failed || 0, "Failed"),
    tile(active, "In progress / waiting"), tile(c.cancelled || 0, "Cancelled"));
  const acts = clear(document.getElementById("b-actions"));
  if (active && can("technician")) {
    acts.append(h("button", {
      class: "btn danger",
      onclick: async () => {
        if (!await confirmDialog("Cancel bulk run", `Cancel the ${active} unfinished job(s)?`, { okText: "Cancel jobs", danger: true })) return;
        try { await api(`/api/batches/${BID}/cancel`, { method: "POST" }); toast("Cancel requested"); load(); } catch (e) { toastError(e); }
      },
    }, "Cancel unfinished"));
  }
  clear(document.getElementById("b-table")).append(table([
    { label: "Machine", render: (j) => h("a", { href: `/machines/${j.machine_id}` }, j.hostname) },
    { label: "Status", render: (j) => badge(j.status) },
    { label: "Exit", key: "exit_code", num: true },
    { label: "Finished", render: (j) => fmtTime(j.finished_at) },
    { label: "Error", render: (j) => h("span", { class: "muted small" }, j.error || "") },
  ], b.jobs, { onRow: (j) => { location.href = `/jobs/${j.id}`; } }));
  if (!active && timer) { clearInterval(timer); timer = null; }
  if (active && !timer) timer = setInterval(load, 3000);
}

load();
