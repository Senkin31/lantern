# Lantern Telegram bot

**Run your own bot** (see [Run](#run)): create one with @BotFather and put its token in `.env`. With no `LANTERN_PASSWORD` set (the default) the bot answers everyone and the web app has no login. Set a password to make both private (see **Private bot** below).

Residents send a sidewalk problem from Telegram: **photo → location → Send**. Nothing else is asked: the model reads from the photo what is there and how bad it is (the server fills `passable` and `hazard` from its verdict, marked as the AI's). The bot is a thin client of the Lantern server:

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
4. Optional, the Mini App (**📸 Report a sidewalk**: live camera, the phone's own location, a map preview). It needs the app over https. Start a tunnel, then start the bot with its link. The link changes every time the tunnel restarts, so restart the bot with the new one:
   ```
   cloudflared tunnel --url http://127.0.0.1:8000
   $env:WEBAPP_URL = 'https://<the link cloudflared printed>'; python -m app.bot.telegram_bot
   ```
   Don't commit the link. Through it, only the Mini App, `/health` and `/login` answer. Details: [Mini App](../README.md#telegram-mini-app-photo-taken-now-the-phones-own-location).

The bot uses long polling, so the bot itself needs no public address (only the Mini App page does).

Commands: `/start`, `/status` (my tickets), `/lang` (LV / EN), `/cancel`, `/help`, plus `/login` and `/logout` when the bot is private. A user can also just send a photo to start a report. Under the message field there is a button bar: **📸 Report a sidewalk** (with the Mini App), **📋 My reports**, **🌐 Language** and **❓ Help**.

**Private bot.** With a password in `.env`, everybody logs in first: after `/start` the bot asks for the login, then the password, and deletes both answers from the chat. The login is the web app's `LANTERN_USER` / `LANTERN_PASSWORD`, or `BOT_USER` / `BOT_PASSWORD` if set. People who are not logged in get no buttons and no Mini App. Details: [Login and the private bot](../README.md#login-and-the-private-bot-nobody-else-spends-our-ai-credit).

**Languages:** Latvian and English. Chats that had chosen Russian before get English.

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
| `LANTERN_USER` / `LANTERN_PASSWORD` | `lantern` / empty | the team login the private bot asks for; empty password = public bot. Never commit the real values |
| `BOT_USER` / `BOT_PASSWORD` | empty | a separate login for the bot only |
| `TELEGRAM_ALLOWED_USERS` | empty | Telegram ids that skip the login |
| `WEBAPP_URL` | empty | public https address of the app, which turns on the Mini App button |
| `GPS_ACCURACY_M` | `75` | Mini App: GPS accuracy (m) that still counts as an exact place |
| `PIN_MOVE_M` | `10` | Mini App: how far (m) the resident may move the pin from the phone's fix |

## Tests

`python -m pytest app/tests/test_bot.py -q` runs the bot against a fake Telegram Bot API and the real app in-process. The tests cover the full conversation, the hashed device id, the accept and reject paths, status pushes, and retrying after a server outage.
