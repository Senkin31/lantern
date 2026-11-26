/* Contractor screen (phone first): jobs of my district, crop of the sidewalk, complaints, "Cleared" button.
   Full camera frames are never requested here; the server strips frame_url for this role anyway. */
(function () {
  "use strict";
  const L$ = window.Lantern;
  const { t, esc, api } = L$;

  const params = new URLSearchParams(location.search);
  const S = {
    meta: null, contractor: params.get("contractor"), alerts: [], view: "list", map: null, layers: new Map(),
    fitted: false, lastHTML: "", busy: new Set(), completedOpen: false,
  };
  const $ = (sel) => document.querySelector(sel);
  const URG = { high: 0, medium: 1, low: 2 };

  async function boot() {
    try { S.meta = await api("/meta"); } catch (e) {
      $("#main").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return;
    }
    const known = (S.meta.contractors || []).map((c) => c.id);
    if (!S.contractor || !known.includes(S.contractor)) S.contractor = known[0] || null;
    if (S.contractor && params.get("contractor") !== S.contractor) history.replaceState(null, "", "/contractor?contractor=" + encodeURIComponent(S.contractor));
    L$.syncFromSettings(S.meta.settings);
    chrome();
    document.addEventListener("lantern:lang", () => { S.lastHTML = ""; chrome(); render(); });
    await refresh();
    setInterval(refresh, 5000);
  }

  function me() { return (S.meta.contractors || []).find((c) => c.id === S.contractor); }

  function chrome() {
    L$.renderHeader($("#top"), S.meta, S.contractor ? "contractor:" + S.contractor : "inspector");
    L$.renderFooter($("#foot"), S.meta);
  }

  async function refresh() {
    if (!S.contractor) { $("#main").innerHTML = `<div class="empty">${esc(t("pickContractor"))}</div>`; return; }
    try {
      const res = await api("/alerts?role=contractor&contractor=" + encodeURIComponent(S.contractor));
      L$.syncFromSettings(res.settings);
      S.alerts = res.alerts;
      render();
    } catch (e) { console.warn("refresh failed", e); }
  }

  function sorted() {
    const todo = S.alerts.filter((a) => a.status === "open" || a.status === "reopened");
    const waiting = S.alerts.filter((a) => a.status === "done_reported");
    const done = S.alerts.filter((a) => a.status === "verified");
    // overdue first, then defect acts, then reopened, then urgency
    todo.sort((a, b) => (b.overdue - a.overdue) || ((b.severity === "act") - (a.severity === "act"))
      || (b.status === "reopened") - (a.status === "reopened") || (b.urgency_score - a.urgency_score)
      || (URG[a.urgency_level] - URG[b.urgency_level]) || (new Date(a.opened_at) - new Date(b.opened_at)));
    waiting.sort((a, b) => new Date(b.done_reported_at) - new Date(a.done_reported_at));
    done.sort((a, b) => new Date(b.verified_at) - new Date(a.verified_at));
    return { todo, waiting, done };
  }

  function osm(a) { return `https://www.openstreetmap.org/?mlat=${a.lat}&mlon=${a.lon}#map=19/${a.lat}/${a.lon}`; }
  function geo(a) { return `geo:${a.lat},${a.lon}?q=${a.lat},${a.lon}`; }

  function jobHTML(a) {
    const banner = (a.overdue ? `<div class="banner overdue">⚠ ${esc(t("overdueJob"))}</div>` : "")
      + (a.status === "reopened" ? `<div class="banner">↻ ${esc(t("redo"))}</div>`
        : a.status === "done_reported" ? `<div class="banner done">⏳ ${esc(t("waitingCheck"))}</div>` : "");
    const open = a.status !== "verified";
    const photos = (a.report_photos || []).map((p) => `<img src="${esc(p)}" data-zoom="${esc(p)}" alt="${esc(t("residentPhotos"))}" loading="lazy">`).join("");
    const canClear = a.status === "open" || a.status === "reopened";
    const facts = [
      open && a.fix_due_at ? `${esc(t("fixDue"))}: <b style="${a.overdue ? "color:var(--high)" : ""}">${esc(L$.fmtTime(a.fix_due_at))}</b>` : "",
      a.status === "verified" ? "" : `${esc(t("sinceOpened"))}: <b>${L$.sinceSpan(a.notified_at || a.opened_at)}</b>`,
      `${esc(t("complaints"))}: <b>${a.report_count}</b>`,
      a.status === "verified" ? `${esc(t("verifiedAt"))}: <b>${esc(L$.fmtTime(a.verified_at))}</b>` : "",
      a.status === "verified" && a.response_hours != null ? `${esc(t("responseTime"))}: <b>${L$.hours(a.response_hours)} ${esc(t("h"))}</b>` : "",
    ].filter(Boolean).map((f) => `<span>${f}</span>`).join("");
    return `<article class="job u-${esc(a.status === "verified" ? "none" : a.urgency_level)}" id="job-${a.id}">
      ${banner}
      <div class="body">
        <div class="top">
          <div><h2>${esc(L$.place(a.place_type))} · #${a.id}</h2>
            <div class="muted small">${esc(a.district || "")}${a.hazard_now && a.hazard_now !== "reported" ? ` · ${esc(L$.hazard(a.hazard_now))}` : ""}</div></div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">${L$.levelBadge(a.urgency_level, a.status)}${L$.statusBadge(a.status)}</div>
        </div>
        ${open ? `<div class="sev-box">${L$.severityBadge(a)}<span class="muted small">${esc(t(a.severity === "act" ? "actJob" : "noticeJob"))}</span></div>` : ""}
        ${a.latest_crop_url ? `<figure style="margin:0"><img class="crop" src="${esc(a.latest_crop_url)}" data-zoom="${esc(a.latest_crop_url)}" alt="${esc(t("lastFrame"))}" loading="lazy"><figcaption class="muted small">${esc(t("lastFrame"))}</figcaption></figure>` : ""}
        <div class="facts">${facts}</div>
        ${photos ? `<div><div class="muted small" style="margin-bottom:4px">${esc(t("residentPhotos"))}</div><div class="thumbs">${photos}</div></div>` : ""}
        <div class="links">
          <a class="btn" href="${esc(osm(a))}" target="_blank" rel="noopener">🗺 ${esc(t("openInMap"))}</a>
          <a class="btn" href="${esc(geo(a))}">➜ ${esc(t("directions"))}</a>
        </div>
        ${canClear ? `<button class="btn primary big" type="button" data-clear="${a.id}" ${S.busy.has(a.id) ? "disabled" : ""}>✓ ${esc(t("cleared"))}</button>` : ""}
      </div>
    </article>`;
  }

  function render() {
    const c = me();
    const { todo, waiting, done } = sorted();
    const head = `<div class="c-head">
        <h1>${esc(t("myJobs"))}${c ? ` · ${esc(c.name)}` : ""}</h1>
        <div class="seg" role="group">
          <button type="button" data-view="list" aria-pressed="${S.view === "list"}">${esc(t("listView"))}</button>
          <button type="button" data-view="map" aria-pressed="${S.view === "map"}">${esc(t("mapView"))}</button>
        </div></div>
      <div class="summary">
        <div><b>${todo.length}</b><span>${esc(t("toDo"))}</span></div>
        <div><b>${waiting.length}</b><span>${esc(t("waiting"))}</span></div>
        <div><b>${done.length}</b><span>${esc(t("doneToday"))}</span></div>
      </div>`;
    let body;
    if (S.view === "map") body = `<div id="cmap" role="region" aria-label="Map"></div>`;
    else {
      const active = todo.concat(waiting);
      body = (active.length ? active.map(jobHTML).join("") : `<div class="empty">${esc(t("noJobs"))}</div>`)
        + (done.length ? `<details class="completed" ${S.completedOpen ? "open" : ""}><summary>${esc(t("completed"))} (${done.length})</summary>${done.map(jobHTML).join("")}</details>` : "");
    }
    const html = head + body;
    if (html === S.lastHTML && !(S.view === "map")) return;
    if (S.view === "map" && S.lastHTML.startsWith(head) && S.map && document.getElementById("cmap")) {
      updateMap(); return;
    }
    S.lastHTML = html;
    if (S.map) { S.map.remove(); S.map = null; S.layers.clear(); S.fitted = false; }
    $("#main").innerHTML = html;
    L$.updateSince($("#main"));
    bind();
    if (S.view === "map") { S.map = L$.makeMap($("#cmap"), S.meta); updateMap(); }
  }

  function updateMap() {
    if (!S.map) return;
    const seen = new Set();
    S.alerts.forEach((a) => {
      seen.add(a.id);
      let col = L$.alertColor(a);
      if (a.status === "done_reported") col = "#e8a33d";
      const style = { radius: a.status === "verified" ? 6 : 11, color: a.status === "reopened" ? L$.COLORS.reopened : "#fff",
        weight: a.status === "reopened" ? 4 : 2, fillColor: col, fillOpacity: a.status === "verified" ? .5 : .95 };
      let l = S.layers.get(a.id);
      if (!l) {
        l = {};
        if (a.polygon) l.poly = L.polygon(L$.toLatLngs(a.polygon), { color: col, weight: 2, fillOpacity: .35 }).addTo(S.map);
        l.marker = L.circleMarker([a.lat, a.lon], style).addTo(S.map);
        l.marker.on("click", () => { S.view = "list"; S.lastHTML = ""; render(); const j = document.getElementById("job-" + a.id); if (j) j.scrollIntoView({ behavior: "smooth" }); });
        S.layers.set(a.id, l);
      } else {
        l.marker.setStyle(style); l.marker.setRadius(style.radius);
        if (l.poly) l.poly.setStyle({ color: col });
      }
      l.marker.bindTooltip(`#${a.id} · ${esc(L$.place(a.place_type))} · ${esc(t("st_" + a.status))}`);
    });
    S.layers.forEach((l, id) => { if (!seen.has(id)) { if (l.poly) l.poly.remove(); l.marker.remove(); S.layers.delete(id); } });
    if (!S.fitted) {
      const pts = S.alerts.map((a) => [a.lat, a.lon]);
      if (pts.length) S.map.fitBounds(pts, { padding: [40, 40], maxZoom: 17 });
      else {
        const c = me();
        const cams = (S.meta.cameras || []).filter((x) => !c || (c.districts || []).includes(x.district)).map((x) => [x.lat, x.lon]);
        const riga = L.latLng(56.9496, 24.1052);  // prefer Riga over the Finnish demo cameras
        const home = cams.filter((p) => riga.distanceTo(L.latLng(p)) < 50000);
        if (cams.length) S.map.fitBounds(home.length ? home : cams, { padding: [60, 60], maxZoom: 16 });
      }
      S.fitted = true;
    }
  }

  function bind() {
    document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => { S.view = b.dataset.view; S.lastHTML = ""; render(); }));
    const det = document.querySelector("details.completed");
    if (det) det.addEventListener("toggle", () => { S.completedOpen = det.open; });
    document.querySelectorAll("[data-clear]").forEach((b) => b.addEventListener("click", async () => {
      const id = +b.dataset.clear;
      if (!confirm(t("confirmCleared"))) return;
      S.busy.add(id); b.disabled = true;
      try {
        await api(`/alerts/${id}/status`, { json: { status: "done_reported", role: "contractor", contractor: S.contractor, actor: S.contractor } });
        L$.toast(t("waitingCheck"));
      } catch (e) {
        L$.toast(e.message, true);
      } finally {
        S.busy.delete(id);
        S.lastHTML = "";
        await refresh();
      }
    }));
  }

  boot();
})();
