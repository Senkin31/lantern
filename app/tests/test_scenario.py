"""The demo day 25.11 from brief v3 ("Моки v3 и сценарий демо"), replayed through the API
on a frozen clock. Times in the comments are Riga time (UTC+2); the API gets UTC."""
import io
import json
import random
from datetime import timedelta

from PIL import Image

from app.rules import clearing_deadline
from app.timeutil import parse_ts

CROSSING, SQUARE, SIDEWALK = "mock_cam_1:crossing", "mock_cam_2:square", "mock_cam_2:sidewalk"
AT_CROSSING = (56.9498, 24.1052)   # inside the crossing polygon of mock_cam_1
STOP = (56.9600, 24.1300)          # a bus stop without a camera


def photo(seed: int) -> bytes:
    rnd = random.Random(seed)
    im = Image.new("RGB", (64, 48))
    im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(64 * 48)])
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def riga(hhmm: str, day: int = 25):
    """'09:40' Riga on 25.11 -> UTC datetime."""
    h, m = map(int, hhmm.split(":"))
    return parse_ts(f"2026-11-{day:02d}T{h - 2:02d}:{m:02d}:00Z") if h >= 2 else \
        parse_ts(f"2026-11-{day - 1:02d}T{h + 22:02d}:{m:02d}:00Z")


def utc(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class Day:
    def __init__(self, client, engine, clock, verdicts):
        self.client, self.engine, self.clock, self.verdicts = client, engine, clock, verdicts

    def at(self, hhmm):
        """Move the clock forward to hhmm (Riga), ticking every 10 minutes like the background loop."""
        target = riga(hhmm)
        t = self.clock.now()
        while t < target:
            t = min(t + timedelta(minutes=10), target)
            self.clock.set(t)
            self.engine.tick()

    def signal(self, zone, cls, share, conf=0.85):
        cam = zone.split(":")[0]
        stamp = utc(self.clock.now()).replace("-", "").replace(":", "")[:13] + "Z"
        r = self.client.post("/signals", json={
            "source": "camera", "camera_id": cam, "zone_id": zone, "lat": 56.95, "lon": 24.11,
            "timestamp": utc(self.clock.now()), "hazard_class": cls, "blocked_share": share, "confidence": conf,
            "frame_url": f"http://localhost:8001/media/frames/{cam}/{stamp}.jpg",
            "crop_url": f"/static/crops/{cam}/{stamp}_{zone.split(':')[1]}.jpg"})
        assert r.status_code == 201, r.text
        return r.json()["alert_id"]

    def report(self, device, where, passable, seed, name="p.jpg", place="crossing", **extra):
        r = self.client.post("/reports", data={"lat": where[0], "lon": where[1], "passable": passable,
                                               "device_id": device, "place_type": place,
                                               "timestamp": utc(self.clock.now()), **extra},
                             files={"photo": (name, photo(seed), "image/jpeg")})
        assert r.status_code == 201, r.text
        return r.json()

    def alert(self, alert_id, role="inspector", **kw):
        return self.client.get(f"/alerts/{alert_id}", params={"role": role, **kw}).json()


def test_deadline_rule_riga_time():
    d = lambda end, seen=None: clearing_deadline(parse_ts(end) if end else None, parse_ts(seen) if seen else None)
    assert d("2026-11-25T01:00:00Z") == riga("08:00")               # ended 03:00 -> 08:00
    assert d("2026-11-25T12:00:00Z") == riga("22:00")               # ended 14:00 -> 22:00
    assert d("2026-11-25T05:59:00Z") == riga("08:00")               # 07:59 -> 08:00
    assert d("2026-11-25T06:00:00Z") == riga("22:00")               # 08:00 sharp -> 22:00
    assert d("2026-11-25T21:30:00Z") == riga("08:00", day=26)       # 23:30 -> 08:00 next day
    assert d(None, "2026-11-25T07:00:00Z") == riga("08:00")         # unknown -> 08:00 of the day seen
    # summer time: Riga is UTC+3, 08:00 Riga = 05:00 UTC
    assert d("2026-07-01T02:00:00Z") == parse_ts("2026-07-01T05:00:00Z")


def test_demo_day_25_11(make_client, mock_dir):
    day = Day(*make_client())
    c = day.client
    day.clock.set(riga("07:00"))
    # 03:00 snowfall 1 ended (the script sends it at 07:00, at the start) -> deadline 08:00
    sf = c.post("/snowfalls", json={"start": utc(riga("23:00", day=24)), "end": utc(riga("03:00"))}).json()
    assert sf["deadline_at"] == utc(riga("08:00"))

    # 08:00 deadline passes; cameras are silent (dark)
    day.at("09:00")
    crossing = day.signal(CROSSING, "blocked", 0.8, 0.86)        # wall of snow on the crossing
    square = day.signal(SQUARE, "snow", 0.4, 0.8)                # partly cleared
    assert day.signal(SIDEWALK, "clear", 0.05, 0.9) is None       # clean -> no alert
    a = day.alert(crossing)
    assert a["status"] == "open" and a["severity"] == "act" and a["contractor_id"] == "A"
    assert [h["to_status"] for h in a["history"]] == ["open"]     # straight to open, no watch step
    assert a["deadline_at"] == utc(riga("08:00")) and a["notified_at"] == utc(riga("09:00"))
    assert a["fix_due_at"] == utc(riga("09:00", day=26))          # 24 h to fix
    s = day.alert(square)
    assert s["status"] == "open" and s["severity"] == "notice" and s["contractor_id"] == "B"

    day.at("09:40")  # "impassable" next to the crossing -> joins, high
    r1 = day.report("dev-1", AT_CROSSING, "no", 1)
    assert r1["alert_id"] == crossing and day.alert(crossing)["urgency_level"] == "high"

    day.at("10:15")  # a stop without a camera -> new alert, at most medium, on the check list
    r2 = day.report("dev-2", STOP, "no", 2, place="stop", registration_no="RD-2026/123")
    stop = day.alert(r2["alert_id"])
    assert r2["alert_id"] not in (crossing, square) and stop["urgency_level"] == "medium"
    assert stop["registration_nos"] == ["RD-2026/123"]
    today = c.get("/inspection/today").json()["alerts"]
    assert "no_camera" in next(x for x in today if x["id"] == stop["id"])["why"]

    day.at("11:00")  # off-topic photo -> /analyze reject, never an alert
    day.verdicts["cat.jpg"] = "reject"
    r3 = day.report("dev-3", AT_CROSSING, "no", 3, name="cat.jpg")
    assert r3["relevant"] == "reject" and r3["alert_id"] is None

    day.at("11:30")  # contractor A presses "done" on the crossing
    r = c.post(f"/alerts/{crossing}/status", json={"status": "done_reported", "role": "contractor", "contractor": "A"})
    assert r.status_code == 200 and r.json()["status"] == "done_reported"

    day.at("11:50")  # second complaint at the crossing, another phone -> +1 confirmation
    day.report("dev-4", AT_CROSSING, "partly", 4)
    assert day.alert(crossing)["report_count"] == 2

    day.at("12:00")  # crossing: snow still there -> reopened, flagged for the council
    day.signal(CROSSING, "snow", 0.7, 0.82)
    a = day.alert(crossing)
    assert a["status"] == "reopened" and a["flagged_for_council"] and a["reopened_count"] == 1

    day.at("13:30")  # square: clean, nobody pressed "done" -> verified anyway
    day.signal(SQUARE, "clear", 0.05, 0.9)
    assert day.alert(square)["status"] == "verified"

    day.at("14:00")  # snowfall 2 (13:00-14:00) -> new deadline 22:00; crossing clean -> verified in 5 h
    sf2 = c.post("/snowfalls", json={"start": utc(riga("13:00")), "end": utc(riga("14:00"))}).json()
    assert sf2["deadline_at"] == utc(riga("22:00"))
    day.signal(CROSSING, "clear", 0.03, 0.91)
    a = day.alert(crossing)
    assert a["status"] == "verified" and a["response_hours"] == 5 and not a["overdue"]

    day.at("14:30")  # sidewalk: snow after snowfall 2 -> watch, the contractor does not see it
    sidewalk = day.signal(SIDEWALK, "snow", 0.4, 0.8)
    w = day.alert(sidewalk)
    assert w["status"] == "watch" and w["deadline_at"] == utc(riga("22:00"))
    contractor_ids = {x["id"] for x in c.get("/alerts", params={"role": "contractor", "contractor": "B"}).json()["alerts"]}
    assert sidewalk not in contractor_ids and square in contractor_ids

    day.at("15:30")  # sidewalk clean before 22:00 -> cleared_in_time
    day.signal(SIDEWALK, "clear", 0.02, 0.9)
    assert day.alert(sidewalk)["status"] == "cleared_in_time"
    day.at("23:00")  # nothing reopens after the deadline: it is closed
    assert day.alert(sidewalk)["status"] == "cleared_in_time"

    # --- response stats per contractor: average, share within 24 h, reopened
    st = {x["id"]: x for x in c.get("/stats/response").json()["by_contractor"]}
    assert st["A"]["avg_response_hours"] == 5 and st["A"]["share_within"] == 1 and st["A"]["reopened_times"] == 1
    assert st["B"]["avg_response_hours"] == 4.5

    # --- evidence package: inspector only; frames after the deadline with Riga time, no device ids
    ev = c.get(f"/alerts/{crossing}/evidence", params={"format": "json"}).json()
    labels = [f["label"] for f in ev["frames"]]
    assert labels == ["first_snow_after_deadline", "last_snow", "clear"]
    assert ev["frames"][0]["riga_time"] == "25.11.2026 09:00" and ev["deadline"]["riga_time"] == "25.11.2026 08:00"
    assert len(ev["resident_photos"]) == 2 and "dev-1" not in json.dumps(ev)
    html = c.get(f"/alerts/{crossing}/evidence")
    assert html.status_code == 200 and "localhost:8001/media/frames" in html.text and "dev-1" not in html.text
    assert c.get(f"/alerts/{crossing}/evidence", params={"role": "contractor"}).status_code == 403

    # --- privacy: the contractor never gets full frames or the evidence link
    job = day.alert(crossing, role="contractor", contractor="A")
    dumped = json.dumps(job)

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)

    leaked = {k for k in keys(job) if "frame" in k or k in ("evidence", "evidence_url", "device")}
    assert not leaked, leaked
    assert "localhost:8001/media/frames" not in dumped and "dev-" not in dumped
    assert job["severity"] == "act" and job["fix_due_at"]


def test_overdue_and_severity_override(make_client, mock_dir):
    day = Day(*make_client())
    c = day.client
    day.clock.set(riga("09:00"))   # no snowfall known -> deadline 08:00 of today, already passed
    sq = day.signal(SQUARE, "snow", 0.4, 0.8)
    a = day.alert(sq)
    assert a["status"] == "open" and a["severity"] == "notice" and a["snowfall_id"] is None
    r = c.post(f"/alerts/{sq}/status", json={"severity": "act", "role": "inspector", "actor": "anna"})
    assert r.status_code == 200 and r.json()["severity"] == "act" and r.json()["severity_manual"] == "act"
    assert "severity notice -> act" in r.json()["history"][-1]["note"]
    assert c.post(f"/alerts/{sq}/status", json={"severity": "notice", "role": "contractor",
                                                "contractor": "B"}).status_code == 403
    day.signal(SQUARE, "snow", 0.35, 0.8)  # a new signal must not undo the inspector's choice
    assert day.alert(sq)["severity"] == "act"

    day.at("09:01")
    day.clock.set(riga("09:30", day=26))  # 24 h later, still not verified
    a = day.alert(sq)
    assert a["overdue"]
    today = c.get("/inspection/today").json()["alerts"]
    assert today[0]["id"] == sq and today[0]["why"][:2] == ["act", "overdue"]
    assert c.get("/stats/response").json()["by_contractor"][0]["overdue"] == 1


def test_two_zones_of_one_camera_make_an_act(make_client, mock_dir):
    day = Day(*make_client())
    day.clock.set(riga("09:00"))
    sq = day.signal(SQUARE, "snow", 0.4, 0.8)
    assert day.alert(sq)["severity"] == "notice"
    day.signal(SIDEWALK, "snow", 0.4, 0.8)   # neighbouring zone of mock_cam_2 also has snow
    assert day.alert(sq)["severity"] == "act"


def test_watch_waits_for_deadline_and_ongoing_snowfall(make_client, mock_dir):
    day = Day(*make_client())
    c = day.client
    day.clock.set(riga("06:00"))
    c.post("/snowfalls", json={"start": utc(riga("01:00")), "end": utc(riga("05:00"))})
    al = day.signal(SQUARE, "snow", 0.4, 0.8)
    assert day.alert(al)["status"] == "watch"
    assert al not in {x["id"] for x in c.get("/alerts", params={"role": "contractor", "contractor": "B"}).json()["alerts"]}
    day.at("07:00")
    c.post("/snowfalls", json={"start": utc(riga("07:00"))})   # it starts snowing again, end unknown
    day.at("09:00")
    assert day.alert(al)["status"] == "watch" and day.alert(al)["deadline_at"] is None
    c.post("/snowfalls", json={"start": utc(riga("07:00")), "end": utc(riga("09:00"))})  # ended 09:00 -> 22:00
    assert day.alert(al)["deadline_at"] == utc(riga("22:00"))
    day.at("22:10")  # background tick opens it after the deadline, no new signal needed
    a = day.alert(al)
    assert a["status"] == "open" and a["notified_at"] == utc(riga("22:00"))  # the tick right at 22:00
    assert a["notify_seconds"] == 0  # KPI 2: notified_at - max(detected_at, deadline_at)
    assert c.get(f"/alerts/{al}/evidence", params={"format": "json"}).json()["frames"] == []  # last frame 06:00


def test_partly_cleaned_stays_with_the_inspector(make_client, mock_dir):
    """Brief 1.1, model v2: snow with confidence < 0.5 = "partly cleaned", inspector only.
    What counts is the zone's latest frame: >= 0.5 opens after the deadline, < 0.5 does not."""
    day = Day(*make_client())
    c = day.client
    day.clock.set(riga("09:00"))
    c.post("/snowfalls", json={"start": utc(riga("01:00")), "end": utc(riga("03:00"))})  # deadline 08:00
    al = day.signal(SQUARE, "snow", 0.4, 0.35)                      # partly, after the deadline
    a = day.alert(al)
    assert a["status"] == "watch" and "partly" in a["inspector_flags"]
    contractor = lambda: {x["id"] for x in c.get("/alerts", params={"role": "contractor", "contractor": "B"}).json()["alerts"]}
    assert al not in contractor()
    assert al in {x["id"] for x in c.get("/inspection/today").json()["alerts"]}  # on the check list
    day.at("09:30")
    day.signal(SQUARE, "snow", 0.7, 0.8)                            # not cleaned at all -> open
    assert day.alert(al)["status"] == "open" and al in contractor()


def test_latest_frame_partly_keeps_watch(make_client, mock_dir):
    """Reliable snow early, but the zone's last frame before the deadline says "partly": no dispatch."""
    day2 = Day(*make_client())
    day2.clock.set(riga("06:00"))
    day2.client.post("/snowfalls", json={"start": utc(riga("01:00")), "end": utc(riga("03:00"))})
    b = day2.signal(CROSSING, "snow", 0.8, 0.85)
    day2.at("07:30")
    day2.signal(CROSSING, "snow", 0.3, 0.4)
    day2.at("08:30")
    assert day2.alert(b)["status"] == "watch" and "partly" in day2.alert(b)["inspector_flags"]


def test_inactive_camera_is_switched_off(make_client, tmp_path, monkeypatch):
    """Brief 1.1: cameras with "active": false (Lahti, Oulu) are not on the map and make no alerts."""
    import json as _json

    from app.main import settings
    cams = {"cameras": [
        {"camera_id": "on", "lat": 56.95, "lon": 24.11, "district": "demo-centre",
         "zones": [{"zone_id": "on:sidewalk", "label": "sidewalk"}]},
        {"camera_id": "off", "active": False, "lat": 56.96, "lon": 24.12, "district": "demo-centre",
         "zones": [{"zone_id": "off:road", "label": "sidewalk"}]},
    ]}
    f = tmp_path / "cameras.json"
    f.write_text(_json.dumps(cams), encoding="utf-8")
    monkeypatch.setattr(settings, "cameras_file", f)
    monkeypatch.setattr(settings, "cameras_fallback", tmp_path / "none.json")
    day = Day(*make_client())
    ids = {cam["camera_id"] for cam in day.client.get("/meta").json()["cameras"]}
    assert ids == {"on"}
    day.clock.set(riga("09:00"))
    assert day.signal("off:road", "snow", 0.9, 0.9) is None
    assert day.signal("on:sidewalk", "snow", 0.9, 0.9) is not None


def test_kpi_block_and_false_alarm(make_client, mock_dir):
    """KPI 1 = jobs closed as false alarm per camera hour; KPI 2 = notified <= 15 min; KPI 3 = exact location."""
    day = Day(*make_client())
    c = day.client
    day.clock.set(riga("09:00"))
    c.post("/snowfalls", json={"start": utc(riga("01:00")), "end": utc(riga("03:00"))})   # deadline 08:00
    sq = day.signal(SQUARE, "snow", 0.4, 0.8)            # open at 09:00, notified at once
    day.at("11:00")
    day.signal(SIDEWALK, "clear", 0.0, 0.9)              # mock_cam_2 worked 09:00-11:00 -> 2 camera hours
    assert c.post(f"/alerts/{sq}/status", json={"status": "verified", "false_alarm": True,
                                               "role": "contractor", "contractor": "B"}).status_code == 403
    r = c.post(f"/alerts/{sq}/status", json={"status": "verified", "false_alarm": True, "role": "inspector"})
    assert r.status_code == 200 and r.json()["status"] == "verified" and r.json()["false_alarm"] is True
    st = c.get("/stats/response").json()
    k = st["kpi"]
    assert k["false_alarm_jobs"] == 1 and k["camera_hours"] == 2.0 and k["false_alarms_per_hour"] == 0.5
    assert k["notify_total"] == 0                        # a false alarm is not the contractor's job
    assert k["precise_share"] == 1.0 and k["signals_total"] == 2
    assert all(row["opened"] == 0 for row in st["by_contractor"]) or not st["by_contractor"]


def test_demo_clock_runs_fast(make_client):
    import time
    client, engine, clock, _ = make_client()
    clock.set(None)
    r = client.post("/demo/clock", json={"scenario_start": "2026-11-25T05:00:00Z", "factor": 600})
    assert r.status_code == 200 and r.json()["clock"]["mode"] == "demo"
    t0 = parse_ts(client.get("/demo/clock").json()["now"])
    time.sleep(1.1)
    t1 = parse_ts(client.get("/demo/clock").json()["now"])
    assert 500 <= (t1 - t0).total_seconds() <= 1500      # ~600 scenario seconds per real second
    assert client.post("/demo/clock", json={}).json()["clock"]["mode"] == "real"
    clock.reset()


def test_one_device_one_vote_and_review(make_client, mock_dir):
    client, engine, clock, verdicts = make_client()
    clock.set(parse_ts("2026-11-25T12:00:00Z"))
    client.post("/snowfalls", json={"end": "2026-11-25T05:00:00Z"})
    photos = {p.name: p.read_bytes() for p in (mock_dir / "photos").glob("report_*.jpg")}

    def report(device, passable="no", name="a.jpg", lat=56.9600, lon=24.1300, photo="report_snow_1.jpg"):
        r = client.post("/reports", data={"lat": lat, "lon": lon, "passable": passable, "device_id": device,
                                          "place_type": "sidewalk"},
                        files={"photo": (name, photos[photo], "image/jpeg")})
        assert r.status_code == 201, r.text
        return r.json()

    r1 = report("dev-x")
    r2 = report("dev-x", photo="report_snow_2.jpg")
    assert r2["alert_id"] == r1["alert_id"] and r2["duplicate"]
    a = client.get(f"/alerts/{r1['alert_id']}").json()
    assert a["report_count"] == 1 and a["status"] == "open"  # deadline long passed -> straight to contractor
    verdicts["unsure.jpg"] = "review"
    r3 = report("dev-y", name="unsure.jpg", photo="report_stop.jpg")
    a = client.get(f"/alerts/{r3['alert_id']}").json()
    assert a["report_count"] == 1 and "review_report" in a["inspector_flags"]
    m = client.post(f"/reports/{r3['report_id']}/moderate", json={"decision": "accept"})
    assert m.status_code == 200
    a = client.get(f"/alerts/{r3['alert_id']}").json()
    assert a["report_count"] == 2 and "review_report" not in a["inspector_flags"]
    assert a["urgency_score"] == 3 + 1  # passable=no + one confirmation

    t = client.get(f"/reports/ticket/{r1['ticket']}").json()
    assert t["state"] == "accepted" and t["alert_status"] == "open" and t["other_reports"] == 1


def test_validation(make_client, mock_dir):
    client, *_ = make_client()
    bad = client.post("/signals", json={"camera_id": "x", "zone_id": "x:z", "lat": 1, "lon": 1,
                                        "timestamp": "yesterday", "hazard_class": "snow", "blocked_share": 0.2,
                                        "confidence": 0.9})
    assert bad.status_code == 422
    bad = client.post("/reports", data={"lat": 56.9, "lon": 24.1, "passable": "maybe"},
                      files={"photo": ("a.jpg", b"123", "image/jpeg")})
    assert bad.status_code == 422
    bad = client.post("/reports", data={"lat": 56.9, "lon": 24.1, "passable": "no"},
                      files={"photo": ("a.txt", b"123", "text/plain")})
    assert bad.status_code == 415
    clear = client.post("/signals", json={"camera_id": "mock_cam_1", "zone_id": CROSSING, "lat": 1, "lon": 1,
                                          "timestamp": "2026-11-25T10:00:00Z", "hazard_class": "clear",
                                          "blocked_share": 0, "confidence": 0.9})
    assert clear.status_code == 201 and clear.json() == {"alert_id": None}
    assert client.post("/snowfalls", json={}).status_code == 422
    assert client.post("/snowfalls", json={"start": "2026-11-25T10:00:00Z",
                                           "end": "2026-11-25T09:00:00Z"}).status_code == 422
    exp = client.get("/export.geojson").json()
    assert exp["type"] == "FeatureCollection"
