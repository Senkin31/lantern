/* Lantern shared helpers: API, i18n (EN/LV), header, footer, formatting, map styles. */
(function () {
  "use strict";

  const I18N = {
    en: {
      inspector: "Inspector", contractor: "Contractor", role: "View as", residentForm: "Resident form",
      source: "Source", loading: "Loading…", retry: "Retry",
      // demo bar
      demo: "Demo", snowfallEnd: "Snowfall ended", deadline: "Clearing deadline", notSet: "not set",
      clearing: "Clearing time", hourIs: "1 h =", sec: "s", passed: "passed", in: "in",
      btnSnowfall: "Snowfall ended now", btnReset: "Reset demo", btnApply: "Apply",
      confirmReset: "Delete all alerts, signals, reports and history? Settings are kept.",
      hourSecondsLabel: "1 h = s", clearingHoursLabel: "Clearing, h",
      demoTimeNote: "Durations are shown in scenario hours",
      // tabs
      tabToday: "Where to go today", tabAll: "All alerts", tabReports: "Reports", tabStats: "Response times",
      todayHint: "Top 10 by urgency and age: dispatched work, contractor checks and things only you should look at.",
      allStatuses: "All statuses", activeOnly: "Active only",
      nothingToday: "Nothing needs a visit right now.", noAlerts: "No alerts yet.",
      // statuses
      st_watch: "Watch", st_open: "Open", st_done_reported: "Done reported", st_verified: "Verified", st_reopened: "Reopened",
      lv_high: "High", lv_medium: "Medium", lv_low: "Low",
      watchNote: "Clearing deadline has not passed yet. The contractor does not see this alert.",
      // why chips / flags
      why_reopened: "Reopened", why_check_done: "Check contractor's “done”", why_possible_ice: "Possible ice",
      why_low_confidence: "Low-confidence frame", why_ice_report: "Resident: ice / icicles",
      why_review_report: "Report needs review", why_high: "High urgency", flagCouncil: "Flagged for the council",
      // places / hazards
      pl_sidewalk: "Sidewalk", pl_crossing: "Crossing", pl_ramp: "Curb ramp", pl_stop: "Stop", pl_path: "Path",
      pl_square: "Square", pl_other: "Other place",
      hz_clear: "Clear", hz_snow: "Snow", hz_blocked: "Blocked", hz_possible_ice: "Possible ice", hz_ice: "Ice",
      hz_icicles: "Icicles", hz_other: "Other", hz_reported: "Reported by residents",
      ps_no: "Cannot pass", ps_partly: "Partly passable", ps_yes: "Passable",
      // reasons
      r_camera_blocked: "Camera: blocked, {share} of zone", r_camera_snow: "Camera: snow, passable ({share})",
      r_camera_possible_ice: "Camera: possible ice", r_camera_clear: "Camera: clear",
      r_resident_no: "Resident: cannot pass", r_resident_partly: "Resident: partly passable", r_resident_yes: "Resident: passable",
      r_place: "Place: {value}", r_near_sensitive: "Near a school or hospital",
      r_confirmations: "{count} confirmation(s) from other sources", r_cap_unconfirmed: "Single unconfirmed report: capped at medium",
      lowConfTag: "conf. {c}",
      // card
      back: "Back", alert: "Alert", urgency: "Urgency", score: "score", why: "Why this urgency", flags: "Needs your attention",
      where: "Where", district: "District", contractorL: "Contractor", none: "—", zone: "Camera zone", reportOnly: "Resident reports only (no camera)",
      timeline: "Timeline", firstSeen: "First seen", detected: "Violation detected", opened: "Sent to contractor",
      doneReported: "Contractor: done", verified: "Verified", responseTime: "Response time", notifyDelay: "Notification delay",
      reopenedTimes: "Reopened", times: "time(s)",
      evidence: "Before / after", before: "Before", after: "After (latest)", fullFrame: "Full frame", crop: "Crop for contractor",
      noFrames: "No camera frames — resident photos below.",
      reports: "Resident reports", noReports: "No resident reports.", duplicate: "same device — not counted",
      notCounted: "not counted", signals: "Camera signals", history: "Status history (evidence)",
      when: "When", from: "From", to: "To", who: "Who", note: "Note", time: "Time", cls: "Class", share: "Share", conf: "Conf.",
      actions: "Actions", noteLabel: "Note (optional, goes to history)",
      actDispatch: "Dispatch now", actVerify: "Confirm on site", actDispute: "Dispute “done”", actReopenVerified: "Dispute verification",
      done: "Done", saved: "Saved",
      // moderation
      reviewQueue: "Needs review", rejected: "Rejected by the model", accept: "Accept", reject: "Reject",
      aiSays: "Model", noReview: "No reports waiting for review.", noRejected: "No rejected reports.",
      spamTitle: "Spam protection (24 h)", blockSender: "Block sender", unblock: "Unblock", blockedSenders: "Blocked senders",
      noBlocked: "Nobody is blocked.", samePhotoAs: "Same photo as #{n}", blockAsk: "Block this sender for 24 hours? Their new reports will be refused.",
      sp_blocked: "refused: blocked sender", sp_device_hourly_limit: "refused: hourly limit", sp_device_daily_limit: "refused: daily limit",
      sp_ip_hourly_limit: "refused: too many from one network", sp_outside_area: "refused: outside Riga",
      sp_duplicate_place: "repeat of the same place (not counted)", sp_same_photo: "same photo again (not counted)",
      spLimits: "Limits: {h}/hour and {d}/day per sender, {ip}/hour per network; muted for {bh} h after {r} rejected photos or {dup} repeats.",
      until: "until",
      // stats
      byContractor: "By contractor", byDistrict: "By district", withinH: "Closed within (h)",
      c_opened: "Opened", c_verified: "Verified", c_active: "Active", c_avg: "Avg response, h", c_within: "Closed ≤ {n} h",
      c_reopened: "Reopened", c_notify: "Avg notify, min", c_kpi: "Notify ≤ {n} min",
      exportGeo: "Export GeoJSON", exportCsv: "Export CSV", noStats: "No alerts have been sent to contractors yet.",
      // contractor
      myJobs: "My jobs", listView: "List", mapView: "Map", toDo: "To do", waiting: "Waiting for check", doneToday: "Verified",
      noJobs: "No jobs for your district right now.", completed: "Completed",
      redo: "Camera still sees snow after “done” — please clear again",
      waitingCheck: "Reported done — waiting for the camera check",
      complaints: "Complaints", sinceOpened: "Open for", openInMap: "Open in map", directions: "Directions",
      cleared: "Cleared", confirmCleared: "Mark this place as cleared? The next camera frame will check it.",
      pickContractor: "Choose a contractor in the header.", lastFrame: "Latest view of the sidewalk",
      residentPhotos: "Resident photos", verifiedAt: "Verified", ago: "ago",
      h: "h", min: "min", s: "s", justNow: "just now",
    },
    lv: {
      inspector: "Inspektors", contractor: "Darbuzņēmējs", role: "Skatīt kā", residentForm: "Iedzīvotāju forma",
      source: "Pirmkods", loading: "Ielādē…", retry: "Mēģināt vēlreiz",
      demo: "Demo", snowfallEnd: "Snigšana beidzās", deadline: "Tīrīšanas termiņš", notSet: "nav iestatīts",
      clearing: "Tīrīšanas laiks", hourIs: "1 h =", sec: "s", passed: "pagājis", in: "pēc",
      btnSnowfall: "Snigšana beigusies tagad", btnReset: "Atiestatīt demo", btnApply: "Lietot",
      confirmReset: "Dzēst visus brīdinājumus, signālus, ziņojumus un vēsturi? Iestatījumi paliks.",
      hourSecondsLabel: "1 h = s", clearingHoursLabel: "Tīrīšana, h",
      demoTimeNote: "Ilgumi rādīti scenārija stundās",
      tabToday: "Kur doties šodien", tabAll: "Visi brīdinājumi", tabReports: "Ziņojumi", tabStats: "Reakcijas laiks",
      todayHint: "10 svarīgākie pēc steidzamības un vecuma: nosūtītie darbi, darbuzņēmēja pārbaudes un tas, ko jāskata tikai jums.",
      allStatuses: "Visi statusi", activeOnly: "Tikai aktīvie",
      nothingToday: "Šobrīd nekur nav jābrauc.", noAlerts: "Brīdinājumu vēl nav.",
      st_watch: "Novērošanā", st_open: "Atvērts", st_done_reported: "Ziņots: notīrīts", st_verified: "Pārbaudīts", st_reopened: "Atvērts atkārtoti",
      lv_high: "Augsta", lv_medium: "Vidēja", lv_low: "Zema",
      watchNote: "Tīrīšanas termiņš vēl nav beidzies. Darbuzņēmējs šo brīdinājumu neredz.",
      why_reopened: "Atvērts atkārtoti", why_check_done: "Pārbaudīt “notīrīts”", why_possible_ice: "Iespējams ledus",
      why_low_confidence: "Neskaidrs kadrs", why_ice_report: "Iedzīvotājs: ledus / lāstekas",
      why_review_report: "Ziņojums jāpārbauda", why_high: "Augsta steidzamība", flagCouncil: "Atzīmēts domei",
      pl_sidewalk: "Ietve", pl_crossing: "Gājēju pāreja", pl_ramp: "Nobrauktuve", pl_stop: "Pietura", pl_path: "Celiņš",
      pl_square: "Laukums", pl_other: "Cita vieta",
      hz_clear: "Tīrs", hz_snow: "Sniegs", hz_blocked: "Aizsprostots", hz_possible_ice: "Iespējams ledus", hz_ice: "Ledus",
      hz_icicles: "Lāstekas", hz_other: "Cits", hz_reported: "Ziņojuši iedzīvotāji",
      ps_no: "Nevar paiet", ps_partly: "Daļēji var paiet", ps_yes: "Var paiet",
      r_camera_blocked: "Kamera: aizsprostots, {share} zonas", r_camera_snow: "Kamera: sniegs, var paiet ({share})",
      r_camera_possible_ice: "Kamera: iespējams ledus", r_camera_clear: "Kamera: tīrs",
      r_resident_no: "Iedzīvotājs: nevar paiet", r_resident_partly: "Iedzīvotājs: daļēji var paiet", r_resident_yes: "Iedzīvotājs: var paiet",
      r_place: "Vieta: {value}", r_near_sensitive: "Blakus skola vai slimnīca",
      r_confirmations: "{count} apstiprinājums(-i) no citiem avotiem", r_cap_unconfirmed: "Viens neapstiprināts ziņojums: ne augstāk par vidēju",
      lowConfTag: "ticam. {c}",
      back: "Atpakaļ", alert: "Brīdinājums", urgency: "Steidzamība", score: "punkti", why: "Kāpēc šāda steidzamība", flags: "Jāpievērš uzmanība",
      where: "Kur", district: "Rajons", contractorL: "Darbuzņēmējs", none: "—", zone: "Kameras zona", reportOnly: "Tikai iedzīvotāju ziņojumi (bez kameras)",
      timeline: "Laika līnija", firstSeen: "Pirmoreiz redzēts", detected: "Pārkāpums konstatēts", opened: "Nosūtīts darbuzņēmējam",
      doneReported: "Darbuzņēmējs: notīrīts", verified: "Pārbaudīts", responseTime: "Reakcijas laiks", notifyDelay: "Paziņošanas aizkave",
      reopenedTimes: "Atvērts atkārtoti", times: "reizi(-es)",
      evidence: "Pirms / pēc", before: "Pirms", after: "Pēc (jaunākais)", fullFrame: "Pilns kadrs", crop: "Izgriezums darbuzņēmējam",
      noFrames: "Kameras kadru nav — zemāk iedzīvotāju foto.",
      reports: "Iedzīvotāju ziņojumi", noReports: "Iedzīvotāju ziņojumu nav.", duplicate: "tā pati ierīce — netiek skaitīts",
      notCounted: "netiek skaitīts", signals: "Kameras signāli", history: "Statusu vēsture (pierādījums)",
      when: "Kad", from: "No", to: "Uz", who: "Kas", note: "Piezīme", time: "Laiks", cls: "Klase", share: "Daļa", conf: "Ticam.",
      actions: "Darbības", noteLabel: "Piezīme (nav obligāta, tiek saglabāta vēsturē)",
      actDispatch: "Nosūtīt tagad", actVerify: "Apstiprināt uz vietas", actDispute: "Apstrīdēt “notīrīts”", actReopenVerified: "Apstrīdēt pārbaudi",
      done: "Gatavs", saved: "Saglabāts",
      reviewQueue: "Jāpārbauda", rejected: "Modelis noraidīja", accept: "Pieņemt", reject: "Noraidīt",
      aiSays: "Modelis", noReview: "Nav ziņojumu, kas gaida pārbaudi.", noRejected: "Nav noraidītu ziņojumu.",
      spamTitle: "Aizsardzība pret surogātu (24 h)", blockSender: "Bloķēt sūtītāju", unblock: "Atbloķēt", blockedSenders: "Bloķētie sūtītāji",
      noBlocked: "Neviens nav bloķēts.", samePhotoAs: "Tas pats foto kā #{n}", blockAsk: "Bloķēt šo sūtītāju uz 24 stundām? Viņa jaunie ziņojumi tiks atteikti.",
      sp_blocked: "atteikts: bloķēts sūtītājs", sp_device_hourly_limit: "atteikts: stundas limits", sp_device_daily_limit: "atteikts: dienas limits",
      sp_ip_hourly_limit: "atteikts: pārāk daudz no viena tīkla", sp_outside_area: "atteikts: ārpus Rīgas",
      sp_duplicate_place: "tās pašas vietas atkārtojums (neskaitās)", sp_same_photo: "tas pats foto vēlreiz (neskaitās)",
      spLimits: "Limiti: {h}/stundā un {d}/dienā vienam sūtītājam, {ip}/stundā vienam tīklam; bloķē uz {bh} h pēc {r} noraidītiem foto vai {dup} atkārtojumiem.",
      until: "līdz",
      byContractor: "Pēc darbuzņēmēja", byDistrict: "Pēc rajona", withinH: "Slēgts (h) laikā",
      c_opened: "Atvērti", c_verified: "Pārbaudīti", c_active: "Aktīvi", c_avg: "Vid. reakcija, h", c_within: "Slēgti ≤ {n} h",
      c_reopened: "Atkārtoti", c_notify: "Vid. paziņoš., min", c_kpi: "Paziņots ≤ {n} min",
      exportGeo: "Eksportēt GeoJSON", exportCsv: "Eksportēt CSV", noStats: "Darbuzņēmējiem vēl nekas nav nosūtīts.",
      myJobs: "Mani darbi", listView: "Saraksts", mapView: "Karte", toDo: "Jādara", waiting: "Gaida pārbaudi", doneToday: "Pārbaudīti",
      noJobs: "Jūsu rajonā šobrīd darbu nav.", completed: "Pabeigtie",
      redo: "Kamera pēc “notīrīts” joprojām redz sniegu — lūdzu, notīriet vēlreiz",
      waitingCheck: "Ziņots: notīrīts — gaida kameras pārbaudi",
      complaints: "Sūdzības", sinceOpened: "Atvērts", openInMap: "Atvērt kartē", directions: "Maršruts",
      cleared: "Notīrīts", confirmCleared: "Atzīmēt šo vietu kā notīrītu? Nākamais kameras kadrs to pārbaudīs.",
      pickContractor: "Izvēlieties darbuzņēmēju galvenē.", lastFrame: "Jaunākais ietves skats",
      residentPhotos: "Iedzīvotāju foto", verifiedAt: "Pārbaudīts", ago: "atpakaļ",
      h: "h", min: "min", s: "s", justNow: "tikko",
    },
  };

  let lang = "en";
  try { lang = localStorage.getItem("lantern_lang") || (navigator.language || "").slice(0, 2) || "en"; } catch (e) { /* storage blocked */ }
  if (!I18N[lang]) lang = "en";
  document.documentElement.lang = lang;

  function t(key, vars) {
    let s = (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
    if (vars) for (const k in vars) s = s.split("{" + k + "}").join(vars[k]);
    return s;
  }
  function setLang(l) {
    if (!I18N[l]) return;
    lang = l;
    try { localStorage.setItem("lantern_lang", l); } catch (e) { /* ignore */ }
    document.documentElement.lang = l;
    document.dispatchEvent(new CustomEvent("lantern:lang"));
  }

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function api(path, opts) {
    const o = Object.assign({ headers: {} }, opts || {});
    if (o.json !== undefined) {
      o.method = o.method || "POST";
      o.headers["Content-Type"] = "application/json";
      o.body = JSON.stringify(o.json);
      delete o.json;
    }
    const r = await fetch(path, o);
    let data = null;
    const text = await r.text();
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
    if (!r.ok) {
      let msg = (data && data.detail) || r.statusText || "Request failed";
      if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join("; ");
      const err = new Error(msg);
      err.status = r.status;
      throw err;
    }
    return data;
  }

  // ---------------------------------------------------------------- time
  // server/client clock offset so countdowns follow the server
  let clockOffset = 0;
  function syncClock(serverNow) {
    if (!serverNow) return;
    clockOffset = new Date(serverNow).getTime() - Date.now();
  }
  function now() { return Date.now() + clockOffset; }
  function fmtTime(iso) {
    if (!iso) return t("none");
    const d = new Date(iso);
    const p = (n) => String(n).padStart(2, "0");
    const today = new Date(now());
    const sameDay = d.toDateString() === today.toDateString();
    const hm = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
    return sameDay ? hm : `${p(d.getDate())}.${p(d.getMonth() + 1)} ${hm}`;
  }
  // real seconds -> scenario duration text (hour_seconds real seconds = 1 rule hour)
  let hourSeconds = 3600;
  function setHourSeconds(h) { if (h > 0) hourSeconds = h; }
  function fmtDur(realSeconds) {
    if (realSeconds == null || isNaN(realSeconds)) return t("none");
    const rule = Math.max(0, realSeconds) * 3600 / hourSeconds;
    if (rule < 60) return rule < 5 ? t("justNow") : `${Math.round(rule)} ${t("s")}`;
    const mins = Math.round(rule / 60);
    if (mins < 60) return `${mins} ${t("min")}`;
    const h = Math.floor(mins / 60), m = mins % 60;
    return m ? `${h} ${t("h")} ${m} ${t("min")}` : `${h} ${t("h")}`;
  }
  function since(iso) { return iso ? fmtDur((now() - new Date(iso).getTime()) / 1000) : t("none"); }
  // live "time since" spans: rendered empty (so HTML stays stable between polls), filled every second
  function sinceSpan(iso, suffix) {
    if (!iso) return esc(t("none"));
    return `<span data-since="${esc(iso)}" data-suffix="${esc(suffix || "")}">…</span>`;
  }
  function updateSince(root) {
    (root || document).querySelectorAll("[data-since]").forEach((el) => {
      const s = el.dataset.suffix;
      el.textContent = since(el.dataset.since) + (s ? " " + s : "");
    });
  }
  setInterval(() => updateSince(), 1000);
  function hours(h) { return h == null ? t("none") : (Math.round(h * 10) / 10).toFixed(1); }
  function pct(x) { return x == null ? t("none") : `${Math.round(x * 100)}%`; }

  // ---------------------------------------------------------------- labels
  const statusBadge = (s) => `<span class="badge st-${esc(s)}">${esc(t("st_" + s))}</span>`;
  const levelBadge = (lvl, status) => status === "watch"
    ? `<span class="lvl lvl-watch">${esc(t("lv_" + lvl))}</span>`
    : `<span class="lvl lvl-${esc(lvl)}">${esc(t("lv_" + lvl))}</span>`;
  const place = (p) => t("pl_" + (p || "other"));
  const hazard = (h) => (h ? t("hz_" + h) : t("none"));

  function reasonText(r) {
    const share = r.share != null ? pct(r.share) : "";
    let s = t("r_" + r.code, { share, value: place(r.value), count: r.count });
    if (r.confidence != null && r.confidence < 0.5) s += ` · ${t("lowConfTag", { c: r.confidence.toFixed(2) })}`;
    return s;
  }

  const COLORS = { high: "#d64545", medium: "#e8a33d", low: "#4c7bd9", watch: "#9aa3ae", verified: "#3e9b6b", reopened: "#8e44ad" };
  function alertColor(a) {
    if (a.status === "verified") return COLORS.verified;
    if (a.status === "watch") return COLORS.watch;
    return COLORS[a.urgency_level] || COLORS.low;
  }

  // ---------------------------------------------------------------- header / footer
  const LOGO = `<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><rect x="12" y="2" width="8" height="4" rx="1.5" fill="#f2a93b"/><path d="M9 9h14l-2 16H11z" fill="#f2a93b" opacity=".25"/><path d="M9 9h14l-2 16H11z" fill="none" stroke="#f2a93b" stroke-width="2" stroke-linejoin="round"/><circle cx="16" cy="17" r="3.4" fill="#f2a93b"/><rect x="8" y="26" width="16" height="3" rx="1.5" fill="#f2a93b"/></svg>`;

  function renderHeader(el, meta, current) {
    const opts = [`<option value="inspector" ${current === "inspector" ? "selected" : ""}>${esc(t("inspector"))}</option>`]
      .concat((meta.contractors || []).map((c) => {
        const v = "contractor:" + c.id;
        return `<option value="${esc(v)}" ${current === v ? "selected" : ""}>${esc(t("contractor"))}: ${esc(c.name)} (${esc((c.districts || []).join(", "))})</option>`;
      }));
    el.innerHTML = `
      <a class="brand" href="/inspector">${LOGO}<span>Lantern</span></a>
      <span class="spacer"></span>
      <label for="roleSel">${esc(t("role"))}</label>
      <select id="roleSel" aria-label="${esc(t("role"))}">${opts.join("")}</select>
      <a class="tb-link" href="/report" target="_blank" rel="noopener">${esc(t("residentForm"))}</a>
      <span class="lang" role="group" aria-label="Language">
        <button type="button" data-lang="en" aria-pressed="${lang === "en"}">EN</button>
        <button type="button" data-lang="lv" aria-pressed="${lang === "lv"}">LV</button>
      </span>`;
    el.querySelector("#roleSel").addEventListener("change", (e) => {
      const v = e.target.value;
      location.href = v === "inspector" ? "/inspector" : "/contractor?contractor=" + encodeURIComponent(v.split(":")[1]);
    });
    el.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
  }

  function renderFooter(el, meta) {
    el.innerHTML = `
      <span>Map: ${meta.tile_attribution || "OpenStreetMap"}</span>
      <span>${esc(meta.images_credit || "")}</span>
      <a href="${esc(meta.source_url || "#")}" target="_blank" rel="noopener">${esc(t("source"))}</a>
      <span>AGPL-3.0</span>`;
  }

  // ---------------------------------------------------------------- ui bits
  let toastTimer = null;
  function toast(msg, isError) {
    let el = document.querySelector(".toast");
    if (!el) { el = document.createElement("div"); el.className = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
    el.textContent = msg;
    el.classList.toggle("error", !!isError);
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.add("hidden"), isError ? 6000 : 2500);
  }

  function lightbox(src) {
    const box = document.createElement("div");
    box.className = "lightbox";
    box.innerHTML = `<img src="${esc(src)}" alt="">`;
    const close = () => { box.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    box.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    document.body.appendChild(box);
  }
  document.addEventListener("click", (e) => {
    const img = e.target.closest("img[data-zoom]");
    if (img) { e.preventDefault(); e.stopPropagation(); lightbox(img.dataset.zoom || img.src); }
  });

  function makeMap(el, meta) {
    const map = L.map(el, { zoomControl: true, attributionControl: true }).setView([56.9515, 24.112], 15);
    L.tileLayer(meta.tile_url, { maxZoom: 19, attribution: meta.tile_attribution }).addTo(map);
    if (window.ResizeObserver) new ResizeObserver(() => map.invalidateSize()).observe(el);
    return map;
  }
  const toLatLngs = (poly) => (poly || []).map((p) => [p[1], p[0]]);

  window.Lantern = {
    t, setLang, get lang() { return lang; }, esc, api, syncClock, now, fmtTime, fmtDur, since, sinceSpan, updateSince, hours, pct,
    setHourSeconds, statusBadge, levelBadge, place, hazard, reasonText, alertColor, COLORS,
    renderHeader, renderFooter, toast, lightbox, makeMap, toLatLngs,
  };
})();
