// Machine page, Phase 2 tabs: Debloat, Tweaks, Cleanup (Windows / Profiles / Disk).
import {
  api, badge, checkbox, clear, confirmDialog, fmtBytes, fmtTime, h, runAction, runAndWait, table, toast, toastError,
} from "/static/app.js";

const latest = (mid, action) => api(`/api/machines/${mid}/latest`, { query: { action } });

function head(title, ...right) {
  return h("div", { class: "card-head" }, h("h2", {}, title), h("div", { class: "row" }, right));
}
const when = (job) => (job ? h("p", { class: "muted small" }, `Checked ${fmtTime(job.finished_at)}`) : null);
const btn = (label, onclick, cls = "") => h("button", { class: `btn ${cls}`, onclick }, label);

/** Refresh a read-only state action quietly with a busy button. */
async function refresh(mid, action, params, button) {
  const old = button?.textContent;
  if (button) { button.disabled = true; button.textContent = "Checking..."; }
  try {
    const j = await runAndWait(mid, action, params);
    if (j.status === "queued") toast("Machine is offline: the check runs when it comes online.");
    else if (j.status !== "succeeded") toast(`${action}: ${j.status} ${j.error || ""}`, "error");
    return j;
  } finally {
    if (button) { button.disabled = false; button.textContent = old; }
  }
}

// ================================================================= Debloat

export async function renderDebloat(p, m) {
  clear(p);
  let scan = await latest(m.id, "debloat.scan");
  let mode = "remove";
  const sel = new Set();
  const body = h("div", {});

  const draw = () => {
    clear(body);
    if (!scan) {
      body.append(h("div", { class: "empty" }, "Not checked yet. Check which of the listed apps are installed."));
      return;
    }
    const apps = scan.result.apps;
    const selectable = (a) => (mode === "remove" ? a.installed || a.provisioned : !a.installed);
    const cats = [...new Set(apps.map((a) => a.category))];
    const count = h("span", {});
    const go = h("button", { class: `btn ${mode === "remove" ? "danger" : "primary"}` });
    const sync = () => {
      count.textContent = `${sel.size} selected`;
      go.textContent = mode === "remove" ? `Remove ${sel.size}` : `Reinstall ${sel.size}`;
      go.disabled = !sel.size || !m.canRun;
    };
    go.addEventListener("click", async () => {
      const pk = [...sel];
      const names = apps.filter((a) => sel.has(a.package)).map((a) => a.name).join(", ");
      const ok = await confirmDialog(mode === "remove" ? "Remove apps" : "Reinstall apps",
        mode === "remove"
          ? `Remove from ${m.hostname} for all users (new users won't get them either):\n${names}`
          : `Reinstall on ${m.hostname} with winget:\n${names}`,
        { okText: mode === "remove" ? "Remove" : "Reinstall", danger: mode === "remove" });
      if (!ok) return;
      try {
        await runAction(m.id, mode === "remove" ? "debloat.remove" : "debloat.reinstall", { packages: pk },
          mode === "remove" ? "Remove apps" : "Reinstall apps");
        sel.clear();
        const j = await refresh(m.id, "debloat.scan", {});
        if (j.status === "succeeded") scan = j;
        draw();
      } catch (e) { toastError(e); }
    });
    body.append(
      h("div", { class: "row" },
        h("div", { class: "seg" },
          ["remove", "reinstall"].map((md) => h("button", {
            class: mode === md ? "active" : "", onclick: () => { mode = md; sel.clear(); draw(); },
          }, md === "remove" ? "Remove" : "Reinstall"))),
        h("span", { class: "muted small" },
          `${apps.filter((a) => a.installed).length} of ${apps.length} listed apps installed`)),
      h("div", { class: "app-groups", style: "margin-top:12px" }, cats.map((cat) => {
        const list = apps.filter((a) => a.category === cat);
        const pickable = list.filter(selectable);
        return h("div", { class: "app-group" },
          h("h3", {}, cat, h("button", {
            class: "btn small ghost", disabled: !pickable.length || !m.canRun,
            onclick: () => { const on = !pickable.every((a) => sel.has(a.package)); pickable.forEach((a) => (on ? sel.add(a.package) : sel.delete(a.package))); draw(); },
          }, "All")),
          list.map((a) => h("label", { class: `check ${selectable(a) ? "" : "dim-row"}` },
            checkbox(sel.has(a.package), (on) => { on ? sel.add(a.package) : sel.delete(a.package); sync(); },
              { disabled: !selectable(a) || !m.canRun }),
            a.name, " ", a.installed ? badge("installed", "ok") : badge("not installed", "muted"))));
      })),
      m.canRun ? h("div", { class: "sticky-bar" }, count, go) : null,
    );
    sync();
  };

  const refreshBtn = btn(scan ? "Check again" : "Check installed apps", async () => {
    const j = await refresh(m.id, "debloat.scan", {}, refreshBtn);
    if (j.status === "succeeded") { scan = j; draw(); }
  });
  p.append(h("section", { class: "card" }, head("Debloat: pre-installed Store apps", m.canRun ? refreshBtn : null), when(scan), body));
  draw();
}

// ================================================================= Tweaks

const STATE_BADGE = (v) => (v === true ? badge("applied", "ok") : v === false ? badge("not applied", "muted") : badge("can't check", "UNKNOWN"));
const SECTION = { essential: "Essential", advanced: "Advanced (use with care)", privacy: "Privacy", org: "Organisation" };

export async function renderTweaks(p, m) {
  clear(p);
  let st = await latest(m.id, "tweaks.state");
  const sel = new Set();
  const body = h("div", {});
  const reload = async () => {
    const j = await refresh(m.id, "tweaks.state", {});
    if (j.status === "succeeded") { st = j; draw(); }
  };

  const draw = () => {
    clear(body);
    if (!st) { body.append(h("div", { class: "empty" }, "Not checked yet.")); return; }
    const r = st.result;
    if (!r.users.length) {
      body.append(h("div", { class: "banner warn" }, "No user is signed in to this PC. Per-user tweaks and preferences are skipped until someone signs in."));
    } else {
      body.append(h("p", { class: "muted small" }, `Per-user settings go to: ${r.users.join(", ")}`));
    }
    const count = h("span", {});
    const applyBtn = btn("Apply", () => run("apply"), "primary");
    const undoBtn = btn("Undo", () => run("undo"));
    const sync = () => {
      count.textContent = `${sel.size} selected`;
      applyBtn.disabled = undoBtn.disabled = !sel.size || !m.canRun;
    };
    async function run(mode) {
      const names = r.tweaks.filter((t) => sel.has(t.id)).map((t) => t.name).join("\n");
      if (!await confirmDialog(mode === "apply" ? "Apply tweaks" : "Undo tweaks", `${m.hostname}:\n${names}`,
        { okText: mode === "apply" ? "Apply" : "Undo" })) return;
      try {
        const j = await runAction(m.id, "tweaks.apply", { ids: [...sel], mode }, mode === "apply" ? "Apply tweaks" : "Undo tweaks");
        if (j?.result?.tweaks) {
          const bad = j.result.tweaks.filter((t) => t.ok === false);
          if (bad.length) toast(`${bad.length} tweak(s) failed`, "error");
        }
        sel.clear();
        await reload();
      } catch (e) { toastError(e); }
    }
    for (const sec of Object.keys(SECTION)) {
      const list = r.tweaks.filter((t) => t.section === sec);
      if (!list.length) continue;
      body.append(h("h3", { class: "muted small", style: "margin:16px 0 6px;text-transform:uppercase;letter-spacing:.6px" }, SECTION[sec]),
        h("div", { class: "card flush" }, table([
          { label: "", render: (t) => checkbox(sel.has(t.id), (on) => { on ? sel.add(t.id) : sel.delete(t.id); sync(); }, { disabled: !m.canRun }) },
          { label: "Tweak", render: (t) => h("div", {}, h("div", { class: "check-name" }, t.name, t.per_user ? h("span", { class: "tag" }, "per user") : null),
            h("div", { class: "check-detail" }, t.description), t.can_undo ? null : h("div", { class: "check-impact" }, "No undo")) },
          { label: "State", render: (t) => STATE_BADGE(t.applied) },
        ], list)));
    }
    if (m.canRun) body.append(h("div", { class: "sticky-bar" }, count, h("div", { class: "row" }, undoBtn, applyBtn)));
    sync();

    // preferences + power plan
    body.append(h("div", { class: "grid2", style: "margin-top:16px" },
      h("section", { class: "card" }, h("h2", {}, "Preferences"),
        h("p", { class: "muted small" }, "Apply at once. Explorer may need a restart or sign-out to show some."),
        table([
          { label: "Setting", render: (pf) => h("div", {}, h("div", { class: "check-name" }, pf.name), h("div", { class: "check-detail" }, pf.description)) },
          { label: "Now", render: (pf) => (pf.on === null ? badge("not set", "muted") : badge(pf.on ? "on" : "off", pf.on ? "ok" : "muted")) },
          {
            label: "", render: (pf) => m.canRun ? h("div", { class: "seg" },
              [true, false].map((on) => h("button", {
                class: pf.on === on ? "active" : "",
                onclick: async () => {
                  try { await runAndWait(m.id, "tweaks.pref", { id: pf.id, on }); await reload(); }
                  catch (e) { toastError(e); }
                },
              }, on ? "On" : "Off"))) : null,
          },
        ], r.preferences, { empty: "No preferences defined." })),
      r.has_power ? h("section", { class: "card" }, h("h2", {}, "Power plan"),
        h("p", {}, "Active: ", h("b", {}, r.power_plan || "unknown")),
        m.canRun ? h("div", { class: "row" },
          btn("Ultimate Performance", async () => { await runAction(m.id, "tweaks.power", { plan: "ultimate" }, "Power plan"); reload(); }),
          btn("Balanced", async () => { await runAction(m.id, "tweaks.power", { plan: "balanced" }, "Power plan"); reload(); })) : null)
        : null));
  };

  const refreshBtn = btn(st ? "Check again" : "Read current state", async () => {
    const j = await refresh(m.id, "tweaks.state", {}, refreshBtn);
    if (j.status === "succeeded") { st = j; draw(); }
  });
  p.append(h("section", { class: "card" }, head("Tweaks", m.canRun ? refreshBtn : null), when(st), body));
  draw();
}

// ================================================================= Cleanup

export async function renderCleanup(p, m) {
  clear(p);
  const panes = { windows: h("div", {}), profiles: h("div", { hidden: true }), disk: h("div", { hidden: true }) };
  const loaded = {};
  const RENDER = { windows: cleanWindows, profiles: cleanProfiles, disk: diskPane };
  const tabs = h("div", { class: "subtabs" }, Object.entries({ windows: "Windows cleanup", profiles: "User profiles", disk: "Disk analysis" })
    .map(([k, label]) => h("button", { class: k === "windows" ? "active" : "", dataset: { k }, onclick: () => show(k) }, label)));
  async function show(k) {
    tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.k === k));
    for (const [n, el] of Object.entries(panes)) el.hidden = n !== k;
    if (!loaded[k]) { loaded[k] = true; try { await RENDER[k](panes[k], m); } catch (e) { toastError(e); } }
  }
  p.append(tabs, ...Object.values(panes));
  show("windows");
}

async function cleanWindows(p, m) {
  let scan = await latest(m.id, "cleanup.scan");
  let sel = null;
  const body = h("div", {});
  const draw = () => {
    clear(body);
    if (!scan) { body.append(h("div", { class: "empty" }, "Not scanned yet. A scan only measures sizes (takes about a minute).")); return; }
    const items = scan.result.groups.flatMap((g) => g.items);
    if (!sel) sel = new Set(items.filter((i) => i.default).map((i) => i.id));
    const total = h("b", {});
    const go = btn("Clean", null, "danger");
    const sync = () => {
      const bytes = items.filter((i) => sel.has(i.id)).reduce((s, i) => s + (i.size || 0), 0);
      total.textContent = `${sel.size} selected · ${fmtBytes(bytes)}`;
      go.disabled = !sel.size || !m.canRun;
    };
    go.addEventListener("click", async () => {
      const chosen = items.filter((i) => sel.has(i.id));
      const risky = chosen.filter((i) => i.confirm);
      let msg = `Delete the contents of ${chosen.length} location(s) on ${m.hostname}:\n${chosen.map((i) => i.label).join("\n")}`;
      if (risky.length) msg += `\n\nCAREFUL:\n${risky.map((i) => i.confirm_msg || i.label).join("\n\n")}`;
      if (chosen.some((i) => i.slow)) msg += "\n\nSome items (component store) can take 5-15 minutes.";
      if (!await confirmDialog("Clean up", msg, { okText: "Clean", danger: true })) return;
      try {
        const j = await runAction(m.id, "cleanup.clean", { ids: chosen.map((i) => i.id) }, "Cleanup");
        if (j?.result) toast(`Freed ${fmtBytes(j.result.freed)}`, "ok");
        const s = await refresh(m.id, "cleanup.scan", {});
        if (s.status === "succeeded") { scan = s; sel = null; draw(); }
      } catch (e) { toastError(e); }
    });
    body.append(h("p", {}, "Reclaimable: ", h("b", {}, fmtBytes(scan.result.total))),
      h("div", { class: "app-groups" }, scan.result.groups.map((g) => h("div", { class: "app-group" },
        h("h3", {}, g.label),
        g.items.map((i) => h("label", { class: "check" },
          checkbox(sel.has(i.id), (on) => { on ? sel.add(i.id) : sel.delete(i.id); sync(); }, { disabled: !m.canRun }),
          h("span", { style: "flex:1" }, i.label), h("span", { class: "muted small mono" }, fmtBytes(i.size))))))),
      m.canRun ? h("div", { class: "sticky-bar" }, total, go) : null);
    sync();
  };
  const refreshBtn = btn(scan ? "Scan again" : "Scan sizes", async () => {
    const j = await refresh(m.id, "cleanup.scan", {}, refreshBtn);
    if (j.status === "succeeded") { scan = j; sel = null; draw(); }
  });
  p.append(h("section", { class: "card" }, head("Windows cleanup", m.canRun ? refreshBtn : null), when(scan), body));
  draw();
}

async function cleanProfiles(p, m) {
  let res = await latest(m.id, "cleanup.profiles");
  const body = h("div", {});
  const draw = () => {
    clear(body);
    if (!res) { body.append(h("div", { class: "empty" }, "Not scanned yet.")); return; }
    body.append(table([
      { label: "User", render: (pr) => h("div", {}, h("b", {}, pr.user), h("div", { class: "muted small mono" }, pr.path)) },
      { label: "Last used", key: "last_use" },
      { label: "Signed in", render: (pr) => (pr.loaded ? badge("yes", "info") : "") },
      { label: "Junk", render: (pr) => fmtBytes(pr.junk), num: true },
      { label: "", render: (pr) => (m.canRun && pr.categories?.length ? btn("Clean...", () => cleanOne(pr), "small") : null) },
    ], res.result.profiles, { empty: "No user profiles found." }));
  };
  async function cleanOne(pr) {
    const pick = new Set(pr.categories.filter((c) => c.size > 0).map((c) => c.id));
    const ok = await new Promise((resolve) => {
      let yes = false;
      const d = document.createElement("dialog");
      d.append(h("h2", {}, `Clean ${pr.user}`),
        h("div", { class: "stack" }, pr.categories.map((c) => h("label", { class: "check" },
          checkbox(pick.has(c.id), (on) => (on ? pick.add(c.id) : pick.delete(c.id))),
          h("span", { style: "flex:1" }, c.label), h("span", { class: "muted small mono" }, fmtBytes(c.size))))),
        pr.loaded ? h("p", { class: "muted small" }, "This user is signed in: files in use are skipped.") : null,
        h("div", { class: "dialog-actions" },
          h("button", { class: "btn ghost", onclick: () => d.close() }, "Cancel"),
          h("button", { class: "btn danger", onclick: () => { yes = true; d.close(); } }, "Clean")));
      d.addEventListener("close", () => { d.remove(); resolve(yes); });
      document.body.append(d);
      d.showModal();
    });
    if (!ok || !pick.size) return;
    try {
      const j = await runAction(m.id, "cleanup.profile_clean", { sid: pr.sid, categories: [...pick] }, `Clean ${pr.user}`);
      if (j?.result) toast(`Freed ${fmtBytes(j.result.freed)}`, "ok");
      const r = await refresh(m.id, "cleanup.profiles", {});
      if (r.status === "succeeded") { res = r; draw(); }
    } catch (e) { toastError(e); }
  }
  const refreshBtn = btn(res ? "Scan again" : "Scan profiles", async () => {
    const j = await refresh(m.id, "cleanup.profiles", {}, refreshBtn);
    if (j.status === "succeeded") { res = j; draw(); }
  });
  p.append(h("section", { class: "card" }, head("User profiles", m.canRun ? refreshBtn : null),
    h("p", { class: "muted small" }, "Temp files, browser caches, thumbnails and similar junk per user. Profiles themselves are never deleted."),
    when(res), body));
  draw();
}

async function diskPane(p, m) {
  let health = await latest(m.id, "disk.health");
  const drivesBox = h("div", {});
  const drawDrives = () => {
    clear(drivesBox);
    if (!health) { drivesBox.append(h("div", { class: "empty" }, "Not checked yet.")); return; }
    drivesBox.append(table([
      { label: "Drive", key: "letter" },
      { label: "Health", render: (d) => badge(d.health, d.health === "Healthy" ? "ok" : d.health === "Unknown" ? "muted" : "fail") },
      {
        label: "Used", render: (d) => {
          const used = d.size ? (d.size - d.free) / d.size : 0;
          return h("div", { class: "row" }, h("div", { class: `bar ${used > 0.9 ? "fail" : used > 0.8 ? "warn" : ""}` },
            h("span", { style: `width:${Math.round(used * 100)}%` })), `${Math.round(used * 100)}%`);
        },
      },
      { label: "Free", render: (d) => fmtBytes(d.free), num: true },
      { label: "Size", render: (d) => fmtBytes(d.size), num: true },
    ], health.result.drives));
  };
  const healthBtn = btn(health ? "Check again" : "Check drives", async () => {
    const j = await refresh(m.id, "disk.health", {}, healthBtn);
    if (j.status === "succeeded") { health = j; drawDrives(); }
  });

  let path = "C:\\";
  const input = h("input", { value: path, style: "min-width:320px", "aria-label": "Folder path" });
  const out = h("div", {});
  const scanBtn = btn("Scan folder", () => scan(input.value.trim()), "primary");
  async function scan(target) {
    path = target;
    input.value = target;
    clear(out).append(h("div", { class: "empty" }, `Measuring ${target} ... large folders take a while.`));
    scanBtn.disabled = true;
    try {
      const j = await runAndWait(m.id, "disk.folders", { path: target });
      clear(out);
      if (j.status !== "succeeded") { out.append(h("p", { class: "error" }, j.error || j.status)); return; }
      const r = j.result;
      const max = Math.max(1, ...r.folders.map((f) => f.size));
      out.append(table([
        { label: "Folder", render: (f) => h("a", { href: "#", onclick: (e) => { e.preventDefault(); scan(f.path); } }, f.path.split("\\").pop() || f.path) },
        { label: "", render: (f) => h("div", { class: "bar" }, h("span", { style: `width:${Math.round((f.size / max) * 100)}%` })) },
        { label: "Size", render: (f) => fmtBytes(f.size), num: true },
      ], r.folders, { empty: "No subfolders." }), h("p", { class: "muted small" }, `Files directly in this folder: ${fmtBytes(r.files_size)}`));
    } catch (e) { toastError(e); } finally { scanBtn.disabled = false; }
  }
  const up = btn("Up", () => {
    const parts = path.replace(/\\+$/, "").split("\\");
    if (parts.length > 1) scan(parts.length === 2 ? `${parts[0]}\\` : parts.slice(0, -1).join("\\"));
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") scan(input.value.trim()); });

  p.append(
    h("section", { class: "card" }, head("Drives", m.canRun ? healthBtn : null), when(health), drivesBox),
    h("section", { class: "card" }, h("h2", {}, "Folder sizes"),
      m.canRun ? h("div", { class: "toolbar" }, input, up, scanBtn) : h("p", { class: "muted" }, "Technicians can measure folder sizes."), out),
  );
  drawDrives();
}
