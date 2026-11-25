# Demo Day walkthrough (app side)

The jury should see one full alert cycle through two roles (brief v2, "Сценарий демо"). Everything runs on one laptop with no internet except map tiles, and the camera is replayed from recorded frames.

## Before you go on stage

1. Unzip `lantern_mock.zip` into the repo root. Later, use the Fintraffic frames instead.
2. Start the app with `app\start.ps1`, or run `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
3. Open two windows side by side:
   - **left, large:** http://127.0.0.1:8000/inspector
   - **right, phone-sized** (browser dev tools → device toolbar, or a real phone on the same Wi-Fi): http://127.0.0.1:8000/contractor?contractor=A
4. Do one dry run with `python -m app.demo --auto-done`, then press **Reset demo** in the inspector bar.
5. Optional: start the Telegram bot (`python -m app.bot.telegram_bot`) and keep the phone ready to send a report live.
6. Record a screen video of a good run as a fallback.

## On stage (about 2.5 min with `--speed 10`)

Start the replay: `python -m app.demo --speed 10`. At this speed one scenario hour takes 10 s. The script sets the snowfall end and the deadline by itself.

| Real time | Scenario time | What happens | What to say |
| --- | --- | --- | --- |
| 0 s | 04:30 | The crossing camera reports `possible_ice`. The inspector sees it right away under "Where to go today". | Ice can't wait for the clearing deadline, so it goes straight to the inspector. |
| 15–35 s | 06:00–08:00 | Snow and a snowbank appear. The zones are grey `watch`, and the contractor screen is empty. | Snowfall ended at 05:00 and the crews have 6 h. Until then there are no alarms, so the city doesn't get hundreds of empty ones. |
| 52 s | 09:40 | A resident reports the crossing. The report merges into the camera alert. | Two sources about one place make one alert. |
| 65 s | 11:00 | The deadline passes and the snow is still there. The alert turns **open** and appears on Contractor A's phone with the sidewalk crop. | The contractor sees only the crop with people blurred, never the full frame. The server filters it. |
| 77 s | 12:10 | A second resident reports the same spot, and the alert is **high**. | It is now first in the inspector's "Where to go today". |
| **~80–85 s** | 12:30–13:00 | **Press "Cleared" on the contractor phone.** | The contractor says it's done. |
| 100 s | 14:30 | The camera still sees snow, so the alert is **reopened** and flagged for the council. | The next camera frame checks every "done". This is evidence for a dispute. |
| 125 s | 17:00 | The camera sends `clear`, and the alert is **verified**. | Open the alert card and show the before/after frames, the response time (6 h) and the status history (who and when). |

Finish on the **Response times** tab: average response per contractor, share closed within N hours, reopen count and notification delay against the 15 min KPI. Then click **Export GeoJSON** to show the open-data requirement.

**Timing.** Press "Cleared" at least one scenario hour before the 14:30 frame (before about 90 s at `--speed 10`). If you press later, the camera check waits for the next frame and the reopen step won't show. If in doubt, use `--auto-done`.

## Questions the jury may ask

- **"What if the AI is wrong?"** Frames with confidence below 0.5 and `possible_ice` go only to the inspector. Resident photos the model is unsure about go to the moderation queue. Rejected photos are stored, and the inspector can rescue one.
- **"Privacy?"** Video never leaves the city servers. Contractors get crops only. Residents send no name or phone number: the web form uses a random cookie id, and the bot sends a hashed id.
- **"Why not just the 1201 phone line?"** This complements 1201 by adding a photo and an exact point. The camera catches problems nobody reports.
