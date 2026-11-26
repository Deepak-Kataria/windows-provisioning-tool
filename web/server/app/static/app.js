// Shared helpers for every page. DOM is built with textContent only (no innerHTML with data).

const body = document.body;
export const me = {
  username: body.dataset.user || "",
  id: Number(body.dataset.userId || 0),
  role: body.dataset.role || "viewer",
};
const RANK = { viewer: 0, technician: 1, admin: 2 };
export const can = (role) => (RANK[me.role] ?? -1) >= RANK[role];

// ---------------------------------------------------------------- API

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", json, query, raw = false } = {}) {
  let url = path;
  if (query) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== "") q.set(k, v);
    const s = q.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  const headers = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = body.dataset.csrf || "";
  if (json !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch(url, {
    method, headers, credentials: "same-origin",
    body: json !== undefined ? JSON.stringify(json) : undefined,
  });
  if (r.status === 401 && !path.startsWith("/api/auth/")) {
    location.href = "/login";
    throw new ApiError(401, "Session expired");
  }
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const d = await r.json();
      msg = typeof d.detail === "string" ? d.detail : (d.detail?.[0]?.msg || JSON.stringify(d.detail));
    } catch { /* not json */ }
    throw new ApiError(r.status, msg);
  }
  if (raw) return r;
  return r.status === 204 ? null : r.json();
}

// ---------------------------------------------------------------- DOM

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const clear = (el) => { el.replaceChildren(); return el; };

export const badge = (text, cls = text) => h("span", { class: `badge b-${cls}` }, text);

export function table(columns, rows, { empty = "Nothing here yet.", onRow } = {}) {
  if (!rows.length) return h("div", { class: "empty" }, empty);
  return h("table", {},
    h("thead", {}, h("tr", {}, columns.map((c) => h("th", { class: c.num ? "num" : null }, c.label)))),
    h("tbody", {}, rows.map((r) => {
      const tr = h("tr", { class: onRow ? "clickable" : null },
        columns.map((c) => h("td", { class: c.num ? "num" : null }, c.render ? c.render(r) : (r[c.key] ?? ""))));
      if (onRow) tr.addEventListener("click", (e) => { if (!e.target.closest("a,button,input,select")) onRow(r); });
      return tr;
    })));
}

// ---------------------------------------------------------------- time

export const parseTime = (s) => (s ? new Date(s.endsWith("Z") ? s : s + "Z") : null);
export function fmtTime(s) {
  const d = parseTime(s);
  return d ? d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "-";
}
export function ago(s) {
  const d = parseTime(s);
  if (!d) return "never";
  const sec = Math.round((Date.now() - d.getTime()) / 1000);
  if (sec < 45) return "just now";
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)} h ago`;
  return `${Math.round(sec / 86400)} d ago`;
}
export function timeEl(s) {
  return h("time", { datetime: s || "", title: fmtTime(s) }, ago(s));
}

// ---------------------------------------------------------------- toasts, dialogs

export function toast(msg, kind = "") {
  const t = h("div", { class: `toast ${kind}`, role: kind === "error" ? "alert" : "status" }, msg);
  $("#toasts")?.append(t);
  setTimeout(() => t.remove(), kind === "error" ? 8000 : 4000);
}
export const toastError = (e) => toast(e?.message || String(e), "error");

export function dialog(title, content, { wide = false, buttons = [] } = {}) {
  const d = h("dialog", { class: wide ? "wide" : null },
    h("h2", {}, title), content,
    h("div", { class: "dialog-actions" }, buttons));
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  return d;
}

export function confirmDialog(title, message, { okText = "OK", danger = false } = {}) {
  return new Promise((resolve) => {
    let ok = false;
    const d = dialog(title, h("p", {}, message), {
      buttons: [
        h("button", { class: "btn ghost", onclick: () => d.close() }, "Cancel"),
        h("button", { class: `btn ${danger ? "danger" : "primary"}`, onclick: () => { ok = true; d.close(); } }, okText),
      ],
    });
    d.addEventListener("close", () => resolve(ok));
  });
}

/** fields: [{name, label, type, value, options, required, help}] -> resolves to values or null */
export function formDialog(title, fields, { okText = "Save", intro } = {}) {
  return new Promise((resolve) => {
    const form = h("form", { class: "stack", method: "dialog" },
      intro ? h("p", { class: "muted" }, intro) : null,
      fields.map((f) => {
        let input;
        if (f.type === "select") {
          input = h("select", { name: f.name }, f.options.map((o) =>
            h("option", { value: o.value ?? o, selected: (o.value ?? o) === f.value }, o.label ?? o)));
        } else if (f.type === "checkbox") {
          return h("label", { class: "check" }, h("input", { type: "checkbox", name: f.name, checked: !!f.value }), f.label);
        } else {
          input = h("input", {
            name: f.name, type: f.type || "text", value: f.value ?? "", required: f.required,
            minlength: f.minlength, maxlength: f.maxlength, autocomplete: f.autocomplete || "off", pattern: f.pattern,
          });
        }
        return h("label", {}, f.label, input, f.help ? h("span", { class: "small" }, f.help) : null);
      }));
    let result = null;
    const submit = h("button", { class: "btn primary", type: "submit" }, okText);
    form.append(h("div", { class: "dialog-actions" },
      h("button", { class: "btn ghost", type: "button", onclick: () => d.close() }, "Cancel"), submit));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      result = {};
      for (const f of fields) {
        const el = form.elements[f.name];
        result[f.name] = f.type === "checkbox" ? el.checked : el.value;
      }
      d.close();
    });
    const d = dialog(title, form);
    d.querySelector(".dialog-actions:last-child:empty")?.remove();
    d.addEventListener("close", () => resolve(result));
  });
}

// ---------------------------------------------------------------- jobs

export const ACTIVE = new Set(["queued", "sent", "running"]);

export function streamJob(jobId, { onLine, onStatus }) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/jobs/${encodeURIComponent(jobId)}/stream`);
  let finished = false;
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "line") onLine(m);
    else if (m.type === "status") {
      onStatus(m);
      if (!ACTIVE.has(m.status)) finished = true;
    }
  };
  // Fallback: if the socket drops early, poll until the job is done.
  ws.onclose = async () => {
    let seq = 0;
    while (!finished) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const lines = await api(`/api/jobs/${jobId}/logs`, { query: { after_seq: seq } });
        for (const l of lines) { seq = l.seq; onLine(l); }
        const j = await api(`/api/jobs/${jobId}`);
        if (!ACTIVE.has(j.status)) { finished = true; onStatus({ status: j.status, exit_code: j.exit_code, final: true }); }
      } catch { finished = true; }
    }
  };
  return { close: () => { finished = true; ws.close(); } };
}

export function consoleLine(con, line) {
  const atBottom = con.scrollHeight - con.scrollTop - con.clientHeight < 40;
  con.append(h("div", { class: line.stream }, line.data));
  if (atBottom) con.scrollTop = con.scrollHeight;
}

/** Live job window. Resolves with the final job when closed. */
export function jobConsole(job, title) {
  return new Promise((resolve) => {
    const status = h("span", {}, badge(job.status));
    const con = h("div", { class: "console" });
    const cancelBtn = h("button", { class: "btn danger", hidden: !can("technician") }, "Cancel job");
    cancelBtn.addEventListener("click", async () => {
      try { await api(`/api/jobs/${job.id}/cancel`, { method: "POST" }); toast("Cancel requested"); }
      catch (e) { toastError(e); }
    });
    const d = dialog(title || job.action_id, h("div", { class: "stack" },
      h("div", { class: "row" }, "Status:", status, h("a", { href: `/jobs/${job.id}`, class: "small" }, "Open job page")),
      con), {
      wide: true,
      buttons: [cancelBtn, h("button", { class: "btn", onclick: () => d.close() }, "Close")],
    });
    const s = streamJob(job.id, {
      onLine: (l) => consoleLine(con, l),
      onStatus: (m) => {
        status.replaceChildren(badge(m.status));
        if (!ACTIVE.has(m.status)) {
          cancelBtn.hidden = true;
          consoleLine(con, { stream: "system", data: `--- ${m.status}${m.exit_code != null ? ` (exit ${m.exit_code})` : ""} ---` });
        }
      },
    });
    d.addEventListener("close", async () => {
      s.close();
      try { resolve(await api(`/api/jobs/${job.id}`)); } catch { resolve(null); }
    });
  });
}

export async function runAction(machineId, action, params = {}, title) {
  const job = await api(`/api/machines/${machineId}/jobs`, { method: "POST", json: { action, params } });
  if (job.status === "queued") toast("Machine is offline: job queued, it runs when the agent connects.");
  return jobConsole(job, title);
}

// ---------------------------------------------------------------- page chrome

$("#logout")?.addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch { /* already gone */ }
  location.href = "/login";
});

// ---------------------------------------------------------------- phase 2 helpers

export function fmtBytes(n) {
  if (n === null || n === undefined) return "-";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = Number(n);
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
}

/** Run a job without the console window; resolves with the finished job. */
export async function runAndWait(machineId, action, params = {}, { timeoutMs = 30 * 60e3 } = {}) {
  let job = await api(`/api/machines/${machineId}/jobs`, { method: "POST", json: { action, params } });
  const until = Date.now() + timeoutMs;
  while (ACTIVE.has(job.status) && Date.now() < until) {
    await new Promise((r) => setTimeout(r, 1500));
    job = await api(`/api/jobs/${job.id}`);
  }
  return job;
}

export function checkbox(checked, onchange, attrs = {}) {
  return h("input", { type: "checkbox", checked, onchange: (e) => onchange(e.target.checked), ...attrs });
}
