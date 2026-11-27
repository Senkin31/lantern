"""Telegram Mini App: signed pass, live-camera reports with the phone's GPS, and the public tunnel
reaching nothing but the Mini App."""
import json
import time

import pytest

from app import tgapp
from app.bot.telegram_bot import LanternBot, State
from app.tests.test_bot import FakeTelegram, Telegram, httpx
from app.tests.test_trust import photo, setup

TUNNEL = {"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "203.0.113.7"}


@pytest.fixture(autouse=True)
def bot_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test-token")


def app_report(client, pass_, *, accuracy=12, capture="live", seed=1, lat=56.9600, lon=24.1300, headers=TUNNEL,
               gps=None):
    data = {"lat": lat, "lon": lon, "capture": capture, "tg_pass": pass_}
    if accuracy is not None:
        data["accuracy"] = accuracy
    if gps:  # the phone's own fix, when the resident moved the pin to lat/lon
        data.update({k: v for k, v in zip(("gps_lat", "gps_lon"), gps) if v is not None})
    return client.post("/reports/app", data=data, files={"photo": ("camera.jpg", photo(seed), "image/jpeg")},
                       headers=headers)


def test_pass_is_signed_and_expires(monkeypatch):
    p = tgapp.make_pass("abc123")
    assert tgapp.check_pass(p) == "abc123"
    device, expires, sig = p.split(".")
    assert tgapp.check_pass(f"someone.{expires}.{sig}") is None              # another device, same signature
    assert tgapp.check_pass(f"{device}.{int(expires) + 999}.{sig}") is None  # stretched expiry
    assert tgapp.check_pass(p, now=time.time() + (tgapp.PASS_HOURS + 1) * 3600) is None
    assert tgapp.check_pass("garbage") is None and tgapp.check_pass("") is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999:other-bot")
    assert tgapp.check_pass(p) is None                                       # key comes from the bot token
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert tgapp.make_pass("abc123") is None                                 # no token: Mini App is off


def test_live_photo_with_gps_counts_as_exact(make_client):
    client, engine, _ = setup(make_client)
    r = app_report(client, tgapp.make_pass("dev-app"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["relevant"] == "accept"
    assert engine.alert(body["alert_id"])["status"] == "open"   # exact place + live photo: goes on its own
    rep = client.get("/reports", params={"role": "inspector"}).json()[0]
    assert rep["channel"] == "telegram" and rep["loc_source"] == "gps" and rep["capture"] == "live"
    assert rep["flags"] == []
    assert engine.db.one("SELECT device_id FROM reports WHERE id = ?", (body["report_id"],))["device_id"] == "dev-app"


def test_rough_location_and_file_dialog_are_flagged(make_client):
    client, engine, _ = setup(make_client)
    rough = app_report(client, tgapp.make_pass("dev-1"), accuracy=900, seed=2).json()
    assert engine.alert(rough["alert_id"])["status"] == "watch"  # wifi / cell-tower fix alone does not dispatch
    unknown = app_report(client, tgapp.make_pass("dev-2"), accuracy=None, seed=3, lat=56.9700, lon=24.1500).json()
    picked = app_report(client, tgapp.make_pass("dev-3"), capture="picker", seed=4, lat=56.9500, lon=24.1000)
    assert picked.status_code == 201
    reps = {r["id"]: r for r in client.get("/reports", params={"role": "inspector"}).json()}
    assert reps[rough["report_id"]]["loc_source"] == "coarse" and reps[rough["report_id"]]["flags"] == ["coarse_location"]
    assert reps[unknown["report_id"]]["loc_source"] == "coarse"
    assert reps[picked.json()["report_id"]]["flags"] == ["picked_photo"]
    assert picked.json()["relevant"] == "review"  # the file dialog may offer the gallery: inspector first


def test_pin_moved_a_few_metres_is_kept_with_the_phone_fix(make_client):
    """The preview map lets the resident move the pin up to PIN_MOVE_M (10 m) from the phone's fix."""
    client, engine, _ = setup(make_client)
    m_lat = 1 / 111_320  # one metre north, in degrees
    fix = (56.9600, 24.1300)
    moved = app_report(client, tgapp.make_pass("dev-pin"), lat=fix[0] + 7 * m_lat, lon=fix[1], gps=fix)
    assert moved.status_code == 201, moved.text
    rep = {r["id"]: r for r in client.get("/reports", params={"role": "inspector"}).json()}[moved.json()["report_id"]]
    assert rep["flags"] == ["moved_pin"] and 6.5 <= rep["pin_moved_m"] <= 7.5
    assert (rep["gps_lat"], rep["gps_lon"]) == fix and rep["lat"] == pytest.approx(fix[0] + 7 * m_lat)
    assert engine.alert(moved.json()["alert_id"])["status"] == "open"  # a small move does not hold the report back
    # the pin where the phone put it: no flag, and nothing else changes
    same = app_report(client, tgapp.make_pass("dev-pin2"), seed=5, lat=56.9700, lon=24.1500, gps=(56.9700, 24.1500))
    rep2 = {r["id"]: r for r in client.get("/reports", params={"role": "inspector"}).json()}[same.json()["report_id"]]
    assert rep2["flags"] == [] and rep2["pin_moved_m"] == 0
    # the contractor never gets the phone's raw fix
    assert "gps_lat" not in client.get("/reports/ticket/" + same.json()["ticket"]).json()


def test_pin_moved_too_far_or_half_a_fix_is_refused(make_client):
    client, _, _ = setup(make_client)
    m_lat = 1 / 111_320
    far = app_report(client, tgapp.make_pass("dev-far"), lat=56.9600 + 25 * m_lat, lon=24.1300, gps=(56.9600, 24.1300))
    assert far.status_code == 422 and far.json()["detail"]["code"] == "moved_too_far"
    half = app_report(client, tgapp.make_pass("dev-half"), gps=(56.9600, None))
    assert half.status_code == 422 and half.json()["detail"]["code"] == "bad_fix"
    assert client.get("/reports", params={"role": "inspector"}).json() == []  # nothing was stored


def test_bad_or_missing_pass_is_refused(make_client):
    client, _, _ = setup(make_client)
    assert app_report(client, "dev-x.9999999999.00000000000000000000000000000000").status_code == 403
    assert app_report(client, tgapp.make_pass("dev-x"), capture="gallery").status_code == 422
    assert client.post("/reports/app", data={"lat": 56.96, "lon": 24.13},
                       files={"photo": ("c.jpg", photo(1), "image/jpeg")}).status_code == 422


def test_public_tunnel_reaches_only_the_mini_app(make_client):
    client, _, _ = setup(make_client)
    for path in ("/inspector", "/contractor", "/report", "/alerts", "/reports", "/meta", "/docs", "/export.csv",
                 "/demo/clock", "/media/x.jpg", "/static/x.jpg"):
        assert client.get(path, headers=TUNNEL).status_code == 404, path
    assert client.post("/admin/reset", headers=TUNNEL).status_code == 404
    assert client.post("/reports", data={"lat": 56.96, "lon": 24.13, "device_id": "spoofed"},
                       files={"photo": ("p.jpg", photo(9), "image/jpeg")}, headers=TUNNEL).status_code == 404
    assert client.get("/tg", headers=TUNNEL).status_code == 200
    assert client.get("/assets/js/tg.js", headers=TUNNEL).status_code == 200
    assert client.get("/health", headers=TUNNEL).status_code == 200
    assert client.get("/inspector").status_code == 200              # on this machine everything still works


def test_tunnel_request_is_never_trusted_by_address(make_client, monkeypatch):
    """Through the tunnel every request arrives from 127.0.0.1; it must not get the local trust."""
    client, engine, _ = setup(make_client)
    guard = client.app.state.guard
    monkeypatch.setattr(guard.cfg, "trusted_hosts", {"testclient"})  # TestClient's address counts as local
    monkeypatch.setattr(tgapp, "PUBLIC_PATHS", tgapp.PUBLIC_PATHS | {"/reports"})  # open the gate to probe
    r = client.post("/reports", data={"lat": 56.96, "lon": 24.13, "device_id": "spoofed"},
                    files={"photo": ("p.jpg", photo(9), "image/jpeg")}, headers=TUNNEL)
    assert r.status_code == 201
    dev = engine.db.one("SELECT device_id FROM reports WHERE id = ?", (r.json()["report_id"],))["device_id"]
    assert dev != "spoofed"
    r = client.post("/reports", data={"lat": 56.97, "lon": 24.14, "device_id": "bot-dev"},
                    files={"photo": ("p.jpg", photo(10), "image/jpeg")})
    dev = engine.db.one("SELECT device_id FROM reports WHERE id = ?", (r.json()["report_id"],))["device_id"]
    assert dev == "bot-dev"                                           # the local bot is still trusted


# ---------------------------------------------------------------- bot in Mini App mode
def make_app_bot(client, tmp_path):
    fake = FakeTelegram()
    tg = Telegram("TOKEN", "http://tg.test", client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    return LanternBot(tg, client, State(tmp_path / "bot_state.json"), "https://lantern.example/"), fake


def last_markup(fake):
    return [p.get("reply_markup") for m, p in fake.sent if m == "sendMessage"][-1]


def test_bot_offers_the_app_and_follows_its_ticket(make_client, tmp_path):
    client, engine, _ = setup(make_client)
    bot, fake = make_app_bot(client, tmp_path)
    chat = 4242
    bot.handle_update(fake.msg(chat, text="/start"))
    bot.handle_update(fake.cb(chat, "lang:en"))
    button = last_markup(fake)["keyboard"][0][0]
    assert "Report a sidewalk" in button["text"]
    url = button["web_app"]["url"]
    assert url.startswith("https://lantern.example/tg?t=") and "&lang=en" in url
    pass_ = url.split("t=")[1].split("&")[0]
    assert tgapp.check_pass(pass_) == bot.device_id(chat)

    # a photo sent in the chat is not taken any more: it could be old or from the gallery
    bot.handle_update(fake.msg(chat, photo=[{"file_id": "big", "width": 1280, "height": 960}]))
    assert "can be old" in fake.texts(chat)[-1]
    assert engine.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 0

    # the app sends the report, then hands the ticket back to the bot
    ticket = app_report(client, pass_).json()["ticket"]
    bot.handle_update(fake.msg(chat, web_app_data={"data": json.dumps({"ticket": ticket}), "button_text": "x"}))
    assert ticket in fake.texts(chat)[-1]
    assert [x["ticket"] for x in bot.state.chat(chat)["tickets"]] == [ticket]
    bot.handle_update(fake.msg(chat, web_app_data={"data": json.dumps({"ticket": ticket})}))   # twice: once
    bot.handle_update(fake.msg(chat, web_app_data={"data": json.dumps({"ticket": "NOPE2345"})}))  # unknown
    bot.handle_update(fake.msg(chat, web_app_data={"data": "not json"}))
    assert len(bot.state.chat(chat)["tickets"]) == 1


def test_rejected_photo_gets_no_ticket(make_client):
    client, engine, verdicts = setup(make_client)
    verdicts["camera.jpg"] = "reject"
    body = app_report(client, tgapp.make_pass("dev-r")).json()
    assert body["relevant"] == "reject" and body["ticket"] is None and body["alert_id"] is None
    row = engine.db.one("SELECT ticket FROM reports WHERE id = ?", (body["report_id"],))
    assert client.get(f"/reports/ticket/{row['ticket']}").status_code == 404   # internal ref only
    verdicts["web.jpg"] = "reject"
    web = client.post("/reports", data={"lat": 56.96, "lon": 24.13},
                      files={"photo": ("web.jpg", photo(77), "image/jpeg")}).json()
    assert web["ticket"] is None                                                # the web form too


def test_bot_buttons_menu_and_description(make_client, tmp_path):
    client, _, _ = setup(make_client)
    bot, fake = make_app_bot(client, tmp_path)
    chat = 5151
    bot.handle_update(fake.msg(chat, text="hello"))          # first contact without /start
    texts = fake.texts(chat)
    assert "Lantern" in texts[-2] and "📸" in texts[-1]       # welcome, then how to start
    rows = last_markup(fake)["keyboard"]
    assert "web_app" in rows[0][0] and [b["text"] for b in rows[1]] == ["📋 Mani pieteikumi", "🌐 Valoda", "❓ Palīdzība"]
    bot.handle_update(fake.msg(chat, text="📋 Mani pieteikumi"))  # the button works like /status
    assert "Tev vēl nav pieteikumu" in fake.texts(chat)[-1]
    bot.handle_update(fake.msg(chat, text="❓ Palīdzība"))
    assert "Kā ziņot" in fake.texts(chat)[-1]
    bot.handle_update(fake.msg(chat, text="🌐 Valoda"))
    assert "Choose a language" in fake.texts(chat)[-1]

    fake.sent.clear()
    bot.setup_profile()
    sent = [(m, p.get("language_code")) for m, p in fake.sent]
    for method in ("setMyCommands", "setMyDescription", "setMyShortDescription"):
        assert {code for m, code in sent if m == method} == {None, "lv", "en", "ru"}
    en = next(p for m, p in fake.sent if m == "setMyCommands" and p.get("language_code") == "en")
    assert [c["command"] for c in en["commands"]] == ["start", "status", "lang", "help"]


def test_chat_mode_has_the_buttons_too(make_client, tmp_path):
    client, _, _ = setup(make_client)
    fake = FakeTelegram()
    tg = Telegram("TOKEN", "http://tg.test", client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    bot = LanternBot(tg, client, State(tmp_path / "s.json"))      # no WEBAPP_URL: photos in the chat
    bot.handle_update(fake.msg(77, text="/start"))
    bot.handle_update(fake.cb(77, "lang:en"))
    rows = last_markup(fake)["keyboard"]
    assert len(rows) == 1 and rows[0][0]["text"] == "📋 My reports"
    assert "Send one photo" in fake.texts(77)[-1]


# ---------------------------------------------------------------- private bot
def test_private_bot_answers_only_allowed_people(make_client, tmp_path):
    client, engine, _ = setup(make_client)
    fake = FakeTelegram()
    tg = Telegram("TOKEN", "http://tg.test", client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    bot = LanternBot(tg, client, State(tmp_path / "s.json"), "https://lantern.example", allowed={1001})
    stranger, owner = 2002, 1001

    for update in (fake.msg(stranger, text="/start"), fake.msg(stranger, text="hello"),
                   fake.msg(stranger, photo=[{"file_id": "p", "width": 9, "height": 9}]),
                   fake.msg(stranger, web_app_data={"data": json.dumps({"ticket": "ABCDEFGH"})})):
        bot.handle_update(update)
    texts = fake.texts(stranger)
    assert len(texts) == 4 and all("private" in x for x in texts)
    assert all("web_app" not in json.dumps(p.get("reply_markup")) for m, p in fake.sent)  # no pass for them
    bot.handle_update(fake.cb(stranger, "lang:en"))
    assert fake.sent[-1][0] == "answerCallbackQuery"
    assert str(stranger) not in bot.state.data["chats"]                                  # nothing stored
    assert engine.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 0

    bot.handle_update(fake.msg(owner, text="/start"))
    bot.handle_update(fake.cb(owner, "lang:en"))
    assert "web_app" in last_markup(fake)["keyboard"][0][0]                              # owner gets the app

    fake.sent.clear()
    bot.setup_profile()
    methods = [m for m, p in fake.sent]
    assert methods.count("deleteMyCommands") == 4                       # strangers see no command menu
    scoped = [p for m, p in fake.sent if m == "setMyCommands"]
    assert scoped and all(p["scope"] == {"type": "chat", "chat_id": owner} for p in scoped)
    about = [p["description"] for m, p in fake.sent if m == "setMyDescription"]
    assert all("private" in d or "privāts" in d or "приватный" in d for d in about)


def test_public_bot_when_no_allowlist(make_client, tmp_path):
    client, _, _ = setup(make_client)
    bot, fake = make_app_bot(client, tmp_path)
    bot.handle_update(fake.msg(31337, text="/start"))
    assert "private" not in fake.texts(31337)[-1]
