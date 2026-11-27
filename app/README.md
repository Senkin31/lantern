# app/ — Lantern backend and screens (Daniil)

FastAPI + SQLite on port 8000. It takes in camera signals (from `vision/`) and resident reports (web form and Telegram bot), merges them into alerts, and applies the clearing deadline, urgency and statuses. It serves three screens:

| URL | Who | What |
| --- | --- | --- |
| `/inspector` | City inspector | Map of zones by urgency, check list for 08:30–17:00, alert card with act/notice level, deadline, fix-by time, before/after frames and status history, **evidence package**, report moderation, response times, GeoJSON/CSV export, snowfall buttons and demo clock |
| `/alerts/{id}/evidence` | Inspector | One printable page (Print → PDF): place, deadline and its snowfall, frames after the deadline with Riga time, resident photos, status history |
| `/contractor?contractor=A` | Contractor (phone) | Their district's jobs: crop of the sidewalk, act/notice, "fix by", overdue mark, complaints, resident photos, **Cleared** button. Never receives full frames or the evidence package. |
| `/report` | Resident | Photo + place (the AI reads the rest from the photo), LV/EN, ticket status |
| Telegram bot | Resident | Same report through Telegram ([bot/README.md](bot/README.md)) |

```
camera model (vision, :8001) ──POST /signals──┐
resident web form /report ───POST /reports──┐ │
Telegram bot ────────────────POST /reports──┤ │
                                            ▼ ▼
                              Lantern app :8000 ──POST /analyze──▶ model :8001
                              (merge · deadline · urgency · statuses · SQLite)
                                  │                       │
                     /alerts?role=inspector     /alerts?role=contractor (no frame_url)
                                  ▼                       ▼
                          Inspector screen         Contractor screen
```

## Run

```powershell
pip install -r requirements.txt
copy .env.example .env          # optional: everything has defaults
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/inspector. API docs are at http://127.0.0.1:8000/docs.

On Windows, use `127.0.0.1` rather than `localhost`: `localhost` tries IPv6 first and adds about 2 s to every request.

### What the inspector sees

The screens use a plain public-service look: light only, a navy header with the service name and a **Prototype** label, white panels with thin borders, square corners, and no emoji. The footer says it is a prototype and not an official service. There is no coat of arms and no city or agency branding. The resident form (`/report`) and the Telegram Mini App (`/tg`) use the same look; the Mini App also asks Telegram to paint its own bar navy where the client allows it.

- **Tabs:** Today's visits, All cases, Resident reports, Statistics (LV: Šodienas apsekošana, Visi gadījumi, Iedzīvotāju ziņojumi, Statistika). In Latvian an alert is a *gadījums* (case), so it does not clash with *brīdinājums* (the warning to the contractor).
- **List row:** place and district, "No. X · contractor · camera · time ago", the status tag, and only the flags worth a glance (overdue, high urgency, possible ice, complaint without a camera, report to review, problem place).
- **Case card:** case number, place and district, status, then contractor, fix-by time, who detected it, first seen and the situation. Below that come the photos, the **inspector's decision** (note, buttons, evidence package), the **warning to the contractor**, and the resident reports.
- **More details** is closed by default and stays as you left it between refreshes. It holds the timeline, why this urgency (points), the camera signals with confidences, the status history and the camera zone id. Coordinates are not shown anywhere: the map point is enough.

### Demo: the 25.11 day from brief v3

Unzip the mock archive into the repo root so that `mock/` exists. The images in `mock/frames|crops|photos` are gitignored and must never be committed. Then, with the app running:

```powershell
python -m app.demo                 # 1 scenario hour = 6 s; the whole day takes ~1.5 min
python -m app.demo --auto-done     # also presses Contractor A's "Cleared" at 11:30
```

`app.demo` resets the app and starts the accelerated demo clock (`POST /demo/clock`, 1 h = 6 s). If `mock/signals.json` is Nikita's v3 file, his `mock/send_signals.py` drives the replay. Otherwise the built-in copy of the brief's timeline runs, using the frames and photos already in `mock/`. Watch `/inspector` in one window and `/contractor?contractor=A` in another (phone width).

| Riga time | Event | What you should see |
| --- | --- | --- |
| 07:00 | Snowfall 1 ended at 03:00 | Deadline 08:00 |
| 09:00 | Crossing: wall of snow · square: partly cleared · sidewalk: clean | Crossing **open, act**, Contractor A · square **open, notice**, Contractor B · sidewalk: no alert |
| 09:40 | "Impassable" at the crossing | Joins the crossing alert, **high** |
| 10:15 | Complaint at a stop without a camera | New alert, at most medium, on the check list |
| 11:00 | Off-topic photo | `/analyze` → reject (the built-in stub accepts it until `ANALYZE_URL` is set) |
| 11:30 | Contractor A presses "Cleared" | `done_reported` |
| 11:50 | Second phone at the crossing | +1 confirmation |
| 12:00 | Crossing still has snow | **reopened**, flagged for the council |
| 13:30 | Square clean, nobody pressed "Cleared" | **verified** |
| 14:00 | Snowfall 2 (13:00–14:00) · crossing clean | New deadline 22:00 · crossing **verified**, response **5 h** |
| 14:30 | Sidewalk: snow | **watch** (deadline 22:00), the contractor does not see it |
| 15:30 | Sidewalk clean | **cleared_in_time** |

Finish on the crossing card: **Evidence package** opens the printable page. The demo clock keeps running fast after the replay, so open alerts will become overdue within a minute or two. That is useful for showing the red mark. `POST /demo/clock {}` goes back to real time.

## Rules (brief v3, "Правила заявок")

Everything lives in [engine.py](engine.py); the deadline table is in [rules.py](rules.py).

- **Deadline (regulation RD-24-270-sn).** Deadlines are counted on the Riga clock; the database and API stay in UTC. A snowfall ending before 08:00 gives 08:00 that day; 08:00–22:00 gives 22:00; after 22:00 gives 08:00 the next day. With no known snowfall, the deadline is 08:00 of the day the snow was seen. The end of a snowfall arrives through `POST /snowfalls` (the replay script, the inspector's buttons, later LVĢMC weather data). While it is still snowing (end unknown) there is no deadline yet.
- **Watch → open.** Until the deadline an alert is `watch`: the inspector sees it grey, the contractor does not. After the deadline, if the zone's latest signal still shows snow with confidence ≥ 0.5, it becomes `open` and goes to the district's contractor. A background task checks this every second on `clock.now()`, not only when a signal arrives. Snow first seen after the deadline (the 09:00 frame) goes straight to `open` without a watch step.
- **Clear before the deadline** gives `cleared_in_time`: closed, and the contractor never saw it.
- **Act or notice (`severity`).** The suggestion is `act` (defect act) when the camera sees `blocked` or ≥ 60 % at confidence ≥ 0.7, or snow in two zones of one camera, or a camera plus a resident report that is "impassable" (the model's `accept` of the photo, or an explicit `passable=no` from an API caller). Everything else in `open` is `notice` (a letter). It is kept for ordering and the statistics, but **the screens no longer show a fine or a "defect act" button**: the inspector writes a **warning to the contractor** instead (see below). The API can still switch it (`severity` in `POST /alerts/{id}/status`). Both levels give 24 h to fix: `fix_due_at = notified_at + 24 h`. If it is not verified by then, the alert is **overdue** (red for the inspector and in the contractor's stats). A person draws up the act, not the system.
- **Inspector-first cases.** `possible_ice`, ice/icicle reports and frames with confidence < 0.5 go to the inspector straight away (`inspector_flags`). They never reach the contractor on their own.
- **Partly cleaned (model v2, brief 1.1).** The model now has two snow levels: "not cleaned at all" = `snow` with confidence ≥ 0.5 (can go to the contractor) and "partly cleaned" = `snow` with confidence < 0.5 (inspector only). When the zone's **latest** frame is partly cleaned, the alert gets the `partly` flag ("Partly cleaned (camera) · inspector only"), stays in `watch` after the deadline and is on the inspector's check list. An earlier full-snow frame does not dispatch it; a later one with confidence ≥ 0.5 does, and so does a counted resident report. Only a `clear` frame closes an alert.
- **Merging.** Signals for the same `zone_id` always join that zone's open alert. A report joins an open alert within 30 m whose last evidence is ≤ 6 h old; otherwise it starts a new alert. Each device gets one vote per alert.
- **Urgency.** Urgency = base (the maximum over signals and reports in the 6 h window) + place (crossing/ramp/stop +1) + near a school/hospital +1 + confirmations from other sources (+1 each, at most +2). 5+ is high, 3–4 medium, otherwise low. A single unconfirmed report never goes above medium. The card lists every term (`urgency_reasons`).
- **Statuses.** `watch → open → done_reported → verified`, plus `cleared_in_time`, and `reopened` when the camera still sees snow after "done" or the inspector disputes it. A clear frame closes the alert, not the button: `verified` works without "done" too. Every status or severity change is written to `status_history` with who and when; that history is part of the evidence package.
- **Warning to the contractor (instead of a fine).** On an alert the contractor has (`open`, `done_reported`, `reopened`), the inspector writes a message in a text box and presses **Send warning**. The contractor sees it at the top of that job ("Warning from the inspector", with the time), and it goes to the status history, so it is part of the evidence package. `POST /alerts/{id}/warning {"role": "inspector", "actor", "message"}` (1–500 characters); a watch or closed alert answers 409. Every alert carries `warnings` (newest first).
- **Check list (`/inspection/today`, 08:30–17:00).** Suggested acts first (not shown as such), then overdue `fix_due_at`, complaints without a camera, problem places (reopened within 30 days), then urgency.
- **KPIs.** Response time = `verified_at − notified_at`. Per contractor: average, share closed within 24 h, reopened, overdue. The **Statistics** tab starts with the three challenge KPIs (`kpi` in `/stats/response`):
  - **KPI 1, false alarms per camera hour:** jobs the inspector closed with **False alarm (no snow)** (`POST /alerts/{id}/status {"status": "verified", "false_alarm": true}`, inspector only), divided by hours of camera work (first to last signal of each camera). False alarms are left out of the contractors' response times.
  - **KPI 2, notification ≤ 15 min:** `notified_at − max(detected_at, deadline_at)`, over all jobs.
  - **KPI 3, exact location:** share of signals with a point (camera signals always; resident reports that are not rejected and have a map point).
- **Clock.** Every rule reads `clock.now()`. The demo speeds it up with `POST /demo/clock {scenario_start, real_start, factor}` (factor 600 = 1 h in 6 s); the screens follow the server clock and show Riga time. The clock survives a restart, and `POST /demo/clock {}` goes back to real time.
- **Report-only alerts.** An accepted complaint with no camera opens for the district's contractor after the deadline, as in v2. The v3 brief only says it goes on the check list, so this is a question for Nikita.
- **Street sections** (`GET /sections`; the maps now draw the sidewalk network below instead). The council wanted **pieces of street**, not only dots. Each active alert is snapped to the nearest block of sidewalk or street (a sidewalk within 15 m wins; reports up to 25 m, camera zones up to 40 m). A block is painted when the evidence is about the street: a **camera** alert lies on it, or **2+ different residents** reported on it (counted reports, one vote per device). A single complaint stays a dot that gets redder with more reports. The block takes its worst alert's colour (reopened → high → medium → low; watch is dashed grey). Blocks come from OpenStreetMap: `python -m app.osm_sidewalks` writes `config/riga_sidewalks.geojson`: central Riga, 4,359 blocks from junction to junction (median 78 m, at most 220 m). Pieces that meet where nothing else joins (a dropped crosswalk, a way boundary) and share name and kind are glued together. `--bbox` sets another area, `--keep-paths` keeps park paths, `--remerge` re-glues an existing file without downloading. A painted section shorter than 80 m grows through its junctions along the same street (straightest way on), so it reads as a street, not a dot; `block_m` keeps the block's own length. **Squares** (Doma laukums, Brīvības laukums, pedestrian areas: 143 outlines from OSM, `--add-squares`) are one place, so an alert inside a square paints **the whole square** as a filled area instead of a line, with the dot on top; the square's outline is not a street block. Unnamed pedestrian areas take the name of the street that runs through them. Without that file, alerts within 80 m are joined by a line instead. Street data © OpenStreetMap contributors, ODbL. When the city's sidewalk GIS layer arrives, it can replace the file (LineStrings with `id`, `name`, `kind`).
- **Sidewalk map like Riga's pGIS.** Both maps (inspector and contractor) are drawn the way the city's winter maintenance system ([hagberg.pgis.lv](https://hagberg.pgis.lv/#/lv/dashboard)) draws them. There, every stretch of sidewalk is its own object: a thin solid line along the sidewalk itself, one per side of the street, cut into sections. It is always visible and takes the colour of its **latest task**: blue = no task, red = *Reģistrēts* (registered), yellow = *Uzsākts* (started), green = *Pabeigts* (finished). **The same sidewalks, 1:1:** `python -m app.pgis_sidewalks` downloads the city's own objects from the public map's API into `data/pgis_sidewalks.geojson`, in one request for lines and one for areas, the same ones the dashboard makes. That is all of Riga: 1,889 maintained stretches (categories 1–3, season 24/25), 4,071 line pieces with their real gaps, plus the 3 Old Riga zones as areas. The app uses that file when it is there. **It is not committed:** the data belongs to the city and pGIS, and `data/` is git-ignored. Ask the council before showing it outside the demo. **Cut into blocks at the crossings:** one pGIS object can be 1.5 km of one street (Brīvības iela), so a red line alone would not say where the problem is. The script cuts every line into **sections between crossings**: where a street meets it (OpenStreetMap junctions and crosswalks of all of Riga, `config/riga_crossings.json`, committed; plus the OSM street centre lines of the centre), and where another maintained sidewalk runs across it (more than 45°; the two sidewalks of a side street give one cut, on the street). A stretch with no known crossing is cut evenly, at most 200 m. Cuts closer than 40 m are one crossing (a wide junction's crosswalks): the one on a street stays. The result is 9,874 sections (median 99 m) from 4,071 pieces. The cut is lossless: the sections together are exactly the pGIS line, with the same gaps. Each section is its own object, so **an alert colours only its block**, and the tooltip shows the block's length. `--no-cut` keeps the whole objects (an alert then colours the whole object, as a pGIS task does). `python -m app.osm_sidewalks --crossings` downloads the crossings again (Overpass, 16 tiles, falls back across 4 public servers and retries; if a tile still fails, the committed file is left as it is). A report in a gap, more than 25 m from a maintained sidewalk, colours nothing and stays a dot, as in pGIS. Some of their names were imported with broken letters ("BaloÅ¾u iela"); the script repairs them ("Baložu iela"). **Every section is named after its street.** In the city's data many lines carry only the district ("Centrs" for every line in the centre, "Avoti", "Āgenskalns": 760 sections) or no name at all (445), and others use old names (Maskavas iela, now Latgales iela), a route number ("Miera iela (Maršruts Nr:19)") or a misspelling ("Ciekurkalna 2. skerlinija"). So each section takes the name of the street that runs alongside it, from OpenStreetMap's named streets of all of Riga (`config/riga_streets.json`, committed, ODbL, made by `python -m app.osm_sidewalks --streets`). How: every 5 m along the section, the nearest street centre line within 35 m running alongside it (within 30°) gets a vote; streets beat named paths. The city's own street wins when it also runs alongside at least a quarter of the section (spelt as in OSM), else the street with the most votes. A short corner piece takes the nearest street within 20 m. Where no street runs alongside, the city's name stays, unless it is only a district. Result: 9,857 of 9,874 sections have a street name. The other 17 are paths away from any street and show as "Sidewalk (district)". The city's name is kept as `pgis_name`. `python -m app.pgis_sidewalks --names-only` re-names an existing file without downloading it again. *Without that file*, the OpenStreetMap blocks above are drawn instead (central Riga only): every `kind=sidewalk` block, plus a street centre line only where no sidewalk is mapped beside it (2,099 sidewalk blocks + 754 streets + 143 squares in central Riga; lines inside a square are left out, the square itself is coloured). The base map is grey, the lines are 2 px (3 px from zoom 17), and the colours are theirs. **Our alerts are the tasks:** `open`, `reopened` → registered (red); `watch` (deadline still running), `done_reported` (cleaned, to check) → started (yellow); `verified`, `cleared_in_time` → finished (green). A stretch takes the state of its latest alert, but an open problem is never hidden by an older finished one. Unlike the street sections above, *any* alert colours its stretch (pGIS has no "2 residents" rule). The line is only 2 px, and the dot on it still shows how many reports there are. Every alert's dot is **snapped onto its line** and drawn on top. Only drawn lines take alerts, so a colour or dot never lands on a hidden centre line. Hover a line for its street (with the district), length and state; click a coloured one to open its alert. The contractor sees only their own jobs coloured. `GET /map/network` (geometry, built once, gzipped: ~410 KB with the pGIS sections, ~150 KB with OSM; an ETag, so a new file shows at once) and `GET /map/status` (colours and dots, polled) serve it; the map credits the data source. `/sections` below is unchanged.
- **Zoom levels on both maps.** *Far away* (zoom < 16): **only the coloured sidewalk lines**, as in pGIS. There are no dots and no count bubbles. *Close up* (zoom ≥ 16, a few streets on screen): every alert's dot on its line. *Block view* (zoom ≥ 17): the camera positions too. Picking an alert in the list flies in to it, so its dot shows (`DOT_ZOOM` in `common.js`). **No camera rectangles** on the inspector or contractor map: a camera zone's rectangle is drawn on the image, so on the map it lands on buildings. A camera alert is shown by its stretch of sidewalk or square and a dot, and the dot is **snapped onto the line** (the nearest drawn block within 40 m; `map_point` in the alert, `points` in `/map/status`), so it is not on a roof where the zone's centre fell. Resident dots are snapped onto their line too (within 25 m); a report with no line nearby stays at its exact spot. The zone stays on the evidence package, where it is what the camera measured.
- **Cameras.** `config/cameras.json` (vision side) is read first; `mock/cameras_mock.json` adds the demo cameras it does not define, so the mock demo keeps working once the Finnish cameras land. `source: skyfinder` cameras are never shown. Cameras with `"active": false` (Lahti; Oulu is back on since Nikita's 25.11 model, with a crossing zone) are switched off: not on the map, no zones, and their signals are stored but never make an alert (`{"alert_id": null}`). The first file that lists a camera wins, including when it switches it off.
- **Privacy.** The contractor and export responses are filtered on the server: no `frame_url`, no evidence link, no device ids and no low-confidence frames. The evidence package answers `403` to `role=contractor` and never contains device ids. `frame_url` may be an absolute `http://localhost:8001/media/...` link (real camera) or a relative `/static/...` one (mocks); both work.
- **Analysis.** `/analyze` gets a 10 s timeout; on timeout or error the report goes to `review`. While `ANALYZE_URL` is empty, a stub answers `accept`, so the irrelevant-photo report is accepted until the model is connected. `reject` reports are stored but never become alerts, and the inspector can still rescue one from the Resident reports tab.

## Spam protection

The rules are in [spam.py](spam.py). They cover every channel (web form, Telegram, and later WhatsApp), and every check runs **before** the photo goes to `/analyze`, so spam costs no model calls.

| Check | Default | What happens |
| --- | --- | --- |
| Same place, same sender | one vote per sender per alert | Stored, but not counted and not re-analysed |
| Same photo again (exact copy, or a resized/re-compressed one via a 64-bit perceptual hash) | 7 days | Stored, but never counted as a new confirmation, even from another phone |
| Too many reports per sender | 6 per hour, 20 per day | `429`, "try again later" |
| Too many reports from one network (web form) | 30 per hour | `429`. This backstops spammers who clear their cookies. |
| Outside the service area | Riga bounding box | `422 outside_area` |
| Auto-mute | 3 rejected photos or 5 repeats in 24 h | Sender blocked for 24 h |
| Inspector | "Block sender" / "Unblock" in the Resident reports tab | Manual block, plus a 24 h summary of what was refused |

**Identity.** Telegram (and later WhatsApp) sends a stable hashed user id. The web form gets a random cookie, and only trusted callers (`TRUSTED_HOSTS`, or the `INTERNAL_API_KEY` header) may name their own `device_id`. IPs are stored only as salted hashes. All limits are in `.env`.

Example: one phone sends 99 pictures of the same spot. 6 are stored, the place still has 1 vote, `/analyze` is called once, the other 93 are refused, and the sender is muted for a day. This case is in `tests/test_spam.py`.

### Fake reports (wrong place, picture of a screen, repeat offenders)

Spam limits stop floods; these rules stop a single convincing fake. None of them refuses a report: they decide whether it may **send the contractor on its own** or must **wait for the inspector** (`review` / `watch`). The inspector sees why on the report.

| Case | How it is spotted | What happens |
| --- | --- | --- |
| Place picked on a map, typed, or tapped on the web map | `location_source`: `gps` (phone measured it: Telegram adds `horizontal_accuracy`, the web form used "Use my location"), `pin`, `typed`, `map` | Only a GPS place, a camera or **two different people** can send the contractor. One approximate report waits for the inspector. Flag `approx_location`. KPI 3 counts only exact places. |
| Screenshot, webcam frame, stock photo | the model's note (`screenshot`, `webcam`, `stock photo`, `watermark`…) or its optional `source` field | `accept` becomes `review`. Flag `not_street_photo`. |
| Sender with false alarms | 2+ alerts this sender confirmed were closed by the inspector as "False alarm" (`FALSE_ALARM_STRIKES`) | Their `accept` becomes `review`. Flag `false_alarm_sender`. Other people are not affected. |

API callers that send no `location_source` (demo script, replay) count as exact. Tests: `tests/test_trust.py`.

### Login and the private bot (nobody else spends our AI credit)

Every report is checked by the AI service on our paid API key. Nobody can read that key (it stays in the model service's `.env`), but strangers could *use* it by sending reports. So:

- **Web app login:** with `LANTERN_PASSWORD` set (in `.env`, with `LANTERN_USER`, default `lantern`), the inspector, contractor and resident pages and the API docs open a login page first. The session lasts 12 h; **Log out** is in the header. Changing the password logs everybody out. 5 wrong passwords in 15 min from one address mean waiting.
- **API:** needs the login too, except for programs on this computer (the bot, the camera worker, the demo script: `TRUSTED_HOSTS` without proxy headers) or callers with the `INTERNAL_API_KEY` header. Through the public link only the Mini App, `/health` and `/login` work without logging in.
- **Private bot:** everybody logs in. After `/start` the bot asks for the **login**, then the **password** (the web app's `LANTERN_USER` / `LANTERN_PASSWORD`, or `BOT_USER` / `BOT_PASSWORD`) and deletes both answers from the chat. It then remembers the Telegram id in `data/bot_state.json`; `/logout` undoes it. 5 wrong tries an hour. People not logged in get no buttons, no Mini App pass and no command menu, and nothing about them is stored. Mini App passes last 12 h and are signed with the bot token *and* the team password, so a new password cancels every pass. `TELEGRAM_ALLOWED_USERS` can list ids that skip the login.

Tests: `tests/test_login.py`.

### Telegram Mini App (photo taken now, the phone's own location)

A photo sent in a chat can be old or from the gallery, and a place can be typed. With the Mini App the bot shows a **📸 Report a sidewalk** button instead. It opens `/tg` inside Telegram: the page takes the photo with the **live camera** (no gallery) and sends the phone's position (Telegram's `LocationManager`, else the browser's geolocation) with its accuracy.

- **Who is sending:** the button URL carries a pass the bot signs for this person: `device_id.expiry.hmac`, key derived from `TELEGRAM_BOT_TOKEN`, valid 72 h, renewed with every bot reply. The server (`POST /reports/app`) refuses a missing or forged pass (403). It never sees the raw Telegram id.
- **Trust:** a valid pass plus accuracy ≤ `GPS_ACCURACY_M` (75 m) counts as an exact place (`gps`); a rougher fix is `coarse` (flag `coarse_location`, waits like a typed place). Time is the server's. **No live camera, no report; no location, no report.** If the camera is blocked or does not open, the page says a report needs it, explains how to allow it and offers **Try again**. There is no file or gallery fallback, and the server refuses anything but `capture=live` (422 `live_only`). Send waits for a location fix, and a refused location shows the same kind of message. (Reports from an older version may still carry the flag `picked_photo`.) Live photos show a green "📷 Taken live in the Telegram app" chip in the inspector.
- **Location: the best recent fix, then a preview.** The page keeps following the phone's position while it is open (the browser's `watchPosition`, or Telegram's `LocationManager` asked every 3 s). GPS usually improves for 10–20 s after the first wifi / cell-tower guess, so it keeps the best recent fix. A newer fix replaces it when it is as accurate, when the kept one is older than 15 s, or when the two disagree by more than both accuracies together (the phone moved). A passing timeout does not hide a fix it already has.
- **"Is the point in the right place?"** After the photo a small map (OpenStreetMap tiles, no pGIS data) shows the point, the phone's accuracy circle and a dashed 10 m circle. The resident may drag the pin or tap the map; the pin stops at `PIN_MOVE_M` (10 m) from the phone's fix. The page sends the pin as `lat`/`lon` and the fix as `gps_lat`/`gps_lon`. The server refuses a pin more than 10 m (plus 1.5 m slack) from the reported fix (422 `moved_too_far`), or half a fix (422 `bad_fix`). It keeps both points (`gps_lat`, `gps_lon`, `pin_moved_m`), and a move of 1 m or more gets the flag `moved_pin`: the inspector sees "Pin moved 6 m by the sender" on the report. A small move does not hold the report back. This does not change what the server can prove: the fix was always the phone's word. If the map cannot start, the page sends the phone's fix as before.
- **Back to the bot:** when the page is done it hands the ticket to the bot (`web_app_data`), which replies with the AI's verdict and follows the status as before. While the Mini App is on, photos sent in the chat are not taken.
- **No ticket for a rejected photo.** When the AI sees no sidewalk problem, nobody gets a ticket (web form, bot, Mini App): the API answers `"ticket": null` and the resident is told nothing was created. The Mini App stays open with **📸 Take another photo**. The row is still kept under an internal lowercase reference (inspector's "Rejected by the model" list, spam checks: 3 rejected photos in 24 h mute the sender), and `/reports/ticket/…` never shows it.
- **Bot buttons.** Under the message field there is always a button bar: **📸 Report a sidewalk** (Mini App on) and **📋 My reports · 🌐 Language · ❓ Help**. At start the bot also sets its command menu (`/start`, `/status`, `/lang`, `/help`) and the "What can this bot do?" text people see before pressing START, in LV and EN.
- **Languages: Latvian and English only** (the bot, the Mini App it opens and the web form `/report`). Russian was dropped: chats that had chosen it get English, the old Russian button bar still works until the bot sends the new one, and at start the bot removes the Russian menu and description Telegram still kept. On `/report`, a visitor who had picked RU before, or whose phone is set to Russian, gets English.
- **Needs https.** For a phone test run a tunnel: `cloudflared tunnel --url http://127.0.0.1:8000` and start the bot with `WEBAPP_URL=https://<the link>`. Requests that came through the tunnel (forwarding headers) reach only `/tg`, `/assets/`, `/reports/app` and `/health`; the inspector, contractor, API and demo controls answer 404, and such requests never get the local `TRUSTED_HOSTS` trust. Without `WEBAPP_URL` the bot works as before (photos in the chat).
- **Limits, honestly:** a web page cannot prove a photo is live. This stops the easy fakes (gallery photos, screenshots sent from the chat, a picked place); a phone with a fake-GPS app or a camera pointed at a screen can still lie, and someone who copies their own Mini App link can post any file claiming `capture=live`: `capture` and `accuracy` are the phone's word, so the green chip is a claim, not proof. The pass only proves *who* sent it. The screen case is also caught by the "picture of a screen" rule above.

Tests: `tests/test_miniapp.py`.

## API

| Method | Path | |
| --- | --- | --- |
| POST | `/signals` | camera signal (JSON, contract from the brief) → `201 {"alert_id": 12 \| null}` |
| POST | `/reports` | multipart: `photo`, `lat`, `lon` (+ `passable`, `hazard`: optional, residents are no longer asked; when missing the server takes them from the model: accept → `no`, review → `partly`, reject → `yes`, hint → hazard, stored with `passable_by = ai`; `location_source`: `gps` | `pin` | `typed` | `map`; `place_type`, `comment`, `device_id`, `timestamp`, `channel`, `registration_no` for a formal council complaint) |
| POST | `/reports/app` | Telegram Mini App: multipart `photo`, `lat`, `lon` (the pin), `accuracy` (m), `capture` (`live` only, anything else is 422 `live_only`), `tg_pass` (signed by the bot), optional `gps_lat` + `gps_lon` (the phone's fix when the pin was moved; at most `PIN_MOVE_M` away) |
| GET | `/reports/ticket/{ticket}` | resident's status for one report |
| GET | `/reports?role=inspector&relevant=review\|reject\|all` | moderation list |
| POST | `/reports/{id}/moderate` | `{"decision": "accept\|reject"}` |
| GET | `/alerts?role=inspector` / `?role=contractor&contractor=A` (or `&district=…`) | alerts by role, with `severity`, `deadline_at`, `fix_due_at`, `overdue` |
| GET | `/alerts/{id}?role=…` | alert with signals, reports and history |
| POST | `/alerts/{id}/status` | `{"status"?, "severity"? (inspector), "role", "actor", "contractor", "note"}`, with role rules enforced |
| POST | `/alerts/{id}/warning` | `{"role": "inspector", "actor", "message"}`: a written warning the contractor sees on the job; goes to the history |
| GET | `/alerts/{id}/evidence?role=inspector` | evidence package: HTML for print (`&lang=lv`), or `&format=json` |
| POST | `/snowfalls` | `{"start", "end"}` (ISO UTC, `"now"` works; no `end` = still snowing) → deadline |
| GET | `/settings` | clock, current snowfall, deadline, rule settings |
| POST | `/demo/clock` | demo only: `{"scenario_start", "real_start", "factor"}`; `{}` = real time |
| GET | `/inspection/today` | check list in the v3 order |
| GET | `/map/network` | the sidewalk network both maps draw (like Riga's pGIS): `blocks` with `id`, `name`, `kind`, `shape` (`line` / `area`), `length_m` or `area_m2`, `coords` [[lat, lon], ...]; gzipped, cacheable, OSM attribution |
| GET | `/map/status` | colour of each stretch: `blocks` {block_id: `state` (registered / started / finished), `status`, `alert_id`, `alert_ids`}; a stretch not listed has no task (blue); `points` {alert_id: [lat, lon]} = the dot on its line. `role=contractor&contractor=` gives only their jobs |
| GET | `/sections` | street sections for the inspector map (inspector only): `name`, `shape` (`line`, or `area` for a square, with `area_m2`), `length_m`, `coords`, worst `status` / `urgency_level`, `alert_ids`, `residents`, `camera` |
| GET | `/stats/response` | `kpi` (KPI 1–3) and response time (`verified − notified`), share within 24 h, reopened, overdue, notification KPI by contractor and district |
| GET | `/export.geojson`, `/export.csv` | open-data export |
| POST | `/admin/reset` | demo only (alerts, reports, snowfalls; the clock is kept) |
| GET | `/meta` | cameras, contractors, tile URL, credits, source link |
| GET | `/spam?role=inspector` | what was refused / not counted in 24 h, blocked senders, limits |
| POST | `/reports/{id}/block-sender` | `{"hours": 24, "reason": "..."}`: block the sender of that report |
| POST | `/devices/unblock` | `{"device_id": "..."}` |

## Tests

```powershell
python -m pytest app/tests -q
```

`test_scenario.py` replays the 25.11 day from brief v3 on a frozen clock and checks every line of its table, plus the deadline table (including summer time), overdue, severity override, two zones of one camera, an ongoing snowfall and the demo clock. It also checks that no contractor response contains a frame or the evidence link. `test_spam.py` covers spam protection, and `test_bot.py` runs the Telegram bot against a fake Bot API.

## Not done yet / next

- There is no real login. The role switcher is a demo filter, as the brief allows, and the inspector name is recorded as `inspector`.
- `/static` (mock frames) and `/media` (resident photos) are public URLs. The server never sends frame URLs to contractors, but a guessed URL would still open the image. Before the pilot, put these behind role checks.
- WhatsApp is not included: it needs a Meta Business account and a public webhook. The bot is a thin client, so a WhatsApp adapter would post to the same `/reports`.
- Browsers only allow geolocation on HTTPS or localhost, so a phone opening the form over plain-HTTP LAN has to tap the map instead.
