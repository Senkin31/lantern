/* Inspector screen: map of zones by urgency, "where to go today", alert card, moderation, KPIs, demo controls. */
(function () {
  "use strict";
  const L$ = window.Lantern;
  const { t, esc, api } = L$;

  const S = {
    meta: null, map: null, alerts: [], settings: null,
    tab: "today", selected: null, detail: null, filter: "active",
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
      const jobs = [api("/sections?role=inspector").then((r) => { S.sections = r.sections; }).catch(() => {})];
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
        <button class="btn" id="dSnowStart" type="button">🌨 ${esc(t("btnSnowStart"))}</button>
        <button class="btn primary" id="dSnowBtn" type="button">❄ ${esc(t("btnSnowfall"))}</button>
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
      d.innerHTML = [["high", c.high], ["medium", c.medium], ["low", c.low]].map(([k, col]) => `<div><i style="background:${col}"></i>${esc(t("lv_" + k))}</div>`).join("")
        + `<div><i style="background:${c.watch}"></i>${esc(t("st_watch"))}</div>`
        + `<div><i style="background:${c.reopened}"></i>${esc(t("st_reopened"))}</div>`
        + `<div><i style="background:${c.verified}"></i>${esc(t("st_verified"))}</div>`
        + `<div><i style="background:${c.cleared}"></i>${esc(t("st_cleared_in_time"))}</div>`
        + `<div><i style="background:${c.high};height:5px;border-radius:3px;margin-top:4px"></i>${esc(t("sectionLegend"))}</div>`
        + `<div><i class="legend-bubble" style="background:${c.medium}">3</i>${esc(t("bubbleLegend"))}</div>`;
      return d;
    };
    S.legend.addTo(S.map);
  }

  function clearAlertLayers() {
    S.layers.forEach((l) => l.marker.remove());
    S.layers.clear();
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

  // Street sections: a block of sidewalk/street with a camera alert or 2+ residents, in its worst alert's colour
  function updateSections() {
    if (!S.sectionLayer) S.sectionLayer = L.layerGroup().addTo(S.map);
    const key = JSON.stringify((S.sections || []).map((s) => [s.id, s.status, s.urgency_level, s.alert_ids]));
    if (key === S.sectionKey) return;
    S.sectionKey = key;
    S.sectionLayer.clearLayers();
    (S.sections || []).forEach((s) => {
      const col = L$.alertColor({ status: s.status, urgency_level: s.urgency_level });
      const dash = s.status === "watch" ? "8 8" : null;
      // a square is one place: paint the whole area; a street: a thick line along the block
      const line = s.shape === "area"
        ? L.polygon(s.coords, { color: col, weight: 3, fillColor: col, fillOpacity: 0.35, dashArray: dash }).addTo(S.sectionLayer)
        : L.polyline(s.coords, { color: col, weight: 9, opacity: 0.7, lineCap: "round", dashArray: dash }).addTo(S.sectionLayer);
      const who = [s.camera ? "📷" : "", s.residents ? `${s.residents} 👤` : ""].filter(Boolean).join(" · ");
      const size = s.shape === "area" ? `${t("squareL")} · ${Math.round(s.area_m2).toLocaleString()} m²` : `${s.length_m} m`;
      line.bindTooltip(`${esc(s.name || t("sectionNoName"))} · ${esc(size)}<br>${esc(t("lv_" + s.urgency_level))} · ${who} · #${s.alert_ids.join(", #")}`);
      line.on("click", () => {
        S.map.fitBounds(line.getBounds(), { padding: [80, 80], maxZoom: 18 });
        select(s.alert_ids[0], false);
      });
      line.bringToBack();
    });
  }

  // ---------------------------------------------------------------- zoom levels
  // City view (zoom <= 16): street lines only; an alert that is not on a line is a dot, and dots that crowd
  // become one count bubble. Block view (zoom >= 17): every dot and camera zone, the line fades behind them.
  const DETAIL_ZOOM = 17;
  const BUBBLE_PX = 46;
  const RANK = (a) => (a.status === "reopened" ? 5 : a.status === "watch" ? 1 : ({ high: 4, medium: 3, low: 2 }[a.urgency_level] || 2));

  function show(layer, on) {
    if (!layer) return;
    if (on && !S.map.hasLayer(layer)) layer.addTo(S.map);
    if (!on && S.map.hasLayer(layer)) layer.remove();
  }

  function applyView() {
    if (!S.map) return;
    const detail = S.map.getZoom() >= DETAIL_ZOOM;
    show(S.camGroup, detail);
    // the section is the shape of the problem at every zoom (there are no camera rectangles); up close it is
    // a little thinner so the dots on it stay readable
    if (S.sectionLayer) S.sectionLayer.eachLayer((l) => l.setStyle(l instanceof L.Polygon
      ? (detail ? { weight: 3, opacity: 0.9, fillOpacity: 0.3 } : { weight: 3, opacity: 0.9, fillOpacity: 0.35 })
      : (detail ? { weight: 8, opacity: 0.7 } : { weight: 10, opacity: 0.85 })));
    const onLine = new Set((S.sections || []).flatMap((s) => s.alert_ids));
    const loose = [];
    S.alerts.forEach((a) => {
      const l = S.layers.get(a.id);
      if (!l) return;
      const visible = detail || a.id === S.selected;
      show(l.marker, visible);
      if (!visible && !L$.isClosed(a) && !onLine.has(a.id)) loose.push(a);
    });
    if (!S.bubbleLayer) S.bubbleLayer = L.layerGroup().addTo(S.map);
    const groups = [];
    loose.forEach((a) => {
      const p = S.map.latLngToLayerPoint([a.lat, a.lon]);
      const g = groups.find((x) => x.p.distanceTo(p) <= BUBBLE_PX);
      if (g) g.items.push(a); else groups.push({ p, items: [a] });
    });
    groups.forEach((g) => { if (g.items.length === 1) show(S.layers.get(g.items[0].id).marker, true); });
    // rebuild the bubbles only when they change: a bubble replaced every 3 s refresh would swallow clicks
    const key = detail ? "detail" : S.map.getZoom() + "|" + groups.filter((g) => g.items.length > 1)
      .map((g) => g.items.map((a) => `${a.id}:${a.status}:${a.urgency_level}`).join(",")).join(";");
    if (key === S.bubbleKey) return;
    S.bubbleKey = key;
    S.bubbleLayer.clearLayers();
    groups.forEach((g) => {
      if (g.items.length === 1) return;
      const worst = g.items.reduce((m, a) => (RANK(a) > RANK(m) ? a : m));
      const col = L$.alertColor(worst);
      const b = L.latLngBounds(g.items.map((a) => [a.lat, a.lon]));
      const n = g.items.length;
      L.marker(b.getCenter(), { icon: L.divIcon({ className: "bubble", html: `<span style="background:${col}">${n}</span>`, iconSize: [34, 34] }) })
        .bindTooltip(esc(t("bubbleTip", { n })))
        .on("click", () => S.map.fitBounds(b.pad(0.3), { maxZoom: DETAIL_ZOOM + 1 }))
        .addTo(S.bubbleLayer);
    });
  }

  function updateMap() {
    if (!S.map) return;
    updateSections();
    // an alert on a street section is drawn on that street (the backend snaps it), not on a roof
    const dotAt = new Map();
    (S.sections || []).forEach((s) => Object.entries(s.points || {}).forEach(([id, p]) => dotAt.set(Number(id), p)));
    const seen = new Set();
    const bounds = [];
    S.alerts.forEach((a) => {
      seen.add(a.id);
      const st = styleFor(a);
      let l = S.layers.get(a.id);
      const tip = `#${a.id} · ${t("st_" + a.status)} · ${t("lv_" + a.urgency_level)} (${a.urgency_score})${a.opened_at ? " · " + t("sev_" + a.severity) : ""}${a.overdue ? " · " + t("overdue") : ""}<br>${esc(L$.place(a.place_type))}${a.report_count ? ` · ${a.report_count} 👤` : ""}`;
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
    if (l && pan) S.map.panTo(l.marker.getLatLng(), { animate: true });
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

  function itemHTML(a, rank) {
    const col = L$.alertColor(a);
    const chips = (a.why || a.inspector_flags || []).map((w) => {
      const cls = w === "act" ? "sev-act" : w === "overdue" ? "overdue" : w === "reopened" ? "purple"
        : (w === "high" || w === "possible_ice" || w === "ice_report") ? "alarm" : "warn";
      return `<span class="chip ${cls}">${esc(t("why_" + w))}</span>`;
    }).join("");
    const meta = [
      esc(L$.place(a.place_type)),
      esc(a.contractor_name || a.district || ""),
      a.report_count ? `${a.report_count} 👤` : "",
      a.zone_id ? "📷" : "",
      `${esc(t("firstSeen"))}: ${L$.sinceSpan(a.first_seen_at, t("ago"))}`,
    ].filter(Boolean).join(" · ");
    return `<button type="button" class="item ${a.status === "watch" ? "watchy" : ""} ${S.selected === a.id ? "active" : ""}" data-alert="${a.id}">
      <span class="bar" style="background:${col}"></span>
      <span>
        <span class="title">#${a.id} ${L$.statusBadge(a.status)} ${a.opened_at && !a.why ? L$.severityBadge(a) : ""} ${a.overdue && !a.why ? `<span class="chip overdue">${esc(t("overdue"))}</span>` : ""} ${a.flagged_for_council ? `<span class="chip purple">⚑</span>` : ""}</span>
        <span class="meta">${meta}</span>
        ${chips ? `<span style="display:block;margin-top:4px">${chips}</span>` : ""}
      </span>
      <span class="right">${rank ? `<span class="rank">${rank}</span>` : ""}${L$.levelBadge(a.urgency_level, a.status)}<span class="muted small">${a.urgency_score}</span></span>
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
    const ai = [r.relevant, r.ai_hint, r.ai_score != null ? (+r.ai_score).toFixed(2) : null].filter(Boolean).join(" · ");
    return `<div class="mod">
      ${r.photo_url ? `<img src="${esc(r.photo_url)}" data-zoom="${esc(r.photo_url)}" alt="" loading="lazy">` : "<div></div>"}
      <div>
        <div><b>#${r.id}</b> · ${esc(L$.fmtTime(r.timestamp))} · ${esc(r.channel || "")}</div>
        <div class="small">${esc(t("ps_" + r.passable))} · ${esc(L$.hazard(r.hazard))} · ${esc(L$.place(r.place_type))}</div>
        ${r.comment ? `<div class="small">“${esc(r.comment)}”</div>` : ""}
        ${r.registration_no ? `<div class="small">${esc(t("regNo"))}: <b>${esc(r.registration_no)}</b></div>` : ""}
        <div class="small muted">${esc(t("aiSays"))}: ${esc(ai)}${r.ai_note ? ` — ${esc(r.ai_note)}` : ""}</div>
        ${r.same_photo_as ? `<div class="chip warn">${esc(t("samePhotoAs", { n: r.same_photo_as }))}</div>` : ""}
        ${r.alert_id ? `<div class="small"><a href="#" data-alert="${r.alert_id}">${esc(t("alert"))} #${r.alert_id}</a></div>` : ""}
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
      <th class="num">${esc(t("c_overdue"))}</th><th class="num">${esc(t("c_act"))}</th>
      <th class="num">${esc(t("c_notify"))}</th><th class="num">${esc(t("c_kpi", { n: k }))}</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td>${esc(r.name || r.id)}</td><td class="num">${r.opened}</td><td class="num">${r.verified}</td>
        <td class="num">${L$.hours(r.avg_response_hours)}</td><td class="num">${L$.pct(r.share_within)}</td>
        <td class="num">${r.reopened_times}</td>
        <td class="num" style="${r.overdue ? "color:var(--high);font-weight:700" : ""}">${r.overdue}</td><td class="num">${r.act}</td>
        <td class="num">${r.avg_notify_minutes == null ? t("none") : Math.round(r.avg_notify_minutes)}</td>
        <td class="num">${L$.pct(r.share_notify_kpi)}</td></tr>`).join("")}
      </tbody></table></div>`;
  }

  function statsHTML() {
    const st = S.data.stats;
    if (!st) return `<div class="empty">${esc(t("loading"))}</div>`;
    const exp = `<div class="actions" style="margin:6px 0 12px">
      <a class="btn" href="/export.geojson" download>⤓ ${esc(t("exportGeo"))}</a>
      <a class="btn" href="/export.csv" download>⤓ ${esc(t("exportCsv"))}</a></div>`;
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
    const flags = d.inspector_flags || [];
    const reasons = (d.urgency_reasons || []).map((r) => `<li><span>${esc(L$.reasonText(r))}</span><span class="pts">${r.points != null ? "+" + r.points : ""}</span></li>`).join("");
    const tl = [
      [t("firstSeen"), L$.fmtTime(d.first_seen_at)],
      [t("deadlineAt"), L$.fmtTime(d.deadline_at)],
      [t("detected"), L$.fmtTime(d.detected_at)],
      [t("opened"), L$.fmtTime(d.notified_at)],
      [t("fixDue"), d.fix_due_at ? { html: `${esc(L$.fmtTime(d.fix_due_at))}${d.overdue ? ` <span class="chip overdue">${esc(t("overdue"))}</span>` : ""}` } : t("none")],
      [t("doneReported"), L$.fmtTime(d.done_reported_at)],
      [t("verified"), L$.fmtTime(d.verified_at)],
      [t("responseTime"), d.response_hours != null ? `${L$.hours(d.response_hours)} ${t("h")}` : (d.notified_at && !L$.isClosed(d) ? { html: L$.sinceSpan(d.notified_at, "…") } : t("none"))],
      [t("notifyDelay"), d.notify_seconds != null ? L$.fmtDur(d.notify_seconds) : t("none")],
      [t("reopenedTimes"), `${d.reopened_count} ${t("times")}`],
    ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v && v.html ? v.html : esc(v)}</dd>`).join("");
    const hasFrames = d.before_frame_url || d.after_frame_url;
    const ba = hasFrames ? `<div class="ba">${frameFig(t("before"), d.before_frame_url, d.before_crop_url)}${d.after_frame_url ? frameFig(t("after"), d.after_frame_url, d.after_crop_url) : "<figure></figure>"}</div>`
      : `<p class="muted small">${esc(t("noFrames"))}</p>`;
    const reps = (d.reports || []).length ? `<div class="photos">${d.reports.map((r) => `<div class="photo-item">
        ${r.photo_url ? `<img src="${esc(r.photo_url)}" data-zoom="${esc(r.photo_url)}" alt="" loading="lazy">` : ""}
        <div><b>${esc(t("ps_" + r.passable))}</b> · ${esc(L$.hazard(r.hazard))}</div>
        <div>${esc(L$.fmtTime(r.timestamp))} · ${esc(r.channel || "")} · ${esc(r.device || "")}</div>
        ${r.comment ? `<div>“${esc(r.comment)}”</div>` : ""}
        ${r.registration_no ? `<div>${esc(t("regNo"))}: <b>${esc(r.registration_no)}</b></div>` : ""}
        ${r.duplicate ? `<div class="chip">${esc(t("duplicate"))}</div>` : (!r.counted ? `<div class="chip warn">${esc(t("notCounted"))} (${esc(r.relevant)})</div>` : "")}
      </div>`).join("")}</div>` : `<p class="muted small">${esc(t("noReports"))}</p>`;
    const sigs = (d.signals || []).length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>${esc(t("time"))}</th><th>${esc(t("cls"))}</th><th class="num">${esc(t("share"))}</th><th class="num">${esc(t("conf"))}</th><th></th></tr></thead><tbody>
      ${d.signals.slice().reverse().map((s) => `<tr><td>${esc(L$.fmtTime(s.timestamp))}</td><td>${esc(L$.hazard(s.hazard_class))}</td>
        <td class="num">${L$.pct(s.blocked_share)}</td><td class="num" style="${s.confidence < 0.5 ? "color:var(--high);font-weight:700" : ""}">${(+s.confidence).toFixed(2)}</td>
        <td>${s.frame_url ? `<a href="${esc(s.frame_url)}" data-zoom="${esc(s.frame_url)}">${esc(t("fullFrame"))}</a>` : ""}</td></tr>`).join("")}</tbody></table></div>` : "";
    const hist = `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>${esc(t("when"))}</th><th>${esc(t("to"))}</th><th>${esc(t("who"))}</th><th>${esc(t("note"))}</th></tr></thead><tbody>
      ${(d.history || []).slice().reverse().map((h) => `<tr><td>${esc(L$.fmtTime(h.at))}</td><td>${L$.statusBadge(h.to_status)}</td><td>${esc(h.actor)}</td><td>${esc(h.note || "")}</td></tr>`).join("")}
      </tbody></table></div>`;

    const acts = [];
    if (d.status === "watch") acts.push(["open", t("actDispatch"), "primary"]);
    if (d.status === "watch") acts.push(["cleared_in_time", t("actClean"), "good"]);
    else if (!L$.isClosed(d)) acts.push(["verified", t("actVerify"), "good"]);
    if (!L$.isClosed(d)) acts.push(["false_alarm", t("actFalse"), ""]);
    if (d.status === "done_reported") acts.push(["reopened", t("actDispute"), "bad"]);
    if (d.status === "verified" && d.opened_at) acts.push(["reopened", t("actReopenVerified"), "bad"]);

    return `<div class="card">
      <button class="btn card-back" type="button" id="cardBack">← ${esc(t("back"))}</button>
      <section>
        <h2>${esc(t("alert"))} #${d.id} ${L$.statusBadge(d.status)} ${L$.levelBadge(d.urgency_level, d.status)}
          ${d.flagged_for_council ? `<span class="chip purple">⚑ ${esc(t("flagCouncil"))}</span>` : ""}
          ${d.false_alarm ? `<span class="chip">${esc(t("falseAlarm"))}</span>` : ""}</h2>
        <div class="muted">${esc(L$.place(d.place_type))} · ${esc(t("district"))}: ${esc(d.district || t("none"))} · ${esc(t("contractorL"))}: ${esc(d.contractor_name || t("none"))}</div>
        <div class="muted small">${d.zone_id ? `${esc(t("zone"))}: ${esc(d.zone_id)}` : esc(t("reportOnly"))} · ${esc(t("hz_" + (d.hazard_now || "other")))}</div>
        ${d.status === "watch" ? `<div class="note-box">${esc(t("watchNote"))}</div>` : ""}
        ${d.status === "cleared_in_time" ? `<div class="note-box">${esc(t("clearedNote"))}</div>` : ""}
        ${flags.length ? `<div style="margin-top:8px">${flags.map((f) => `<span class="chip ${f === "possible_ice" || f === "ice_report" ? "alarm" : "warn"}">${esc(t("why_" + f))}</span>`).join("")}</div>` : ""}
      </section>
      <section><h3>${esc(t("sevTitle"))}</h3>
        <div class="sev-box">${L$.severityBadge(d)}
          <span class="muted small">${d.severity_manual ? esc(t("sevManual")) + " · " : ""}${esc(t("sevSuggested", { s: t("sev_" + (d.severity_suggested || "notice")) }))}${d.severity_reason ? " — " + esc(d.severity_reason) : ""}</span>
          <button class="btn" type="button" id="sevToggle" data-sev="${d.severity === "act" ? "notice" : "act"}">${esc(t(d.severity === "act" ? "sevToNotice" : "sevToAct"))}</button>
          ${d.evidence_url ? `<a class="btn primary" href="${esc(d.evidence_url)}&lang=${esc(L$.lang)}" target="_blank" rel="noopener" title="${esc(t("evidenceHint"))}">📄 ${esc(t("evidencePack"))}</a>` : ""}
        </div>
        <p class="muted small" style="margin:6px 0 0">${esc(t("sevNote"))}</p>
      </section>
      <section><h3>${esc(t("why"))} · ${esc(t("urgency"))} ${d.urgency_score}</h3><ul class="reasons">${reasons || `<li class="muted">${esc(t("none"))}</li>`}</ul></section>
      <section><h3>${esc(t("actions"))}</h3>
        <div class="actions">
          <textarea id="actNote" maxlength="500" placeholder="${esc(t("noteLabel"))}" aria-label="${esc(t("noteLabel"))}"></textarea>
          ${acts.map(([s, label, cls]) => `<button class="btn ${cls}" type="button" data-act="${s}">${esc(label)}</button>`).join("")}
        </div>
        <div class="err" id="actErr" role="alert"></div>
      </section>
      <section><h3>${esc(t("evidence"))}</h3>${ba}</section>
      <section><h3>${esc(t("timeline"))}</h3><dl class="timeline">${tl}</dl></section>
      <section><h3>${esc(t("reports"))} (${d.report_count})</h3>${reps}</section>
      ${sigs ? `<section><h3>${esc(t("signals"))} (${d.signals.length})</h3>${sigs}</section>` : ""}
      <section><h3>${esc(t("history"))}</h3>${hist}</section>
    </div>`;
  }

  function renderCard(el) {
    const d = S.detail;
    if (!d || d.id !== S.selected) {
      setHTML(el, "panel", `<button class="btn card-back" type="button" id="cardBack">← ${esc(t("back"))}</button><div class="empty">${esc(t("loading"))}</div>`);
      bindCard(el);
      return;
    }
    const note = el.querySelector("#actNote");
    if (note && document.activeElement === note) return; // don't disturb typing
    const noteVal = note ? note.value : "";
    const errVal = el.querySelector("#actErr") ? el.querySelector("#actErr").textContent : "";
    if (setHTML(el, "panel", cardHTML(d))) {
      if (el.querySelector("#actNote")) el.querySelector("#actNote").value = noteVal;
      if (el.querySelector("#actErr")) el.querySelector("#actErr").textContent = errVal;
      bindCard(el);
    }
  }

  function bindCard(el) {
    const back = el.querySelector("#cardBack");
    if (back) back.addEventListener("click", () => { S.selected = null; S.detail = null; S.rendered.panel = null; renderTabs(); renderPanel(); updateMap(); });
    const sev = el.querySelector("#sevToggle");
    if (sev) sev.addEventListener("click", async () => {
      sev.disabled = true;
      try {
        S.detail = await api(`/alerts/${S.selected}/status`, { json: { severity: sev.dataset.sev, role: "inspector", actor: ACTOR,
          note: (el.querySelector("#actNote") || {}).value || "" } });
        S.rendered.panel = null;
        L$.toast(t("saved"));
        await refresh();
      } catch (e) { sev.disabled = false; L$.toast(e.message, true); }
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
