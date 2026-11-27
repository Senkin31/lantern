# Lantern

**Lantern tells snow-clearing contractors where a sidewalk still needs clearing or gritting, and confirms with the next camera frame that it was done.** It uses the city's own fixed cameras, weather data and photos from residents. Inspectors get a map of what is still open and time-stamped photo evidence for the cases that need an act.

Built at [RobotHack 2026](https://rh26.hacktribe.co/) (Riga, 24–28 November 2026) for the partner challenge **PCH4 – Spot Winter Sidewalk Hazards** (Riga City Council) and the **CH3 – Smart Cities** track. Team 26-LANTERN: Nikita Senkin (camera and AI) and Daniil Dobelis (app, screens, bot).

## What it does

- [x] Judges the sidewalk zone on every daytime camera frame by the council's rule for "cleared" (RD-24-270-sn): a cleared track of at least half the width and 1.5 m; packed snow is fine, untouched snow is not
- [x] Double-checks each frame with a vision-language model; when the two disagree, the inspector decides and the contractor gets nothing
- [x] Flags likely black ice from the weather (thaw then frost, freezing rain, wet ground at 0 °C) and warns the inspector that gritting is needed, also at night
- [x] Accepts resident photos through a web form and a Telegram bot; AI rejects off-topic and repeated photos
- [x] Merges camera, weather and resident signals about one place into one alert and ranks it by urgency
- [x] Waits for the clearing deadline (08:00 / 22:00 Riga time after a snowfall), then sends the contractor of that district a notification with a cropped photo and 24 h to fix
- [x] Closes the notification only when the next camera frame shows the sidewalk cleared; reopens it otherwise; the inspector can then send the contractor a written warning, and only a person decides on a defect act
- [x] Draws Riga's sidewalk network the way the city's own winter maintenance map (pGIS) does, every section named after its street
- [x] Measures the challenge KPIs and builds a printable evidence package for the inspector

## How it works

```
city cameras ──► vision worker (:8001) ── small model + VLM second opinion + ice risk ──┐
residents ─────► web form / Telegram bot ──► /analyze (AI checks the photo) ────────────┤
                                                                                        ▼
                                            Lantern app (:8000): merge · deadline · urgency · statuses
                                                     │                                 │
                                           Inspector screen                   Contractor screen
                                 (map, check list, evidence package)  (to-do list, cropped photo, "Cleared")
```

1. Every 10 minutes the worker takes a frame from each camera and crops the sidewalk zone. Night and dusk frames are skipped (sun below −3°).
2. A small model (frozen YOLO11n-cls features + logistic regression, CPU only) gives "not cleared / check / cleared". Kimi-K3 looks at the same zone as a second opinion.
3. Before the deadline nobody is disturbed. After it, the contractor gets "Clear this"; a likely-ice warning goes to the inspector. The next frame confirms the fix or reopens the job.

## Getting started

Requirements: Python 3.11+ on Windows, macOS or Linux. No GPU.

**1. The app (port 8000)**

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/inspector (inspector), http://127.0.0.1:8000/contractor?contractor=A (contractor, phone width) and http://127.0.0.1:8000/report (resident). On Windows, `app\start.ps1` does this in one step.

**2. The vision service (port 8001)**

```bash
cd vision
pip install -r requirements.txt
cp .env.example .env        # put NEBIUS_API_KEY here for the VLM second opinion; never commit .env
python -m uvicorn service:app --host 127.0.0.1 --port 8001
```

In the app's `.env`, set `ANALYZE_URL=http://127.0.0.1:8001/analyze` so resident photos are checked by the model.

**3. Cameras**

```bash
cd vision
python camera_worker.py --live --every 10 --vlm-all --ice                         # live Fintraffic cameras
python camera_worker.py --replay <frames folder> --speed 2 --vlm-all --ice        # replay saved frames
python ice_risk.py                                                                # ice risk for every camera now
```

Without a Nebius key, leave out `--vlm-all`. Without internet, leave out `--ice`.

**4. Demo day replay**

Unzip the mock archive into the repo root so that `mock/` exists, then `python -m app.demo --auto-done`. The archive is not in this repository because it holds camera frames; the app runs without it, and the demo video shows the full day. The walkthrough is in [docs/demo.md](docs/demo.md).

## AI and results

We tested on cameras the model has never seen (Finnish road cameras, labelled by a vision-language model and checked by hand):

| Test | Cleared sidewalk → wrong notification | Uncleared sidewalk → flagged |
| --- | --- | --- |
| Small model, new camera | 0 of 36 frames | 26 of 35 (74%) |
| Kimi-K3, new camera | 0 of 36 | 23 of 35 (66%) |
| Small model + Kimi together | 0 of 36 | **33 of 35 (94%)** |
| Small model, 4 demo cameras, camera held out | 5 of 71 | — |

These numbers are preliminary: so far only one camera had real violations. The hard case is a thin, even layer of fresh snow with no cleared track. The council's mentor told us this is "not really a violation, but it needs clearing", so Lantern sends it as a notification, never as an act. We collect history from 100 Finnish road cameras every day (`vision/harvest_fintraffic.py`), so every snowfall adds test data.

Black ice cannot be seen on a camera frame, so Lantern does not try to. It uses Open-Meteo weather per camera (`vision/ice_risk.py`) and warns the inspector that gritting is needed where ice is likely.

## Council rules built in

- Clearing deadline from Riga City Council regulation RD-24-270-sn: snowfall ending before 08:00 → 08:00; 08:00–22:00 → 22:00; after 22:00 → 08:00 next day.
- "Cleared" as explained by the council: a track of at least 50% of the width and 1.5 m; packed snow and side banks are normal; snow on a grass verge is not a violation; slippery sections must be gritted.
- 24 hours to fix after a notification. A person, not the system, decides on a defect act.

## Data and licences

| Data | Used for | Licence / permission |
| --- | --- | --- |
| [Fintraffic / Digitraffic](https://www.digitraffic.fi/) road weather cameras | camera frames for the prototype and tests | CC BY 4.0 |
| [Open-Meteo](https://open-meteo.com/) | hourly weather for the ice risk | CC BY 4.0 |
| Riga winter sidewalk maintenance sections ([pGIS](https://hagberg.pgis.lv/)) | sidewalk map and sections | copied with the council's permission, 26.11.2026 |
| [Rīgas apkaimes](https://data.gov.lv/) | neighbourhood names | CC BY 4.0 |
| OpenStreetMap | map tiles and street sections | ODbL |
| SkyFinder webcam dataset | offline evaluation only | not redistributed, not in this repo |

Camera frames, resident photos, keys and the database are never committed. People in photos sent to contractors are blurred (`vision/privacy.py`); full frames are only for inspectors.

## Project structure

```
app/      backend (FastAPI + SQLite), inspector / contractor / resident screens, Telegram bot (app/bot)
vision/   camera model, VLM second opinion, ice risk, /analyze service, data harvesting and labelling tools
tools/    frame collector and zone drawing tool
config/   cameras.json, contractors.json, riga_sidewalk_sections_pgis.geojson, riga_sidewalks.geojson
docs/     demo walkthrough
mock/     demo scenario (images are not committed)
```

More detail: [app/README.md](app/README.md) (rules, API), [app/bot/README.md](app/bot/README.md) (Telegram bot), [vision/README.md](vision/README.md) (model).

## Team

- Nikita Senkin — cameras, AI, data
- Daniil Dobelis — app, screens, Telegram bot

Thanks to our mentor at Riga City Council for explaining how clearing is checked today, and to our professor at TSI for his feedback on the model and data.

## License

Copyright (C) 2026 Nikita Senkin and Daniil Dobelis

Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0). We use [Ultralytics YOLO](https://github.com/ultralytics/ultralytics), which is AGPL-3.0, so the project uses the same licence. If you run a modified version as a network service, you must offer its source code to the users of that service.
