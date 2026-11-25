# app/ — Lantern backend and screens (Daniil)

FastAPI + SQLite on port 8000. It takes in camera signals (from `vision/`) and resident reports (web form and Telegram bot), merges them into alerts, and applies the clearing deadline, urgency and statuses. It serves three screens:

| URL | Who | What |
| --- | --- | --- |
| `/inspector` | City inspector | Map of zones by urgency, check list for 08:30–17:00, alert card with act/notice level, deadline, fix-by time, before/after frames and status history, **evidence package**, report moderation, response times, GeoJSON/CSV export, snowfall buttons and demo clock |
| `/alerts/{id}/evidence` | Inspector | One printable page (Print → PDF): place, deadline and its snowfall, frames after the deadline with Riga time, resident photos, status history |
| `/contractor?contractor=A` | Contractor (phone) | Their district's jobs: crop of the sidewalk, act/notice, "fix by", overdue mark, complaints, resident photos, **Cleared** button. Never receives full frames or the evidence package. |
| `/report` | Resident | Photo + place + "can you get through?", LV/EN/RU, ticket status |
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
- **Act or notice (`severity`).** The suggestion is `act` (defect act) when the camera sees `blocked` or ≥ 60 % at confidence ≥ 0.7, or snow in two zones of one camera, or a camera plus a resident saying "impassable". Everything else in `open` is `notice` (a letter). The inspector switches it with one click and the change goes to the history. Both levels give 24 h to fix: `fix_due_at = notified_at + 24 h`. If it is not verified by then, the alert is **overdue** (red for the inspector and in the contractor's stats). A person draws up the act, not the system.
- **Inspector-first cases.** `possible_ice`, ice/icicle reports and frames with confidence < 0.5 go to the inspector straight away (`inspector_flags`). They never reach the contractor on their own.
- **Partly cleaned (model v2, brief 1.1).** The model now has two snow levels: "not cleaned at all" = `snow` with confidence ≥ 0.5 (can go to the contractor) and "partly cleaned" = `snow` with confidence < 0.5 (inspector only). When the zone's **latest** frame is partly cleaned, the alert gets the `partly` flag ("Partly cleaned (camera) · inspector only"), stays in `watch` after the deadline and is on the inspector's check list. An earlier full-snow frame does not dispatch it; a later one with confidence ≥ 0.5 does, and so does a counted resident report. Only a `clear` frame closes an alert.
- **Merging.** Signals for the same `zone_id` always join that zone's open alert. A report joins an open alert within 30 m whose last evidence is ≤ 6 h old; otherwise it starts a new alert. Each device gets one vote per alert.
- **Urgency.** Urgency = base (the maximum over signals and reports in the 6 h window) + place (crossing/ramp/stop +1) + near a school/hospital +1 + confirmations from other sources (+1 each, at most +2). 5+ is high, 3–4 medium, otherwise low. A single unconfirmed report never goes above medium. The card lists every term (`urgency_reasons`).
- **Statuses.** `watch → open → done_reported → verified`, plus `cleared_in_time`, and `reopened` when the camera still sees snow after "done" or the inspector disputes it. A clear frame closes the alert, not the button: `verified` works without "done" too. Every status or severity change is written to `status_history` with who and when; that history is part of the evidence package.
- **Check list (`/inspection/today`, 08:30–17:00).** Defect acts first, then overdue `fix_due_at`, complaints without a camera, problem places (reopened within 30 days), then urgency.
- **KPIs.** Response time = `verified_at − notified_at`. Per contractor: average, share closed within 24 h, reopened, overdue. KPI 2 (notification ≤ 15 min) = `notified_at − max(detected_at, deadline_at)`.
- **Clock.** Every rule reads `clock.now()`. The demo speeds it up with `POST /demo/clock {scenario_start, real_start, factor}` (factor 600 = 1 h in 6 s); the screens follow the server clock and show Riga time. The clock survives a restart, and `POST /demo/clock {}` goes back to real time.
- **Report-only alerts.** An accepted complaint with no camera opens for the district's contractor after the deadline, as in v2. The v3 brief only says it goes on the check list, so this is a question for Nikita.
- **Cameras.** `config/cameras.json` (vision side) is read first; `mock/cameras_mock.json` adds the demo cameras it does not define, so the mock demo keeps working once the Finnish cameras land. `source: skyfinder` cameras are never shown. Cameras with `"active": false` (brief 1.1: Lahti and Oulu, whose zones are not on the sidewalk) are switched off: not on the map, no zones, and their signals are stored but never make an alert (`{"alert_id": null}`). The first file that lists a camera wins, including when it switches it off.
- **Privacy.** The contractor and export responses are filtered on the server: no `frame_url`, no evidence link, no device ids and no low-confidence frames. The evidence package answers `403` to `role=contractor` and never contains device ids. `frame_url` may be an absolute `http://localhost:8001/media/...` link (real camera) or a relative `/static/...` one (mocks); both work.
- **Analysis.** `/analyze` gets a 10 s timeout; on timeout or error the report goes to `review`. While `ANALYZE_URL` is empty, a stub answers `accept`, so the irrelevant-photo report is accepted until the model is connected. `reject` reports are stored but never become alerts, and the inspector can still rescue one from the Reports tab.

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
| Inspector | "Block sender" / "Unblock" in the Reports tab | Manual block, plus a 24 h summary of what was refused |

**Identity.** Telegram (and later WhatsApp) sends a stable hashed user id. The web form gets a random cookie, and only trusted callers (`TRUSTED_HOSTS`, or the `INTERNAL_API_KEY` header) may name their own `device_id`. IPs are stored only as salted hashes. All limits are in `.env`.

Example: one phone sends 99 pictures of the same spot. 6 are stored, the place still has 1 vote, `/analyze` is called once, the other 93 are refused, and the sender is muted for a day. This case is in `tests/test_spam.py`.

## API

| Method | Path | |
| --- | --- | --- |
| POST | `/signals` | camera signal (JSON, contract from the brief) → `201 {"alert_id": 12 \| null}` |
| POST | `/reports` | multipart: `photo`, `lat`, `lon`, `passable` (+ `hazard`, `place_type`, `comment`, `device_id`, `timestamp`, `channel`, `registration_no` for a formal council complaint) |
| GET | `/reports/ticket/{ticket}` | resident's status for one report |
| GET | `/reports?role=inspector&relevant=review\|reject\|all` | moderation list |
| POST | `/reports/{id}/moderate` | `{"decision": "accept\|reject"}` |
| GET | `/alerts?role=inspector` / `?role=contractor&contractor=A` (or `&district=…`) | alerts by role, with `severity`, `deadline_at`, `fix_due_at`, `overdue` |
| GET | `/alerts/{id}?role=…` | alert with signals, reports and history |
| POST | `/alerts/{id}/status` | `{"status"?, "severity"? (inspector), "role", "actor", "contractor", "note"}`, with role rules enforced |
| GET | `/alerts/{id}/evidence?role=inspector` | evidence package: HTML for print (`&lang=lv`), or `&format=json` |
| POST | `/snowfalls` | `{"start", "end"}` (ISO UTC, `"now"` works; no `end` = still snowing) → deadline |
| GET | `/settings` | clock, current snowfall, deadline, rule settings |
| POST | `/demo/clock` | demo only: `{"scenario_start", "real_start", "factor"}`; `{}` = real time |
| GET | `/inspection/today` | check list in the v3 order |
| GET | `/stats/response` | response time (`verified − notified`), share within 24 h, reopened, overdue, notification KPI by contractor and district |
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
