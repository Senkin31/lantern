/* Lantern shared helpers: API, i18n (EN/LV), header, footer, formatting, map styles. */
(function () {
  "use strict";

  const I18N = {
    en: {
      inspector: "Inspector", contractor: "Contractor", role: "View as", residentForm: "Resident form",
      serviceSub: "Winter sidewalk maintenance supervision", prototype: "Prototype",
      protoNote: "Prototype made at RobotHack 2026. Not an official service of any authority.",
      source: "Source", loading: "Loading…", retry: "Retry",
      // demo bar
      demo: "Demo", snowfallEnd: "Snowfall", deadline: "Clearing deadline", notSet: "not set",
      rigaTime: "Riga time", demoClock: "demo clock ×{f}", snowingSince: "snowing since {t}", snowEnded: "ended {t}",
      snowUnknown: "unknown (08:00 rule)", passed: "passed", in: "in",
      btnSnowStart: "Snowfall started", btnSnowfall: "Snowfall ended now", btnReset: "Reset demo",
      confirmReset: "Delete all cases, signals, reports, snowfalls and history? The demo clock is kept.",
      deadlineRule: "Regulation RD-24-270-sn: snowfall ended before 08:00 → 08:00, 08:00–22:00 → 22:00, after 22:00 → 08:00 next day.",
      // tabs
      tabToday: "Today's visits", tabAll: "All cases", tabReports: "Resident reports", tabStats: "Statistics",
      todayHint: "Check list for {h}, most urgent first: overdue fixes, complaints without a camera, problem places (reopened within 30 days).",
      allStatuses: "All statuses", activeOnly: "Active only",
      nothingToday: "Nothing needs a visit right now.", noAlerts: "No cases yet.",
      caseNo: "Case No.", caseShort: "No.", reportNo: "Report No.", backToList: "Back to the list", srcCamera: "camera", srcResidents: "residents",
      nReports: "{n} report(s)", detectedBy: "Detected by", situation: "Situation", decision: "Inspector's decision",
      noDecision: "The case is closed.", moreDetails: "More details: timeline, urgency, camera data, history", closedL: "Closed",
      // statuses
      st_watch: "Watch", st_cleared_in_time: "Cleared in time", st_open: "Open", st_done_reported: "Done reported", st_verified: "Verified", st_reopened: "Reopened",
      sev_act: "Defect act", sev_notice: "Notice", sevTitle: "Response level", sevSuggested: "suggested: {s}", sevManual: "set by inspector",
      sevToAct: "Make it a defect act", sevToNotice: "Make it a notice", sevNote: "A suggestion: the act itself is drawn up by a person. Both levels: 24 h to fix.",
      fixDue: "Fix by", overdue: "Overdue", fixLeft: "{d} left", evidencePack: "Evidence package", evidenceHint: "One printable page: place, deadline, frames after the deadline, photos, history.",
      deadlineAt: "Clearing deadline", regNo: "Council reg. no.",
      lv_high: "High", lv_medium: "Medium", lv_low: "Low",
      watchNote: "Clearing deadline has not passed yet. The contractor does not see this alert.",
      clearedNote: "Clear frame before the deadline: cleaned in time, closed. The contractor never saw it.",
      // why chips / flags
      why_reopened: "Reopened", why_check_done: "Check contractor's “done”", why_possible_ice: "Possible ice",
      why_low_confidence: "Low-confidence frame", why_ice_report: "Resident: ice / icicles",
      why_partly: "Partly cleaned (camera) · inspector only",
      why_review_report: "Report needs review", why_high: "High urgency", flagCouncil: "Flagged for the council",
      why_act: "Defect act", why_overdue: "Overdue (24 h)", why_no_camera: "Complaint, no camera", why_problem_place: "Problem place",
      // places / hazards
      pl_sidewalk: "Sidewalk", pl_crossing: "Crossing", pl_ramp: "Curb ramp", pl_stop: "Stop", pl_path: "Path",
      pl_square: "Square", pl_other: "Other place",
      hz_clear: "Clear", hz_snow: "Snow", hz_blocked: "Blocked", hz_possible_ice: "Possible ice", hz_ice: "Ice",
      hz_icicles: "Icicles", hz_other: "Other", hz_reported: "Reported by residents",
      ps_no: "Cannot pass", ps_partly: "Partly passable", ps_yes: "Passable",
      // reasons
      r_camera_blocked: "Camera: blocked, {share} of zone", r_camera_snow: "Camera: snow, {share} of zone",
      r_camera_possible_ice: "Camera: possible ice", r_camera_clear: "Camera: clear",
      r_resident_no: "Resident: cannot pass", r_resident_partly: "Resident: partly passable", r_resident_yes: "Resident: passable",
      r_place: "Place: {value}", r_near_sensitive: "Near a school or hospital",
      r_confirmations: "{count} confirmation(s) from other sources", r_cap_unconfirmed: "Single unconfirmed report: capped at medium",
      lowConfTag: "conf. {c}",
      // card
      back: "Back", alert: "Case", urgency: "Urgency", score: "score", why: "Why this urgency", flags: "Needs your attention",
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
      warnTitle: "Warning to the contractor", warnSend: "Send warning", warnSent: "Warning sent to the contractor",
      warnPlaceholder: "Write the message the contractor will see: what is wrong and by when it must be fixed.",
      warnNotYet: "The contractor does not have this job, so there is nobody to warn.", warnEmpty: "Write the message first.",
      warnHistory: "Warnings sent", warnFromInspector: "Warning from the inspector",
      actDispatch: "Dispatch now", actVerify: "Confirm on site", actClean: "Clean on site (in time)", actDispute: "Dispute “done”", actReopenVerified: "Dispute verification",
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
      c_opened: "Notified", c_verified: "Verified", c_active: "Active", c_avg: "Avg response, h", c_within: "Closed ≤ {n} h",
      c_reopened: "Reopened", c_notify: "Avg notify, min", c_kpi: "Notify ≤ {n} min", c_overdue: "Overdue", c_act: "Acts",
      statsNote: "Response time = verified − notified. Notification delay = notified − max(snow seen, deadline).",
      kpiTitle: "KPI", kpi1: "False alarms per camera hour", kpi1Sub: "{n} jobs closed as false alarm / {h} h of camera work",
      kpi2: "Reached the contractor in ≤ {n} min", kpi2Sub: "{a} of {b} jobs",
      kpi3: "Signals with an exact location", kpi3Sub: "{a} of {b} (cameras always, reports with a map point)",
      actFalse: "False alarm (no snow)", falseAlarm: "False alarm", byAi: "AI, from the photo",
      flag_approx_location: "Place picked or typed, not GPS", flagTip_approx_location: "Alone it does not send the contractor: needs GPS, a camera or a second person",
      flag_not_street_photo: "Looks like a screenshot or webcam", flagTip_not_street_photo: "The AI's note says this is not a photo taken on the street",
      flag_false_alarm_sender: "Sender had false alarms", flagTip_false_alarm_sender: "Earlier reports from this sender were closed as false alarms",
      logout: "Log out",
      flag_moved_pin: "Pin moved {m} m by the sender", flagTip_moved_pin: "On the preview map the sender moved the point away from the phone's own position (at most 10 m). Both points are kept.",
      flag_coarse_location: "Rough phone location", flagTip_coarse_location: "The phone gave its position only to wifi or cell-tower accuracy (worse than GPS)",
      flag_picked_photo: "Photo from the file dialog", flagTip_picked_photo: "The in-app camera did not open, so the phone's file dialog was used: it could be an older photo. Waits for the inspector",
      capture_live: "Taken live in the Telegram app", captureTip_live: "Photo taken in the app's own camera just now, at the phone's GPS position",
      sectionLegend: "Street section or square (camera or 2+ residents)", sectionNoName: "Sidewalk", squareL: "square",
      bubbleLegend: "Several alerts close together", bubbleTip: "{n} alerts here: click to zoom in",
      net_title: "Sidewalks", net_title_pgis: "Sidewalks (pGIS)", net_none: "No task", net_registered: "Registered: to be cleaned",
      net_started: "Started: to be checked", net_finished: "Finished",
      net_on: "Sidewalk lines", legendDots: "Cases (colour = urgency)", dotsZoomNote: "Points appear when you zoom in",
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
      fixBy: "Fix by {t}", overdueJob: "Overdue — the 24 hours have passed", actJob: "Defect act candidate — fix within 24 h", noticeJob: "Letter level — fix within 24 h",
      h: "h", min: "min", s: "s", justNow: "just now",
    },
    lv: {
      inspector: "Inspektors", contractor: "Darbuzņēmējs", role: "Skatīt kā", residentForm: "Iedzīvotāju forma",
      serviceSub: "Ietvju ziemas uzturēšanas uzraudzība", prototype: "Prototips",
      protoNote: "Prototips, izveidots RobotHack 2026. Nav nevienas iestādes oficiāls pakalpojums.",
      source: "Pirmkods", loading: "Ielādē…", retry: "Mēģināt vēlreiz",
      demo: "Demo", snowfallEnd: "Snigšana", deadline: "Tīrīšanas termiņš", notSet: "nav iestatīts",
      rigaTime: "Rīgas laiks", demoClock: "demo pulkstenis ×{f}", snowingSince: "snieg kopš {t}", snowEnded: "beidzās {t}",
      snowUnknown: "nav zināms (08:00 noteikums)", passed: "pagājis", in: "pēc",
      btnSnowStart: "Sāka snigt", btnSnowfall: "Snigšana beigusies tagad", btnReset: "Atiestatīt demo",
      confirmReset: "Dzēst visus gadījumus, signālus, ziņojumus, snigšanas un vēsturi? Demo pulkstenis paliks.",
      deadlineRule: "Noteikumi RD-24-270-sn: snigšana beidzās pirms 08:00 → 08:00, 08:00–22:00 → 22:00, pēc 22:00 → 08:00 nākamajā dienā.",
      tabToday: "Šodienas apsekošana", tabAll: "Visi gadījumi", tabReports: "Iedzīvotāju ziņojumi", tabStats: "Statistika",
      todayHint: "Pārbaužu saraksts {h}, steidzamākie vispirms: nokavētie labojumi, sūdzības bez kameras, problēmvietas (atkārtoti atvērtas 30 dienās).",
      allStatuses: "Visi statusi", activeOnly: "Tikai aktīvie",
      nothingToday: "Šobrīd nekur nav jābrauc.", noAlerts: "Gadījumu vēl nav.",
      caseNo: "Gadījums Nr.", caseShort: "Nr.", reportNo: "Ziņojums Nr.", backToList: "Atpakaļ uz sarakstu", srcCamera: "kamera", srcResidents: "iedzīvotāji",
      nReports: "ziņojumi: {n}", detectedBy: "Konstatēja", situation: "Situācija", decision: "Inspektora lēmums",
      noDecision: "Gadījums ir slēgts.", moreDetails: "Sīkāka informācija: laika līnija, steidzamība, kameras dati, vēsture", closedL: "Slēgts",
      st_watch: "Novērošanā", st_cleared_in_time: "Notīrīts laikā", st_open: "Atvērts", st_done_reported: "Ziņots: notīrīts", st_verified: "Pārbaudīts", st_reopened: "Atvērts atkārtoti",
      sev_act: "Defektu akts", sev_notice: "Vēstule", sevTitle: "Reakcijas līmenis", sevSuggested: "ieteikums: {s}", sevManual: "iestatīja inspektors",
      sevToAct: "Pārvērst par defektu aktu", sevToNotice: "Pārvērst par vēstuli", sevNote: "Tikai ieteikums: aktu sastāda cilvēks. Abos līmeņos 24 h labošanai.",
      fixDue: "Novērst līdz", overdue: "Nokavēts", fixLeft: "atlikušas {d}", evidencePack: "Pierādījumu pakete", evidenceHint: "Viena drukājama lapa: vieta, termiņš, kadri pēc termiņa, foto, vēsture.",
      deadlineAt: "Tīrīšanas termiņš", regNo: "Domes reģ. nr.",
      lv_high: "Augsta", lv_medium: "Vidēja", lv_low: "Zema",
      watchNote: "Tīrīšanas termiņš vēl nav beidzies. Darbuzņēmējs šo gadījumu neredz.",
      clearedNote: "Tīrs kadrs pirms termiņa: notīrīts laikā, slēgts. Darbuzņēmējs to neredzēja.",
      why_reopened: "Atvērts atkārtoti", why_check_done: "Pārbaudīt “notīrīts”", why_possible_ice: "Iespējams ledus",
      why_low_confidence: "Neskaidrs kadrs", why_ice_report: "Iedzīvotājs: ledus / lāstekas",
      why_partly: "Daļēji notīrīts (kamera) · tikai inspektoram",
      why_review_report: "Ziņojums jāpārbauda", why_high: "Augsta steidzamība", flagCouncil: "Atzīmēts domei",
      why_act: "Defektu akts", why_overdue: "Nokavēts (24 h)", why_no_camera: "Sūdzība bez kameras", why_problem_place: "Problēmvieta",
      pl_sidewalk: "Ietve", pl_crossing: "Gājēju pāreja", pl_ramp: "Nobrauktuve", pl_stop: "Pietura", pl_path: "Celiņš",
      pl_square: "Laukums", pl_other: "Cita vieta",
      hz_clear: "Tīrs", hz_snow: "Sniegs", hz_blocked: "Aizsprostots", hz_possible_ice: "Iespējams ledus", hz_ice: "Ledus",
      hz_icicles: "Lāstekas", hz_other: "Cits", hz_reported: "Ziņojuši iedzīvotāji",
      ps_no: "Nevar paiet", ps_partly: "Daļēji var paiet", ps_yes: "Var paiet",
      r_camera_blocked: "Kamera: aizsprostots, {share} zonas", r_camera_snow: "Kamera: sniegs, {share} zonas",
      r_camera_possible_ice: "Kamera: iespējams ledus", r_camera_clear: "Kamera: tīrs",
      r_resident_no: "Iedzīvotājs: nevar paiet", r_resident_partly: "Iedzīvotājs: daļēji var paiet", r_resident_yes: "Iedzīvotājs: var paiet",
      r_place: "Vieta: {value}", r_near_sensitive: "Blakus skola vai slimnīca",
      r_confirmations: "{count} apstiprinājums(-i) no citiem avotiem", r_cap_unconfirmed: "Viens neapstiprināts ziņojums: ne augstāk par vidēju",
      lowConfTag: "ticam. {c}",
      back: "Atpakaļ", alert: "Gadījums", urgency: "Steidzamība", score: "punkti", why: "Kāpēc šāda steidzamība", flags: "Jāpievērš uzmanība",
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
      warnTitle: "Brīdinājums darbuzņēmējam", warnSend: "Nosūtīt brīdinājumu", warnSent: "Brīdinājums nosūtīts darbuzņēmējam",
      warnPlaceholder: "Uzrakstiet ziņu, ko redzēs darbuzņēmējs: kas nav kārtībā un līdz kuram laikam tas jānovērš.",
      warnNotYet: "Darbuzņēmējam šī darba nav, tāpēc nav, kam nosūtīt brīdinājumu.", warnEmpty: "Vispirms uzrakstiet ziņu.",
      warnHistory: "Nosūtītie brīdinājumi", warnFromInspector: "Inspektora brīdinājums",
      actDispatch: "Nosūtīt tagad", actVerify: "Apstiprināt uz vietas", actClean: "Tīrs uz vietas (laikā)", actDispute: "Apstrīdēt “notīrīts”", actReopenVerified: "Apstrīdēt pārbaudi",
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
      c_opened: "Paziņoti", c_verified: "Pārbaudīti", c_active: "Aktīvi", c_avg: "Vid. reakcija, h", c_within: "Slēgti ≤ {n} h",
      c_reopened: "Atkārtoti", c_notify: "Vid. paziņoš., min", c_kpi: "Paziņots ≤ {n} min", c_overdue: "Nokavēti", c_act: "Akti",
      statsNote: "Reakcijas laiks = pārbaudīts − paziņots. Paziņošanas aizkave = paziņots − max(sniegs pamanīts, termiņš).",
      kpiTitle: "KPI", kpi1: "Viltus trauksmes uz kameras stundu", kpi1Sub: "{n} darbi slēgti kā viltus trauksme / {h} h kameru darba",
      kpi2: "Darbuzņēmējs saņēma ≤ {n} min", kpi2Sub: "{a} no {b} darbiem",
      kpi3: "Signāli ar precīzu vietu", kpi3Sub: "{a} no {b} (kameras vienmēr, ziņojumi ar punktu kartē)",
      actFalse: "Viltus trauksme (nav sniega)", falseAlarm: "Viltus trauksme", byAi: "MI, pēc foto",
      flag_approx_location: "Vieta izvēlēta vai ierakstīta, nav GPS", flagTip_approx_location: "Viena pati nenosūta darbuzņēmēju: vajag GPS, kameru vai otru cilvēku",
      flag_not_street_photo: "Izskatās pēc ekrānuzņēmuma vai tīmekļa kameras", flagTip_not_street_photo: "MI piezīme saka, ka foto nav uzņemts uz ielas",
      flag_false_alarm_sender: "Sūtītājam bijušas viltus trauksmes", flagTip_false_alarm_sender: "Iepriekšējie šī sūtītāja ziņojumi slēgti kā viltus trauksme",
      logout: "Iziet",
      flag_moved_pin: "Sūtītājs pārvietoja punktu par {m} m", flagTip_moved_pin: "Priekšskatījuma kartē sūtītājs pārvietoja punktu no tālruņa noteiktās vietas (ne vairāk kā 10 m). Abi punkti ir saglabāti.",
      flag_coarse_location: "Aptuvena tālruņa atrašanās vieta", flagTip_coarse_location: "Tālrunis noteica vietu tikai pēc wifi vai mobilā torņa (sliktāk nekā GPS)",
      flag_picked_photo: "Foto no failu izvēles", flagTip_picked_photo: "Lietotnes kamera neatvērās, tāpēc izmantota tālruņa failu izvēle: foto var būt vecāks. Gaida inspektoru",
      capture_live: "Uzņemts tieši Telegram lietotnē", captureTip_live: "Foto uzņemts lietotnes kamerā tikko, tālruņa GPS vietā",
      sectionLegend: "Ielas posms vai laukums (kamera vai 2+ iedzīvotāji)", sectionNoName: "Ietve", squareL: "laukums",
      bubbleLegend: "Vairāki gadījumi tuvu", bubbleTip: "Šeit {n} gadījumi: klikšķini, lai pietuvinātu",
      net_title: "Ietves", net_title_pgis: "Ietves (pGIS)", net_none: "Nav uzdevuma", net_registered: "Reģistrēts: jātīra",
      net_started: "Uzsākts: jāpārbauda", net_finished: "Pabeigts",
      net_on: "Ietvju līnijas", legendDots: "Gadījumi (krāsa = steidzamība)", dotsZoomNote: "Punkti parādās, kad pietuvina",
      exportGeo: "Eksportēt GeoJSON", exportCsv: "Eksportēt CSV", noStats: "Darbuzņēmējiem vēl nekas nav nosūtīts.",
      myJobs: "Mani darbi", listView: "Saraksts", mapView: "Karte", toDo: "Jādara", waiting: "Gaida pārbaudi", doneToday: "Pārbaudīti",
      noJobs: "Jūsu rajonā šobrīd darbu nav.", completed: "Pabeigtie",
      redo: "Kamera pēc “notīrīts” joprojām redz sniegu — lūdzu, notīriet vēlreiz",
      waitingCheck: "Ziņots: notīrīts — gaida kameras pārbaudi",
      complaints: "Sūdzības", sinceOpened: "Atvērts", openInMap: "Atvērt kartē", directions: "Maršruts",
      cleared: "Notīrīts", confirmCleared: "Atzīmēt šo vietu kā notīrītu? Nākamais kameras kadrs to pārbaudīs.",
      pickContractor: "Izvēlieties darbuzņēmēju galvenē.", lastFrame: "Jaunākais ietves skats",
      residentPhotos: "Iedzīvotāju foto", verifiedAt: "Pārbaudīts", ago: "atpakaļ",
      fixBy: "Novērst līdz {t}", overdueJob: "Nokavēts — 24 stundas pagājušas", actJob: "Defektu akta kandidāts — novērst 24 h laikā", noticeJob: "Vēstules līmenis — novērst 24 h laikā",
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
  // The server clock is the only clock (brief v3: clock.now()). On the demo it runs faster
  // (POST /demo/clock, factor 600 = 1 h in 6 s), so the page follows it: last server time + elapsed × factor.
  let syncServer = Date.now(), syncLocal = Date.now(), clockFactor = 1;
  function syncClock(serverNow, factor) {
    if (!serverNow) return;
    syncServer = new Date(serverNow).getTime();
    syncLocal = Date.now();
    clockFactor = factor > 0 ? factor : 1;
  }
  function syncFromSettings(s) {
    if (!s) return;
    syncClock(s.now, s.clock && s.clock.mode === "demo" ? s.clock.factor : 1);
  }
  function now() { return syncServer + (Date.now() - syncLocal) * clockFactor; }
  // all times are shown on the Riga clock, whatever the viewer's time zone
  const RIGA = "Europe/Riga";
  const fmtParts = (ms) => {
    const o = {};
    new Intl.DateTimeFormat("en-GB", { timeZone: RIGA, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" })
      .formatToParts(new Date(ms)).forEach((p) => { o[p.type] = p.value; });
    return o;
  };
  function fmtTime(iso, withSeconds) {
    if (!iso) return t("none");
    const d = fmtParts(new Date(iso).getTime()), today = fmtParts(now());
    const hm = `${d.hour}:${d.minute}${withSeconds ? ":" + d.second : ""}`;
    return d.day === today.day && d.month === today.month && d.year === today.year ? hm : `${d.day}.${d.month} ${hm}`;
  }
  function clockText() {
    const d = fmtParts(now());
    return `${d.day}.${d.month} ${d.hour}:${d.minute}`;
  }
  function setHourSeconds() { /* v2 time compression is gone; kept so old callers do not break */ }
  function fmtDur(seconds) {
    if (seconds == null || isNaN(seconds)) return t("none");
    const rule = Math.max(0, seconds);
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

  const COLORS = { high: "#d64545", medium: "#e8a33d", low: "#4c7bd9", watch: "#9aa3ae", verified: "#3e9b6b", reopened: "#8e44ad",
    cleared: "#7fb89a", act: "#8e24aa", overdue: "#c62828" };
  const isClosed = (a) => a.status === "verified" || a.status === "cleared_in_time";
  const severityBadge = (a) => a.severity === "act"
    ? `<span class="chip sev-act">${esc(t("sev_act"))}</span>` : `<span class="chip sev-notice">${esc(t("sev_notice"))}</span>`;
  function alertColor(a) {
    if (a.status === "cleared_in_time") return COLORS.cleared;
    if (a.status === "verified") return COLORS.verified;
    if (a.status === "watch") return COLORS.watch;
    return COLORS[a.urgency_level] || COLORS.low;
  }

  // ---------------------------------------------------------------- header / footer
  function renderHeader(el, meta, current) {
    const opts = [`<option value="inspector" ${current === "inspector" ? "selected" : ""}>${esc(t("inspector"))}</option>`]
      .concat((meta.contractors || []).map((c) => {
        const v = "contractor:" + c.id;
        return `<option value="${esc(v)}" ${current === v ? "selected" : ""}>${esc(t("contractor"))}: ${esc(c.name)} (${esc((c.districts || []).join(", "))})</option>`;
      }));
    el.innerHTML = `
      <a class="brand" href="/inspector"><span class="brand-name">Lantern</span><span class="brand-sub">${esc(t("serviceSub"))}</span></a>
      <span class="proto">${esc(t("prototype"))}</span>
      <span class="spacer"></span>
      <label for="roleSel">${esc(t("role"))}</label>
      <select id="roleSel" aria-label="${esc(t("role"))}">${opts.join("")}</select>
      <a class="tb-link" href="/report" target="_blank" rel="noopener">${esc(t("residentForm"))}</a>
      <span class="lang" role="group" aria-label="Language">
        <button type="button" data-lang="en" aria-pressed="${lang === "en"}">EN</button>
        <button type="button" data-lang="lv" aria-pressed="${lang === "lv"}">LV</button>
      </span>
      ${meta.login ? `<a class="tb-link" href="/logout">${esc(t("logout"))}</a>` : ""}`;
    el.querySelector("#roleSel").addEventListener("change", (e) => {
      const v = e.target.value;
      location.href = v === "inspector" ? "/inspector" : "/contractor?contractor=" + encodeURIComponent(v.split(":")[1]);
    });
    el.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
  }

  function renderFooter(el, meta) {
    el.innerHTML = `
      <span class="proto-note">${esc(t("protoNote"))}</span>
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
    // a removed or not-yet-laid-out map throws inside Leaflet; a resize then is harmless to skip
    if (window.ResizeObserver) new ResizeObserver(() => { try { map.invalidateSize(); } catch (e) { /* skip */ } }).observe(el);
    return map;
  }
  const toLatLngs = (poly) => (poly || []).map((p) => [p[1], p[0]]);

  // ---------------------------------------------------------------- sidewalk network (Riga pGIS look)
  // Riga's winter maintenance map (pGIS) draws every stretch of sidewalk as a thin solid line in the colour of
  // its latest task. Same here, same colours: blue no task, red registered, yellow started, green finished.
  // The lines sit on their own canvas pane under our dots; the dots stay clickable on top.
  const NET = { none: "rgb(0,28,255)", registered: "rgb(255,0,0)", started: "rgb(255,250,0)", finished: "rgb(0,255,2)" };
  const NET_STATES = ["none", "registered", "started", "finished"];
  const DOT_ZOOM = 16;  // alert dots appear from this zoom (a few streets on screen); further out only lines

  function sidewalkNetwork(map, opts = {}) {
    map.getContainer().classList.add("net-map");
    if (!map.getPane("network")) map.createPane("network").style.zIndex = 390;
    const renderer = L.canvas({ pane: "network", padding: 0.5, tolerance: 5 });
    const items = [];
    let status = {};
    let source = "osm";  // "pgis" when the lines are the city's pGIS data
    const width = () => (map.getZoom() >= 17 ? 3 : 2);
    const stateOf = (b) => (status[b.id] ? status[b.id].state : "none");
    const styleOf = (b) => {
      const col = NET[stateOf(b)];
      return b.shape === "area" ? { color: col, weight: width(), fillColor: col, fillOpacity: status[b.id] ? 0.3 : 0.08 }
        : { color: col, weight: width() };
    };
    const tip = (b) => {
      const st = status[b.id];
      const size = b.shape === "area" ? `${t("squareL")} · ${Math.round(b.area_m2 || 0).toLocaleString()} m²` : `${b.length_m} m`;
      const nm = b.name || t("sectionNoName");  // the street it runs along; the district in brackets
      const where = b.district && b.district !== nm ? `${nm} (${b.district})` : nm;
      return `${esc(where)} · ${esc(size)}<br>${esc(t("net_" + stateOf(b)))}`
        + (st ? ` · #${st.alert_ids.join(", #")}` : "");
    };
    const ready = api("/map/network").then((r) => {
      if (r.attribution && map.attributionControl) map.attributionControl.addAttribution(esc(r.attribution));
      source = r.source || "osm";
      (r.blocks || []).forEach((b) => {
        const o = { renderer, pane: "network", opacity: 1, lineCap: "butt", lineJoin: "round", ...styleOf(b) };
        const l = b.shape === "area" ? L.polygon(b.coords, o) : L.polyline(b.coords, o);
        l.bindTooltip(() => tip(b), { sticky: true });
        l.on("click", () => { if (status[b.id] && opts.onPick) opts.onPick(status[b.id], b, l); });
        l.addTo(map);
        items.push({ b, l, key: stateOf(b) + width() });
      });
    }).catch((e) => console.warn("sidewalk network", e));
    function setStatus(s) {
      status = s || {};
      items.forEach((x) => {
        const key = stateOf(x.b) + width();
        if (key !== x.key) { x.key = key; x.l.setStyle(styleOf(x.b)); }
      });
    }
    map.on("zoomend", () => setStatus(status));
    function legend() {
      return `<div class="legend-h">${esc(t(source === "pgis" ? "net_title_pgis" : "net_title"))}</div>`
        + NET_STATES.map((k) => `<div><i class="net-line" style="background:${NET[k]}"></i>${esc(t("net_" + k))}</div>`).join("");
    }
    return { ready, setStatus, legend, count: () => items.length };
  }

  window.Lantern = {
    t, setLang, get lang() { return lang; }, esc, api, syncClock, syncFromSettings, now, fmtTime, clockText, fmtDur, since,
    sinceSpan, updateSince, hours, pct, setHourSeconds, statusBadge, levelBadge, severityBadge, isClosed, place, hazard,
    reasonText, alertColor, COLORS, NET, DOT_ZOOM, sidewalkNetwork,
    renderHeader, renderFooter, toast, lightbox, makeMap, toLatLngs,
  };
})();
