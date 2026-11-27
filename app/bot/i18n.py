"""Bot texts in Latvian, English and Russian."""

LANGS = ("lv", "en", "ru")
LANG_NAMES = {"lv": "🇱🇻 Latviešu", "en": "🇬🇧 English", "ru": "🇷🇺 Русский"}

T = {
    "choose_lang": {
        "lv": "Izvēlies valodu / Choose a language / Выберите язык",
        "en": "Izvēlies valodu / Choose a language / Выберите язык",
        "ru": "Izvēlies valodu / Choose a language / Выберите язык",
    },
    "welcome": {
        "lv": "🏮 Lantern — ziņo par neiztīrītām ietvēm Rīgā.\n\n"
              "Nosūti foto un atrašanās vietu, tas ir viss. Mākslīgais intelekts pārbauda foto, "
              "un tikai tad signāls nonāk pie pilsētas inspektora.\n\n"
              "Tas papildina tālruni 1201, nevis aizstāj to. Mēs neprasām vārdu, tālruni vai e-pastu.",
        "en": "🏮 Lantern — report uncleared sidewalks in Riga.\n\n"
              "Send a photo and the location, that's all. AI checks the photo, "
              "and only then the signal reaches the city inspector.\n\n"
              "This complements the 1201 phone line, it does not replace it. We never ask for your name, phone or email.",
        "ru": "🏮 Lantern — сообщите о неубранном тротуаре в Риге.\n\n"
              "Пришлите фото и место, больше ничего не нужно. Нейросеть проверит фото, "
              "и только после этого сигнал попадёт к инспектору города.\n\n"
              "Бот дополняет телефон 1201, а не заменяет его. Имя, телефон и e-mail мы не спрашиваем.",
    },
    "ask_photo": {
        "lv": "📷 1/2 Nosūti vienu foto ar sniegu, ledu vai aizšķērsotu ietvi.",
        "en": "📷 1/2 Send one photo of the snow, ice or blocked sidewalk.",
        "ru": "📷 1/2 Пришлите одно фото снега, льда или перекрытого тротуара.",
    },
    "ask_location": {
        "lv": "📍 2/2 Tagad atrašanās vieta. Nospied pogu zemāk — vai nosūti citu punktu: 📎 → Atrašanās vieta. "
              "No datora: ielīmē koordinātas (56.9496, 24.1052) vai Google Maps / OpenStreetMap saiti.",
        "en": "📍 2/2 Now the location. Tap the button below — or send another point via 📎 → Location. "
              "On a computer: paste coordinates (56.9496, 24.1052) or a Google Maps / OpenStreetMap link.",
        "ru": "📍 2/2 Теперь место. Нажмите кнопку ниже — или отправьте другую точку: 📎 → Геопозиция. "
              "С компьютера: вставьте координаты (56.9496, 24.1052) или ссылку Google Maps / OpenStreetMap.",
    },
    "btn_location": {"lv": "📍 Sūtīt manu atrašanās vietu", "en": "📍 Send my location",
                     "ru": "📍 Отправить моё местоположение"},
    "location_ok": {"lv": "Vieta saņemta ✅", "en": "Location received ✅", "ru": "Место получено ✅"},
    "summary": {
        "lv": "Pārbaudi un apstiprini:\n\n📷 foto: ir\n📍 vieta: {lat:.5f}, {lon:.5f}\n\n"
              "Kas tur ir un cik slikti, novērtēs MI pēc foto.",
        "en": "Check and confirm:\n\n📷 photo: attached\n📍 location: {lat:.5f}, {lon:.5f}\n\n"
              "What is there and how bad: the AI reads it from the photo.",
        "ru": "Проверьте и подтвердите:\n\n📷 фото: есть\n📍 место: {lat:.5f}, {lon:.5f}\n\n"
              "Что там и насколько плохо, ИИ определит по фото.",
    },
    "btn_send": {"lv": "✅ Sūtīt", "en": "✅ Send", "ru": "✅ Отправить"},
    "btn_cancel": {"lv": "✖️ Atcelt", "en": "✖️ Cancel", "ru": "✖️ Отмена"},
    "sending": {"lv": "Sūtu un pārbaudu foto… ⏳", "en": "Sending and checking the photo… ⏳",
                "ru": "Отправляю и проверяю фото… ⏳"},
    "accepted": {
        "lv": "🏮 Paldies, signāls saņemts!\nPieteikuma kods: {ticket}\n\nKad situācija mainīsies, es tev pateikšu. "
              "Statuss: /status",
        "en": "🏮 Thank you, signal received!\nTicket: {ticket}\n\nI'll let you know when something changes. "
              "Status: /status",
        "ru": "🏮 Спасибо, сигнал принят!\nКод заявки: {ticket}\n\nЯ сообщу, когда что-то изменится. "
              "Статус: /status",
    },
    "merged": {
        "lv": "Par šo vietu jau ziņoja — tavs signāls pievienots un paaugstina prioritāti.",
        "en": "This place was already reported — your signal was added and raises the priority.",
        "ru": "Об этом месте уже сообщали — ваш сигнал добавлен и повышает приоритет.",
    },
    "review": {
        "lv": "🏮 Paldies, signāls saņemts!\nPieteikuma kods: {ticket}\n\nInspektors vēl pārbaudīs foto.",
        "en": "🏮 Thank you, signal received!\nTicket: {ticket}\n\nAn inspector will check the photo.",
        "ru": "🏮 Спасибо, сигнал принят!\nКод заявки: {ticket}\n\nИнспектор дополнительно проверит фото.",
    },
    "rejected": {
        "lv": "Paldies! Diemžēl foto neizskatās pēc bīstamas ietves (sniegs, ledus, lāstekas), tāpēc "
              "inspektoram to nenosūtījām. Ja kļūdījāmies — mēģini vēlreiz ar tuvāku foto.\nKods: {ticket}",
        "en": "Thank you! Unfortunately the photo doesn't look like a sidewalk hazard (snow, ice, icicles), so it "
              "was not sent to the inspector. If we got it wrong, try again with a closer photo.\nTicket: {ticket}",
        "ru": "Спасибо! К сожалению, фото не похоже на опасный тротуар (снег, лёд, сосульки), поэтому "
              "к инспектору оно не ушло. Если мы ошиблись — попробуйте ещё раз с фото поближе.\nКод: {ticket}",
    },
    "too_many": {
        "lv": "⏳ Tu šodien jau esi nosūtījis daudz ziņojumu. Paldies! Lūdzu, mēģini vēlāk.",
        "en": "⏳ You have already sent a lot of reports. Thank you! Please try again later.",
        "ru": "⏳ Вы уже отправили много сообщений. Спасибо! Попробуйте позже.",
    },
    "outside_area": {
        "lv": "📍 Šī vieta ir ārpus Rīgas. Lantern pieņem ziņojumus tikai par Rīgu.",
        "en": "📍 This place is outside Riga. Lantern only takes reports about Riga.",
        "ru": "📍 Это место за пределами Риги. Lantern принимает сообщения только по Риге.",
    },
    "same_photo": {
        "lv": "ℹ️ Šis foto jau bija nosūtīts, tāpēc to neskaitām kā jaunu apstiprinājumu.",
        "en": "ℹ️ This photo was already sent before, so it doesn't count as a new confirmation.",
        "ru": "ℹ️ Это фото уже присылали, поэтому оно не считается новым подтверждением.",
    },
    "send_failed": {
        "lv": "Neizdevās nosūtīt — serveris nav pieejams. Mēģini vēlreiz pēc brīža (✅ Sūtīt) vai zvani 1201.",
        "en": "Could not send — the server is unavailable. Try again in a moment (✅ Send) or call 1201.",
        "ru": "Не удалось отправить — сервер недоступен. Попробуйте чуть позже (✅ Отправить) или позвоните 1201.",
    },
    "photo_failed": {
        "lv": "Neizdevās lejupielādēt foto. Lūdzu, nosūti to vēlreiz.",
        "en": "Could not download the photo. Please send it again.",
        "ru": "Не удалось загрузить фото. Пожалуйста, пришлите его ещё раз.",
    },
    "photo_too_big": {
        "lv": "Foto ir lielāks par 10 MB. Lūdzu, nosūti mazāku.",
        "en": "The photo is larger than 10 MB. Please send a smaller one.",
        "ru": "Фото больше 10 МБ. Пожалуйста, пришлите поменьше.",
    },
    "cancelled": {"lv": "Atcelts. Lai sāktu no jauna, nosūti foto.", "en": "Cancelled. Send a photo to start again.",
                  "ru": "Отменено. Чтобы начать заново, пришлите фото."},
    "btn_app": {"lv": "📸 Ziņot par ietvi", "en": "📸 Report a sidewalk", "ru": "📸 Сообщить о тротуаре"},
    "ask_app": {
        "lv": "Spied «📸 Ziņot par ietvi» zemāk. Lietotne uzņems foto tagad un pievienos vietu, kur tu esi.",
        "en": "Press «📸 Report a sidewalk» below. The app takes the photo now and adds where you are.",
        "ru": "Нажмите «📸 Сообщить о тротуаре» ниже. Приложение сделает фото сейчас и добавит, где вы находитесь.",
    },
    "use_app": {
        "lv": "Foto no čata nepieņemam: tas var būt vecs. Spied «📸 Ziņot par ietvi» zemāk un nofotografē vietu tagad.",
        "en": "We don't take photos from the chat: they can be old. Press «📸 Report a sidewalk» below and take the photo now.",
        "ru": "Фото из чата не принимаем: оно может быть старым. Нажмите «📸 Сообщить о тротуаре» ниже и сфотографируйте сейчас.",
    },
    "need_photo": {"lv": "Vispirms nosūti foto 📷", "en": "Please send a photo first 📷",
                   "ru": "Сначала пришлите фото 📷"},
    "need_location": {"lv": "Nosūti atrašanās vietu ar pogu zemāk 📍 vai ielīmē koordinātas / kartes saiti",
                      "en": "Send the location with the button below 📍 or paste coordinates / a map link",
                      "ru": "Отправьте место кнопкой ниже 📍 или вставьте координаты / ссылку на карту"},
    "use_buttons": {"lv": "Izvēlies kādu no pogām ziņā augstāk 👆", "en": "Please choose one of the buttons above 👆",
                    "ru": "Выберите одну из кнопок выше 👆"},
    "help": {
        "lv": "Kā ziņot: nosūti foto → atrašanās vietu → pasaki, vai var paiet → apstiprini.\n\n"
              "/start — jauns ziņojums\n/status — mani pieteikumi\n/lang — valoda\n/cancel — atcelt\n\n"
              "Steidzamos gadījumos zvani 1201 vai 112.",
        "en": "How to report: send a photo → the location → whether people can get through → confirm.\n\n"
              "/start — new report\n/status — my tickets\n/lang — language\n/cancel — cancel\n\n"
              "In urgent cases call 1201 or 112.",
        "ru": "Как сообщить: фото → место → можно ли пройти → подтвердить.\n\n"
              "/start — новое сообщение\n/status — мои заявки\n/lang — язык\n/cancel — отменить\n\n"
              "В срочных случаях звоните 1201 или 112.",
    },
    "no_tickets": {"lv": "Tev vēl nav pieteikumu. Nosūti foto, lai sāktu.",
                   "en": "You have no tickets yet. Send a photo to start.",
                   "ru": "У вас пока нет заявок. Пришлите фото, чтобы начать."},
    "status_header": {"lv": "Tavi pieteikumi:", "en": "Your tickets:", "ru": "Ваши заявки:"},
    "status_unknown": {"lv": "statuss nav pieejams", "en": "status unavailable", "ru": "статус недоступен"},
    # ticket states
    "st_rejected": {"lv": "noraidīts (nav bīstamība)", "en": "rejected (not a hazard)", "ru": "отклонено (не опасность)"},
    "st_in_review": {"lv": "gaida inspektora pārbaudi", "en": "waiting for an inspector check",
                     "ru": "ждёт проверки инспектора"},
    "st_watch": {"lv": "pieņemts, gaidām tīrīšanas termiņu", "en": "accepted, clearing deadline still running",
                 "ru": "принято, срок уборки ещё идёт"},
    "st_open": {"lv": "nosūtīts tīrītājiem", "en": "sent to the cleaning contractor", "ru": "передано подрядчику"},
    "st_done_reported": {"lv": "tīrītāji ziņo, ka notīrīts — pārbaudām", "en": "contractor says it is cleared — checking",
                         "ru": "подрядчик сообщил, что убрано — проверяем"},
    "st_reopened": {"lv": "joprojām nav notīrīts — atkārtoti nosūtīts", "en": "still not cleared — sent back again",
                    "ru": "всё ещё не убрано — отправлено повторно"},
    "st_verified": {"lv": "notīrīts un pārbaudīts ✅", "en": "cleared and verified ✅", "ru": "убрано и проверено ✅"},
    "st_cleared_in_time": {"lv": "notīrīts laikā, pirms termiņa ✅", "en": "cleared in time, before the deadline ✅",
                           "ru": "убрано вовремя, до срока ✅"},
    "others": {"lv": "vēl {n} iedzīvotāji ziņoja", "en": "{n} other residents reported it",
               "ru": "ещё {n} жителей сообщили"},
    "camera": {"lv": "apstiprina pilsētas kamera", "en": "confirmed by a city camera",
               "ru": "подтверждено камерой города"},
    # push notifications
    "push_open": {
        "lv": "🏮 {ticket}: pieteikums nosūtīts tīrītājiem. Paldies, ka ziņoji!",
        "en": "🏮 {ticket}: your report was sent to the cleaning contractor. Thanks for reporting!",
        "ru": "🏮 {ticket}: заявка передана подрядчику по уборке. Спасибо, что сообщили!",
    },
    "push_done_reported": {
        "lv": "🧹 {ticket}: tīrītāji ziņo, ka vieta notīrīta. Pilsēta to vēl pārbaudīs.",
        "en": "🧹 {ticket}: the contractor reports the place is cleared. The city will verify it.",
        "ru": "🧹 {ticket}: подрядчик сообщил, что место убрано. Город это проверит.",
    },
    "push_reopened": {
        "lv": "⚠️ {ticket}: pārbaude rāda, ka vieta joprojām nav notīrīta — pieteikums atkārtoti nosūtīts.",
        "en": "⚠️ {ticket}: the check shows the place is still not cleared — the ticket was sent back.",
        "ru": "⚠️ {ticket}: проверка показала, что место всё ещё не убрано — заявка отправлена повторно.",
    },
    "push_cleared_in_time": {
        "lv": "✅ {ticket}: vieta notīrīta laikā, pirms tīrīšanas termiņa. Paldies, ka ziņoji!",
        "en": "✅ {ticket}: the place was cleared in time, before the clearing deadline. Thanks for reporting!",
        "ru": "✅ {ticket}: место убрали вовремя, до срока уборки. Спасибо, что сообщили!",
    },
    "push_verified": {
        "lv": "✅ {ticket}: vieta notīrīta un pārbaudīta. Paldies, tu palīdzēji kaimiņiem!",
        "en": "✅ {ticket}: the place is cleared and verified. Thank you, you helped your neighbours!",
        "ru": "✅ {ticket}: место убрано и проверено. Спасибо, вы помогли соседям!",
    },
}


def t(key: str, lang: str, **kw) -> str:
    entry = T.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    return text.format(**kw) if kw else text
