// Lantern Telegram Mini App: one photo taken right now in the app's own camera + the phone's
// current position. No gallery, no map, no typed address. The bot opens this page with a signed
// pass (?t=...) that tells the server who is sending; the server stamps the time itself.
(() => {
  "use strict";
  const tg = window.Telegram && window.Telegram.WebApp;
  const q = new URLSearchParams(location.search);
  const PASS = q.get("t") || "";
  const DESKTOP = ["tdesktop", "macos", "web", "weba", "webk", "unigram"];

  const T = {
    lv: {
      service: "Ziņojumi par ietvēm ziemā", proto: "Prototips",
      place_h: "Vai punkts ir pareizajā vietā?",
      place_hint: "Zilais aplis rāda, cik precīzi tālrunis zina vietu. Ja punkts nav uz pareizās ietves, pavelc to vai pieskaries kartei (līdz 10 m).",
      place_moved: "Punkts pārvietots par {m} m.", place_limit: "Tālāk par 10 m nevar. Pieej tuvāk vietai un fotografē vēlreiz.",
      err_moved: "Punktu var pārvietot ne vairāk kā par 10 m.",
      proto_note: "Prototips, izveidots RobotHack 2026. Nav nevienas iestādes oficiāls pakalpojums.",
      title: "Ziņot par ietvi", lead: "Nofotografē vietu tagad. Foto un tava atrašanās vieta aizies kopā.",
      cam_starting: "Atver kameru…",
      cam_denied: "Kamerai nav atļaujas. Atļauj kameru Telegram tālruņa iestatījumos vai izmanto tālruņa kameru zemāk.",
      cam_none: "Šeit kamera neatveras. Izmanto tālruņa kameru zemāk.",
      fallback: "Izmantot tālruņa kameru", retake: "Pārņemt", send: "Nosūtīt", sending: "Sūta…",
      loc_wait: "Nosaka atrašanās vietu…", loc_ok: "Vieta noteikta, precizitāte {m} m",
      loc_rough: "Tikai aptuvena vieta (±{m} m). Ieslēdz GPS vai izej ārā; nosūtīt var arī tā.",
      loc_denied: "Atrašanās vietai nav atļaujas. Atļauj to un mēģini vēlreiz.",
      loc_retry: "Mēģināt vēlreiz", loc_need: "Pagaidi, kamēr nosaka vietu, tad sūti.",
      close: "Aizvērt",
      privacy: "Foto tiek uzņemts tikai šeit, galerija netiek izmantota. Atrašanās vietu ņemam tikai šim ziņojumam.",
      desktop: "Atver šo tālrunī: Lantern vajag tālruņa kameru un atrašanās vietu.",
      no_pass: "Atver formu no Lantern bota (poga «Ziņot par ietvi»). Saite ir personiska.",
      res_accept: "Paldies! Ziņojums pieņemts un nodots inspektoram.",
      res_review: "Paldies! Inspektors pārbaudīs foto.",
      res_reject: "Šajā foto neredzam problēmu uz ietves (sniegs, ledus, lāstekas, aizšķērsots ceļš), tāpēc pieteikums netika izveidots. Nofotografē ietvi tuvāk.", again: "Fotografēt vēlreiz",
      res_ticket: "Pieteikums", err_send: "Neizdevās nosūtīt. Mēģini vēlreiz.",
      err_area: "Šī vieta ir ārpus Rīgas.", err_many: "Pārāk daudz ziņojumu. Mēģini vēlāk.",
      err_pass: "Saite novecojusi. Nosūti botam /start un atver formu vēlreiz.",
    },
    en: {
      service: "Winter sidewalk reports", proto: "Prototype",
      place_h: "Is the point in the right place?",
      place_hint: "The blue circle shows how precisely the phone knows where you are. If the point is not on the right sidewalk, drag it or tap the map (up to 10 m).",
      place_moved: "Point moved by {m} m.", place_limit: "It cannot go further than 10 m. Walk closer to the place and take the photo again.",
      err_moved: "The point can be moved by 10 m at most.",
      proto_note: "Prototype made at RobotHack 2026. Not an official service of any authority.",
      title: "Report a sidewalk", lead: "Take the photo now. The photo and where you are go together.",
      cam_starting: "Opening the camera…",
      cam_denied: "Camera access is blocked. Allow the camera for Telegram in the phone settings, or use the phone camera below.",
      cam_none: "The camera does not open here. Use the phone camera below.",
      fallback: "Use the phone camera", retake: "Retake", send: "Send", sending: "Sending…",
      loc_wait: "Finding your location…", loc_ok: "Location found, accurate to {m} m",
      loc_rough: "Only a rough location (±{m} m). Turn on GPS or step outside; you can still send.",
      loc_denied: "Location access is off. Allow it, then try again.",
      loc_retry: "Try again", loc_need: "Wait for the location, then send.",
      close: "Close",
      privacy: "The photo is taken only here, the gallery is never used. Your location is used for this report only.",
      desktop: "Open this on your phone: Lantern needs the phone's camera and location.",
      no_pass: "Open the form from the Lantern bot (the «Report a sidewalk» button). The link is personal.",
      res_accept: "Thank you! Report accepted and passed to the inspector.",
      res_review: "Thank you! An inspector will check the photo.",
      res_reject: "We can't see a sidewalk problem in this photo (snow, ice, icicles, a blocked path), so no ticket was created. Take a closer photo of the sidewalk.", again: "Take another photo",
      res_ticket: "Ticket", err_send: "Could not send. Please try again.",
      err_area: "This place is outside Riga.", err_many: "Too many reports. Try again later.",
      err_pass: "The link has expired. Send /start to the bot and open the form again.",
    },
  };
  const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  let lang = (q.get("lang") || (user && user.language_code) || "lv").slice(0, 2).toLowerCase();
  if (!T[lang]) lang = "en";
  const t = (k, vars) => (T[lang][k] || T.en[k] || k).replace(/\{(\w+)\}/g, (_, v) => (vars || {})[v]);
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });

  const $ = (id) => document.getElementById(id);
  const video = $("video"), preview = $("preview"), camMsg = $("cam-msg"), shutter = $("shutter");
  const afterShot = $("after-shot"), sendBtn = $("send"), locBox = $("loc"), locRow = $("loc-row");
  let stream = null, shot = null, loc = null, sent = false, result = null;
  // one small line for debugging on a real phone: platform, Telegram version, camera and location path
  const diag = { cam: "…", loc: "…", map: "" };
  function showDiag() {
    $("diag").textContent = [tg ? `${tg.platform} · TG ${tg.version}` : "no Telegram", `cam: ${diag.cam}`,
      `loc: ${diag.loc}`].concat(diag.map ? [`map: ${diag.map}`] : []).join(" · ");
  }
  showDiag();

  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.setHeaderColor("#0b3a6b"); tg.setBackgroundColor("#eef1f4"); } catch (e) { /* older Telegram: keep its colours */ }
    try { if (tg.isVersionAtLeast && tg.isVersionAtLeast("7.7")) tg.disableVerticalSwipes(); } catch (e) { /* keep swipes */ }
  }

  function stop(msgKey) {
    camMsg.textContent = t(msgKey);
    camMsg.hidden = false;
    shutter.hidden = true;
    locBox.hidden = true;
  }

  // ------------------------------------------------------------------ location
  function setLoc(cls, key, vars) {
    locBox.className = "loc " + cls;
    locBox.textContent = t(key, vars);
    locRow.hidden = cls !== "bad";
  }

  // The phone keeps reporting its position while the app is open (GPS gets better for 10-20 s after
  // the first wifi / cell-tower guess), and we keep the best recent fix. A newer fix wins when it is as
  // accurate, when the kept one is older than FRESH_MS, or when the two disagree by more than both
  // accuracies together (the phone moved). A fix without an accuracy never beats one with it.
  const FRESH_MS = 15000, PIN_MOVE_M = 10, POLL_MS = 3000;
  let watchId = null, pollTimer = null, tracking = false;
  function distM(a, b) {  // metres between two {lat, lon}; plenty exact for a few hundred metres
    const k = Math.PI / 180;
    const x = (b.lon - a.lon) * k * Math.cos(((a.lat + b.lat) / 2) * k), y = (b.lat - a.lat) * k;
    return Math.sqrt(x * x + y * y) * 6371000;
  }
  function better(f, b) {
    if (!b) return true;
    if (f.acc == null) return b.acc == null;
    if (b.acc == null || f.acc <= b.acc) return true;
    if (f.at - b.at > FRESH_MS) return true;
    return distM(f, b) > f.acc + b.acc;
  }

  function showAccuracy() {
    const m = loc.acc == null ? "?" : loc.acc;
    if (loc.acc != null && loc.acc <= 75) setLoc("ok", "loc_ok", { m });
    else setLoc("warn", "loc_rough", { m });
  }

  function gotLocation(lat, lon, acc, via) {
    const f = { lat, lon, acc: acc == null ? null : Math.round(acc), at: Date.now() };
    diag.loc = `${via} ±${f.acc == null ? "?" : f.acc} m`;
    showDiag();
    if (better(f, loc)) {
      loc = f;
      place.update();
    }
    showAccuracy();  // also clears a passing error: the kept fix still stands
  }

  function stopTracking() {
    tracking = false;
    clearTimeout(pollTimer);
    if (watchId != null && navigator.geolocation) navigator.geolocation.clearWatch(watchId);
    watchId = null;
  }

  // A refused permission always shows; a passing timeout or "no fix right now" while tracking
  // does not hide a position we already have.
  function failed(why, refused) {
    diag.loc = why;
    showDiag();
    if (refused || !loc) setLoc("bad", "loc_denied");
  }

  function watchBrowser() {
    if (!navigator.geolocation) { tracking = false; return failed("no geolocation", true); }
    watchId = navigator.geolocation.watchPosition(
      (p) => gotLocation(p.coords.latitude, p.coords.longitude, p.coords.accuracy, "browser"),
      (e) => {
        const refused = !!(e && e.code === 1);
        if (refused) stopTracking();  // permission refused: the retry button starts again
        failed(`browser error ${e && e.code}`, refused);
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
  }

  // Telegram's own location access (Bot API 8.0+) first: it works where the WebView blocks geolocation.
  // It has no "watch", so we ask again every POLL_MS while the app is open.
  function getLocation(quiet) {
    if (tracking) return;
    tracking = true;
    if (!quiet) setLoc("", "loc_wait");
    const lm = tg && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0") ? tg.LocationManager : null;
    if (!lm) return watchBrowser();
    const go = () => {
      if (!lm.isLocationAvailable) return watchBrowser();
      const ask = () => {
        if (!tracking) return;
        lm.getLocation((d) => {
          if (!tracking) return;
          if (d) {
            gotLocation(d.latitude, d.longitude, d.horizontal_accuracy, "telegram");
            pollTimer = setTimeout(ask, POLL_MS);
          } else {
            stopTracking();
            failed("telegram: no access", true);
          }
        });
      };
      ask();
    };
    if (lm.isInited) go(); else lm.init(go);
  }

  $("loc-retry").addEventListener("click", () => {
    const lm = tg && tg.LocationManager;
    if (lm && lm.isInited && lm.isAccessRequested && !lm.isAccessGranted) lm.openSettings();  // needs a tap
    else { stopTracking(); getLocation(false); }
  });

  // ------------------------------------------------------------------ place preview
  // After the photo: a small map with the point, the phone's accuracy circle and the 10 m limit.
  // The resident may drag the pin (or tap the map) up to PIN_MOVE_M from the phone's fix; the
  // server checks the same limit and keeps both points. If the map cannot start, sending works
  // exactly as before (the phone's fix, no map).
  const place = (() => {
    const box = $("place"), note = $("place-note");
    let map = null, pin = null, acc = null, limit = null, anchor = null, at = null, on = false;
    function make() {
      if (map) return true;
      if (!window.L) return false;
      try {
        map = L.map("pmap", { dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false,
          keyboard: false, zoomSnap: 0.5 }).setView([56.9496, 24.1052], 13);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
          { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(map);
        limit = L.circle([0, 0], { radius: PIN_MOVE_M, color: "#545e6b", weight: 1, dashArray: "4 4", fill: false, interactive: false });
        acc = L.circle([0, 0], { radius: 1, color: "#0b3a6b", weight: 1, fillColor: "#0b3a6b", fillOpacity: .12, interactive: false });
        const icon = L.divIcon({ className: "", html: '<div class="pin"></div>', iconSize: [28, 28], iconAnchor: [14, 28] });
        pin = L.marker([0, 0], { draggable: true, icon, keyboard: false });
        pin.on("drag", () => place.moveTo(pin.getLatLng(), false));
        pin.on("dragend", () => place.moveTo(pin.getLatLng(), true));
        map.on("click", (e) => place.moveTo(e.latlng, true));
        return true;
      } catch (e) {
        diag.map = (e && e.message) || "map error";
        showDiag();
        map = null;
        return false;
      }
    }
    function draw(fit) {
      if (!anchor) return;
      limit.setLatLng([anchor.lat, anchor.lon]).addTo(map);
      acc.setLatLng([anchor.lat, anchor.lon]).setRadius(anchor.acc || 1).addTo(map);
      pin.setLatLng([at.lat, at.lon]).addTo(map);
      if (fit) {
        const r = Math.max(anchor.acc || 0, PIN_MOVE_M) + 6;
        map.fitBounds(L.latLng(anchor.lat, anchor.lon).toBounds(2 * r), { maxZoom: 19, padding: [8, 8] });
      }
    }
    function say() {
      const d = anchor && at ? distM(anchor, at) : 0;
      note.textContent = d >= 1 ? t("place_moved", { m: Math.round(d) }) : t("place_hint");
    }
    return {
      show() {
        on = true;
        box.hidden = false;
        if (!make()) { box.hidden = true; on = false; return; }
        map.invalidateSize();  // the box was hidden while Leaflet measured it
        anchor = null; at = null;
        say();
        this.update();
      },
      hide() { on = false; box.hidden = true; anchor = null; at = null; },
      // a better fix arrived: follow it until the resident moves the pin themselves
      update() {
        if (!on || !map || !loc) return;
        if (anchor && at && distM(anchor, at) >= 1) return;
        anchor = loc;
        at = { lat: loc.lat, lon: loc.lon };
        draw(true);
        say();
      },
      moveTo(ll, final) {
        if (!anchor) return;
        let p = { lat: ll.lat, lon: ll.lng };
        const d = distM(anchor, p);
        const over = d > PIN_MOVE_M;
        if (over) {  // stop at the limit, a hair inside so rounding never pushes it over
          const k = (PIN_MOVE_M * 0.98) / d;
          p = { lat: anchor.lat + (p.lat - anchor.lat) * k, lon: anchor.lon + (p.lon - anchor.lon) * k };
        }
        at = p;
        if (over || final) pin.setLatLng([p.lat, p.lon]);
        if (final) pin.addTo(map);
        say();
        if (over) note.textContent = t("place_limit");
      },
      // what to send: the pin and the phone's own fix it was placed from (null: no map, send loc as before)
      point() { return on && anchor && at ? { lat: at.lat, lon: at.lon, gps: anchor } : null; },
    };
  })();

  // ------------------------------------------------------------------ camera
  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      diag.cam = "no getUserMedia";
      showDiag();
      return cameraFailed("cam_none");
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false });
      video.srcObject = stream;
      await video.play().catch(() => {});
      camMsg.hidden = true;
      shutter.hidden = false;
      const tr = stream.getVideoTracks()[0];
      const st = tr && tr.getSettings ? tr.getSettings() : null;
      diag.cam = `live ${st && st.width ? st.width + "x" + st.height : ""}`;
      showDiag();
    } catch (e) {
      diag.cam = (e && e.name) || "error";
      showDiag();
      cameraFailed(e && e.name === "NotAllowedError" ? "cam_denied" : "cam_none");
    }
  }

  function cameraFailed(key) {
    camMsg.textContent = t(key);
    camMsg.hidden = false;
    $("fallback-row").hidden = false;
  }

  function showShot(blob, capture) {
    shot = { blob, capture };
    preview.src = URL.createObjectURL(blob);
    preview.hidden = false;
    video.hidden = true;
    camMsg.hidden = true;
    shutter.hidden = true;
    afterShot.hidden = false;
    $("fallback-row").hidden = true;
    $("frame").classList.add("small");
    if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
    getLocation(true);  // no-op while it is already following the position
    place.show();
  }

  shutter.addEventListener("click", () => {
    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) return;
    const k = Math.min(1, 1600 / Math.max(w, h));
    const c = document.createElement("canvas");
    c.width = Math.round(w * k);
    c.height = Math.round(h * k);
    c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
    c.toBlob((b) => { if (b) showShot(b, "live"); }, "image/jpeg", 0.88);
  });

  $("retake").addEventListener("click", () => {
    shot = null;
    preview.hidden = true;
    afterShot.hidden = true;
    place.hide();
    $("frame").classList.remove("small");
    if (stream) { video.hidden = false; shutter.hidden = false; }
    else { $("fallback-row").hidden = false; camMsg.hidden = false; video.hidden = false; }
  });

  $("fallback").addEventListener("click", () => $("file").click());
  $("file").addEventListener("change", (e) => {
    const f = e.target.files && e.target.files[0];
    if (f) showShot(f, "picker");
    e.target.value = "";
  });

  // ------------------------------------------------------------------ send
  function say(key) {
    if (tg && tg.showAlert) tg.showAlert(t(key)); else alert(t(key));
  }

  async function send() {
    if (!shot || sent) return;
    if (!loc) { setLoc("warn", "loc_need"); getLocation(true); return; }
    sendBtn.disabled = true;
    sendBtn.textContent = t("sending");
    const fd = new FormData();
    fd.append("photo", shot.blob, shot.capture === "live" ? "camera.jpg" : (shot.blob.name || "photo.jpg"));
    const p = place.point();  // the pin on the preview map and the phone's fix it came from
    const fix = p ? p.gps : loc;
    fd.append("lat", p ? p.lat : loc.lat);
    fd.append("lon", p ? p.lon : loc.lon);
    if (p) { fd.append("gps_lat", fix.lat); fd.append("gps_lon", fix.lon); }
    if (fix.acc != null) fd.append("accuracy", fix.acc);
    fd.append("capture", shot.capture);
    fd.append("tg_pass", PASS);
    try {
      const r = await fetch("/reports/app", { method: "POST", body: fd });
      const body = await r.json().catch(() => ({}));
      if (r.status === 201) return done(body);
      const code = body.detail && body.detail.code;
      say(code === "outside_area" ? "err_area" : r.status === 429 ? "err_many" : code === "bad_pass" ? "err_pass"
        : code === "moved_too_far" ? "err_moved" : "err_send");
    } catch (e) {
      say("err_send");
    }
    sendBtn.disabled = false;
    sendBtn.textContent = t("send");
  }
  sendBtn.addEventListener("click", send);

  function done(body) {
    const rel = body.relevant;
    const rejected = rel === "reject" || !body.ticket;
    sent = !rejected;
    if (stream) stream.getTracks().forEach((tr) => tr.stop());
    stream = null;
    if (!rejected) stopTracking();  // done: stop asking the phone for its position
    $("shoot").hidden = true;
    $("done").hidden = false;
    $("res-icon").className = "mark " + (rejected ? "reject" : rel === "review" ? "review" : "ok");
    $("res-text").textContent = t(rejected ? "res_reject" : rel === "review" ? "res_review" : "res_accept");
    $("res-ticket").textContent = rejected ? "" : `${t("res_ticket")}: ${body.ticket}`;
    $("again").hidden = !rejected;
    if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred(rejected ? "warning" : "success");
    if (rejected) return;  // no ticket was created: stay open so they can take a better photo
    result = body;
    setTimeout(finish, 2500);  // hand the ticket to the bot (it follows the status and closes this window)
  }

  $("again").addEventListener("click", () => {
    shot = null;
    $("done").hidden = true;
    $("shoot").hidden = false;
    preview.hidden = true;
    afterShot.hidden = true;
    place.hide();
    $("frame").classList.remove("small");
    video.hidden = false;
    sendBtn.disabled = false;
    sendBtn.textContent = t("send");
    camMsg.textContent = t("cam_starting");
    camMsg.hidden = false;
    startCamera();
    getLocation(true);
  });

  let finished = false;
  function finish() {
    if (!tg || finished || !result) return;
    finished = true;
    try {
      // only works when opened from the bot's keyboard button; then Telegram closes the app itself
      tg.sendData(JSON.stringify({ ticket: result.ticket }));
    } catch (e) { /* opened another way: stay open, the result is on screen */ }
  }
  $("close").addEventListener("click", () => { finish(); if (tg) setTimeout(() => tg.close(), 300); });

  // ------------------------------------------------------------------ start
  if (!PASS) return stop("no_pass");
  if (tg && DESKTOP.includes(tg.platform)) return stop("desktop");
  startCamera();
  getLocation(false);
})();
