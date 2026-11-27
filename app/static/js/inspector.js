/* Inspector screen: map of zones by urgency, "where to go today", alert card, moderation, KPIs, demo controls. */
(function () {
  "use strict";
  const L$ = window.Lantern;
  const { t, esc, api } = L$;

  const S = {
    meta: null, map: null, alerts: [], settings: null,
    tab: "today", selected: null, detail: null, filter: "active", moreOpen: false,
    layers: new Map(), fitted: false, rendered: {}, withinHours: 24,
    data: { today: null, reviewReports: null, rejectReports: null, stats: null },
  };
  const ACTOR = "inspector";

  const $ = (sel) => document.querySelector(sel);
  function setHTML(el, key, html) {
    if (S.rendered[key] === html) return false;
    S.rendered[key] = html;
    el.innerHTML = html;
    L$.updateSince(el);
    return true;
  }

  // ---------------------------------------------------------------- boot
  async function boot() {
    try {
      S.meta = await api("/meta");
    } catch (e) {
      $("#panel").innerHTML = `<div class="empty">${esc(e.message)} <button class="btn" onclick="location.reload()">${esc(t("retry"))}</button></div>`;
      return;
    }
    S.settings = S.meta.settings;
    L$.syncFromSettings(S.settings);
    renderChrome();
    S.map = L$.makeMap($("#map"), S.meta);
    startNetwork();
    drawCameraZones();
    addLegend();
    S.map.on("zoomend", applyView);
    await refresh();
    setInterval(refresh, 3000);
    setInterval(tickCountdown, 1000);
    document.addEventListener("lantern:lang", () => { S.rendered = {}; renderChrome(); renderAll(); addLegend(); });
  }

  function renderChrome() {
    L$.renderHeader($("#top"), S.meta, "inspector");
    L$.renderFooter($("#foot"), S.meta);
    renderTabs();
    renderDemoBar(true);
  }

  // ---------------------------------------------------------------- polling
  async function refresh() {
    try {
      const res = await api("/alerts?role=inspector");
      S.alerts = res.alerts;
      S.settings = res.settings;
      L$.syncFromSettings(S.settings);
      const jobs = [api("/map/status?role=inspector").then((r) => { S.net = r; }).catch(() => {})];
      if (S.tab === "today") jobs.push(api("/inspection/today").then((r) => { S.data.today = r.alerts; }));
      if (S.tab === "reports") {
        jobs.push(api("/reports?role=inspector&relevant=review").then((r) => { S.data.reviewReports = r; }));
        jobs.push(api("/reports?role=inspector&relevant=reject").then((r) => { S.data.rejectReports = r; }));
        jobs.push(api("/spam?role=inspector").then((r) => { S.data.spam = r; }));
      }
      if (S.tab === "stats") jobs.push(api("/stats/response?within_hours=" + encodeURIComponent(S.withinHours)).then((r) => { S.data.stats = r; }));
      if (S.selected) {
        jobs.push(api(`/alerts/${S.selected}?role=inspector`).then((d) => { S.detail = d; })
          .catch((e) => { if (e.status === 404) { S.selected = null; S.detail = null; } }));
      }
      await Promise.all(jobs);
      renderAll();
    } catch (e) {
      console.warn("refresh failed", e);
    }
  }

  function renderAll() {
    updateMap();
    renderDemoBar(false);
    renderTabs();
    renderPanel();
  }

  // ---------------------------------------------------------------- demo bar (clock, snowfall, deadline)
  function renderDemoBar(force) {
    const el = $("#demo");
    const s = S.settings || {};
    if (force || !el.dataset.built) {
      el.innerHTML = `
        <span class="tag">${esc(t("demo"))}</span>
        <span class="kv">${esc(t("rigaTime"))}: <b id="dNow"></b> <span class="muted small" id="dClock"></span></span>
        <span class="kv">${esc(t("snowfallEnd"))}: <b id="dSnow"></b></span>
        <span class="kv" title="${esc(t("deadlineRule"))}">${esc(t("deadline"))}: <b id="dDeadline"></b> <span class="countdown" id="dCount"></span></span>
        <button class="btn" id="dSnowStart" type="button">${esc(t("btnSnowStart"))}</button>
        <button class="btn" id="dSnowBtn" type="button">${esc(t("btnSnowfall"))}</button>
        <button class="btn bad" id="dReset" type="button">${esc(t("btnReset"))}</button>`;
      el.dataset.built = "1";
      $("#dSnowStart").addEventListener("click", () => postSnowfall({ start: "now", source: "inspector" }));
      $("#dSnowBtn").addEventListener("click", () => postSnowfall({ end: "now", source: "inspector" }));
      $("#dReset").addEventListener("click", async () => {
        if (!confirm(t("confirmReset"))) return;
        try {
          await api("/admin/reset", { method: "POST" });
          S.selected = null; S.detail = null; S.rendered = {};
          clearAlertLayers();
          S.fitted = false;
          await refresh();
        } catch (e) { L$.toast(e.message, true); }
      });
    }
    const sf = s.snowfall;
    $("#dSnow").textContent = !sf ? t("snowUnknown")
      : (sf.end ? t("snowEnded", { t: L$.fmtTime(sf.end) }) : t("snowingSince", { t: L$.fmtTime(sf.start) }));
    $("#dDeadline").textContent = s.deadline ? L$.fmtTime(s.deadline) : (s.snowing ? "…" : t("notSet"));
    $("#dClock").textContent = s.clock && s.clock.mode === "demo" ? `(${t("demoClock", { f: s.clock.factor })})` : "";
    $("#dSnowBtn").disabled = !s.snowing && !!sf;
    tickCountdown();
  }

  function tickCountdown() {
    const n = $("#dNow");
    if (n) n.textContent = L$.clockText();
    const el = $("#dCount");
    if (!el || !S.settings) return;
    if (!S.settings.deadline) { el.textContent = ""; return; }
    const left = (new Date(S.settings.deadline).getTime() - L$.now()) / 1000;
    el.classList.toggle("passed", left <= 0);
    el.textContent = left <= 0 ? `(${t("passed")})` : `(${t("in")} ${L$.fmtDur(left)})`;
  }

  async function postSnowfall(body) {
    try {
      const r = await api("/snowfalls", { json: body });
      S.settings = r.settings;
      L$.syncFromSettings(S.settings);
      L$.toast(t("saved"));
      await refresh();
    } catch (e) { L$.toast(e.message, true); }
  }

  // ---------------------------------------------------------------- map
  function drawCameraZones() {
    const group = L.layerGroup().addTo(S.map);
    S.camGroup = group;
    const bounds = [];
    (S.meta.cameras || []).forEach((cam) => {
      bounds.push([cam.lat, cam.lon]);
      (cam.zones || []).forEach((z) => {
        // zone rectangles are not drawn: a camera alert is shown by its street section or square and a dot
        if (z.map_polygon) L$.toLatLngs(z.map_polygon).forEach((p) => bounds.push(p));
      });
      L.circleMarker([cam.lat, cam.lon], { radius: 3, color: "#7a8596", weight: 1, fillOpacity: .6, interactive: true })
        .bindTooltip(esc(cam.name || cam.camera_id)).addTo(group);
    });
    // the Finnish demo cameras are ~500 km away: start on Riga when there are cameras there, else on all cameras
    const riga = L.latLng(56.9496, 24.1052);
    const home = bounds.filter((p) => riga.distanceTo(L.latLng(p)) < 50000);
    const view = home.length ? home : bounds;
    if (view.length) S.map.fitBounds(view, { padding: [40, 40], maxZoom: 16 });
  }

  function addLegend() {
    if (S.legend) S.legend.remove();
    S.legend = L.control({ position: "bottomleft" });
    S.legend.onAdd = () => {
      const d = L.DomUtil.create("div", "map-legend");
      const c = L$.COLORS;
      d.innerHTML = (S.network ? S.network.legend() : "") + `<div class="legend-h">${esc(t("legendDots"))}</div>`
        + [["lv_high", c.high], ["lv_medium", c.medium], ["lv_low", c.low], ["closedL", c.verified]]
          .map(([k, col]) => `<div><i class="dot" style="background:${col}"></i>${esc(t(k))}</div>`).join("")
        + `<div class="legend-note">${esc(t("dotsZoomNote"))}</div>`;
      return d;
    };
    S.legend.addTo(S.map);
  }

  function clearAlertLayers() {
    S.layers.forEach((l) => l.marker.remove());
    S.layers.clear();
  }

  // anti-fake flags from the server: why this report waits for the inspector instead of going straight on
  function trustChips(r) {
    const live = r.capture === "live" ? `<div class="flag flag-ok" title="${esc(t("captureTip_live"))}">${esc(t("capture_live"))}</div>` : "";
    return live + (r.flags || []).map((f) => `<div class="flag flag-red" title="${esc(t("flagTip_" + f))}">${esc(t("flag_" + f))}</div>`).join("");
  }

  function styleFor(a) {
    const col = L$.alertColor(a);
    const sel = S.selected === a.id;
    const verified = L$.isClosed(a);
    return {
      marker: { radius: sel ? 11 : (verified ? 5 : 8), color: a.status === "reopened" ? L$.COLORS.reopened : "#ffffff",
        weight: a.status === "reopened" ? 4 : 2, fillColor: col, fillOpacity: verified ? 0.55 : 0.95,
        dashArray: a.status === "watch" ? "3 3" : null },
    };
  }

  // The sidewalk network, drawn like Riga's pGIS: every stretch is a thin line in the colour of its latest
  // alert (blue none, red registered, yellow started, green finished); click a coloured one to open its alert
  function startNetwork() {
    S.network = L$.sidewalkNetwork(S.map, {
      onPick: (st, b, line) => {
        S.map.fitBounds(line.getBounds(), { padding: [80, 80], maxZoom: 18 });
        select(st.alert_id, false);
      },
    });
    S.network.ready.then(() => { addLegend(); if (S.net) S.network.setStatus(S.net.blocks); });
  }

  // ---------------------------------------------------------------- zoom levels
  // Far away (zoom < DOT_ZOOM): only the coloured sidewalk lines, like Riga's pGIS - no dots, no bubbles.
  // Close up (zoom >= DOT_ZOOM): every alert's dot on its line. Block view (zoom >= DETAIL_ZOOM): camera positions too.
  const DOT_ZOOM = L$.DOT_ZOOM;
  const DETAIL_ZOOM = 17;

  function show(layer, on) {
    if (!layer) return;
    if (on && !S.map.hasLayer(layer)) layer.addTo(S.map);
    if (!on && S.map.hasLayer(layer)) layer.remove();
  }

  function applyView() {
    if (!S.map) return;
    const z = S.map.getZoom();
    show(S.camGroup, z >= DETAIL_ZOOM);
    S.alerts.forEach((a) => {
      const l = S.layers.get(a.id);
      if (l) show(l.marker, z >= DOT_ZOOM);
    });
  }

  function updateMap() {
    if (!S.map) return;
    if (S.network && S.net) S.network.setStatus(S.net.blocks);
    // an alert is drawn on its sidewalk line (the backend snaps it), not on a roof or in the road
    const dotAt = new Map(Object.entries((S.net && S.net.points) || {}).map(([id, p]) => [Number(id), p]));
    const seen = new Set();
    const bounds = [];
    S.alerts.forEach((a) => {
      seen.add(a.id);
      const st = styleFor(a);
      let l = S.layers.get(a.id);
      const tip = `${esc(t("caseNo"))} ${a.id} · ${esc(t("st_" + a.status))}${a.overdue ? " · " + esc(t("overdue")) : ""}<br>${esc(L$.place(a.place_type))}, ${esc(a.district || "")}`;
      if (!l) {
        l = {};
        l.marker = L.circleMarker(dotAt.get(a.id) || a.map_point || [a.lat, a.lon], st.marker).addTo(S.map);
        l.marker.on("click", () => select(a.id));
        l.marker.bindTooltip(tip);
        S.layers.set(a.id, l);
      } else {
        l.marker.setStyle(st.marker);
        l.marker.setRadius(st.marker.radius);
        l.marker.setLatLng(dotAt.get(a.id) || a.map_point || [a.lat, a.lon]);
        l.marker.setTooltipContent(tip);
      }
      if (!L$.isClosed(a) && S.map.hasLayer(l.marker)) l.marker.bringToFront();
      bounds.push([a.lat, a.lon]);
    });
    S.layers.forEach((l, id) => { if (!seen.has(id)) { l.marker.remove(); S.layers.delete(id); } });
    if (!S.fitted && bounds.length) {
      S.fitted = true;
      S.map.fitBounds(L.latLngBounds(bounds), { padding: [50, 50], maxZoom: 16 });  // frame the alerts, not every camera
    }
    applyView();
  }

  function select(id, pan = true) {
    S.selected = id;
    S.detail = null;
    renderPanel();
    updateMap();
    api(`/alerts/${id}?role=inspector`).then((d) => { S.detail = d; renderPanel(); }).catch((e) => L$.toast(e.message, true));
    const l = S.layers.get(id);
    // the dots only show close up: picking an alert from the list flies in to it
    if (l && pan) S.map.setView(l.marker.getLatLng(), Math.max(S.map.getZoom(), DOT_ZOOM + 1), { animate: true });
  }

  // ---------------------------------------------------------------- tabs
  function renderTabs() {
    const reviewCount = S.alerts.filter((a) => !L$.isClosed(a) && (a.inspector_flags || []).includes("review_report")).length;
    const active = S.alerts.filter((a) => !L$.isClosed(a)).length;
    const tabs = [["today", t("tabToday")], ["all", t("tabAll"), active], ["reports", t("tabReports"), reviewCount || null], ["stats", t("tabStats")]];
    const html = tabs.map(([k, label, n]) => `<button role="tab" type="button" data-tab="${k}" aria-selected="${S.tab === k && !S.selected}">${esc(label)}${n ? `<span class="count">${n}</span>` : ""}</button>`).join("");
    if (setHTML($("#tabs"), "tabs", html)) {
      $("#tabs").querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
        S.tab = b.dataset.tab; S.selected = null; S.detail = null; S.rendered.panel = null;
        renderTabs(); renderPanel(); updateMap(); refresh();
      }));
    }
  }

  function renderPanel() {
    const el = $("#panel");
    if (S.selected) return renderCard(el);
    let html;
    if (S.tab === "today") html = todayHTML();
    else if (S.tab === "all") html = allHTML();
    else if (S.tab === "reports") html = reportsHTML();
    else html = statsHTML();
    if (setHTML(el, "panel", html)) bindPanel(el);
  }

  function bindPanel(el) {
    el.querySelectorAll("[data-alert]").forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); select(+b.dataset.alert); }));
    const f = el.querySelector("#statusFilter");
    if (f) f.addEventListener("change", () => { S.filter = f.value; renderPanel(); });
    el.querySelectorAll("[data-moderate]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await api(`/reports/${b.dataset.id}/moderate`, { json: { decision: b.dataset.moderate, actor: ACTOR } });
        L$.toast(t("saved"));
        await refresh();
      } catch (e) { L$.toast(e.message, true); b.disabled = false; }
    }));
    el.querySelectorAll("[data-block]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm(t("blockAsk"))) return;
      b.disabled = true;
      try {
        await api(`/reports/${b.dataset.block}/block-sender`, { json: { hours: 24, actor: ACTOR } });
        L$.toast(t("saved"));
        await refresh();
      } catch (e) { L$.toast(e.message, true); b.disabled = false; }
    }));
    el.querySelectorAll("[data-unblock]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await api("/devices/unblock", { json: { device_id: b.dataset.unblock } });
        L$.toast(t("saved"));
        await refresh();
      } catch (e) { L$.toast(e.message, true); b.disabled = false; }
    }));
    const wh = el.querySelector("#withinH");
    if (wh) wh.addEventListener("change", () => { const v = parseFloat(wh.value); if (v > 0) { S.withinHours = v; refresh(); } });
  }

  // only what is worth a glance in the list; everything else is in the card
  const LIST_FLAGS = ["overdue", "reopened", "high", "possible_ice", "ice_report", "check_done", "review_report", "no_camera", "problem_place"];
  const RED_FLAGS = ["overdue", "high", "possible_ice", "ice_report"];
  const flagHTML = (w) => `<span class="flag ${RED_FLAGS.includes(w) ? "flag-red" : ""}">${esc(t("why_" + w))}</span>`;

  function itemHTML(a, rank) {
    const flags = (a.why || a.inspector_flags || []).filter((w) => LIST_FLAGS.includes(w));
    if (a.overdue && !flags.includes("overdue")) flags.unshift("overdue");
    const meta = [
      `${esc(t("caseShort"))} ${a.id}`,
      esc(a.contractor_name || ""),
      a.zone_id ? esc(t("srcCamera")) : "",
      a.report_count ? esc(t("nReports", { n: a.report_count })) : "",
      L$.sinceSpan(a.first_seen_at, t("ago")),
    ].filter(Boolean).join(" · ");
    return `<button type="button" class="item ${S.selected === a.id ? "active" : ""}" data-alert="${a.id}">
      <span class="bar" style="background:${L$.alertColor(a)}"></span>
      <span class="item-main">
        <span class="title">${rank ? `<span class="rank">${rank}.</span>` : ""}${esc(L$.place(a.place_type))}, ${esc(a.district || t("none"))}</span>
        <span class="meta">${meta}</span>
        ${flags.length ? `<span class="flags">${flags.map(flagHTML).join("")}</span>` : ""}
      </span>
      <span class="right">${L$.statusBadge(a.status)}</span>
    </button>`;
  }

  function todayHTML() {
    const list = S.data.today;
    if (!list) return `<div class="empty">${esc(t("loading"))}</div>`;
    return `<div class="panel-head"><h2>${esc(t("tabToday"))}</h2></div>
      <p class="muted small" style="margin-top:-4px">${esc(t("todayHint", { h: (S.settings && S.settings.inspection_hours) || "08:30-17:00" }))}</p>
      ${list.length ? list.map((a, i) => itemHTML(a, i + 1)).join("") : `<div class="empty">${esc(t("nothingToday"))}</div>`}`;
  }

  function allHTML() {
    const order = { reopened: 0, open: 1, done_reported: 2, watch: 3, verified: 4, cleared_in_time: 5 };
    let list = S.alerts.slice();
    if (S.filter === "active") list = list.filter((a) => !L$.isClosed(a));
    else if (S.filter !== "all") list = list.filter((a) => a.status === S.filter);
    list.sort((a, b) => (order[a.status] - order[b.status]) || (b.urgency_score - a.urgency_score) || (b.id - a.id));
    const opts = [["active", t("activeOnly")], ["all", t("allStatuses")]].concat(["watch", "open", "done_reported", "reopened", "verified", "cleared_in_time"].map((s) => [s, t("st_" + s)]));
    return `<div class="panel-head"><h2>${esc(t("tabAll"))}</h2>
        <select id="statusFilter" aria-label="Status">${opts.map(([v, l]) => `<option value="${v}" ${S.filter === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
      ${list.length ? list.map((a) => itemHTML(a)).join("") : `<div class="empty">${esc(t("noAlerts"))}</div>`}`;
  }

  function modHTML(r, showActions) {
    const ai = [r.relevant, r.ai_hint].filter(Boolean).join(" · ");
    return `<div class="mod">
      ${r.photo_url ? `<img src="${esc(r.photo_url)}" data-zoom="${esc(r.photo_url)}" alt="" loading="lazy">` : "<div></div>"}
      <div>
        <div><b>${esc(t("reportNo"))} ${r.id}</b> · ${esc(L$.fmtTime(r.timestamp))}</div>
        <div class="small">${esc(t("ps_" + r.passable))}${r.passable_by === "ai" ? ` (${esc(t("byAi"))})` : ""} · ${esc(L$.hazard(r.hazard))} · ${esc(L$.place(r.place_type))}</div>
        ${r.comment ? `<div class="small">“${esc(r.comment)}”</div>` : ""}
        ${r.registration_no ? `<div class="small">${esc(t("regNo"))}: <b>${esc(r.registration_no)}</b></div>` : ""}
        <div class="small muted">${esc(t("aiSays"))}: ${esc(ai)}${r.ai_note ? ` — ${esc(r.ai_note)}` : ""}</div>
        ${r.same_photo_as ? `<div class="flag flag-red">${esc(t("samePhotoAs", { n: r.same_photo_as }))}</div>` : ""}
        ${trustChips(r)}
        ${r.alert_id ? `<div class="small"><a href="#" data-alert="${r.alert_id}">${esc(t("caseNo"))} ${r.alert_id}</a></div>` : ""}
        ${showActions ? `<div class="actions" style="margin-top:6px">
          <button class="btn good" type="button" data-moderate="accept" data-id="${r.id}">${esc(t("accept"))}</button>
          ${r.relevant !== "reject" ? `<button class="btn bad" type="button" data-moderate="reject" data-id="${r.id}">${esc(t("reject"))}</button>` : ""}
          <button class="btn" type="button" data-block="${r.id}">${esc(t("blockSender"))}</button>
        </div>` : ""}
      </div></div>`;
  }

  function reportsHTML() {
    const rv = S.data.reviewReports, rj = S.data.rejectReports;
    if (!rv || !rj) return `<div class="empty">${esc(t("loading"))}</div>`;
    const pending = rv.filter((r) => !r.moderated_by);
    return `<div class="panel-head"><h2>${esc(t("reviewQueue"))} (${pending.length})</h2></div>
      ${pending.length ? pending.map((r) => modHTML(r, true)).join("") : `<div class="empty">${esc(t("noReview"))}</div>`}
      <div class="panel-head" style="margin-top:14px"><h2>${esc(t("rejected"))} (${rj.length})</h2></div>
      ${rj.length ? rj.map((r) => modHTML(r, true)).join("") : `<div class="empty">${esc(t("noRejected"))}</div>`}
      ${spamHTML()}`;
  }

  // Spam protection: what was refused or not counted in the last 24 h, and who is blocked (app/spam.py)
  function spamHTML() {
    const sp = S.data.spam;
    if (!sp) return "";
    const ev = Object.entries(sp.events || {}).filter(([, n]) => n > 0);
    const L = sp.limits;
    return `<div class="panel-head" style="margin-top:14px"><h2>${esc(t("spamTitle"))}</h2></div>
      ${ev.length ? `<table class="tbl"><tbody>${ev.map(([k, n]) => `<tr><td>${esc(t("sp_" + k))}</td><td class="num">${n}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">${esc(t("none"))}</div>`}
      <div class="small muted" style="margin:6px 0">${esc(t("spLimits", { h: L.device_per_hour, d: L.device_per_day, ip: L.ip_per_hour, bh: L.auto_block_hours, r: L.auto_block_rejects, dup: L.auto_block_duplicates }))}</div>
      <h3 class="small" style="margin-top:10px">${esc(t("blockedSenders"))} (${sp.blocked.length})</h3>
      ${sp.blocked.length ? sp.blocked.map((b) => `<div class="mod"><div></div><div>
          <div><b>${esc(b.device_id.slice(0, 8))}</b> · ${esc(b.reason || "")}</div>
          <div class="small muted">${esc(b.blocked_by || "")} · ${esc(t("until"))} ${esc(L$.fmtTime(b.blocked_until))}</div>
          <div class="actions" style="margin-top:6px"><button class="btn" type="button" data-unblock="${esc(b.device_id)}">${esc(t("unblock"))}</button></div>
        </div></div>`).join("") : `<div class="empty">${esc(t("noBlocked"))}</div>`}`;
  }

  function statsTable(rows, nameKey) {
    const n = S.data.stats.within_hours, k = S.data.stats.notify_kpi_minutes;
    return `<div class="tbl-wrap"><table class="tbl"><thead><tr>
      <th>${esc(nameKey)}</th><th class="num">${esc(t("c_opened"))}</th><th class="num">${esc(t("c_verified"))}</th>
      <th class="num">${esc(t("c_avg"))}</th><th class="num">${esc(t("c_within", { n }))}</th><th class="num">${esc(t("c_reopened"))}</th>
      <th class="num">${esc(t("c_overdue"))}</th>
      <th class="num">${esc(t("c_notify"))}</th><th class="num">${esc(t("c_kpi", { n: k }))}</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td>${esc(r.name || r.id)}</td><td class="num">${r.opened}</td><td class="num">${r.verified}</td>
        <td class="num">${L$.hours(r.avg_response_hours)}</td><td class="num">${L$.pct(r.share_within)}</td>
        <td class="num">${r.reopened_times}</td>
        <td class="num" style="${r.overdue ? "color:var(--high);font-weight:700" : ""}">${r.overdue}</td>
        <td class="num">${r.avg_notify_minutes == null ? t("none") : Math.round(r.avg_notify_minutes)}</td>
        <td class="num">${L$.pct(r.share_notify_kpi)}</td></tr>`).join("")}
      </tbody></table></div>`;
  }

  function statsHTML() {
    const st = S.data.stats;
    if (!st) return `<div class="empty">${esc(t("loading"))}</div>`;
    const exp = `<div class="actions" style="margin:6px 0 12px">
      <a class="btn" href="/export.geojson" download>${esc(t("exportGeo"))}</a>
      <a class="btn" href="/export.csv" download>${esc(t("exportCsv"))}</a></div>`;
    const head = `<div class="panel-head"><h2>${esc(t("tabStats"))}</h2>
      <span class="group"><label class="muted small" for="withinH">${esc(t("withinH"))}</label>
      <input id="withinH" type="number" min="0.5" step="0.5" value="${esc(S.withinHours)}" style="width:70px;padding:6px;border:1px solid var(--line);border-radius:7px;background:var(--surface-2)"></span></div>`;
    const k = st.kpi || {};
    const tile = (title, val, sub) => `<div class="kpi"><div class="kpi-v">${esc(val)}</div><div class="kpi-t">${esc(title)}</div><div class="small muted">${esc(sub)}</div></div>`;
    const kpis = `<div class="kpis">
      ${tile(t("kpi1"), k.false_alarms_per_hour == null ? t("none") : String(k.false_alarms_per_hour), t("kpi1Sub", { n: k.false_alarm_jobs || 0, h: k.camera_hours || 0 }))}
      ${tile(t("kpi2", { n: k.notify_minutes || 15 }), L$.pct(k.notify_share), t("kpi2Sub", { a: k.notify_ok || 0, b: k.notify_total || 0 }))}
      ${tile(t("kpi3"), L$.pct(k.precise_share), t("kpi3Sub", { a: k.precise || 0, b: k.signals_total || 0 }))}</div>`;
    if (!st.by_contractor.length) return head + kpis + `<div class="empty">${esc(t("noStats"))}</div>` + exp;
    return head + kpis + `<h3 class="muted small">${esc(t("byContractor"))}</h3>${statsTable(st.by_contractor, t("contractorL"))}
      <h3 class="muted small" style="margin-top:14px">${esc(t("byDistrict"))}</h3>${statsTable(st.by_district, t("district"))}
      <p class="muted small">${esc(t("statsNote"))}</p>${exp}`;
  }

  // ---------------------------------------------------------------- alert card
  function frameFig(label, frame, crop) {
    if (!frame && !crop) return `<figure></figure>`;
    const src = frame || crop;
    return `<figure><img src="${esc(src)}" data-zoom="${esc(src)}" alt="${esc(label)}" loading="lazy">
      <figcaption>${esc(label)}${crop && frame ? ` · <a href="${esc(crop)}" data-zoom="${esc(crop)}">${esc(t("crop"))}</a>` : ""}</figcaption></figure>`;
  }

  function cardHTML(d) {
    const flags = (d.inspector_flags || []).filter((f) => f !== "low_confidence");
    const src = (d.source_types || []).map((s) => t(s === "camera" ? "srcCamera" : "srcResidents")).join(", ");
    const facts = [
      [t("contractorL"), esc(d.contractor_name || t("none"))],
      [t("fixDue"), d.fix_due_at ? `${esc(L$.fmtTime(d.fix_due_at))}${d.overdue ? ` <span class="flag flag-red">${esc(t("overdue"))}</span>` : ""}` : esc(t("none"))],
      [t("detectedBy"), esc(src || t("none"))],
      [t("firstSeen"), esc(L$.fmtTime(d.first_seen_at))],
      [t("situation"), esc(t("hz_" + (d.hazard_now || "other")))],
    ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("");

    // camera frames before / after; resident photos have their own section
    const photos = d.before_frame_url || d.after_frame_url
      ? `<div class="ba">${frameFig(t("before"), d.before_frame_url, d.before_crop_url)}${d.after_frame_url ? frameFig(t("after"), d.after_frame_url, d.after_crop_url) : "<figure></figure>"}</div>` : "";
    const reps = (d.reports || []).map((r) => `<div class="photo-item">
        ${r.photo_url ? `<img src="${esc(r.photo_url)}" data-zoom="${esc(r.photo_url)}" alt="" loading="lazy">` : ""}
        <div><b>${esc(t("ps_" + r.passable))}</b> · ${esc(L$.fmtTime(r.timestamp))}</div>
        ${r.comment ? `<div>“${esc(r.comment)}”</div>` : ""}
        ${r.registration_no ? `<div>${esc(t("regNo"))}: ${esc(r.registration_no)}</div>` : ""}
        ${r.duplicate ? `<div class="flag">${esc(t("duplicate"))}</div>` : (!r.counted ? `<div class="flag">${esc(t("notCounted"))}</div>` : "")}
        ${trustChips(r)}
      </div>`).join("");

    const acts = [];
    if (d.status === "watch") acts.push(["open", t("actDispatch"), "primary"]);
    if (d.status === "watch") acts.push(["cleared_in_time", t("actClean"), "good"]);
    else if (!L$.isClosed(d)) acts.push(["verified", t("actVerify"), "good"]);
    if (!L$.isClosed(d)) acts.push(["false_alarm", t("actFalse"), ""]);
    if (d.status === "done_reported") acts.push(["reopened", t("actDispute"), "bad"]);
    if (d.status === "verified" && d.opened_at) acts.push(["reopened", t("actReopenVerified"), "bad"]);

    // the details an inspector rarely needs: closed by default
    const reasons = (d.urgency_reasons || []).map((r) => `<li><span>${esc(L$.reasonText(r))}</span><span class="pts">${r.points != null ? "+" + r.points : ""}</span></li>`).join("");
    const tl = [
      [t("deadlineAt"), L$.fmtTime(d.deadline_at)],
      [t("detected"), L$.fmtTime(d.detected_at)],
      [t("opened"), L$.fmtTime(d.notified_at)],
      [t("doneReported"), L$.fmtTime(d.done_reported_at)],
      [t("verified"), L$.fmtTime(d.verified_at)],
      [t("responseTime"), d.response_hours != null ? `${L$.hours(d.response_hours)} ${t("h")}` : t("none")],
      [t("notifyDelay"), d.notify_seconds != null ? L$.fmtDur(d.notify_seconds) : t("none")],
      [t("reopenedTimes"), `${d.reopened_count} ${t("times")}`],
    ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
    const sigs = (d.signals || []).length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>${esc(t("time"))}</th><th>${esc(t("cls"))}</th><th class="num">${esc(t("share"))}</th><th class="num">${esc(t("conf"))}</th><th></th></tr></thead><tbody>
      ${d.signals.slice().reverse().map((s) => `<tr><td>${esc(L$.fmtTime(s.timestamp))}</td><td>${esc(L$.hazard(s.hazard_class))}</td>
        <td class="num">${L$.pct(s.blocked_share)}</td><td class="num">${(+s.confidence).toFixed(2)}</td>
        <td>${s.frame_url ? `<a href="${esc(s.frame_url)}" data-zoom="${esc(s.frame_url)}">${esc(t("fullFrame"))}</a>` : ""}</td></tr>`).join("")}</tbody></table></div>` : "";
    const hist = `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>${esc(t("when"))}</th><th>${esc(t("to"))}</th><th>${esc(t("who"))}</th><th>${esc(t("note"))}</th></tr></thead><tbody>
      ${(d.history || []).slice().reverse().map((h) => `<tr><td>${esc(L$.fmtTime(h.at))}</td><td>${esc(t("st_" + h.to_status))}</td><td>${esc(h.actor)}</td><td>${esc(h.note || "")}</td></tr>`).join("")}
      </tbody></table></div>`;

    return `<div class="card">
      <button class="btn link card-back" type="button" id="cardBack">← ${esc(t("backToList"))}</button>
      <section class="case-head">
        <div class="case-no">${esc(t("caseNo"))} ${d.id}</div>
        <h2>${esc(L$.place(d.place_type))}, ${esc(d.district || t("none"))}</h2>
        <div class="status-line">${L$.statusBadge(d.status)}${d.false_alarm ? `<span class="flag">${esc(t("falseAlarm"))}</span>` : ""}${d.flagged_for_council ? `<span class="flag">${esc(t("flagCouncil"))}</span>` : ""}${flags.map(flagHTML).join("")}</div>
        ${d.status === "watch" ? `<div class="note-box">${esc(t("watchNote"))}</div>` : ""}
        ${d.status === "cleared_in_time" ? `<div class="note-box">${esc(t("clearedNote"))}</div>` : ""}
        <dl class="facts">${facts}</dl>
      </section>
      ${photos ? `<section><h3>${esc(t("evidence"))}</h3>${photos}</section>` : ""}
      <section><h3>${esc(t("decision"))}</h3>
        ${acts.length ? `<textarea id="actNote" class="field" maxlength="500" placeholder="${esc(t("noteLabel"))}" aria-label="${esc(t("noteLabel"))}"></textarea>
        <div class="actions">${acts.map(([s, label, cls]) => `<button class="btn ${cls}" type="button" data-act="${s}">${esc(label)}</button>`).join("")}</div>
        <div class="err" id="actErr" role="alert"></div>` : `<p class="muted small">${esc(t("noDecision"))}</p>`}
        ${d.evidence_url ? `<p class="small" style="margin:10px 0 0"><a href="${esc(d.evidence_url)}&lang=${esc(L$.lang)}" target="_blank" rel="noopener" title="${esc(t("evidenceHint"))}">${esc(t("evidencePack"))}</a> · <span class="muted">${esc(t("evidenceHint"))}</span></p>` : ""}
      </section>
      ${warnHTML(d)}
      ${reps ? `<section><h3>${esc(t("reports"))} (${d.report_count})</h3><div class="photos">${reps}</div></section>` : ""}
      <details class="more" id="more" ${S.moreOpen ? "open" : ""}><summary>${esc(t("moreDetails"))}</summary>
        <h4>${esc(t("timeline"))}</h4><dl class="timeline">${tl}</dl>
        <h4>${esc(t("why"))}</h4><ul class="reasons">${reasons || `<li class="muted">${esc(t("none"))}</li>`}</ul>
        ${sigs ? `<h4>${esc(t("signals"))} (${d.signals.length})</h4>${sigs}` : ""}
        <h4>${esc(t("history"))}</h4>${hist}
        ${d.zone_id ? `<p class="small muted">${esc(t("zone"))}: ${esc(d.zone_id)}</p>` : ""}
      </details>
    </div>`;
  }

  // the written warning to the contractor (replaces the old "defect act" fine button)
  function warnHTML(d) {
    const can = ["open", "done_reported", "reopened"].includes(d.status) && d.contractor_id;
    const sent = (d.warnings || []).map((w) => `<li><span class="when">${esc(L$.fmtTime(w.at))}</span><span>${esc(w.message)}</span></li>`).join("");
    return `<section><h3>${esc(t("warnTitle"))}${d.contractor_name ? ` · ${esc(d.contractor_name)}` : ""}</h3>
      ${can ? `<div class="warn-form">
          <textarea id="warnMsg" class="field" maxlength="500" placeholder="${esc(t("warnPlaceholder"))}" aria-label="${esc(t("warnTitle"))}"></textarea>
          <div class="actions"><button class="btn primary" type="button" id="warnSend">${esc(t("warnSend"))}</button></div>
          <div class="err" id="warnErr" role="alert"></div>
        </div>` : `<p class="muted small">${esc(t("warnNotYet"))}</p>`}
      ${sent ? `<div class="small muted" style="margin-top:10px">${esc(t("warnHistory"))}</div><ul class="warn-list">${sent}</ul>` : ""}
    </section>`;
  }

  function renderCard(el) {
    const d = S.detail;
    if (!d || d.id !== S.selected) {
      setHTML(el, "panel", `<button class="btn card-back" type="button" id="cardBack">← ${esc(t("back"))}</button><div class="empty">${esc(t("loading"))}</div>`);
      bindCard(el);
      return;
    }
    // don't disturb typing: the panel re-renders on every poll
    const typing = ["actNote", "warnMsg"].some((id) => { const x = el.querySelector("#" + id); return x && document.activeElement === x; });
    if (typing) return;
    const keep = {};
    ["actNote", "warnMsg"].forEach((id) => { const x = el.querySelector("#" + id); if (x) keep[id] = x.value; });
    const errs = {};
    ["actErr", "warnErr"].forEach((id) => { const x = el.querySelector("#" + id); if (x) errs[id] = x.textContent; });
    if (setHTML(el, "panel", cardHTML(d))) {
      Object.entries(keep).forEach(([id, v]) => { const x = el.querySelector("#" + id); if (x) x.value = v; });
      Object.entries(errs).forEach(([id, v]) => { const x = el.querySelector("#" + id); if (x) x.textContent = v; });
      bindCard(el);
    }
  }

  function bindCard(el) {
    const more = el.querySelector("#more");
    if (more) more.addEventListener("toggle", () => { S.moreOpen = more.open; });
    const back = el.querySelector("#cardBack");
    if (back) back.addEventListener("click", () => { S.selected = null; S.detail = null; S.rendered.panel = null; renderTabs(); renderPanel(); updateMap(); });
    const send = el.querySelector("#warnSend");
    if (send) send.addEventListener("click", async () => {
      const box = el.querySelector("#warnMsg");
      const errEl = el.querySelector("#warnErr");
      const message = (box && box.value || "").trim();
      if (errEl) errEl.textContent = "";
      if (!message) { if (errEl) errEl.textContent = t("warnEmpty"); if (box) box.focus(); return; }
      send.disabled = true;
      try {
        S.detail = await api(`/alerts/${S.selected}/warning`, { json: { role: "inspector", actor: ACTOR, message } });
        if (box) box.value = "";
        S.rendered.panel = null;
        L$.toast(t("warnSent"));
        await refresh();
      } catch (e) {
        send.disabled = false;
        if (errEl) errEl.textContent = e.message;
        L$.toast(e.message, true);
      }
    });
    el.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
      const note = (el.querySelector("#actNote") || {}).value || "";
      const errEl = el.querySelector("#actErr");
      if (errEl) errEl.textContent = "";
      el.querySelectorAll("[data-act]").forEach((x) => { x.disabled = true; });
      try {
        const fa = b.dataset.act === "false_alarm";  // KPI 1: the inspector found no snow on site
        S.detail = await api(`/alerts/${S.selected}/status`, { json: { status: fa ? "verified" : b.dataset.act, false_alarm: fa,
          role: "inspector", actor: ACTOR, note } });
        S.rendered.panel = null;
        const n = el.querySelector("#actNote"); if (n) n.value = "";
        L$.toast(t("saved"));
        await refresh();
      } catch (e) {
        el.querySelectorAll("[data-act]").forEach((x) => { x.disabled = false; });
        if (errEl) errEl.textContent = e.message;
        L$.toast(e.message, true);
      }
    }));
  }

  boot();
})();
