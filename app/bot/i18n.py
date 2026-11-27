"""Bot texts in Latvian and English."""

LANGS = ("lv", "en")
LANG_NAMES = {"lv": "🇱🇻 Latviešu", "en": "🇬🇧 English"}
DROPPED_LANGS = ("ru",)  # was offered before: its own Telegram menu and description are removed at start

T = {
    "choose_lang": {
        "lv": "Izvēlies valodu / Choose a language",
        "en": "Izvēlies valodu / Choose a language",
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
    },
    "ask_photo": {
        "lv": "📷 1/2 Nosūti vienu foto ar sniegu, ledu vai aizšķērsotu ietvi.",
        "en": "📷 1/2 Send one photo of the snow, ice or blocked sidewalk.",
    },
    "ask_location": {
        "lv": "📍 2/2 Tagad atrašanās vieta. Nospied pogu zemāk — vai nosūti citu punktu: 📎 → Atrašanās vieta. "
              "No datora: ielīmē koordinātas (56.9496, 24.1052) vai Google Maps / OpenStreetMap saiti.",
        "en": "📍 2/2 Now the location. Tap the button below — or send another point via 📎 → Location. "
              "On a computer: paste coordinates (56.9496, 24.1052) or a Google Maps / OpenStreetMap link.",
    },
    "btn_location": {"lv": "📍 Sūtīt manu atrašanās vietu", "en": "📍 Send my location"},
    "location_ok": {"lv": "Vieta saņemta ✅", "en": "Location received ✅"},
    "summary": {
        "lv": "Pārbaudi un apstiprini:\n\n📷 foto: ir\n📍 vieta: {lat:.5f}, {lon:.5f}\n\n"
              "Kas tur ir un cik slikti, novērtēs MI pēc foto.",
        "en": "Check and confirm:\n\n📷 photo: attached\n📍 location: {lat:.5f}, {lon:.5f}\n\n"
              "What is there and how bad: the AI reads it from the photo.",
    },
    "btn_send": {"lv": "✅ Sūtīt", "en": "✅ Send"},
    "btn_cancel": {"lv": "✖️ Atcelt", "en": "✖️ Cancel"},
    "sending": {"lv": "Sūtu un pārbaudu foto… ⏳", "en": "Sending and checking the photo… ⏳"},
    "accepted": {
        "lv": "🏮 Paldies, signāls saņemts!\nPieteikuma kods: {ticket}\n\nKad situācija mainīsies, es tev pateikšu. "
              "Statuss: /status",
        "en": "🏮 Thank you, signal received!\nTicket: {ticket}\n\nI'll let you know when something changes. "
              "Status: /status",
    },
    "merged": {
        "lv": "Par šo vietu jau ziņoja — tavs signāls pievienots un paaugstina prioritāti.",
        "en": "This place was already reported — your signal was added and raises the priority.",
    },
    "review": {
        "lv": "🏮 Paldies, signāls saņemts!\nPieteikuma kods: {ticket}\n\nInspektors vēl pārbaudīs foto.",
        "en": "🏮 Thank you, signal received!\nTicket: {ticket}\n\nAn inspector will check the photo.",
    },
    "rejected": {
        "lv": "🤷 Šajā foto neredzam problēmu uz ietves (sniegs, ledus, lāstekas, aizšķērsots ceļš), tāpēc "
              "pieteikums netika izveidots. Nofotografē ietvi tuvāk un mēģini vēlreiz.",
        "en": "🤷 We can't see a sidewalk problem in this photo (snow, ice, icicles, a blocked path), so no "
              "ticket was created. Take a closer photo of the sidewalk and try again.",
    },
    "too_many": {
        "lv": "⏳ Tu šodien jau esi nosūtījis daudz ziņojumu. Paldies! Lūdzu, mēģini vēlāk.",
        "en": "⏳ You have already sent a lot of reports. Thank you! Please try again later.",
    },
    "outside_area": {
        "lv": "📍 Šī vieta ir ārpus Rīgas. Lantern pieņem ziņojumus tikai par Rīgu.",
        "en": "📍 This place is outside Riga. Lantern only takes reports about Riga.",
    },
    "same_photo": {
        "lv": "ℹ️ Šis foto jau bija nosūtīts, tāpēc to neskaitām kā jaunu apstiprinājumu.",
        "en": "ℹ️ This photo was already sent before, so it doesn't count as a new confirmation.",
    },
    "send_failed": {
        "lv": "Neizdevās nosūtīt — serveris nav pieejams. Mēģini vēlreiz pēc brīža (✅ Sūtīt) vai zvani 1201.",
        "en": "Could not send — the server is unavailable. Try again in a moment (✅ Send) or call 1201.",
    },
    "photo_failed": {
        "lv": "Neizdevās lejupielādēt foto. Lūdzu, nosūti to vēlreiz.",
        "en": "Could not download the photo. Please send it again.",
    },
    "photo_too_big": {
        "lv": "Foto ir lielāks par 10 MB. Lūdzu, nosūti mazāku.",
        "en": "The photo is larger than 10 MB. Please send a smaller one.",
    },
    "cancelled": {"lv": "Atcelts. Lai sāktu no jauna, nosūti foto.", "en": "Cancelled. Send a photo to start again."},
    "private": {
        "lv": "🔒 Šis bots ir privāts. / This bot is private.",
        "en": "🔒 Šis bots ir privāts. / This bot is private.",
    },
    "private_login": {
        "lv": "🔒 Šis bots ir privāts. Komandas dalībnieki: /login parole\n"
              "🔒 This bot is private. Team members: /login password",
        "en": "🔒 Šis bots ir privāts. Komandas dalībnieki: /login parole\n"
              "🔒 This bot is private. Team members: /login password",
    },
    "login_intro": {"lv": "🔒 Lantern bots ir tikai komandai. Lūdzu, ienāc.",
                    "en": "🔒 The Lantern bot is for the team only. Please log in."},
    "ask_login": {"lv": "👤 Ieraksti lietotājvārdu:", "en": "👤 Enter your login:"},
    "ask_password": {"lv": "🔑 Ieraksti paroli (ziņa tiks izdzēsta):", "en": "🔑 Enter your password (the message will be deleted):"},
    "login_ok": {"lv": "✅ Tu esi iekšā.", "en": "✅ You're logged in."},
    "login_bad": {"lv": "❌ Nepareizs lietotājvārds vai parole.", "en": "❌ Wrong login or password."},
    "login_wait": {"lv": "⏳ Pārāk daudz mēģinājumu, pagaidi stundu.", "en": "⏳ Too many tries, wait an hour."},
    "login_already": {"lv": "Tu jau esi iekšā ✅", "en": "You're already in ✅"},
    "logout_ok": {"lv": "👋 Izgājis / Logged out", "en": "👋 Izgājis / Logged out"},
    "bot_short_private": {"lv": "🔒 Privāts Lantern komandas testa bots.", "en": "🔒 Private test bot of the Lantern team."},
    "bot_about_private": {
        "lv": "🔒 Šis ir privāts Lantern komandas testa bots. Tas atbild tikai komandas dalībniekiem "
              "(spied START un ienāc ar lietotājvārdu un paroli).",
        "en": "🔒 This is a private test bot of the Lantern team. It only answers team members "
              "(press START and log in with the team login and password).",
    },
    "btn_status": {"lv": "📋 Mani pieteikumi", "en": "📋 My reports"},
    "btn_lang": {"lv": "🌐 Valoda", "en": "🌐 Language"},
    "btn_help": {"lv": "❓ Palīdzība", "en": "❓ Help"},
    "cmd_start": {"lv": "Jauns ziņojums", "en": "New report"},
    "cmd_status": {"lv": "Mani pieteikumi", "en": "My reports"},
    "cmd_lang": {"lv": "Valoda", "en": "Language"},
    "cmd_help": {"lv": "Kā tas strādā", "en": "How it works"},
    "bot_short": {
        "lv": "Ziņo par neiztīrītu ietvi Rīgā: foto + vieta. Bez vārda un tālruņa.",
        "en": "Report an uncleared sidewalk in Riga: photo + place. No name or phone needed.",
    },
    "bot_about": {
        "lv": "🏮 Lantern palīdz Rīgai ātrāk notīrīt ietves.\n\nSpied START, tad «📸 Ziņot par ietvi»: "
              "nofotografē sniegu, ledu vai lāstekas, un tālrunis pievienos vietu. Mākslīgais intelekts pārbauda "
              "foto, un tikai tad signāls nonāk pie pilsētas inspektora.",
        "en": "🏮 Lantern helps Riga clear sidewalks faster.\n\nPress START, then «📸 Report a sidewalk»: take a "
              "photo of the snow, ice or icicles and the phone adds the place. AI checks the photo, and only then "
              "the signal reaches the city inspector.",
    },
    "welcome_app": {
        "lv": "🏮 Lantern — ziņo par neiztīrītām ietvēm Rīgā.\n\n"
              "Spied «📸 Ziņot par ietvi» zemāk, nofotografē vietu, un tālrunis pievienos, kur tu esi. "
              "Mākslīgais intelekts pārbauda foto, un tikai tad signāls nonāk pie pilsētas inspektora.\n\n"
              "Tas papildina tālruni 1201, nevis aizstāj to. Mēs neprasām vārdu, tālruni vai e-pastu.",
        "en": "🏮 Lantern — report uncleared sidewalks in Riga.\n\n"
              "Press «📸 Report a sidewalk» below, take the photo, and the phone adds where you are. "
              "AI checks the photo, and only then the signal reaches the city inspector.\n\n"
              "This complements the 1201 phone line, it does not replace it. We never ask for your name, phone or email.",
    },
    "btn_app": {"lv": "📸 Ziņot par ietvi", "en": "📸 Report a sidewalk"},
    "ask_app": {
        "lv": "Spied «📸 Ziņot par ietvi» zemāk. Lietotne uzņems foto tagad un pievienos vietu, kur tu esi.",
        "en": "Press «📸 Report a sidewalk» below. The app takes the photo now and adds where you are.",
    },
    "use_app": {
        "lv": "Foto no čata nepieņemam: tas var būt vecs. Spied «📸 Ziņot par ietvi» zemāk un nofotografē vietu tagad.",
        "en": "We don't take photos from the chat: they can be old. Press «📸 Report a sidewalk» below and take the photo now.",
    },
    "help_app": {
        "lv": "Kā ziņot: spied «📸 Ziņot par ietvi» → nofotografē vietu → Nosūtīt. Vietu pievieno tālrunis.\n\n"
              "/start — jauns ziņojums\n/status — mani pieteikumi\n/lang — valoda\n\n"
              "Steidzamos gadījumos zvani 1201 vai 112.",
        "en": "How to report: press «📸 Report a sidewalk» → take the photo → Send. The phone adds the place.\n\n"
              "/start — new report\n/status — my tickets\n/lang — language\n\n"
              "In an emergency call 1201 or 112.",
    },
    "need_photo": {"lv": "Vispirms nosūti foto 📷", "en": "Please send a photo first 📷"},
    "need_location": {"lv": "Nosūti atrašanās vietu ar pogu zemāk 📍 vai ielīmē koordinātas / kartes saiti",
                      "en": "Send the location with the button below 📍 or paste coordinates / a map link"},
    "use_buttons": {"lv": "Izvēlies kādu no pogām ziņā augstāk 👆", "en": "Please choose one of the buttons above 👆"},
    "help": {
        "lv": "Kā ziņot: nosūti foto → atrašanās vietu → pasaki, vai var paiet → apstiprini.\n\n"
              "/start — jauns ziņojums\n/status — mani pieteikumi\n/lang — valoda\n/cancel — atcelt\n\n"
              "Steidzamos gadījumos zvani 1201 vai 112.",
        "en": "How to report: send a photo → the location → whether people can get through → confirm.\n\n"
              "/start — new report\n/status — my tickets\n/lang — language\n/cancel — cancel\n\n"
              "In urgent cases call 1201 or 112.",
    },
    "no_tickets": {"lv": "Tev vēl nav pieteikumu. Nosūti foto, lai sāktu.",
                   "en": "You have no tickets yet. Send a photo to start."},
    "status_header": {"lv": "Tavi pieteikumi:", "en": "Your tickets:"},
    "status_unknown": {"lv": "statuss nav pieejams", "en": "status unavailable"},
    # ticket states
    "st_rejected": {"lv": "noraidīts (nav bīstamība)", "en": "rejected (not a hazard)"},
    "st_in_review": {"lv": "gaida inspektora pārbaudi", "en": "waiting for an inspector check"},
    "st_watch": {"lv": "pieņemts, gaidām tīrīšanas termiņu", "en": "accepted, clearing deadline still running"},
    "st_open": {"lv": "nosūtīts tīrītājiem", "en": "sent to the cleaning contractor"},
    "st_done_reported": {"lv": "tīrītāji ziņo, ka notīrīts — pārbaudām", "en": "contractor says it is cleared — checking"},
    "st_reopened": {"lv": "joprojām nav notīrīts — atkārtoti nosūtīts", "en": "still not cleared — sent back again"},
    "st_verified": {"lv": "notīrīts un pārbaudīts ✅", "en": "cleared and verified ✅"},
    "st_cleared_in_time": {"lv": "notīrīts laikā, pirms termiņa ✅", "en": "cleared in time, before the deadline ✅"},
    "others": {"lv": "vēl {n} iedzīvotāji ziņoja", "en": "{n} other residents reported it"},
    "camera": {"lv": "apstiprina pilsētas kamera", "en": "confirmed by a city camera"},
    # push notifications
    "push_open": {
        "lv": "🏮 {ticket}: pieteikums nosūtīts tīrītājiem. Paldies, ka ziņoji!",
        "en": "🏮 {ticket}: your report was sent to the cleaning contractor. Thanks for reporting!",
    },
    "push_done_reported": {
        "lv": "🧹 {ticket}: tīrītāji ziņo, ka vieta notīrīta. Pilsēta to vēl pārbaudīs.",
        "en": "🧹 {ticket}: the contractor reports the place is cleared. The city will verify it.",
    },
    "push_reopened": {
        "lv": "⚠️ {ticket}: pārbaude rāda, ka vieta joprojām nav notīrīta — pieteikums atkārtoti nosūtīts.",
        "en": "⚠️ {ticket}: the check shows the place is still not cleared — the ticket was sent back.",
    },
    "push_cleared_in_time": {
        "lv": "✅ {ticket}: vieta notīrīta laikā, pirms tīrīšanas termiņa. Paldies, ka ziņoji!",
        "en": "✅ {ticket}: the place was cleared in time, before the clearing deadline. Thanks for reporting!",
    },
    "push_verified": {
        "lv": "✅ {ticket}: vieta notīrīta un pārbaudīta. Paldies, tu palīdzēji kaimiņiem!",
        "en": "✅ {ticket}: the place is cleared and verified. Thank you, you helped your neighbours!",
    },
}


def t(key: str, lang: str, **kw) -> str:
    entry = T.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    return text.format(**kw) if kw else text
