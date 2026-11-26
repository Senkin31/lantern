"""Lantern Telegram bot: residents send photo + location, the Lantern server does the rest.

The bot is a thin client. It never calls the model: it posts the report to the Lantern
server (POST /reports), the server asks /analyze whether the photo is a real sidewalk
hazard, and only accepted reports reach the inspector. The bot relays the verdict and
later pushes status changes (sent to contractor, cleared, verified).

Run from the repo root:   python -m app.bot.telegram_bot
Needs TELEGRAM_BOT_TOKEN (from @BotFather) and LANTERN_API_URL in .env.

Privacy: the server only gets device_id = sha256(salt + telegram user id)[:16]. The raw
Telegram id and chat id stay in the bot's local state file (data/bot_state.json).
"""
import hashlib
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from ..config import ROOT, env
from .i18n import LANG_NAMES, LANGS, t

log = logging.getLogger("lantern.bot")

MAX_PHOTO = 10 * 1024 * 1024
COMMENT_MAX = 200
# Telegram on a computer cannot send a location pin: accept "56.9496, 24.1052" or a map link
# (Google Maps "@56.94,24.10" / "?q=56.94,24.10", OpenStreetMap "#map=17/56.94/24.10" or mlat/mlon)
_COORDS = [re.compile(r"mlat=(-?\d{1,2}\.\d+)&mlon=(-?\d{1,3}\.\d+)"),
           re.compile(r"(?<![\d.])(-?\d{1,2}\.\d{3,})\s*[,;/ ]\s*(-?\d{1,3}\.\d{3,})(?![\d.])")]


def coords_from_text(text: str) -> Optional[tuple]:
    """(lat, lon) from typed coordinates or a map link, else None."""
    for rx in _COORDS:
        m = rx.search(text or "")
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
    return None
TRACK_DAYS = 7
STATUS_EVERY = 30.0
NOTIFY_STATUSES = ("open", "done_reported", "reopened", "verified", "cleared_in_time")
HAZARDS = ("snow", "ice", "icicles", "other")
PLACES = ("sidewalk", "crossing", "ramp", "stop", "other")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TelegramError(Exception):
    pass


class Telegram:
    """Minimal Bot API client over an injectable httpx.Client."""

    def __init__(self, token: str, api_base: str = "https://api.telegram.org", client: Optional[httpx.Client] = None):
        self.base = f"{api_base.rstrip('/')}/bot{token}/"
        self.file_base = f"{api_base.rstrip('/')}/file/bot{token}/"
        self.http = client or httpx.Client(timeout=httpx.Timeout(40.0, connect=10.0))

    def call(self, method: str, **params):
        for attempt in range(3):
            resp = self.http.post(self.base + method, json=params)
            try:
                data = resp.json()
            except ValueError:
                raise TelegramError(f"{method}: HTTP {resp.status_code}")
            if data.get("ok"):
                return data.get("result")
            retry = (data.get("parameters") or {}).get("retry_after")
            if resp.status_code == 429 and retry and attempt < 2:  # flood control
                time.sleep(min(float(retry), 30.0))
                continue
            raise TelegramError(f"{method}: {data.get('description') or resp.status_code}")
        raise TelegramError(f"{method}: too many retries")

    def download(self, file_id: str) -> bytes:
        info = self.call("getFile", file_id=file_id)
        if info.get("file_size") and info["file_size"] > MAX_PHOTO:
            raise ValueError("too big")
        resp = self.http.get(self.file_base + info["file_path"])
        if resp.status_code != 200:  # don't raise httpx errors here: their text contains the URL with the token
            raise TelegramError(f"file download: HTTP {resp.status_code}")
        if len(resp.content) > MAX_PHOTO:
            raise ValueError("too big")
        return resp.content


class State:
    """Local bot state: device salt, per-chat language and tickets. Never sent to the server."""

    def __init__(self, path: Optional[Path]):
        self.path = path
        self.lock = threading.Lock()
        self.data = {"salt": "", "offset": 0, "chats": {}}
        if path and path.is_file():
            try:
                self.data.update(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError) as exc:
                log.warning("could not read %s: %s", path, exc)
        env_salt = env("TELEGRAM_DEVICE_SALT", "")
        if not env_salt and not self.data.get("salt"):
            self.data["salt"] = secrets.token_hex(16)
        self.salt = env_salt or self.data["salt"]
        self.save()

    def save(self) -> None:
        if not self.path:
            return
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)

    def chat(self, chat_id) -> dict:
        return self.data["chats"].setdefault(str(chat_id), {"lang": None, "tickets": []})


class LanternBot:
    def __init__(self, telegram: Telegram, api: httpx.Client, state: State):
        self.tg = telegram
        self.api = api
        self.state = state
        self.drafts: dict = {}  # chat_id -> in-progress report (in memory only)
        self.last_status_check = 0.0

    # ------------------------------------------------------------------ helpers
    def device_id(self, user_id) -> str:
        return hashlib.sha256(f"{self.state.salt}:{user_id}".encode()).hexdigest()[:16]

    def lang(self, chat_id) -> str:
        return self.state.chat(chat_id).get("lang") or "lv"

    def send(self, chat_id, text: str, markup: Optional[dict] = None) -> None:
        params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if markup is not None:
            params["reply_markup"] = markup
        try:
            self.tg.call("sendMessage", **params)
        except (TelegramError, httpx.HTTPError) as exc:
            log.warning("sendMessage to %s failed: %s", chat_id, exc)

    @staticmethod
    def inline(rows) -> dict:
        return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row] for row in rows]}

    def ask_lang(self, chat_id) -> None:
        self.send(chat_id, t("choose_lang", "en"),
                  self.inline([[(LANG_NAMES[c], f"lang:{c}") for c in LANGS]]))

    def ask_photo(self, chat_id) -> None:
        self.drafts[chat_id] = {"step": "photo"}
        self.send(chat_id, t("ask_photo", self.lang(chat_id)), {"remove_keyboard": True})

    def ask_location(self, chat_id) -> None:
        L = self.lang(chat_id)
        self.drafts[chat_id]["step"] = "location"
        self.send(chat_id, t("ask_location", L), {
            "keyboard": [[{"text": t("btn_location", L), "request_location": True}]],
            "resize_keyboard": True, "one_time_keyboard": True})

    def ask_passable(self, chat_id) -> None:
        L = self.lang(chat_id)
        self.drafts[chat_id]["step"] = "passable"
        self.send(chat_id, t("ask_passable", L), self.inline([[
            (t("pass_no", L), "pass:no"), (t("pass_partly", L), "pass:partly"), (t("pass_yes", L), "pass:yes")]]))

    def ask_hazard(self, chat_id) -> None:
        L = self.lang(chat_id)
        self.drafts[chat_id]["step"] = "hazard"
        self.send(chat_id, t("ask_hazard", L), self.inline([
            [(t("haz_snow", L), "haz:snow"), (t("haz_ice", L), "haz:ice")],
            [(t("haz_icicles", L), "haz:icicles"), (t("haz_other", L), "haz:other")],
            [(t("skip", L), "haz:skip")]]))

    def ask_place(self, chat_id) -> None:
        L = self.lang(chat_id)
        self.drafts[chat_id]["step"] = "place"
        self.send(chat_id, t("ask_place", L), self.inline([
            [(t("place_sidewalk", L), "place:sidewalk"), (t("place_crossing", L), "place:crossing")],
            [(t("place_ramp", L), "place:ramp"), (t("place_stop", L), "place:stop")],
            [(t("place_other", L), "place:other"), (t("skip", L), "place:skip")]]))

    def ask_comment(self, chat_id) -> None:
        L = self.lang(chat_id)
        self.drafts[chat_id]["step"] = "comment"
        self.send(chat_id, t("ask_comment", L), self.inline([[(t("skip", L), "com:skip")]]))

    def ask_confirm(self, chat_id) -> None:
        L = self.lang(chat_id)
        d = self.drafts[chat_id]
        d["step"] = "confirm"
        none = t("none", L)
        text = t("summary", L, lat=d["lat"], lon=d["lon"], passable=t(f"pass_{d['passable']}", L),
                 hazard=t(f"haz_{d['hazard']}", L) if d.get("hazard") else none,
                 place=t(f"place_{d['place_type']}", L) if d.get("place_type") else none,
                 comment=d.get("comment") or none)
        self.send(chat_id, text, self.inline([[(t("btn_send", L), "ok:send"), (t("btn_cancel", L), "ok:cancel")]]))

    # ------------------------------------------------------------------ updates
    def handle_update(self, update: dict) -> None:
        try:
            if "callback_query" in update:
                self.on_callback(update["callback_query"])
            elif "message" in update:
                self.on_message(update["message"])
        except Exception:  # one bad update must never stop the bot
            log.exception("failed to handle update %s", update.get("update_id"))

    def on_message(self, msg: dict) -> None:
        chat_id = msg["chat"]["id"]
        if msg["chat"].get("type", "private") != "private":
            return
        user_id = (msg.get("from") or {}).get("id", chat_id)
        text = (msg.get("text") or "").strip()
        chat = self.state.chat(chat_id)
        if text.startswith("/"):
            cmd = text.split()[0].split("@")[0].lower()
            if cmd == "/start":
                if not chat.get("lang"):
                    self.drafts[chat_id] = {"step": "lang"}
                    self.ask_lang(chat_id)
                else:
                    self.send(chat_id, t("welcome", self.lang(chat_id)))
                    self.ask_photo(chat_id)
            elif cmd == "/lang":
                self.drafts.setdefault(chat_id, {"step": "idle"})
                self.ask_lang(chat_id)
            elif cmd == "/cancel":
                self.drafts.pop(chat_id, None)
                self.send(chat_id, t("cancelled", self.lang(chat_id)), {"remove_keyboard": True})
            elif cmd == "/status":
                self.show_status(chat_id)
            else:
                self.send(chat_id, t("help", self.lang(chat_id)))
            return

        if not chat.get("lang"):
            # first contact without /start: default to Latvian but offer the choice
            chat["lang"] = "lv"
            self.state.save()

        file_id, mime = self._photo_of(msg)
        if file_id:
            self.on_photo(chat_id, user_id, file_id, mime)
            return

        draft = self.drafts.get(chat_id)
        step = (draft or {}).get("step")
        L = self.lang(chat_id)
        typed = coords_from_text(text) if step in ("location", "confirm") and not msg.get("location") else None
        if typed:
            msg = {**msg, "location": {"latitude": typed[0], "longitude": typed[1]}}
        if msg.get("location") or msg.get("venue"):
            loc = msg.get("location") or msg["venue"]["location"]
            if step in ("location", "passable", "hazard", "place", "comment", "confirm") and draft.get("photo"):
                draft["lat"], draft["lon"] = float(loc["latitude"]), float(loc["longitude"])
                self.send(chat_id, t("location_ok", L), {"remove_keyboard": True})
                if step == "location":
                    self.ask_passable(chat_id)
                elif step == "confirm":
                    self.ask_confirm(chat_id)
            else:
                self.send(chat_id, t("need_photo", L))
            return
        if step == "comment" and text:
            if len(text) > COMMENT_MAX:
                self.send(chat_id, t("comment_too_long", L, n=len(text)))
                return
            draft["comment"] = text
            self.ask_confirm(chat_id)
            return
        if step == "location":
            self.send(chat_id, t("need_location", L))
        elif step in ("passable", "hazard", "place", "confirm", "lang"):
            self.send(chat_id, t("use_buttons", L))
        else:
            if not draft:
                self.send(chat_id, t("welcome", L))
            self.ask_photo(chat_id)

    @staticmethod
    def _photo_of(msg: dict):
        if msg.get("photo"):
            best = max(msg["photo"], key=lambda p: (p.get("width", 0) * p.get("height", 0), p.get("file_size", 0)))
            return best["file_id"], "image/jpeg"
        doc = msg.get("document")
        if doc and (doc.get("mime_type") or "").startswith("image/"):
            return doc["file_id"], doc["mime_type"]
        return None, None

    def on_photo(self, chat_id, user_id, file_id: str, mime: str) -> None:
        L = self.lang(chat_id)
        try:
            data = self.tg.download(file_id)
        except ValueError:
            self.send(chat_id, t("photo_too_big", L))
            return
        except (TelegramError, httpx.HTTPError) as exc:
            log.warning("photo download failed: %s", exc)
            self.send(chat_id, t("photo_failed", L))
            return
        self.drafts[chat_id] = {"step": "location", "photo": data, "mime": mime, "user_id": user_id}
        self.ask_location(chat_id)

    def on_callback(self, cb: dict) -> None:
        msg = cb.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        data = cb.get("data") or ""
        try:
            self.tg.call("answerCallbackQuery", callback_query_id=cb["id"])
        except (TelegramError, httpx.HTTPError):
            pass
        if chat_id is None:
            return
        # remove the buttons from the answered message so it can't be pressed twice
        if msg.get("message_id"):
            try:
                self.tg.call("editMessageReplyMarkup", chat_id=chat_id, message_id=msg["message_id"],
                             reply_markup={"inline_keyboard": []})
            except (TelegramError, httpx.HTTPError):
                pass
        kind, _, value = data.partition(":")
        draft = self.drafts.get(chat_id) or {}
        step = draft.get("step")
        if kind == "lang" and value in LANGS:
            chat = self.state.chat(chat_id)
            first = not chat.get("lang")
            chat["lang"] = value
            self.state.save()
            reask = {"photo": self.ask_photo, "location": self.ask_location, "passable": self.ask_passable,
                     "hazard": self.ask_hazard, "place": self.ask_place, "comment": self.ask_comment,
                     "confirm": self.ask_confirm}
            if first or step not in reask:
                self.send(chat_id, t("welcome", value))
                self.ask_photo(chat_id)
            else:
                reask[step](chat_id)  # continue the report in the new language
            return
        if kind == "pass" and step == "passable" and value in ("no", "partly", "yes"):
            draft["passable"] = value
            self.ask_hazard(chat_id)
        elif kind == "haz" and step == "hazard":
            draft["hazard"] = value if value in HAZARDS else None
            self.ask_place(chat_id)
        elif kind == "place" and step == "place":
            draft["place_type"] = value if value in PLACES else None
            self.ask_comment(chat_id)
        elif kind == "com" and step == "comment":
            draft["comment"] = ""
            self.ask_confirm(chat_id)
        elif kind == "ok" and step == "confirm":
            if value == "send":
                self.submit(chat_id)
            else:
                self.drafts.pop(chat_id, None)
                self.send(chat_id, t("cancelled", self.lang(chat_id)))
        # stale buttons from an old message are ignored silently

    # ------------------------------------------------------------------ server
    def submit(self, chat_id) -> None:
        L = self.lang(chat_id)
        d = self.drafts[chat_id]
        self.send(chat_id, t("sending", L))
        fields = {"lat": str(d["lat"]), "lon": str(d["lon"]), "passable": d["passable"],
                  "device_id": self.device_id(d["user_id"]), "channel": "telegram"}
        if d.get("hazard"):
            fields["hazard"] = d["hazard"]
        if d.get("place_type"):
            fields["place_type"] = d["place_type"]
        if d.get("comment"):
            fields["comment"] = d["comment"]
        ext = {"image/png": "png", "image/webp": "webp", "image/heic": "heic"}.get(d["mime"], "jpg")
        try:
            resp = self.api.post("/reports", data=fields,
                                 files={"photo": (f"telegram.{ext}", d["photo"], d["mime"])})
            if resp.status_code in (422, 429):  # spam limits / outside Riga: tell the person, drop the draft
                detail = (resp.json() if "json" in resp.headers.get("content-type", "") else {}).get("detail")
                code = detail.get("code") if isinstance(detail, dict) else None
                if code in ("outside_area",) or resp.status_code == 429:
                    self.drafts.pop(chat_id, None)
                    self.send(chat_id, t("outside_area" if code == "outside_area" else "too_many", L))
                    return
            if resp.status_code != 201:
                raise httpx.HTTPStatusError(f"HTTP {resp.status_code}: {resp.text[:200]}",
                                            request=resp.request, response=resp)
            result = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("report submit failed: %s", exc)
            self.send(chat_id, t("send_failed", L))
            return  # draft kept at the confirm step: pressing Send again retries
        self.drafts.pop(chat_id, None)
        ticket = result["ticket"]
        rel = result.get("relevant")
        chat = self.state.chat(chat_id)
        chat["tickets"].append({"ticket": ticket, "sent_at": _iso(_now()), "relevant": rel,
                                "alert_status": None, "done": rel == "reject"})
        chat["tickets"] = chat["tickets"][-30:]
        self.state.save()
        if rel == "reject":
            self.send(chat_id, t("rejected", L, ticket=ticket))
        elif rel == "review":
            self.send(chat_id, t("review", L, ticket=ticket))
        else:
            text = t("accepted", L, ticket=ticket)
            if result.get("alert_id") and self._merged(ticket):
                text += "\n\n" + t("merged", L)
            if result.get("same_photo"):
                text += "\n\n" + t("same_photo", L)
            self.send(chat_id, text)
        log.info("report %s from chat sent: %s", ticket, rel)

    def _merged(self, ticket: str) -> bool:
        st = self.ticket(ticket)
        return bool(st and (st.get("other_reports") or st.get("camera_confirmed")))

    def ticket(self, ticket: str) -> Optional[dict]:
        try:
            resp = self.api.get(f"/reports/ticket/{ticket}")
            return resp.json() if resp.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return None

    def describe(self, st: Optional[dict], L: str) -> str:
        if not st:
            return t("status_unknown", L)
        if st.get("state") == "rejected":
            return t("st_rejected", L)
        parts = []
        status = st.get("alert_status")
        if st.get("state") == "in_review":
            parts.append(t("st_in_review", L))
        elif status:
            parts.append(t(f"st_{status}", L))
        if st.get("other_reports"):
            parts.append(t("others", L, n=st["other_reports"]))
        if st.get("camera_confirmed"):
            parts.append(t("camera", L))
        return ", ".join(parts) or t("status_unknown", L)

    def show_status(self, chat_id) -> None:
        L = self.lang(chat_id)
        tickets = self.state.chat(chat_id)["tickets"][-10:]
        if not tickets:
            self.send(chat_id, t("no_tickets", L))
            return
        lines = [t("status_header", L)]
        for item in reversed(tickets):
            lines.append(f"• {item['ticket']} ({item['sent_at'][:16].replace('T', ' ')} UTC): "
                         f"{self.describe(self.ticket(item['ticket']), L)}")
        self.send(chat_id, "\n".join(lines))

    def check_statuses(self) -> int:
        """Push a message when a resident's alert changes status. Returns messages sent."""
        sent = 0
        cutoff = _now() - timedelta(days=TRACK_DAYS)
        changed = False
        for chat_id, chat in list(self.state.data["chats"].items()):
            L = chat.get("lang") or "lv"
            for item in chat.get("tickets", []):
                if item.get("done"):
                    continue
                if datetime.strptime(item["sent_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) < cutoff:
                    item["done"] = True
                    changed = True
                    continue
                st = self.ticket(item["ticket"])
                if not st:
                    continue
                if st.get("state") == "rejected":
                    item["done"] = True
                    changed = True
                    continue
                status = st.get("alert_status")
                if status and status != item.get("alert_status"):
                    item["alert_status"] = status
                    changed = True
                    if status in NOTIFY_STATUSES:
                        self.send(int(chat_id), t(f"push_{status}", L, ticket=item["ticket"]))
                        sent += 1
                    if status in ("verified", "cleared_in_time"):
                        item["done"] = True
        if changed:
            self.state.save()
        return sent

    # ------------------------------------------------------------------ loop
    def poll_once(self, timeout: int = 25) -> int:
        updates = self.tg.call("getUpdates", offset=self.state.data.get("offset", 0), timeout=timeout,
                               allowed_updates=["message", "callback_query"])
        for u in updates or []:
            self.state.data["offset"] = u["update_id"] + 1
            self.handle_update(u)
        if updates:
            self.state.save()
        return len(updates or [])

    def run_forever(self) -> None:
        me = self.tg.call("getMe")
        log.info("bot @%s started, Lantern server %s", me.get("username"), self.api.base_url)
        backoff = 1.0
        while True:
            try:
                self.poll_once()
                backoff = 1.0
            except (TelegramError, httpx.HTTPError) as exc:
                log.warning("polling failed: %s (retry in %.0fs)", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            if time.monotonic() - self.last_status_check >= STATUS_EVERY:
                self.last_status_check = time.monotonic()
                try:
                    self.check_statuses()
                except Exception:
                    log.exception("status check failed")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stdout)
    # httpx logs every request URL at INFO, and Telegram URLs contain the bot token
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    token = env("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set. Create a bot with @BotFather in Telegram, put the token "
              "into .env (TELEGRAM_BOT_TOKEN=...) and run again.", file=sys.stderr)
        sys.exit(2)
    api_url = env("LANTERN_API_URL", "http://127.0.0.1:8000")
    tg = Telegram(token, env("TELEGRAM_API_BASE", "https://api.telegram.org"))
    key = env("INTERNAL_API_KEY", "")  # lets the server trust our hashed device ids from another host
    api = httpx.Client(base_url=api_url, headers={"X-Lantern-Key": key} if key else None)
    state = State(ROOT / env("BOT_STATE_FILE", "data/bot_state.json"))
    LanternBot(tg, api, state).run_forever()


if __name__ == "__main__":
    main()
