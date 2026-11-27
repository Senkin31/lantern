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
      title: "Ziņot par ietvi", lead: "Nofotografē vietu tagad. Foto un tava atrašanās vieta aizies kopā.",
      cam_starting: "Atver kameru…",
      cam_denied: "Kamerai nav atļaujas. Atļauj kameru Telegram tālruņa iestatījumos vai izmanto tālruņa kameru zemāk.",
      cam_none: "Šeit kamera neatveras. Izmanto tālruņa kameru zemāk.",
      fallback: "Izmantot tālruņa kameru", retake: "Pārņemt", send: "Nosūtīt", sending: "Sūta…",
      loc_wait: "📍 Nosaka atrašanās vietu…", loc_ok: "📍 Vieta noteikta, precizitāte {m} m",
      loc_rough: "📡 Tikai aptuvena vieta (±{m} m). Ieslēdz GPS vai izej ārā; nosūtīt var arī tā.",
      loc_denied: "📍 Atrašanās vietai nav atļaujas. Atļauj to un mēģini vēlreiz.",
      loc_retry: "Mēģināt vēlreiz", loc_need: "📍 Pagaidi, kamēr nosaka vietu, tad sūti.",
      close: "Aizvērt",
      privacy: "Foto tiek uzņemts tikai šeit, galerija netiek izmantota. Atrašanās vietu ņemam tikai šim ziņojumam.",
      desktop: "Atver šo tālrunī: Lantern vajag tālruņa kameru un atrašanās vietu.",
      no_pass: "Atver formu no Lantern bota (poga 📸). Saite ir personiska.",
      res_accept: "Paldies! Ziņojums pieņemts un nodots inspektoram.",
      res_review: "Paldies! Inspektors pārbaudīs foto.",
      res_reject: "Šajā foto neredzam problēmu uz ietves (sniegs, ledus, lāstekas, aizšķērsots ceļš), tāpēc pieteikums netika izveidots. Nofotografē ietvi tuvāk.", again: "📸 Fotografēt vēlreiz",
      res_ticket: "Pieteikums", err_send: "Neizdevās nosūtīt. Mēģini vēlreiz.",
      err_area: "Šī vieta ir ārpus Rīgas.", err_many: "Pārāk daudz ziņojumu. Mēģini vēlāk.",
      err_pass: "Saite novecojusi. Nosūti botam /start un atver formu vēlreiz.",
    },
    en: {
      title: "Report a sidewalk", lead: "Take the photo now. The photo and where you are go together.",
      cam_starting: "Opening the camera…",
      cam_denied: "Camera access is blocked. Allow the camera for Telegram in the phone settings, or use the phone camera below.",
      cam_none: "The camera does not open here. Use the phone camera below.",
      fallback: "Use the phone camera", retake: "Retake", send: "Send", sending: "Sending…",
      loc_wait: "📍 Finding your location…", loc_ok: "📍 Location found, accurate to {m} m",
      loc_rough: "📡 Only a rough location (±{m} m). Turn on GPS or step outside; you can still send.",
      loc_denied: "📍 Location access is off. Allow it, then try again.",
      loc_retry: "Try again", loc_need: "📍 Wait for the location, then send.",
      close: "Close",
      privacy: "The photo is taken only here, the gallery is never used. Your location is used for this report only.",
      desktop: "Open this on your phone: Lantern needs the phone's camera and location.",
      no_pass: "Open the form from the Lantern bot (the 📸 button). The link is personal.",
      res_accept: "Thank you! Report accepted and passed to the inspector.",
      res_review: "Thank you! An inspector will check the photo.",
      res_reject: "We can't see a sidewalk problem in this photo (snow, ice, icicles, a blocked path), so no ticket was created. Take a closer photo of the sidewalk.", again: "📸 Take another photo",
      res_ticket: "Ticket", err_send: "Could not send. Please try again.",
      err_area: "This place is outside Riga.", err_many: "Too many reports. Try again later.",
      err_pass: "The link has expired. Send /start to the bot and open the form again.",
    },
    ru: {
      title: "Сообщить о тротуаре", lead: "Сфотографируйте место сейчас. Фото и ваше местоположение уйдут вместе.",
      cam_starting: "Открываем камеру…",
      cam_denied: "Нет доступа к камере. Разрешите камеру для Telegram в настройках телефона или используйте камеру телефона ниже.",
      cam_none: "Камера здесь не открывается. Используйте камеру телефона ниже.",
      fallback: "Камера телефона", retake: "Переснять", send: "Отправить", sending: "Отправляем…",
      loc_wait: "📍 Определяем местоположение…", loc_ok: "📍 Место определено, точность {m} м",
      loc_rough: "📡 Только примерное место (±{m} м). Включите GPS или выйдите на улицу; отправить можно и так.",
      loc_denied: "📍 Нет доступа к местоположению. Разрешите и попробуйте снова.",
      loc_retry: "Попробовать снова", loc_need: "📍 Дождитесь местоположения, затем отправьте.",
      close: "Закрыть",
      privacy: "Фото делается только здесь, галерея не используется. Местоположение берём только для этого сообщения.",
      desktop: "Откройте это на телефоне: Lantern нужны камера и местоположение телефона.",
      no_pass: "Откройте форму из бота Lantern (кнопка 📸). Ссылка личная.",
      res_accept: "Спасибо! Сообщение принято и передано инспектору.",
      res_review: "Спасибо! Инспектор проверит фото.",
      res_reject: "На этом фото не видно проблемы на тротуаре (снег, лёд, сосульки, перекрытый проход), поэтому заявка не создана. Сфотографируйте тротуар поближе.", again: "📸 Снять ещё раз",
      res_ticket: "Заявка", err_send: "Не удалось отправить. Попробуйте снова.",
      err_area: "Это место за пределами Риги.", err_many: "Слишком много сообщений. Попробуйте позже.",
      err_pass: "Ссылка устарела. Отправьте боту /start и откройте форму заново.",
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
  const diag = { cam: "…", loc: "…" };
  function showDiag() {
    $("diag").textContent = [tg ? `${tg.platform} · TG ${tg.version}` : "no Telegram", `cam: ${diag.cam}`,
      `loc: ${diag.loc}`].join(" · ");
  }
  showDiag();

  if (tg) {
    tg.ready();
    tg.expand();
    document.documentElement.dataset.theme = tg.colorScheme === "dark" ? "dark" : "light";
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

  function gotLocation(lat, lon, acc, via) {
    loc = { lat, lon, acc: acc == null ? null : Math.round(acc) };
    diag.loc = `${via} ±${loc.acc == null ? "?" : loc.acc} m`;
    showDiag();
    const m = loc.acc == null ? "?" : loc.acc;
    if (loc.acc != null && loc.acc <= 75) setLoc("ok", "loc_ok", { m });
    else setLoc("warn", "loc_rough", { m });
  }

  function browserLocation(quiet) {
    if (!navigator.geolocation) { if (!quiet) setLoc("bad", "loc_denied"); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => gotLocation(p.coords.latitude, p.coords.longitude, p.coords.accuracy, "browser"),
      (e) => { diag.loc = `browser error ${e && e.code}`; showDiag(); if (!quiet || !loc) setLoc("bad", "loc_denied"); },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
  }

  // Telegram's own location access (Bot API 8.0+) first: it works where the WebView blocks geolocation
  function getLocation(quiet) {
    if (!quiet) setLoc("", "loc_wait");
    const lm = tg && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0") ? tg.LocationManager : null;
    if (!lm) return browserLocation(quiet);
    const go = () => {
      if (!lm.isLocationAvailable) return browserLocation(quiet);
      lm.getLocation((d) => {
        if (d) gotLocation(d.latitude, d.longitude, d.horizontal_accuracy, "telegram");
        else { diag.loc = "telegram: no access"; showDiag(); if (!quiet || !loc) setLoc("bad", "loc_denied"); }
      });
    };
    if (lm.isInited) go(); else lm.init(go);
  }

  $("loc-retry").addEventListener("click", () => {
    const lm = tg && tg.LocationManager;
    if (lm && lm.isInited && lm.isAccessRequested && !lm.isAccessGranted) lm.openSettings();  // needs a tap
    else getLocation(false);
  });

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
    if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred("light");
    getLocation(true);  // refresh the position for the moment of the photo
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
    fd.append("lat", loc.lat);
    fd.append("lon", loc.lon);
    if (loc.acc != null) fd.append("accuracy", loc.acc);
    fd.append("capture", shot.capture);
    fd.append("tg_pass", PASS);
    try {
      const r = await fetch("/reports/app", { method: "POST", body: fd });
      const body = await r.json().catch(() => ({}));
      if (r.status === 201) return done(body);
      const code = body.detail && body.detail.code;
      say(code === "outside_area" ? "err_area" : r.status === 429 ? "err_many" : code === "bad_pass" ? "err_pass" : "err_send");
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
    $("shoot").hidden = true;
    $("done").hidden = false;
    $("res-icon").textContent = rejected ? "🤷" : rel === "review" ? "🔎" : "✅";
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
