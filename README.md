# Lantern

Lantern helps winter maintenance dispatchers decide which sidewalks need attention first. It uses footage from fixed street cameras and photos submitted by residents to flag snow blocking a walkway, mark possible ice for review, and rank alerts by urgency on a map.

Built at [RobotHack 2026](https://rh26.hacktribe.co/) (Riga, 24–28 November 2026) for the partner challenge **PCH4 – Spot Winter Sidewalk Hazards** and the **CH3 – Smart Cities** track.

> **Status:** work in progress. This README will be filled in during the hackathon.

## What it does

- [ ] Detects snow blocking the walkway on fixed-camera views
- [ ] Flags possible ice for dispatcher review
- [x] Accepts resident photo reports through a web form and a Telegram bot
- [x] Merges signals about the same place into one alert and ranks it by urgency
- [x] Shows alerts on a map with before/after frames
- [x] Sends alerts to the district's contractor only after the clearing deadline, and checks their "cleared" against the next camera frame
- [x] Measures contractor response time and exports alerts as GeoJSON/CSV

## Getting started

Requirements: Python 3.11+.

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000/inspector (city inspector), http://127.0.0.1:8000/contractor?contractor=A (contractor, phone) and http://127.0.0.1:8000/report (resident form). On Windows, `app\start.ps1` does all of this in one step.

To replay the mock day (unzip `lantern_mock.zip` into the repo root first):

```bash
python -m app.demo --auto-done
```

More: [app/README.md](app/README.md) (backend, rules, API), [app/bot/README.md](app/bot/README.md) (Telegram bot), [docs/demo.md](docs/demo.md) (Demo Day walkthrough).

## Project structure

```
app/      backend (FastAPI + SQLite) and the inspector, contractor and resident screens; Telegram bot in app/bot
vision/   model, zones, /analyze
tools/    frame collector, zone labelling
config/   cameras.json (vision side), contractors.json (app side)
mock/     stub signals and frames for building the app without the model (images are not committed)
docs/     API contract, demo walkthrough, slides
```

## Data

Footage, frames and model weights are not stored in this repository.

_TODO: where to get the demo data._

## Team

- Nikita Senkin
- Daniil Dobelis

## License

Copyright (C) 2026 Nikita Senkin and Daniil Dobelis

Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0). We use [Ultralytics YOLO](https://github.com/ultralytics/ultralytics), which is AGPL-3.0, so the project uses the same licence. If you run a modified version as a network service, you must offer its source code to the users of that service.
