# Demo Day walkthrough (app side)

The jury should see one full cycle of the crossing (brief v3): **open → complaint → "Cleared" → reopened → verified → evidence package**. Everything runs on one laptop with no internet except map tiles, and the cameras are replayed from recorded frames.

## Before you go on stage

1. Unzip the mock archive into the repo root (`mock/`). It is not in this repository because it holds camera frames; ask the team for it. Camera frames can also be replayed with `vision/camera_worker.py --replay`.
1. Start the model service (photo check, port 8001) in its own window: `cd vision` then `py -m uvicorn service:app --host 127.0.0.1 --port 8001`. Its `.env` holds `NEBIUS_API_KEY` (never commit it), and the app's `.env` has `ANALYZE_URL=http://127.0.0.1:8001/analyze`. Check http://127.0.0.1:8001/health.
   - With the real model the mock photos get real verdicts: the off-topic photo is **rejected**, the first crossing photo goes to **review** (approve it on the Reports tab to show the +1), and the other mock photos (old webcam frames) are judged "cleared" and rejected. To show a complaint live, send a real phone photo through the form or the bot.
2. Start the app with `app\start.ps1`, or run `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
3. Open two windows side by side:
   - **left, large:** http://127.0.0.1:8000/inspector
   - **right, phone-sized** (browser dev tools → device toolbar, or a real phone on the same Wi-Fi): http://127.0.0.1:8000/contractor?contractor=A
4. Do one dry run with `python -m app.demo --auto-done`. Then press **Reset demo** in the inspector bar.
5. Optional: start the Telegram bot ([@lantern_riga_bot](https://t.me/lantern_riga_bot)) and keep a phone ready to send a report live.
   - Start it with `python -m app.bot.telegram_bot`.
   - Log in on that phone beforehand. The team login is not in the repo.
   - For the **📸 Report a sidewalk** button: start `cloudflared tunnel --url http://127.0.0.1:8000`, then start the bot with `WEBAPP_URL` set to the new link (it changes on every tunnel start).
6. Record a screen video of a good run as a fallback.

## On stage (about 1.5 min at the default speed)

Start the replay: `python -m app.demo`. One scenario hour takes 6 s. The script starts the demo clock and sends the snowfalls by itself. The clock in the inspector bar shows Riga time.

| Real time | Riga time | What happens | What to say |
| --- | --- | --- | --- |
| 0 s | 07:00 | Snowfall 1 ended at 03:00, so the deadline is **08:00** (shown in the bar). | The council's regulation: snow that stops before 08:00 must be gone by 08:00. |
| 6 s | 08:00 | The deadline passes; the cameras are silent because it is dark. | The model does not judge night frames. Inspectors start at 08:30 anyway. |
| 12 s | 09:00 | First daylight frames. The crossing has a wall of snow and goes straight to **open, Defect act** on Contractor A's phone. The square is partly cleared: **open, Notice** for Contractor B. The sidewalk is clean, so there is no alert. | The camera frame taken after the deadline is the proof. The council can only prove a violation with a photo, and here it is. |
| 16 s | 09:40 | A resident reports "impassable" at the crossing. The report joins the camera alert, which becomes **high**. | Two sources about one place make one alert. |
| 19 s | 10:15 | A complaint at a stop without a camera appears on the inspector's check list. | Complaints used to be sorted by hand in a WhatsApp group. Now each goes to the district's contractor automatically. |
| **27 s** | **11:30** | **Press "Cleared" on the contractor phone.** | The contractor says it's done. |
| 30 s | 12:00 | The camera still sees snow, so the alert is **reopened** and flagged for the council. | The next frame checks every "done". |
| 42 s | 14:00 | Snowfall 2 sets a new deadline of 22:00. The crossing is clean: **verified, response 5 h**. | A clean frame closes the alert, not the button. |
| 45–51 s | 14:30–15:30 | The sidewalk gets snow (**watch**, invisible to the contractor) and is clean by 15:30: **cleared in time**. | Before the deadline nobody is alarmed. |

While the crossing and the square are open, point at the map: zoomed out, the inspector sees only **street sections** (coloured lines) and count bubbles, not a carpet of dots. Click a line to zoom into the block: the single dots appear on it. Say: "Two or more people on one block, or a camera, and the council sees the whole street section, not a dot."

Then open the crossing card and click **📄 Evidence package**: map, deadline and the snowfall it came from, the first frame with snow after the deadline, the last snowy frame and the clean frame (each with Riga time), resident photos and the status history. **Print → Save as PDF**. Say: "The inspector gets the proof without driving out."

Finish on the **Response times** tab: average response per contractor, share closed within 24 h, reopened, overdue and the 15-min notification KPI. Then click **Export GeoJSON** for the open-data requirement. After the replay the clock keeps running fast, so the stop complaint turns **overdue** (red) about two minutes later.

**Timing.** Press "Cleared" between 11:30 and 12:00 (27–30 s). If you press later, the 12:00 frame arrives before "done" and the reopen step will not show. If in doubt, use `--auto-done`.

## Questions the jury may ask

- **"What if the AI is wrong?"** Model v2 tells "not cleaned at all" from "partly cleaned". On a camera it has never seen, 0–1 % of contractor jobs are false. Partly cleaned (confidence below 0.5) and `possible_ice` go only to the inspector. Resident photos the model is unsure about go to the moderation queue. A single random verdict does not close an alert; a clean frame does. Act or notice is only a suggestion, and the inspector changes it with one click.
- **"Privacy?"** Video never leaves the council's servers. Contractors get sidewalk crops only, with people blurred, never the full frame or the evidence package. Residents send no name or phone number: the web form uses a random cookie id, and the bot sends a hashed id.
- **"Why not just the 1201 phone line?"** This complements 1201 by adding a photo and an exact point. The camera catches problems nobody reports, and the deadline rule is the council's own regulation.
- **"Do you plan routes?"** No. The contractor plans its own routes. The +1 for crossings and schools is our proposal, since the city has no list of priority places.
