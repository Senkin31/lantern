"""Anti-fake rules: a fake place, a picture of a screen or a sender with false alarms never sends the
contractor on its own: the inspector looks first. Honest reports go through as before."""
import io
import random

from PIL import Image

from app.timeutil import parse_ts


def photo(seed: int) -> bytes:
    rnd = random.Random(seed)
    im = Image.new("RGB", (32, 24))
    im.putdata([tuple(rnd.randrange(256) for _ in range(3)) for _ in range(32 * 24)])
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


def setup(make_client):
    client, engine, clock, verdicts = make_client()
    clock.set(parse_ts("2026-11-25T12:00:00Z"))
    client.post("/snowfalls", json={"end": "2026-11-25T05:00:00Z"})   # deadline 08:00 Riga has passed
    return client, engine, verdicts


def send(client, device, lat, lon, seed, source=None, name="p.jpg"):
    data = {"lat": lat, "lon": lon, "device_id": device}
    if source:
        data["location_source"] = source
    r = client.post("/reports", data=data, files={"photo": (name, photo(seed), "image/jpeg")})
    assert r.status_code == 201, r.text
    return r.json()


def test_a_picked_or_typed_place_alone_does_not_send_the_contractor(make_client):
    client, engine, _ = setup(make_client)
    typed = send(client, "dev-a", 56.9600, 24.1300, 1, source="typed")
    a = engine.alert(typed["alert_id"])
    assert typed["relevant"] == "accept" and a["status"] == "watch"          # waits for the inspector
    rep = client.get("/reports", params={"role": "inspector"}).json()[0]
    assert rep["loc_source"] == "typed" and rep["flags"] == ["approx_location"]
    # a second person at the same place: two independent people -> the contractor goes
    send(client, "dev-b", 56.96002, 24.13002, 2, source="pin")
    assert engine.alert(typed["alert_id"])["status"] == "open"
    # one report located by the phone's GPS is enough on its own
    gps = send(client, "dev-c", 56.9700, 24.1400, 3, source="gps")
    assert engine.alert(gps["alert_id"])["status"] == "open"
    assert client.post("/reports", data={"lat": 56.97, "lon": 24.14, "location_source": "teleport"},
                       files={"photo": ("p.jpg", photo(4), "image/jpeg")}).status_code == 422


def test_screenshots_and_webcam_frames_go_to_the_inspector(make_client):
    client, engine, verdicts = setup(make_client)
    verdicts["shot.jpg"] = {"note": "Webcam screenshot of a snowy street"}
    verdicts["src.jpg"] = {"note": "snow on sidewalk", "source": "screen"}
    for i, name in enumerate(("shot.jpg", "src.jpg")):
        r = send(client, f"dev-s{i}", 56.9600 + i / 100, 24.1300, 10 + i, source="gps", name=name)
        assert r["relevant"] == "review" and engine.alert(r["alert_id"])["status"] == "watch"
    flags = [x["flags"] for x in client.get("/reports", params={"role": "inspector"}).json()]
    assert flags == [["not_street_photo"], ["not_street_photo"]]


def test_a_sender_with_false_alarms_goes_to_review(make_client):
    client, engine, _ = setup(make_client)
    for i in range(2):
        r = send(client, "dev-liar", 56.9500 + i / 100, 24.1000, 20 + i, source="gps")
        assert r["relevant"] == "accept"
        assert client.post(f"/alerts/{r['alert_id']}/status",
                           json={"status": "verified", "false_alarm": True, "role": "inspector"}).status_code == 200
    assert engine.false_alarms_of("dev-liar") == 2
    third = send(client, "dev-liar", 56.9800, 24.1000, 30, source="gps")
    assert third["relevant"] == "review" and engine.alert(third["alert_id"])["status"] == "watch"
    assert client.get("/reports", params={"role": "inspector"}).json()[0]["flags"] == ["false_alarm_sender"]
    honest = send(client, "dev-honest", 56.9900, 24.1000, 31, source="gps")   # others are not affected
    assert honest["relevant"] == "accept" and engine.alert(honest["alert_id"])["status"] == "open"


def test_kpi3_counts_only_exact_places(make_client):
    client, engine, _ = setup(make_client)
    send(client, "k1", 56.9600, 24.1300, 40, source="gps")
    send(client, "k2", 56.9700, 24.1300, 41, source="map")
    k = client.get("/stats/response", params={"role": "inspector"}).json()["kpi"]
    assert k["precise"] == 1 and k["signals_total"] == 2 and k["precise_share"] == 0.5
