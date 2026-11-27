# Lantern — vision service (port 8001)

Decides whether the sidewalk zone on a camera frame is cleared, and sends signals to the Lantern app (`POST /signals`).
No torch needed: only onnxruntime + numpy + pillow, so it runs on x86 and on Windows ARM, on a CPU.

## Install
```
cd vision
py -m pip install -r requirements.txt
copy .env.example .env      (put NEBIUS_API_KEY here; never commit .env)
```

## Run
1. The service (takes `/analyze` for residents' photos, serves frames and crops):
   `py -m uvicorn service:app --host 0.0.0.0 --port 8001`
2. Cameras, one of two modes:
   - replay saved frames (for the demo):
     `py camera_worker.py --replay <frames folder> --since 2026-11-24T06:00 --speed 2`
   - live Fintraffic cameras every 10 minutes: `py camera_worker.py --live --every 10`
   - `--dry-run`: send nothing, only print.
   The Lantern app must listen on `APP_URL` (default http://localhost:8000).
3. VLM second opinion (needs `NEBIUS_API_KEY` in `.env`, model `VLM_MODEL=moonshotai/Kimi-K3`): `--vlm-all` sends every daytime frame to the VLM (recommended; ≈ 200 requests a day for 4 cameras, 2–4 s each), `--vlm` only the zones the small model flagged.
   Choice of VLM (25.11): Kimi-K3 gave no false alarms on cleared frames; Gemma-3-27B says "cleared" to almost everything; Qwen2.5-VL is no longer offered by Nebius.
   How the answers are combined (`fuse` in `vlm_check.py`): VLM "not cleared" → a job is possible; "narrow track" → `partial`, notice level; VLM "cleared" but the model "not cleared" → inspector only (`check`); no answer or confidence < 0.5 → the small model decides.
   Check the VLM against your own labels: `py vlm_eval.py --labels <labels.csv> --frames <frames folder>` (results in `vlm_eval_results.csv`).
4. Ice risk (the council: slippery sections must be gritted): `--ice` on `camera_worker.py`. From Open-Meteo weather (free, no key, CC BY 4.0) for each camera: freezing rain, thaw then frost, precipitation on ground at ≤ 0 °C, humid frost. If the zone is cleared but the risk is medium or high, a `possible_ice` signal goes to the inspector (the frame as evidence), also at night when snow is not judged. Check the weather for every camera: `py ice_risk.py` (or `--at 2026-11-24T07:00`).
5. Evaluate on your own labels:
   `py evaluate_fintraffic.py --labels fintraffic_labels.csv --frames <frames folder>`

## Collecting and labelling data
- `harvest_fintraffic.py`: the last 24 hours of frames from 100 Fintraffic cameras north of 61.5° (different camera models, resolutions, distances), daytime only. Fintraffic keeps frames for a day, so run it daily: `py harvest_fintraffic.py --out <folder>`. First run: ≈ 3,800 frames. `contact_sheet.html` shows one frame per camera, to pick cameras that see a sidewalk.
- `config/zones_hist.json`: sidewalk zones on the chosen cameras (so far 2: Kiiminki C1259102 and Oulu, Äimärautio C1264803).
- `vlm_label.py`: Kimi-K3 labels the frames by the council's rule, then a person checks every frame in `review_kimi.html` → `labels_checked.csv`.

## Endpoints
- `GET /health`
- `POST /analyze`: multipart `photo`, `comment` → `{relevant: accept|review|reject, score, hint, note}`. Without a key, or on an error or a 10 s timeout → `review`.
- `POST /classify`: multipart `image`, `zones` (JSON `[{zone_id, points}]`, optional) → a verdict for each zone.
- `GET /media/crops/...`, `/media/frames/...`: crops (for the contractor) and full frames (inspector only).

## How the model works (v3, the council's rule)
- The council's rule (RD-24-270-sn, as the mentor explained it on 25.11): sidewalks need not be cleared down to the asphalt; packed snow with a cleared track of ≥ 50% of the width and ≥ 1.5 m is **cleared**. Untouched snow with only footprints is **not cleared**. Snow on a grass verge is not a violation.
- The zone from `config/cameras.json` is cut out whole (letterboxed); everything outside the polygon is grey. Dusk and night frames are not judged: the sun's elevation is computed from the camera's coordinates, and below −3° (end of civil twilight; flag `--min-sun`) the frame is skipped. Dark frames and frames under yellow street lights are also skipped.
- Features: YOLO11n-cls (Ultralytics, AGPL-3.0) → `lantern_embed.onnx`. The main `not_cleared` head in `lantern_heads.json`: SkyFinder (fully snowed-in days = not cleared) + Fintraffic labels v2 (weight 5).
- Levels (`decide` in `lantern_vision.py`): `not_cleared` (p ≥ 0.5 → `snow`, confidence ≥ 0.5, may go to the contractor) · `check` (0.3–0.5 → inspector only) · `cleared`.
- Worker: average over 3 frames + hysteresis ±0.05; a signal when the level changes, `snow` repeated every 30 minutes.
- Crops for the contractor have people blurred (`privacy.py`). The full frame for the inspector is unchanged.
- Demo cameras: Kajaani (zone = the footpath only), Jyväskylä (sidewalk on a bridge), Vaasa (footpath), Oulu (a crossing zone with an island). Lahti is switched off.

## Quality (honest, 26.11)
Metric: a "not cleared" frame counts as found if at least one of the two flagged it (the model `check` or `not_cleared`, Kimi "partial" or "not cleared"). A wrong job = a cleared frame got the level `not_cleared`.

| Test | cleared → wrong job | not cleared → found |
|---|---|---|
| Small model, demo cameras, camera held out (89 frames, 4 cameras) | 5 of 71 | — (no violations on these cameras) |
| Small model, new cameras (never seen) | 0 of 36 (Oulu, Äimärautio) | 26 of 35 = 74% (Kiiminki) |
| Kimi-K3, new cameras | 0 of 36 | 23 of 35 = 66% (mostly "partial") |
| Model + Kimi together | 0 of 36 | 33 of 35 = 94% |
| Kimi-K3, 40 SkyFinder frames | 0 of 24 | 8 of 8 on camera 10917 |

- So far only one camera had real violations (Kiiminki), so 94% is a preliminary number.
- The hard case is a thin, even layer of fresh snow across the whole width with no cleared track. A strict prompt for Kimi catches it 97% of the time, but gives 18 wrong "not cleared" of 71 on the demo cameras (the bridge in Jyväskylä, which the mentor called cleared), so the demo keeps the soft prompt.
- Adding Kiiminki to the small model's training makes it confuse thin untouched snow with the packed track on the Jyväskylä bridge; more cameras with violations are needed (the harvester runs every day).
- Residents' photos taken at eye level are not for the camera model; they go through `/analyze`.

## Data and licences
- SkyFinder (Mihail et al.): training only, frames are not published.
- Fintraffic / digitraffic.fi: CC BY 4.0, credit the source.
- YOLO11 (Ultralytics): AGPL-3.0 (both the classifier and the people detector), so the whole repository is AGPL-3.0.
