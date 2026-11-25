"""Telegram bot against a fake Bot API and the real Lantern app (in-process)."""
import json

import httpx

from app.bot.telegram_bot import LanternBot, State, Telegram
from app.timeutil import parse_ts

USER = 777001
PHOTO = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


class FakeTelegram:
    def __init__(self):
        self.sent = []      # (method, params)
        self.updates = []   # queued for getUpdates
        self.next_id = 1

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/file/botTOKEN/"):
            return httpx.Response(200, content=PHOTO)
        method = path.rsplit("/", 1)[-1]
        params = json.loads(request.content or b"{}")
        self.sent.append((method, params))
        if method == "getUpdates":
            ups = [u for u in self.updates if u["update_id"] >= params.get("offset", 0)]
            self.updates = []
            return httpx.Response(200, json={"ok": True, "result": ups})
        if method == "getFile":
            return httpx.Response(200, json={"ok": True, "result": {"file_id": params["file_id"], "file_size": len(PHOTO),
                                                                     "file_path": "photos/file_1.jpg"}})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    def texts(self, chat_id=None):
        return [p["text"] for m, p in self.sent if m == "sendMessage" and (chat_id is None or p["chat_id"] == chat_id)]

    # ---- update builders
    def _u(self, payload):
        payload["update_id"] = self.next_id
        self.next_id += 1
        return payload

    def msg(self, chat, **fields):
        return self._u({"message": {"message_id": self.next_id, "chat": {"id": chat, "type": "private"},
                                    "from": {"id": chat}, **fields}})

    def cb(self, chat, data):
        return self._u({"callback_query": {"id": f"cb{self.next_id}", "data": data, "from": {"id": chat},
                                           "message": {"message_id": 5, "chat": {"id": chat, "type": "private"}}}})


def make_bot(client, tmp_path):
    fake = FakeTelegram()
    tg = Telegram("TOKEN", "http://tg.test", client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    bot = LanternBot(tg, client, State(tmp_path / "bot_state.json"))
    return bot, fake


def walk_report(bot, fake, chat, comment="Sniega valnis"):
    bot.handle_update(fake.msg(chat, photo=[{"file_id": "small", "width": 90, "height": 60},
                                            {"file_id": "big", "width": 1280, "height": 960}]))
    bot.handle_update(fake.msg(chat, location={"latitude": 56.9600, "longitude": 24.1300}))
    bot.handle_update(fake.cb(chat, "pass:no"))
    bot.handle_update(fake.cb(chat, "haz:snow"))
    bot.handle_update(fake.cb(chat, "place:crossing"))
    bot.handle_update(fake.msg(chat, text=comment))
    bot.handle_update(fake.cb(chat, "ok:send"))


def test_report_through_bot_and_status_push(make_client, tmp_path):
    client, engine, clock, verdicts = make_client()
    clock.set(parse_ts("2026-11-25T12:00:00Z"))
    client.post("/settings", json={"snowfall_end": "2026-11-25T05:00:00Z", "hour_seconds": 3600})
    bot, fake = make_bot(client, tmp_path)

    # /start and the language choice go through real long polling
    fake.updates = [fake.msg(USER, text="/start")]
    assert bot.poll_once(timeout=0) == 1
    assert "Choose a language" in fake.texts(USER)[-1]
    fake.updates = [fake.cb(USER, "lang:en")]
    bot.poll_once(timeout=0)
    assert bot.state.data["offset"] == 3
    assert "Send one photo" in fake.texts(USER)[-1]

    walk_report(bot, fake, USER)
    # it downloaded the largest photo size
    assert ("getFile", {"file_id": "big"}) in fake.sent
    # a summary was shown and the user confirmed before sending
    assert any("Check and confirm" in x for x in fake.texts(USER))
    last = fake.texts(USER)[-1]
    assert "Thank you, signal received" in last

    rows = engine.db.q("SELECT * FROM reports")
    assert len(rows) == 1
    r = rows[0]
    assert r["channel"] == "telegram" and r["passable"] == "no" and r["hazard"] == "snow"
    assert r["place_type"] == "crossing" and r["comment"] == "Sniega valnis"
    assert r["device_id"] == bot.device_id(USER) and str(USER) not in r["device_id"] and len(r["device_id"]) == 16
    assert r["ticket"] in last
    alert_id = r["alert_id"]
    assert engine.alert(alert_id)["status"] == "open"  # deadline passed -> straight to the contractor

    # status push: open -> done_reported -> verified, each sent once
    assert bot.check_statuses() == 1
    assert "sent to the cleaning contractor" in fake.texts(USER)[-1]
    assert bot.check_statuses() == 0
    contractor = engine.alert(alert_id)["contractor_id"]
    client.post(f"/alerts/{alert_id}/status", json={"status": "done_reported", "role": "contractor",
                                                    "contractor": contractor})
    assert bot.check_statuses() == 1 and "contractor reports" in fake.texts(USER)[-1]
    client.post(f"/alerts/{alert_id}/status", json={"status": "verified", "role": "inspector", "actor": "insp"})
    assert bot.check_statuses() == 1 and "cleared and verified" in fake.texts(USER)[-1]
    assert bot.state.chat(USER)["tickets"][0]["done"] is True
    assert bot.check_statuses() == 0

    # /status lists the ticket; state file never contains the raw id on the server side
    bot.handle_update(fake.msg(USER, text="/status"))
    assert r["ticket"] in fake.texts(USER)[-1]


def test_rejected_photo_and_bad_input(make_client, tmp_path):
    client, engine, clock, verdicts = make_client()
    verdicts["telegram.jpg"] = "reject"
    bot, fake = make_bot(client, tmp_path)
    chat = 555
    bot.handle_update(fake.msg(chat, text="/start"))
    bot.handle_update(fake.cb(chat, "lang:ru"))
    # location before a photo -> asks for a photo
    bot.handle_update(fake.msg(chat, location={"latitude": 56.95, "longitude": 24.1}))
    assert "Сначала пришлите фото" in fake.texts(chat)[-1]
    # too long comment is refused
    bot.handle_update(fake.msg(chat, photo=[{"file_id": "p", "width": 10, "height": 10}]))
    bot.handle_update(fake.msg(chat, location={"latitude": 56.95, "longitude": 24.1}))
    bot.handle_update(fake.cb(chat, "pass:partly"))
    bot.handle_update(fake.cb(chat, "haz:skip"))
    bot.handle_update(fake.cb(chat, "place:skip"))
    bot.handle_update(fake.msg(chat, text="x" * 201))
    assert "длиннее 200" in fake.texts(chat)[-1]
    bot.handle_update(fake.cb(chat, "com:skip"))
    bot.handle_update(fake.cb(chat, "ok:send"))
    assert "не похоже на опасный тротуар" in fake.texts(chat)[-1]
    rows = engine.db.q("SELECT * FROM reports")
    assert len(rows) == 1 and rows[0]["relevant"] == "reject" and rows[0]["alert_id"] is None
    assert rows[0]["hazard"] is None and rows[0]["place_type"] is None
    assert bot.check_statuses() == 0  # rejected tickets are not tracked


def test_server_down_keeps_draft(make_client, tmp_path):
    client, engine, clock, verdicts = make_client()
    bot, fake = make_bot(client, tmp_path)
    down = httpx.Client(base_url="http://lantern.test",
                        transport=httpx.MockTransport(lambda req: httpx.Response(503, text="down")))
    bot.api = down
    bot.handle_update(fake.msg(1, text="/start"))
    bot.handle_update(fake.cb(1, "lang:lv"))
    walk_report(bot, fake, 1)
    assert "Neizdevās nosūtīt" in fake.texts(1)[-1]
    assert bot.drafts[1]["step"] == "confirm"
    bot.api = client  # server back: pressing Send again works
    bot.handle_update(fake.cb(1, "ok:send"))
    assert "Paldies, signāls saņemts" in fake.texts(1)[-1]
    # a broken update does not raise
    bot.handle_update({"update_id": 99, "message": {"chat": {}}})
