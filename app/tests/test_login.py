"""Login: strangers cannot use the app (and so the paid AI check) without the team password."""
import json

import pytest

from app import auth
from app.bot.telegram_bot import LanternBot, State
from app.tests.test_bot import FakeTelegram, Telegram, httpx
from app.tests.test_trust import photo, setup

PW = "correct-horse-7"
TUNNEL = {"cf-connecting-ip": "203.0.113.9"}


@pytest.fixture(autouse=True)
def team_password(monkeypatch):
    monkeypatch.setenv("LANTERN_PASSWORD", PW)
    monkeypatch.setenv("LANTERN_USER", "lantern")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test-token")
    auth._fails.clear()


def remote(client, monkeypatch):
    """Pretend the test client is another computer (not a trusted local machine caller)."""
    monkeypatch.setattr(client.app.state.guard.cfg, "trusted_hosts", {"127.0.0.1"})


def test_pages_need_login(make_client):
    client, _, _ = setup(make_client)
    for path in ("/inspector", "/contractor", "/report", "/docs", "/alerts/1/evidence"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login?next="), path
    assert "Password" in client.get("/login").text
    assert client.get("/health").status_code == 200 and client.get("/tg").status_code == 200


def test_api_needs_login_from_other_computers(make_client, monkeypatch):
    client, _, _ = setup(make_client)
    remote(client, monkeypatch)
    assert client.get("/alerts").status_code == 401
    r = client.post("/reports", data={"lat": 56.96, "lon": 24.13}, files={"photo": ("p.jpg", photo(1), "image/jpeg")})
    assert r.status_code == 401                                         # no free AI checks
    assert client.get("/alerts", headers=TUNNEL).status_code == 401


def test_local_machines_still_work_without_login(make_client):
    """The bot, the camera worker and the demo script run on this computer: no cookie needed."""
    client, _, _ = setup(make_client)
    assert client.get("/alerts").status_code == 200
    r = client.post("/reports", data={"lat": 56.96, "lon": 24.13, "device_id": "bot-1"},
                    files={"photo": ("p.jpg", photo(2), "image/jpeg")})
    assert r.status_code == 201


def test_login_logout_and_wrong_password(make_client, monkeypatch):
    client, _, _ = setup(make_client)
    remote(client, monkeypatch)
    bad = client.post("/login", data={"username": "lantern", "password": "nope", "next": "/inspector"})
    assert bad.status_code == 401 and "Wrong username or password" in bad.text
    ok = client.post("/login", data={"username": "Lantern", "password": PW, "next": "/inspector"}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/inspector"
    assert client.get("/inspector").status_code == 200
    assert client.get("/alerts").status_code == 200
    assert client.get("/meta").json()["login"] is True
    client.get("/logout")
    assert client.get("/alerts").status_code == 401


def test_logged_in_through_the_public_link(make_client):
    client, _, _ = setup(make_client)
    client.base_url = "https://testserver"          # the public link is https: the cookie is https-only there
    assert client.get("/inspector", headers=TUNNEL, follow_redirects=False).status_code == 303
    client.post("/login", data={"username": "lantern", "password": PW, "next": "/inspector"}, headers=TUNNEL)
    assert client.get("/inspector", headers=TUNNEL, follow_redirects=False).status_code == 200
    # still never "trusted": a logged-in remote user cannot name their own device id
    r = client.post("/reports", data={"lat": 56.96, "lon": 24.13, "device_id": "spoofed"},
                    files={"photo": ("p.jpg", photo(3), "image/jpeg")}, headers=TUNNEL)
    assert r.status_code == 201
    dev = client.app.state.db.one("SELECT device_id FROM reports WHERE id = ?", (r.json()["report_id"],))["device_id"]
    assert dev != "spoofed"


def test_session_cannot_be_forged_and_password_change_logs_out(monkeypatch):
    s = auth.make_session()
    assert auth.valid_session(s)
    name, exp, sig = s.split(".")
    assert not auth.valid_session(f"{name}.{int(exp) + 99999}.{sig}")
    assert not auth.valid_session("lantern.9999999999.0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("LANTERN_PASSWORD", "new-password")
    assert not auth.valid_session(s)


def test_too_many_wrong_passwords(make_client, monkeypatch):
    client, _, _ = setup(make_client)
    for _ in range(auth.MAX_FAILS):
        client.post("/login", data={"username": "lantern", "password": "x"})
    r = client.post("/login", data={"username": "lantern", "password": PW})
    assert r.status_code == 429                                         # even the right one waits now


def test_safe_redirect_after_login():
    assert auth.safe_next("//evil.example/x") == "/inspector"
    assert auth.safe_next("https://evil.example") == "/inspector"
    assert auth.safe_next("/contractor?contractor=A") == "/contractor?contractor=A"


# ---------------------------------------------------------------- bot login
def login_bot(client, tmp_path, allowed=()):
    fake = FakeTelegram()
    tg = Telegram("TOKEN", "http://tg.test", client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    return LanternBot(tg, client, State(tmp_path / "s.json"), "https://lantern.example", set(allowed), PW, "DNH"), fake


def test_bot_asks_login_then_password(make_client, tmp_path):
    client, _, _ = setup(make_client)
    bot, fake = login_bot(client, tmp_path)
    friend = 3003

    bot.handle_update(fake.msg(friend, text="/start"))
    assert "Enter your login" in fake.texts(friend)[-1]
    assert [p for m, p in fake.sent if m == "sendMessage"][-1]["reply_markup"] == {"remove_keyboard": True}
    bot.handle_update(fake.msg(friend, text="dnh"))                      # login is not case-sensitive
    assert "Enter your password" in fake.texts(friend)[-1]
    bot.handle_update(fake.msg(friend, text="wrong"))
    assert "Wrong login or password" in fake.texts(friend)[-1] and "Enter your login" in fake.texts(friend)[-1]
    assert [m for m, p in fake.sent].count("deleteMessage") == 2         # login and password are not left in the chat
    assert str(friend) not in bot.state.data["chats"]                    # nothing stored before a login

    bot.handle_update(fake.msg(friend, text="DNH"))
    bot.handle_update(fake.msg(friend, text=PW))
    assert any("logged in" in x for x in fake.texts(friend))
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["allowed_users"] == [friend]
    bot.handle_update(fake.cb(friend, "lang:en"))
    assert "web_app" in json.dumps([p.get("reply_markup") for m, p in fake.sent if m == "sendMessage"][-1])

    bot.handle_update(fake.msg(friend, text="/logout"))
    assert friend not in bot.state.data["allowed_users"]
    bot.handle_update(fake.msg(friend, text="hello"))
    assert "Enter your login" in fake.texts(friend)[-1]                  # has to log in again


def test_bot_login_speaks_their_language_and_wrong_user_fails(make_client, tmp_path):
    client, _, _ = setup(make_client)
    bot, fake = login_bot(client, tmp_path)
    upd = fake.msg(5005, text="/start")
    upd["message"]["from"]["language_code"] = "lv"
    bot.handle_update(upd)
    assert "Ieraksti lietotājvārdu" in fake.texts(5005)[-1]
    bot.handle_update(fake.msg(5005, text="someone"))
    bot.handle_update(fake.msg(5005, text=PW))                           # right password, wrong login
    assert 5005 not in (bot.state.data.get("allowed_users") or [])


def test_bot_login_tries_are_limited(make_client, tmp_path):
    client, _, _ = setup(make_client)
    bot, fake = login_bot(client, tmp_path)
    bot.handle_update(fake.msg(4004, text="/start"))
    for _ in range(5):
        bot.handle_update(fake.msg(4004, text="DNH"))
        bot.handle_update(fake.msg(4004, text="guess"))
    bot.handle_update(fake.msg(4004, text="DNH"))
    bot.handle_update(fake.msg(4004, text=PW))
    assert "Too many tries" in fake.texts(4004)[-1]
    assert 4004 not in (bot.state.data.get("allowed_users") or [])


def test_mini_app_pass_dies_with_a_new_password(monkeypatch):
    from app import tgapp
    p = tgapp.make_pass("dev-1")
    assert tgapp.check_pass(p) == "dev-1"
    monkeypatch.setenv("LANTERN_PASSWORD", "changed")
    assert tgapp.check_pass(p) is None
