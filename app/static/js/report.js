/* Lantern resident form: photo + place -> POST /reports (the model reads what is there and how bad).
   No login. The server sets a random device cookie; this page never sends a device id. */
(function () {
  "use strict";

  const I18N = {
    lv: {
      page_title: "Lantern — ziņot par ietvi",
      title: "Ziņo par bīstamu ietvi",
      lead: "Foto un vieta — 15 sekundes. Pārējo MI nolasīs no foto.",
      photo_h: "Foto", photo_btn: "Uzņemt vai izvēlēties foto", photo_change: "Mainīt foto",
      loc_h: "Vieta", loc_btn: "Mana atrašanās vieta",
      loc_hint: "Pieskaries kartei vai pavelc atzīmi uz precīzo vietu.",
      loc_finding: "Nosaku atrašanās vietu…",
      loc_found: "Vieta atrasta (±{m} m). Ja vajag, pavelc atzīmi.",
      loc_set: "Vieta atzīmēta. Pavelc atzīmi, lai precizētu.",
      loc_denied: "Atrašanās vieta nav pieejama — pieskaries kartei, kur ir problēma.",
      pass_h: "Vai var paiet garām?", pass_no: "Nevar", pass_partly: "Daļēji", pass_yes: "Var",
      more_h: "Vairāk informācijas (nav obligāti)",
      haz_h: "Kas tur ir?", haz_snow: "Sniegs", haz_ice: "Ledus", haz_icicles: "Lāstekas", haz_other: "Cits",
      place_h: "Kāda vieta?", place_sidewalk: "Ietve", place_crossing: "Gājēju pāreja", place_ramp: "Nobrauktuve",
      place_stop: "Pietura", place_other: "Cits",
      comment_h: "Komentārs", comment_ph: "Piemēram: sniega valnis pie pārejas",
      regno_h: "Domes reģistrācijas numurs (ja ir)", regno_ph: "Oficiālai sūdzībai, nav obligāts",
      submit: "Sūtīt", sending: "Sūta un pārbauda foto…",
      need: "Vēl vajag: {list}", need_photo: "foto", need_loc: "vietu", need_pass: "atbildi, vai var paiet",
      err_send: "Neizdevās nosūtīt. Pārbaudi internetu un mēģini vēlreiz.",
      err_server: "Serveris atbildēja ar kļūdu: {msg}",
      err_too_many: "Tu jau esi nosūtījis daudz ziņojumu. Paldies! Lūdzu, mēģini vēlāk.",
      err_outside: "Šī vieta ir ārpus Rīgas. Pārvieto atzīmi kartē uz Rīgu.",
      done_ok_t: "Paldies, signāls saņemts!",
      done_ok: "Pilsētas inspektors redzēs tavu ziņojumu. Saglabā kodu, lai pārbaudītu statusu.",
      done_review_t: "Paldies, signāls saņemts!",
      done_review: "Inspektors vēl pārbaudīs foto. Saglabā kodu, lai pārbaudītu statusu.",
      done_reject_t: "Paldies!",
      done_reject: "Diemžēl foto neizskatās pēc bīstamas ietves (sniegs, ledus, lāstekas), tāpēc inspektoram to nenosūtījām. Ja kļūdījāmies, mēģini vēlreiz ar tuvāku foto.",
      merged: "Par šo vietu jau ziņoja — tavs signāls paaugstina prioritāti.",
      ticket: "Pieteikuma kods", again: "Ziņot vēlreiz",
      check_h: "Pārbaudīt pieteikumu", check_ph: "Kods, piem. K7QM2XPA", check_btn: "Pārbaudīt",
      check_none: "Šāds kods nav atrasts.", mine: "Mani pieteikumi",
      st_accepted: "Pieņemts", st_in_review: "Gaida inspektora pārbaudi", st_rejected: "Noraidīts — neizskatās pēc bīstamības",
      st_watch: "Pieņemts, tīrīšanas termiņš vēl nav beidzies",
      st_open: "Nosūtīts tīrītājiem",
      st_done_reported: "Tīrītāji ziņo, ka notīrīts — pilsēta pārbauda",
      st_reopened: "Joprojām nav notīrīts — nosūtīts atkārtoti",
      st_verified: "Notīrīts un pārbaudīts",
      st_cleared_in_time: "Notīrīts laikā, pirms termiņa",
      others: "Vēl {n} iedzīvotāji ziņoja par šo vietu",
      camera: "Apstiprina pilsētas kamera",
      updated: "Atjaunots {t}",
      note_1201: "Lantern papildina tālruni 1201, nevis aizstāj to. Steidzamos gadījumos zvani 1201 vai 112.",
      privacy: "Mēs neprasām vārdu, tālruni vai e-pastu. Foto redz pilsētas inspektors un tīrītāji.",
    },
    en: {
      page_title: "Lantern — report a sidewalk",
      title: "Report a dangerous sidewalk",
      lead: "A photo and the place — 15 seconds. The AI reads the rest from the photo.",
      photo_h: "Photo", photo_btn: "Take or choose a photo", photo_change: "Change photo",
      loc_h: "Place", loc_btn: "Use my location",
      loc_hint: "Tap the map or drag the pin to the exact spot.",
      loc_finding: "Finding your location…",
      loc_found: "Location found (±{m} m). Drag the pin if needed.",
      loc_set: "Place marked. Drag the pin to adjust.",
      loc_denied: "Location is not available — tap the map where the problem is.",
      pass_h: "Can people get through?", pass_no: "No", pass_partly: "Partly", pass_yes: "Yes",
      more_h: "More details (optional)",
      haz_h: "What is there?", haz_snow: "Snow", haz_ice: "Ice", haz_icicles: "Icicles", haz_other: "Other",
      place_h: "What kind of place?", place_sidewalk: "Sidewalk", place_crossing: "Crossing", place_ramp: "Curb ramp",
      place_stop: "Bus stop", place_other: "Other",
      comment_h: "Comment", comment_ph: "e.g. snowbank at the crossing",
      regno_h: "Council registration number (if any)", regno_ph: "For a formal complaint, optional",
      submit: "Send", sending: "Sending and checking the photo…",
      need: "Still needed: {list}", need_photo: "a photo", need_loc: "the place", need_pass: "whether people can get through",
      err_send: "Could not send. Check your connection and try again.",
      err_server: "The server returned an error: {msg}",
      err_too_many: "You have already sent a lot of reports. Thank you! Please try again later.",
      err_outside: "This place is outside Riga. Move the pin on the map to Riga.",
      done_ok_t: "Thank you, signal received!",
      done_ok: "The city inspector will see your report. Keep the code to check its status.",
      done_review_t: "Thank you, signal received!",
      done_review: "An inspector will check the photo. Keep the code to check its status.",
      done_reject_t: "Thank you!",
      done_reject: "Unfortunately the photo doesn't look like a sidewalk hazard (snow, ice, icicles), so it was not sent to the inspector. If we got it wrong, try again with a closer photo.",
      merged: "This place was already reported — your signal raises its priority.",
      ticket: "Ticket", again: "Report another",
      check_h: "Check a ticket", check_ph: "Code, e.g. K7QM2XPA", check_btn: "Check",
      check_none: "No ticket with this code.", mine: "My tickets",
      st_accepted: "Accepted", st_in_review: "Waiting for an inspector check", st_rejected: "Rejected — doesn't look like a hazard",
      st_watch: "Accepted, the clearing deadline is still running",
      st_open: "Sent to the cleaning contractor",
      st_done_reported: "Contractor says it's cleared — the city is checking",
      st_reopened: "Still not cleared — sent back again",
      st_verified: "Cleared and verified",
      st_cleared_in_time: "Cleared in time, before the deadline",
      others: "{n} other residents reported this place",
      camera: "Confirmed by a city camera",
      updated: "Updated {t}",
      note_1201: "Lantern complements the 1201 phone line, it does not replace it. In urgent cases call 1201 or 112.",
      privacy: "We never ask for your name, phone or email. The photo is seen by the city inspector and the contractor.",
    },
    ru: {
      page_title: "Lantern — сообщить о тротуаре",
      title: "Сообщите об опасном тротуаре",
      lead: "Фото и место — 15 секунд. Остальное ИИ поймёт по фото.",
      photo_h: "Фото", photo_btn: "Сделать или выбрать фото", photo_change: "Заменить фото",
      loc_h: "Место", loc_btn: "Моё местоположение",
      loc_hint: "Нажмите на карту или перетащите метку на точное место.",
      loc_finding: "Определяю местоположение…",
      loc_found: "Место найдено (±{m} м). При необходимости перетащите метку.",
      loc_set: "Место отмечено. Перетащите метку, чтобы уточнить.",
      loc_denied: "Местоположение недоступно — нажмите на карту там, где проблема.",
      pass_h: "Можно ли пройти?", pass_no: "Нельзя", pass_partly: "Частично", pass_yes: "Можно",
      more_h: "Подробнее (необязательно)",
      haz_h: "Что там?", haz_snow: "Снег", haz_ice: "Лёд", haz_icicles: "Сосульки", haz_other: "Другое",
      place_h: "Что за место?", place_sidewalk: "Тротуар", place_crossing: "Переход", place_ramp: "Съезд",
      place_stop: "Остановка", place_other: "Другое",
      comment_h: "Комментарий", comment_ph: "Например: снежный вал у перехода",
      regno_h: "Регистрационный номер думы (если есть)", regno_ph: "Для формальной жалобы, необязательно",
      submit: "Отправить", sending: "Отправляю и проверяю фото…",
      need: "Ещё нужно: {list}", need_photo: "фото", need_loc: "место", need_pass: "можно ли пройти",
      err_send: "Не удалось отправить. Проверьте интернет и попробуйте ещё раз.",
      err_server: "Сервер ответил ошибкой: {msg}",
      err_too_many: "Вы уже отправили много сообщений. Спасибо! Попробуйте позже.",
      err_outside: "Это место за пределами Риги. Передвиньте метку на карте в Ригу.",
      done_ok_t: "Спасибо, сигнал принят!",
      done_ok: "Инспектор города увидит ваше сообщение. Сохраните код, чтобы проверить статус.",
      done_review_t: "Спасибо, сигнал принят!",
      done_review: "Инспектор дополнительно проверит фото. Сохраните код, чтобы проверить статус.",
      done_reject_t: "Спасибо!",
      done_reject: "К сожалению, фото не похоже на опасный тротуар (снег, лёд, сосульки), поэтому к инспектору оно не ушло. Если мы ошиблись, попробуйте ещё раз с фото поближе.",
      merged: "Об этом месте уже сообщали — ваш сигнал повышает приоритет.",
      ticket: "Код заявки", again: "Сообщить ещё",
      check_h: "Проверить заявку", check_ph: "Код, напр. K7QM2XPA", check_btn: "Проверить",
      check_none: "Заявка с таким кодом не найдена.", mine: "Мои заявки",
      st_accepted: "Принято", st_in_review: "Ждёт проверки инспектора", st_rejected: "Отклонено — не похоже на опасность",
      st_watch: "Принято, срок уборки ещё идёт",
      st_open: "Передано подрядчику",
      st_done_reported: "Подрядчик сообщил, что убрано — город проверяет",
      st_reopened: "Всё ещё не убрано — отправлено повторно",
      st_verified: "Убрано и проверено",
      st_cleared_in_time: "Убрано вовремя, до срока",
      others: "Ещё {n} жителей сообщили об этом месте",
      camera: "Подтверждено камерой города",
      updated: "Обновлено {t}",
      note_1201: "Lantern дополняет телефон 1201, а не заменяет его. В срочных случаях звоните 1201 или 112.",
      privacy: "Мы не спрашиваем имя, телефон или e-mail. Фото видят инспектор города и подрядчик.",
    },
  };

  const RIGA = [56.9496, 24.1052];
  const MAX_SIDE = 1600;
  const $ = (id) => document.getElementById(id);

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };

  let lang = store.get("lantern_lang", null) || pickLang();
  const state = { photo: null, lat: null, lon: null, locMsg: "loc_hint", locArg: {} };
  let map, marker, lastTicket = null, pollTimer = null;

  function pickLang() {
    const n = (navigator.language || "lv").slice(0, 2).toLowerCase();
    return n === "ru" ? "ru" : n === "en" ? "en" : "lv";
  }
  function tr(key, args) {
    let s = (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
    if (args) Object.keys(args).forEach((k) => { s = s.replace("{" + k + "}", args[k]); });
    return s;
  }
  function applyLang() {
    document.documentElement.lang = lang;
    document.title = tr("page_title");
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = tr(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = tr(el.dataset.i18nPh); });
    document.querySelectorAll(".langs button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
    setLocMsg(state.locMsg, state.locArg, $("loc-status").className.replace("hint", "").trim());
    updateMissing();
    renderMine();
    if (lastTicket && !$("done-view").hidden) renderDone(lastTicket);
  }

  // ------------------------------------------------------------------ photo
  function downscale(file) {
    return new Promise((resolve) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
        if (scale === 1 && file.type === "image/jpeg" && file.size < 2.5e6) { URL.revokeObjectURL(url); resolve(file); return; }
        const c = document.createElement("canvas");
        c.width = Math.round(img.naturalWidth * scale);
        c.height = Math.round(img.naturalHeight * scale);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        c.toBlob((b) => resolve(b || file), "image/jpeg", 0.85);
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(file); }; // e.g. HEIC the browser can't decode
      img.src = url;
    });
  }

  $("photo").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const blob = await downscale(file);
    state.photo = blob;
    const prev = $("photo-preview");
    if (prev.src) URL.revokeObjectURL(prev.src);
    prev.src = URL.createObjectURL(blob);
    prev.hidden = false;
    $("photo-empty").hidden = true;
    $("photo-drop").classList.add("has-photo");
    $("photo-change").hidden = false;
    $("sec-photo").classList.add("ok");
    updateMissing();
  });
  $("photo-change").addEventListener("click", () => $("photo").click());

  // ------------------------------------------------------------------ map / location
  function setLocMsg(key, args, cls) {
    state.locMsg = key; state.locArg = args || {};
    const el = $("loc-status");
    el.textContent = tr(key, state.locArg);
    el.className = "hint" + (cls ? " " + cls : "");
  }
  // source: "gps" when the browser measured it, "map" when the person tapped or dragged the pin.
  // A map point alone can't send the contractor (anyone can tap anywhere): the inspector looks first.
  function setPoint(lat, lon, zoom, source = "map") {
    state.lat = +lat.toFixed(6); state.lon = +lon.toFixed(6);
    state.loc_source = source;
    if (!marker) {
      const icon = L.divIcon({ className: "", html: '<div class="pin"></div>', iconSize: [30, 30], iconAnchor: [15, 30] });
      marker = L.marker([lat, lon], { draggable: true, icon, keyboard: true, title: "📍" }).addTo(map);
      marker.on("dragend", () => { const p = marker.getLatLng(); setPoint(p.lat, p.lng); setLocMsg("loc_set", {}, "good"); });
    } else {
      marker.setLatLng([lat, lon]);
    }
    if (zoom) map.setView([lat, lon], zoom);
    $("sec-loc").classList.add("ok");
    updateMissing();
  }
  function locate(auto) {
    if (!("geolocation" in navigator)) { if (!auto) setLocMsg("loc_denied", {}, "warn"); return; }
    setLocMsg("loc_finding");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPoint(pos.coords.latitude, pos.coords.longitude, 18, "gps");
        setLocMsg("loc_found", { m: Math.round(pos.coords.accuracy || 0) }, "good");
      },
      () => setLocMsg(state.lat === null ? "loc_denied" : "loc_set", {}, state.lat === null ? "warn" : "good"),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 }
    );
  }
  function initMap(meta) {
    map = L.map("map", { zoomControl: true, attributionControl: true }).setView(RIGA, 14);
    L.tileLayer(meta.tile_url, { maxZoom: 19, attribution: meta.tile_attribution }).addTo(map);
    map.on("click", (e) => { setPoint(e.latlng.lat, e.latlng.lng); setLocMsg("loc_set", {}, "good"); });
    $("locate").addEventListener("click", () => locate(false));
    locate(true);
  }

  function missing() {
    const m = [];
    if (!state.photo) m.push(tr("need_photo"));
    if (state.lat === null) m.push(tr("need_loc"));
    return m;
  }
  function updateMissing() {
    const m = missing();
    $("missing").textContent = m.length ? tr("need", { list: m.join(", ") }) : "";
  }

  // ------------------------------------------------------------------ submit
  $("report-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("form-error");
    err.hidden = true;
    const m = missing();
    if (m.length) {
      updateMissing();
      const first = !state.photo ? "sec-photo" : "sec-loc";
      $(first).scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const fd = new FormData();
    fd.append("photo", state.photo, "photo.jpg");
    fd.append("lat", String(state.lat));
    fd.append("lon", String(state.lon));
    const regno = ($("regno") && $("regno").value || "").trim();
    if (regno) fd.append("registration_no", regno);
    fd.append("channel", "web");
    fd.append("location_source", state.loc_source || "map");
    const btn = $("submit");
    btn.disabled = true;
    btn.firstElementChild.textContent = tr("sending");
    try {
      const resp = await fetch("/reports", { method: "POST", body: fd, credentials: "same-origin" });
      const data = await resp.json().catch(() => ({}));
      if (resp.status !== 201) {
        // spam limits (429) and "outside Riga" (422) come back as {detail: {code, message}}
        const code = data.detail && typeof data.detail === "object" ? data.detail.code : null;
        err.textContent = resp.status === 429 ? tr("err_too_many")
          : code === "outside_area" ? tr("err_outside")
          : tr("err_server", { msg: typeof data.detail === "string" ? data.detail : resp.status });
        err.hidden = false;
        return;
      }
      const mine = store.get("lantern_tickets", []);
      mine.unshift({ ticket: data.ticket, at: new Date().toISOString(), relevant: data.relevant });
      store.set("lantern_tickets", mine.slice(0, 10));
      lastTicket = data;
      showDone(data);
    } catch (ex) {
      err.textContent = tr("err_send");
      err.hidden = false;
    } finally {
      btn.disabled = false;
      btn.firstElementChild.textContent = tr("submit");
    }
  });

  function showDone(data) {
    $("form-view").hidden = true;
    $("done-view").hidden = false;
    window.scrollTo(0, 0);
    renderDone(data);
    checkTicket(data.ticket, $("done-status"));
    clearInterval(pollTimer);
    if (data.relevant !== "reject") pollTimer = setInterval(() => checkTicket(data.ticket, $("done-status")), 15000);
  }
  function renderDone(data) {
    const kind = data.relevant === "reject" ? "reject" : data.relevant === "review" ? "review" : "ok";
    $("done-icon").textContent = kind === "reject" ? "🙏" : "🏮";
    $("done-icon").className = "done-icon" + (kind === "reject" ? " reject" : "");
    $("done-title").textContent = tr("done_" + kind + "_t");
    $("done-text").textContent = tr("done_" + kind);
    $("done-ticket").textContent = data.ticket;
  }
  $("again").addEventListener("click", () => {
    clearInterval(pollTimer);
    location.href = "/report";
  });

  // ------------------------------------------------------------------ ticket status
  function line(cls, text) {
    const d = document.createElement("div");
    d.className = "status-line";
    const b = document.createElement("span");
    b.className = "badge " + cls;
    const t = document.createElement("span");
    t.textContent = text;
    d.append(b, t);
    return d;
  }
  async function checkTicket(code, box) {
    code = (code || "").trim().toUpperCase();
    if (!code) return;
    try {
      const resp = await fetch("/reports/ticket/" + encodeURIComponent(code));
      box.replaceChildren();
      if (resp.status === 404) { box.append(line("rejected", tr("check_none"))); return; }
      const st = await resp.json();
      if (st.state === "rejected") { box.append(line("rejected", tr("st_rejected"))); return; }
      if (st.state === "in_review") box.append(line("in_review", tr("st_in_review")));
      if (st.alert_status) box.append(line(st.alert_status, tr("st_" + st.alert_status)));
      else if (st.state === "accepted") box.append(line("accepted", tr("st_accepted")));
      if (st.other_reports) box.append(line("watch", tr("others", { n: st.other_reports })));
      if (st.camera_confirmed) box.append(line("verified", tr("camera")));
      if (st.updated_at) {
        const p = document.createElement("p");
        p.className = "hint";
        p.textContent = tr("updated", { t: new Date(st.updated_at).toLocaleString(lang === "lv" ? "lv-LV" : lang === "ru" ? "ru-RU" : "en-GB") });
        box.append(p);
      }
      if (st.alert_status === "verified" || st.alert_status === "cleared_in_time") clearInterval(pollTimer);
    } catch (e) {
      box.replaceChildren(line("rejected", tr("err_send")));
    }
  }
  $("check-form").addEventListener("submit", (e) => {
    e.preventDefault();
    checkTicket($("check-input").value, $("check-result"));
  });
  function renderMine() {
    const ul = $("mine");
    ul.replaceChildren();
    const mine = store.get("lantern_tickets", []);
    if (!mine.length) return;
    const h = document.createElement("li");
    h.className = "hint";
    h.textContent = tr("mine");
    ul.append(h);
    mine.slice(0, 5).forEach((m) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      const code = document.createElement("strong");
      code.textContent = m.ticket;
      const when = document.createElement("small");
      when.textContent = new Date(m.at).toLocaleString(lang === "lv" ? "lv-LV" : lang === "ru" ? "ru-RU" : "en-GB");
      b.append(code, when);
      b.addEventListener("click", () => { $("check-input").value = m.ticket; checkTicket(m.ticket, $("check-result")); });
      li.append(b);
      ul.append(li);
    });
  }

  // ------------------------------------------------------------------ boot
  document.querySelectorAll(".langs button").forEach((b) => b.addEventListener("click", () => {
    lang = b.dataset.lang;
    store.set("lantern_lang", lang);
    applyLang();
  }));

  const params = new URLSearchParams(location.search);
  if (params.get("lang") && I18N[params.get("lang")]) lang = params.get("lang");
  applyLang();
  if (params.get("ticket")) {
    $("check-input").value = params.get("ticket").toUpperCase();
    checkTicket(params.get("ticket"), $("check-result"));
  }

  fetch("/meta").then((r) => r.json()).catch(() => ({})).then((meta) => {
    meta = meta || {};
    meta.tile_url = meta.tile_url || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    meta.tile_attribution = meta.tile_attribution || "&copy; OpenStreetMap contributors";
    if (meta.source_url) $("source-link").href = meta.source_url;
    const tmp = document.createElement("div");
    tmp.innerHTML = meta.tile_attribution;  // server-provided attribution (config), shown as text
    $("tile-credit").textContent = "Map: " + tmp.textContent;
    initMap(meta);
  });
})();
