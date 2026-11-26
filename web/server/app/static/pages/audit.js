import { api, clear, fmtTime, h, table, toastError } from "/static/app.js";

const ev = document.getElementById("event");
const user = document.getElementById("username");
const more = document.getElementById("more");
const PAGE = 100;
let rows = [];

function detail(d) {
  const parts = Object.entries(d || {}).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`);
  return h("span", { class: "mono small" }, parts.join("  "));
}

async function load(append = false) {
  try {
    const page = await api("/api/audit", {
      query: {
        event: ev.value.trim(), username: user.value.trim(), limit: PAGE,
        before_id: append && rows.length ? rows[rows.length - 1].id : undefined,
      },
    });
    rows = append ? rows.concat(page) : page;
    more.hidden = page.length < PAGE;
    clear(document.getElementById("audit-table")).append(table([
      { label: "Time", render: (e) => fmtTime(e.ts) },
      { label: "User", key: "username" },
      { label: "Event", render: (e) => h("b", {}, e.event) },
      { label: "Machine", render: (e) => (e.machine_id ? h("a", { href: `/machines/${e.machine_id}` }, e.machine_id.slice(0, 8)) : "") },
      { label: "IP", render: (e) => h("span", { class: "mono small" }, e.ip) },
      { label: "Detail", render: (e) => detail(e.detail) },
    ], rows, { empty: "No events match." }));
  } catch (e) { toastError(e); }
}

document.getElementById("apply").addEventListener("click", () => load());
for (const el of [ev, user]) el.addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
more.addEventListener("click", () => load(true));
load();
