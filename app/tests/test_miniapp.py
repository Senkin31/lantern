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


def app_report(client, pass_, *, accuracy=12, capture="live", seed=1, lat=56.9600, lon=24.1300, headers=TUNNEL):
    data = {"lat": lat, "lon": lon, "capture": capture, "tg_pass": pass_}
    if accuracy is not None:
        data["accuracy"] = accuracy
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
