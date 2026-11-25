# app/ — Lantern backend and screens (Daniil)

FastAPI + SQLite on port 8000. It takes in camera signals (from `vision/`) and resident reports (web form and Telegram bot), merges them into alerts, and applies the clearing deadline, urgency and statuses. It serves three screens:

| URL | Who | What |
| --- | --- | --- |
| `/inspector` | City inspector | Map of zones by urgency, "where to go today", alert card with before/after frames and status history, report moderation, response times, GeoJSON/CSV export, demo controls |
| `/contractor?contractor=A` | Contractor (phone) | Their district's jobs: crop of the sidewalk, urgency, complaints, resident photos, **Cleared** button. Never receives full frames. |
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

### Demo with the mock data

Unzip `lantern_mock.zip` into the repo root so that `mock/signals.json` exists. The images in `mock/frames|crops|photos` are gitignored and must never be committed. Then, with the app running:

```powershell
python -m app.demo                 # 1 scenario hour = 6 s; the whole day takes ~1.5 min
python -m app.demo --auto-done     # also presses the contractor's "Cleared" at ~13:30
```

`app.demo` resets the app, sets the time compression, starts `mock/send_signals.py` and copies its `SNOWFALL_END` into the app, so nothing needs pasting. Watch the inspector screen in one window and `/contractor?contractor=A` in another (phone width).

What you should see:

1. Until the deadline every zone is grey `watch`, and the contractor list is empty.
2. The deadline passes, the crossing is still blocked, and the alert goes `open` for Contractor A.
3. Two residents report the same place. Their reports merge (<30 m) and the alert is high.
4. The contractor presses "Cleared". The camera still sees snow an hour later, so the alert is `reopened` and flagged for the council.
5. The camera sends `clear`, the alert is `verified`, and the card shows the before/after frames and a 6 h response time.

## Rules (brief v2, "Правила заявок")

Everything lives in [engine.py](engine.py).

- **Deadline.** The deadline is `SNOWFALL_END + CLEARING_HOURS`. Before it, alerts stay `watch` (inspector only). Once it passes, an alert whose latest reliable evidence still shows snow goes `open` and is sent to the district's contractor. `SNOWFALL_END` comes from `.env` or the inspector's "Snowfall ended" button.
- **Inspector-first cases.** `possible_ice`, ice/icicle reports and frames with confidence < 0.5 go to the inspector straight away (`inspector_flags`). They never reach the contractor on their own.
- **Merging.** Signals for the same `zone_id` always join that zone's open alert. A report joins an open alert within 30 m whose last evidence is ≤ 6 h old; otherwise it starts a new alert. Each device gets one vote per alert.
- **Urgency.** Urgency = base (the maximum over signals and reports in the 6 h window) + place (crossing/ramp/stop +1) + near a school/hospital +1 + confirmations from other sources (+1 each, at most +2). 5+ is high, 3–4 medium, otherwise low. A single unconfirmed report never goes above medium. The card lists every term (`urgency_reasons`).
- **Statuses.** `watch → open → done_reported → verified`, plus `reopened` when the camera still sees snow ≥ 1 h after "done" or the inspector disputes it. Every change is written to `status_history` with who and when.
- **KPIs.** Response time = `verified_at − opened_at`. Notification delay = `notified_at − detected_at`, with a KPI of 15 min. `/stats/response` reports both by contractor and by district.
- **Time compression.** All durations are in "rule hours". `HOUR_SECONDS` (or `CLEARING_SECONDS` printed by the replay script) compresses them for the demo.
- **Privacy.** The contractor and export responses are filtered on the server: no `frame_url`, no device ids and no low-confidence frames.
- **Analysis.** `/analyze` gets a 10 s timeout; on timeout or error the report goes to `review`. While `ANALYZE_URL` is empty, a stub answers `accept`, so the irrelevant-photo report is accepted until the model is connected. `reject` reports are stored but never become alerts, and the inspector can still rescue one from the Reports tab.

## API

| Method | Path | |
| --- | --- | --- |
| POST | `/signals` | camera signal (JSON, contract from the brief) → `201 {"alert_id": 12 \| null}` |
| POST | `/reports` | multipart: `photo`, `lat`, `lon`, `passable` (+ `hazard`, `place_type`, `comment`, `device_id`, `timestamp`, `channel`) |
| GET | `/reports/ticket/{ticket}` | resident's status for one report |
| GET | `/reports?role=inspector&relevant=review\|reject\|all` | moderation list |
| POST | `/reports/{id}/moderate` | `{"decision": "accept\|reject"}` |
| GET | `/alerts?role=inspector` / `?role=contractor&contractor=A` (or `&district=…`) | alerts by role |
| GET | `/alerts/{id}?role=…` | alert with signals, reports and history |
| POST | `/alerts/{id}/status` | `{"status", "role", "actor", "contractor", "note"}`, with role rules enforced |
| GET | `/inspection/today` | top 10 by urgency, then age |
| GET | `/stats/response?within_hours=6` | response time and reopen counts by contractor and district |
| GET | `/export.geojson`, `/export.csv` | open-data export |
| GET/POST | `/settings` | `snowfall_end` (`"now"` works), `hour_seconds`, `clearing_hours`, `clearing_seconds` |
| POST | `/admin/reset` | demo only |
| GET | `/meta` | cameras, contractors, tile URL, credits, source link |

## Tests

```powershell
python -m pytest app/tests -q
```

`test_scenario.py` replays the whole mock day with its original timestamps and checks every line of the scenario in `mock/README.md`, including that no contractor response contains a frame. `test_bot.py` runs the Telegram bot against a fake Bot API.

## Not done yet / next

- There is no real login. The role switcher is a demo filter, as the brief allows, and the inspector name is recorded as `inspector`.
- `/static` (mock frames) and `/media` (resident photos) are public URLs. The server never sends frame URLs to contractors, but a guessed URL would still open the image. Before the pilot, put these behind role checks.
- WhatsApp is not included: it needs a Meta Business account and a public webhook. The bot is a thin client, so a WhatsApp adapter would post to the same `/reports`.
- Browsers only allow geolocation on HTTPS or localhost, so a phone opening the form over plain-HTTP LAN has to tap the map instead.
