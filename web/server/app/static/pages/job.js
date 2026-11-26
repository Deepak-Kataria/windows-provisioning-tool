import { ACTIVE, api, badge, can, clear, consoleLine, fmtTime, h, streamJob, toast, toastError } from "/static/app.js";

const root = document.getElementById("job");
const JID = root.dataset.id;
let stream = null;

async function render() {
  let job;
  try { job = await api(`/api/jobs/${JID}`); } catch (e) {
    document.getElementById("j-title").textContent = e.status === 404 ? "Job not found" : "Error";
    toastError(e);
    return;
  }
  let machine = null;
  try { machine = await api(`/api/machines/${job.machine_id}`); } catch { /* deleted */ }
  document.getElementById("j-title").textContent = job.action_id;
  const statusEl = h("span", {}, badge(job.status));
  clear(document.getElementById("j-sub")).append(
    statusEl, " on ",
    machine ? h("a", { href: `/machines/${machine.id}` }, machine.hostname) : "(deleted machine)",
    ` · created ${fmtTime(job.created_at)}`,
  );
  const acts = clear(document.getElementById("j-actions"));
  const cancel = h("button", {
    class: "btn danger", hidden: !(can("technician") && ACTIVE.has(job.status)),
    onclick: async () => {
      try { await api(`/api/jobs/${JID}/cancel`, { method: "POST" }); toast("Cancel requested"); } catch (e) { toastError(e); }
    },
  }, "Cancel job");
  acts.append(cancel);
  if (job.action_id === "security.scan" && job.status === "succeeded") {
    acts.append(h("a", { class: "btn", href: `/api/jobs/${JID}/report.csv` }, "Export CSV"));
  }

  const con = h("div", { class: "console" });
  const details = h("dl", { class: "kv" },
    h("dt", {}, "Parameters"), h("dd", { class: "mono" }, JSON.stringify(job.params)),
    h("dt", {}, "Sent"), h("dd", {}, fmtTime(job.sent_at)),
    h("dt", {}, "Started"), h("dd", {}, fmtTime(job.started_at)),
    h("dt", {}, "Finished"), h("dd", {}, fmtTime(job.finished_at)),
    h("dt", {}, "Exit code"), h("dd", {}, job.exit_code ?? "-"),
    job.error ? [h("dt", {}, "Error"), h("dd", { class: "error" }, job.error)] : null);
  const result = job.result
    ? h("pre", { class: "json" }, JSON.stringify(job.result, null, 2))
    : h("div", { class: "empty" }, "No result data.");
  clear(document.getElementById("j-body")).append(
    h("section", { class: "card" }, h("h2", {}, "Output"), con),
    h("div", { class: "grid2" },
      h("section", { class: "card" }, h("h2", {}, "Details"), details),
      h("section", { class: "card" }, h("h2", {}, "Result"), result)),
  );
  if (job.status === "queued") consoleLine(con, { stream: "system", data: "Waiting for the agent to come online..." });
  stream?.close();
  stream = streamJob(JID, {
    onLine: (l) => consoleLine(con, l),
    onStatus: (m) => {
      statusEl.replaceChildren(badge(m.status));
      if (!ACTIVE.has(m.status)) {
        cancel.hidden = true;
        if (ACTIVE.has(job.status)) setTimeout(render, 300); // finished while watching: refresh result
      }
    },
  });
}

render();
