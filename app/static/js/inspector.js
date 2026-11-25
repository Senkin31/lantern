/* Inspector screen: map of zones by urgency, "where to go today", alert card, moderation, KPIs, demo controls. */
(function () {
  "use strict";
  const L$ = window.Lantern;
  const { t, esc, api } = L$;

  const S = {
    meta: null, map: null, alerts: [], settings: null,
    tab: "today", selected: null, detail: null, filter: "active",
    layers: new Map(), fitted: false, rendered: {}, withinHours: 6,
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
    L$.setHourSeconds(S.settings.hour_seconds);
    L$.syncClock(S.settings.now);
    renderChrome();
    S.map = L$.makeMap($("#map"), S.meta);
    drawCameraZones();
    addLegend();
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
      L$.syncClock(res.now);
      L$.setHourSeconds(S.settings.hour_seconds);
      const jobs = [];
      if (S.tab === "today") jobs.push(api("/inspection/today").then((r) => { S.data.today = r.alerts; }));
      if (S.tab === "reports") {
        jobs.push(api("/reports?role=inspector&relevant=review").then((r) => { S.data.reviewReports = r; }));
        jobs.push(api("/reports?role=inspector&relevant=reject").then((r) => { S.data.rejectReports = r; }));
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

  // ---------------------------------------------------------------- demo bar
  function renderDemoBar(force) {
    const el = $("#demo");
    const s = S.settings || {};
    if (force || !el.dataset.built) {
      el.innerHTML = `
        <span class="tag">${esc(t("demo"))}</span>
        <span class="kv">${esc(t("snowfallEnd"))}: <b id="dSnow"></b></span>
        <span class="kv">${esc(t("deadline"))}: <b id="dDeadline"></b> <span class="countdown" id="dCount"></span></span>
        <span class="group"><label for="dClear" class="muted small">${esc(t("clearingHoursLabel"))}</label><input id="dClear" type="number" min="0" step="0.5"></span>
        <span class="group"><label for="dHour" class="muted small">${esc(t("hourSecondsLabel"))}</label><input id="dHour" type="number" min="0.1" step="0.5"></span>
        <button class="btn" id="dApply" type="button">${esc(t("btnApply"))}</button>
        <button class="btn primary" id="dSnowBtn" type="button">❄ ${esc(t("btnSnowfall"))}</button>
        <button class="btn bad" id="dReset" type="button">${esc(t("btnReset"))}</button>
        <span class="muted small" id="dNote"></span>`;
      el.dataset.built = "1";
      $("#dSnowBtn").addEventListener("click", () => postSettings({ snowfall_end: "now" }));
      $("#dApply").addEventListener("click", () => {
        const body = {};
        const ch = parseFloat($("#dClear").value), hs = parseFloat($("#dHour").value);
        if (!isNaN(ch)) body.clearing_hours = ch;
        if (!isNaN(hs) && hs > 0) body.hour_seconds = hs;
        postSettings(body);
      });
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
    $("#dSnow").textContent = s.snowfall_end ? L$.fmtTime(s.snowfall_end) : t("notSet");
    $("#dDeadline").textContent = s.deadline ? L$.fmtTime(s.deadline) : t("notSet");
    if (document.activeElement !== $("#dClear")) $("#dClear").value = s.clearing_hours != null ? s.clearing_hours : "";
    if (document.activeElement !== $("#dHour")) $("#dHour").value = s.hour_seconds != null ? +(+s.hour_seconds).toFixed(3) : "";
    $("#dNote").textContent = s.hour_seconds && s.hour_seconds !== 3600 ? `${t("hourIs")} ${+(+s.hour_seconds).toFixed(2)} ${t("sec")} · ${t("demoTimeNote")}` : "";
    tickCountdown();
  }

  function tickCountdown() {
    const el = $("#dCount");
    if (!el || !S.settings) return;
    if (!S.settings.deadline) { el.textContent = ""; return; }
    const left = (new Date(S.settings.deadline).getTime() - L$.now()) / 1000;
    el.classList.toggle("passed", left <= 0);
    el.textContent = left <= 0 ? `(${t("passed")})` : `(${t("in")} ${L$.fmtDur(left)})`;
  }

  async function postSettings(body) {
    try {
      S.settings = await api("/settings", { json: body });
      L$.setHourSeconds(S.settings.hour_seconds);
      L$.toast(t("saved"));
      await refresh();
    } catch (e) { L$.toast(e.message, true); }
  }

  // ---------------------------------------------------------------- map
  function drawCameraZones() {
    const group = L.layerGroup().addTo(S.map);
    const bounds = [];
    (S.meta.cameras || []).forEach((cam) => {
      bounds.push([cam.lat, cam.lon]);
      (cam.zones || []).forEach((z) => {
        if (!z.map_polygon) return;
        const ll = L$.toLatLngs(z.map_polygon);
        ll.forEach((p) => bounds.push(p));
        L.polygon(ll, { color: "#7a8596", weight: 1, dashArray: "3 4", fill: false, interactive: false }).addTo(group);
      });
      L.circleMarker([cam.lat, cam.lon], { radius: 3, color: "#7a8596", weight: 1, fillOpacity: .6, interactive: true })
        .bindTooltip(esc(cam.name || cam.camera_id)).addTo(group);
    });
    if (bounds.length) S.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
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
        + `<div><i style="background:${c.verified}"></i>${esc(t("st_verified"))}</div>`;
      return d;
    };
    S.legend.addTo(S.map);
  }

  function clearAlertLayers() {
    S.layers.forEach((l) => { if (l.poly) l.poly.remove(); l.marker.remove(); });
    S.layers.clear();
  }

  function styleFor(a) {
    const col = L$.alertColor(a);
    const sel = S.selected === a.id;
    const verified = a.status === "verified";
    return {
      poly: { color: a.status === "reopened" ? L$.COLORS.reopened : col, weight: sel ? 4 : 2, fillColor: col,
        fillOpacity: verified ? 0.12 : 0.38, opacity: verified ? 0.5 : 0.95, dashArray: a.status === "watch" ? "5 4" : null },
      marker: { radius: sel ? 11 : (verified ? 5 : 8), color: a.status === "reopened" ? L$.COLORS.reopened : "#ffffff",
        weight: a.status === "reopened" ? 4 : 2, fillColor: col, fillOpacity: verified ? 0.55 : 0.95,
        dashArray: a.status === "watch" ? "3 3" : null },
    };
  }

  function updateMap() {
    if (!S.map) return;
    const seen = new Set();
    const bounds = [];
    S.alerts.forEach((a) => {
      seen.add(a.id);
      const st = styleFor(a);
      let l = S.layers.get(a.id);
      const tip = `#${a.id} · ${t("st_" + a.status)} · ${t("lv_" + a.urgency_level)} (${a.urgency_score})<br>${esc(L$.place(a.place_type))}${a.report_count ? ` · ${a.report_count} 👤` : ""}`;
      if (!l) {
        l = {};
        if (a.polygon) {
          l.poly = L.polygon(L$.toLatLngs(a.polygon), st.poly).addTo(S.map);
          l.poly.on("click", () => select(a.id));
        }
        l.marker = L.circleMarker([a.lat, a.lon], st.marker).addTo(S.map);
        l.marker.on("click", () => select(a.id));
        l.marker.bindTooltip(tip);
        S.layers.set(a.id, l);
      } else {
        if (l.poly) l.poly.setStyle(st.poly);
        l.marker.setStyle(st.marker);
        l.marker.setRadius(st.marker.radius);
        l.marker.setTooltipContent(tip);
      }
      if (a.status !== "verified") l.marker.bringToFront();
      bounds.push([a.lat, a.lon]);
    });
    S.layers.forEach((l, id) => { if (!seen.has(id)) { if (l.poly) l.poly.remove(); l.marker.remove(); S.layers.delete(id); } });
    if (!S.fitted && bounds.length) {
      S.fitted = true;
      const b = L.latLngBounds(bounds);
      (S.meta.cameras || []).forEach((c) => b.extend([c.lat, c.lon]));
      S.map.fitBounds(b, { padding: [50, 50], maxZoom: 16 });
    }
  }

  function select(id) {
    S.selected = id;
    S.detail = null;
    renderPanel();
    updateMap();
    api(`/alerts/${id}?role=inspector`).then((d) => { S.detail = d; renderPanel(); }).catch((e) => L$.toast(e.message, true));
    const l = S.layers.get(id);
    if (l) S.map.panTo(l.marker.getLatLng(), { animate: true });
  }

  // ---------------------------------------------------------------- tabs
  function renderTabs() {
    const reviewCount = S.alerts.filter((a) => a.status !== "verified" && (a.inspector_flags || []).includes("review_report")).length;
    const active = S.alerts.filter((a) => a.status !== "verified").length;
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
    const wh = el.querySelector("#withinH");
    if (wh) wh.addEventListener("change", () => { const v = parseFloat(wh.value); if (v > 0) { S.withinHours = v; refresh(); } });
  }

  function itemHTML(a, rank) {
    const col = L$.alertColor(a);
    const chips = (a.why || a.inspector_flags || []).map((w) => {
      const cls = w === "reopened" ? "purple" : (w === "high" || w === "possible_ice" || w === "ice_report") ? "alarm" : "warn";
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
        <span class="title">#${a.id} ${L$.statusBadge(a.status)} ${a.flagged_for_council ? `<span class="chip purple">⚑</span>` : ""}</span>
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
      <p class="muted small" style="margin-top:-4px">${esc(t("todayHint"))}</p>
      ${list.length ? list.map((a, i) => itemHTML(a, i + 1)).join("") : `<div class="empty">${esc(t("nothingToday"))}</div>`}`;
  }

  function allHTML() {
    const order = { reopened: 0, open: 1, done_reported: 2, watch: 3, verified: 4 };
    let list = S.alerts.slice();
    if (S.filter === "active") list = list.filter((a) => a.status !== "verified");
    else if (S.filter !== "all") list = list.filter((a) => a.status === S.filter);
    list.sort((a, b) => (order[a.status] - order[b.status]) || (b.urgency_score - a.urgency_score) || (b.id - a.id));
    const opts = [["active", t("activeOnly")], ["all", t("allStatuses")]].concat(["watch", "open", "done_reported", "reopened", "verified"].map((s) => [s, t("st_" + s)]));
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
        <div class="small muted">${esc(t("aiSays"))}: ${esc(ai)}${r.ai_note ? ` — ${esc(r.ai_note)}` : ""}</div>
        ${r.alert_id ? `<div class="small"><a href="#" data-alert="${r.alert_id}">${esc(t("alert"))} #${r.alert_id}</a></div>` : ""}
        ${showActions ? `<div class="actions" style="margin-top:6px">
          <button class="btn good" type="button" data-moderate="accept" data-id="${r.id}">${esc(t("accept"))}</button>
          ${r.relevant !== "reject" ? `<button class="btn bad" type="button" data-moderate="reject" data-id="${r.id}">${esc(t("reject"))}</button>` : ""}
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
      ${rj.length ? rj.map((r) => modHTML(r, true)).join("") : `<div class="empty">${esc(t("noRejected"))}</div>`}`;
  }

  function statsTable(rows, nameKey) {
    const n = S.data.stats.within_hours, k = S.data.stats.notify_kpi_minutes;
    return `<div class="tbl-wrap"><table class="tbl"><thead><tr>
      <th>${esc(nameKey)}</th><th class="num">${esc(t("c_opened"))}</th><th class="num">${esc(t("c_verified"))}</th>
      <th class="num">${esc(t("c_avg"))}</th><th class="num">${esc(t("c_within", { n }))}</th><th class="num">${esc(t("c_reopened"))}</th>
      <th class="num">${esc(t("c_notify"))}</th><th class="num">${esc(t("c_kpi", { n: k }))}</th></tr></thead><tbody>
      ${rows.map((r) => `<tr><td>${esc(r.name || r.id)}</td><td class="num">${r.opened}</td><td class="num">${r.verified}</td>
        <td class="num">${L$.hours(r.avg_response_hours)}</td><td class="num">${L$.pct(r.share_within)}</td>
        <td class="num">${r.reopened_times}</td><td class="num">${r.avg_notify_minutes == null ? t("none") : Math.round(r.avg_notify_minutes)}</td>
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
    if (!st.by_contractor.length) return head + `<div class="empty">${esc(t("noStats"))}</div>` + exp;
    return head + `<h3 class="muted small">${esc(t("byContractor"))}</h3>${statsTable(st.by_contractor, t("contractorL"))}
      <h3 class="muted small" style="margin-top:14px">${esc(t("byDistrict"))}</h3>${statsTable(st.by_district, t("district"))}
      <p class="muted small">${esc(t("demoTimeNote"))}${st.hour_seconds !== 3600 ? ` (${t("hourIs")} ${+(+st.hour_seconds).toFixed(2)} ${t("sec")})` : ""}</p>${exp}`;
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
      [t("detected"), L$.fmtTime(d.detected_at)],
      [t("opened"), L$.fmtTime(d.opened_at)],
      [t("doneReported"), L$.fmtTime(d.done_reported_at)],
      [t("verified"), L$.fmtTime(d.verified_at)],
      [t("responseTime"), d.response_hours != null ? `${L$.hours(d.response_hours)} ${t("h")}` : (d.opened_at && d.status !== "verified" ? { html: L$.sinceSpan(d.opened_at, "…") } : t("none"))],
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
    if (d.status !== "verified") acts.push(["verified", t("actVerify"), "good"]);
    if (d.status === "done_reported") acts.push(["reopened", t("actDispute"), "bad"]);
    if (d.status === "verified" && d.opened_at) acts.push(["reopened", t("actReopenVerified"), "bad"]);

    return `<div class="card">
      <button class="btn card-back" type="button" id="cardBack">← ${esc(t("back"))}</button>
      <section>
        <h2>${esc(t("alert"))} #${d.id} ${L$.statusBadge(d.status)} ${L$.levelBadge(d.urgency_level, d.status)}
          ${d.flagged_for_council ? `<span class="chip purple">⚑ ${esc(t("flagCouncil"))}</span>` : ""}</h2>
        <div class="muted">${esc(L$.place(d.place_type))} · ${esc(t("district"))}: ${esc(d.district || t("none"))} · ${esc(t("contractorL"))}: ${esc(d.contractor_name || t("none"))}</div>
        <div class="muted small">${d.zone_id ? `${esc(t("zone"))}: ${esc(d.zone_id)}` : esc(t("reportOnly"))} · ${esc(t("hz_" + (d.hazard_now || "other")))}</div>
        ${d.status === "watch" ? `<div class="note-box">${esc(t("watchNote"))}</div>` : ""}
        ${flags.length ? `<div style="margin-top:8px">${flags.map((f) => `<span class="chip ${f === "possible_ice" || f === "ice_report" ? "alarm" : "warn"}">${esc(t("why_" + f))}</span>`).join("")}</div>` : ""}
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
    el.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
      const note = (el.querySelector("#actNote") || {}).value || "";
      const errEl = el.querySelector("#actErr");
      if (errEl) errEl.textContent = "";
      el.querySelectorAll("[data-act]").forEach((x) => { x.disabled = true; });
      try {
        S.detail = await api(`/alerts/${S.selected}/status`, { json: { status: b.dataset.act, role: "inspector", actor: ACTOR, note } });
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
