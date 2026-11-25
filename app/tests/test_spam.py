"""Spam protection (app/spam.py): one person must not be able to flood the city with reports."""
import io
import random
from datetime import timedelta

import pytest
from PIL import Image

from app import analyze as analyze_mod
from app.timeutil import parse_ts

PLACE = (56.9600, 24.1300)  # Riga, away from the mock cameras


def make_photo(seed: int) -> bytes:
    """A different random picture for every seed (different exact and perceptual hash)."""
    rnd = random.Random(seed)
    im = Image.new("RGB", (96, 72))
    im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(96 * 72)])
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture
def setup(make_client, monkeypatch):
    client, engine, clock, verdicts = make_client()
    clock.set(parse_ts("2026-11-25T12:00:00Z"))
    client.post("/settings", json={"snowfall_end": "2026-11-25T05:00:00Z", "hour_seconds": 3600})
    calls = []
    real = analyze_mod.analyze  # the conftest fake

    def counting(*a, **kw):
        calls.append(a[3])  # filename
        return real(*a, **kw)

    monkeypatch.setattr(analyze_mod, "analyze", counting)
    return client, clock, verdicts, calls


def send(client, device, photo, lat=PLACE[0], lon=PLACE[1], name="p.jpg", headers=None):
    data = {"lat": lat, "lon": lon, "passable": "no"}
    if device:
        data["device_id"] = device
    return client.post("/reports", data=data, files={"photo": (name, photo, "image/jpeg")}, headers=headers or {})


def test_99_pictures_of_one_place(setup):
    client, clock, verdicts, calls = setup
    codes = [send(client, "spammer", make_photo(i)).status_code for i in range(99)]
    assert codes[0] == 201
    # 1 real report + 5 repeats are stored, then the sender is muted; the other 93 are refused
    assert codes.count(201) == 6 and codes.count(429) == 93
    assert len(calls) == 1  # only the first photo went to /analyze
    first = client.get("/alerts").json()["alerts"]
    assert len(first) == 1 and first[0]["report_count"] == 1  # still one vote
    s = client.get("/spam").json()
    assert s["events"]["blocked"] >= 93 and s["events"]["duplicate_place"] == 5
    assert s["blocked"][0]["device_id"] == "spammer" and s["blocked"][0]["blocked_by"] == "system"
    # everyone else is unaffected
    assert send(client, "neighbour", make_photo(1000)).status_code == 201


def test_hourly_limit_for_different_places(setup):
    client, clock, *_ = setup
    for i in range(6):  # 6 different places, ~200 m apart: all legitimate
        assert send(client, "busy", make_photo(i), lat=56.95 + i * 0.002).status_code == 201
    r = send(client, "busy", make_photo(99), lat=56.99)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "device_hourly_limit"
    assert r.headers["Retry-After"] == "3600"
    clock.advance(hours=1, minutes=1)
    assert send(client, "busy", make_photo(100), lat=56.99).status_code == 201


def test_same_photo_from_another_phone_is_not_a_confirmation(setup):
    client, clock, verdicts, calls = setup
    photo = make_photo(7)
    a = send(client, "dev-a", photo).json()
    b = send(client, "dev-b", photo).json()
    assert b["same_photo"] and b["alert_id"] == a["alert_id"]
    alert = client.get(f"/alerts/{a['alert_id']}").json()
    assert alert["report_count"] == 1  # a forwarded photo does not raise urgency
    assert len(calls) == 1

    # a re-compressed, resized copy is caught too
    im = Image.open(io.BytesIO(photo)).resize((80, 60))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=60)
    c = send(client, "dev-c", buf.getvalue()).json()
    assert c["same_photo"]


def test_rejected_photos_mute_the_sender_and_inspector_can_unblock(setup):
    client, clock, verdicts, calls = setup
    for i in range(3):
        verdicts[f"junk{i}.jpg"] = "reject"
        assert send(client, "joker", make_photo(200 + i), lat=56.95 + i * 0.01, name=f"junk{i}.jpg").status_code == 201
    r = send(client, "joker", make_photo(300), lat=56.99)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "blocked"
    assert client.post("/devices/unblock", json={"device_id": "joker"}).status_code == 200
    assert send(client, "joker", make_photo(301), lat=56.99).status_code == 201


def test_inspector_blocks_a_sender(setup):
    client, *_ = setup
    rid = send(client, "troll", make_photo(400)).json()["report_id"]
    s = client.post(f"/reports/{rid}/block-sender", json={"hours": 48, "reason": "offensive photos"}).json()
    assert any(b["device_id"] == "troll" and b["reason"] == "offensive photos" for b in s["blocked"])
    assert send(client, "troll", make_photo(401), lat=56.99).status_code == 429


def test_outside_riga_is_refused(setup):
    client, *_ = setup
    r = send(client, "tourist", make_photo(500), lat=48.85, lon=2.35)  # Paris
    assert r.status_code == 422 and r.json()["detail"]["code"] == "outside_area"


def test_web_user_cannot_pick_device_id_and_ip_limit_applies(make_client, monkeypatch):
    from fastapi.testclient import TestClient
    client, engine, clock, _ = make_client()
    clock.set(parse_ts("2026-11-25T12:00:00Z"))
    web = TestClient(client.app, client=("10.1.2.3", 5555))  # not a trusted host
    ok = 0
    for i in range(40):
        web.cookies.clear()  # a spammer clearing cookies gets a new device id every time...
        r = send(web, f"fake-{i}", make_photo(600 + i), lat=56.95 + i * 0.002)
        ok += r.status_code == 201
        if r.status_code == 429:
            assert r.json()["detail"]["code"] == "ip_hourly_limit"  # ...but the IP limit still stops them
    assert ok == 30
    devices = {r["device"] for r in client.get("/reports?relevant=all").json()}
    assert not any(d.startswith("fake-") for d in devices)  # client-supplied ids ignored
