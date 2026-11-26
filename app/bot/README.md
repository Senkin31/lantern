# Lantern Telegram bot

Residents send a sidewalk problem from Telegram: **photo → location → "can people get through?"** (plus optional hazard, place type and comment) → **confirm**. The bot is a thin client of the Lantern server:

```
Telegram ──(long polling)── bot ──POST /reports──▶ Lantern app :8000 ──POST /analyze──▶ model :8001
                              ◀── verdict + ticket ──┘     (reject → stored, never reaches the inspector)
```

The bot never calls the model itself. Only reports that the model accepts become alerts for the inspector or contractor. `review` reports go to the inspector to check, and `reject` reports are stored without becoming alerts. The bot also checks each ticket every 30 s and messages the resident when the alert is sent to the contractor, reported done, reopened or verified.

## Run

1. In Telegram, open **@BotFather** → `/newbot` → copy the token.
2. Put it in `.env` in the repo root:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   LANTERN_API_URL=http://127.0.0.1:8000
   ```
3. Start the app (`uvicorn app.main:app --port 8000`), then the bot from the repo root:
   ```
   python -m app.bot.telegram_bot
   ```

The bot uses long polling, so neither the bot nor the app needs a public address.

Commands: `/start`, `/status` (my tickets), `/lang` (LV / EN / RU), `/cancel`, `/help`. A user can also just send a photo to start a report.

**Location from a computer.** Telegram Desktop and Telegram Web cannot send a location pin, so at the location step the bot also takes typed coordinates (`56.9496, 24.1052`) or a map link (Google Maps `@lat,lon` / `?q=lat,lon`, OpenStreetMap `#map=z/lat/lon` or `mlat=…&mlon=…`).

## Privacy

- The server receives only `device_id = sha256(salt + Telegram user id)[:16]`, which still gives one vote per person per alert. It never receives the Telegram id, name or username.
- The salt comes from `TELEGRAM_DEVICE_SALT` or is generated once into `data/bot_state.json`.
- That file also holds the chat → tickets map used for status messages. It stays on the bot host, and `data/` is gitignored.

## Limits

The server's spam protection also applies to the bot: 6 reports per hour and 20 per day per person, one vote per place, and the same photo never counts twice. The bot answers politely ("you have already sent a lot of reports…") and drops the draft. Details: [app/README.md](../README.md#spam-protection).

## Settings

| Variable | Default | |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | — | required |
| `LANTERN_API_URL` | `http://127.0.0.1:8000` | Lantern app |
| `TELEGRAM_API_BASE` | `https://api.telegram.org` | the tests point this at a fake API |
| `TELEGRAM_DEVICE_SALT` | random, saved in state | keep it stable, otherwise one-vote-per-device resets |
| `INTERNAL_API_KEY` | — | only if the bot runs on another host than the app: same value on both sides, so the app trusts the bot's hashed device ids |
| `BOT_STATE_FILE` | `data/bot_state.json` | |

## Tests

`python -m pytest app/tests/test_bot.py -q` runs the bot against a fake Telegram Bot API and the real app in-process. The tests cover the full conversation, the hashed device id, the accept and reject paths, status pushes, and retrying after a server outage.
