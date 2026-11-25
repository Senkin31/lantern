"""Replays mock/signals.json + mock/reports.json with their original timestamps and
checks the demo scenario from mock/README.md and the rules in brief v2."""
import json
from datetime import timedelta

from app.timeutil import parse_ts

ZONE1, SQUARE, SIDEWALK = "mock_cam_1:crossing", "mock_cam_2:square", "mock_cam_2:sidewalk"


def load_events(mock_dir):
    sig = json.loads((mock_dir / "signals.json").read_text(encoding="utf-8"))
    rep = json.loads((mock_dir / "reports.json").read_text(encoding="utf-8"))
    events = [("signal", s) for s in sig["signals"]] + [("report", r) for r in rep["reports"]]
    events.sort(key=lambda e: e[1]["timestamp"])
    return sig["scenario"], events


def send(client, mock_dir, kind, e):
    body = {k: v for k, v in e.items() if not k.startswith("_")}
    if kind == "signal":
        r = client.post("/signals", json=body)
    else:
        photo = mock_dir / body.pop("photo")
        r = client.post("/reports", data={k: str(v) for k, v in body.items()},
                        files={"photo": (photo.name, photo.read_bytes(), "image/jpeg")})
    assert r.status_code == 201, r.text
    return r.json()


def run_until(engine, clock, target, step=timedelta(minutes=10)):
    """Advance the frozen clock to target, ticking like the background loop does."""
    t = clock.now()
    while t < target:
        t = min(t + step, target)
        clock.set(t)
        engine.tick()


def zone_alerts(client, zone):
    alerts = client.get("/alerts", params={"role": "inspector"}).json()["alerts"]
    return [a for a in alerts if a["zone_id"] == zone]


def contractor_alerts(client, contractor):
    return client.get("/alerts", params={"role": "contractor", "contractor": contractor}).json()["alerts"]


def test_full_demo_day(make_client, mock_dir):
    client, engine, clock, verdicts = make_client()
    verdicts["report_irrelevant.jpg"] = "reject"
    scenario, events = load_events(mock_dir)
    clock.set(parse_ts(events[0][1]["timestamp"]) - timedelta(minutes=1))
    r = client.post("/settings", json={"snowfall_end": scenario["snowfall_end"], "hour_seconds": 3600,
                                       "clearing_hours": scenario["clearing_hours"]})
    assert r.status_code == 200 and r.json()["deadline"] == "2026-11-25T11:00:00Z"

    results = {}
    done_at = parse_ts("2026-11-25T13:30:00Z")
    done_sent = False
    snapshots = {}
    for kind, e in events:
        ts = parse_ts(e["timestamp"])
        if not done_sent and ts > done_at:
            run_until(engine, clock, done_at)
            snapshots["before_done"] = zone_alerts(client, ZONE1)[-1]
            aid = snapshots["before_done"]["id"]
            # the wrong contractor cannot close it
            bad = client.post(f"/alerts/{aid}/status", json={"status": "done_reported", "role": "contractor",
                                                             "contractor": "B"})
            assert bad.status_code == 409
            ok = client.post(f"/alerts/{aid}/status", json={"status": "done_reported", "role": "contractor",
                                                            "contractor": "A", "actor": "crew 1"})
            assert ok.status_code == 200, ok.text
            done_sent = True
        run_until(engine, clock, ts)
        results[(kind, e["timestamp"], e.get("zone_id") or e.get("device_id"))] = send(client, mock_dir, kind, e)
        if kind == "signal" and e["timestamp"] == "2026-11-25T10:00:00Z":
            # before the deadline everything is watch and the contractor sees nothing
            assert contractor_alerts(client, "A") == [] and contractor_alerts(client, "B") == []
            a1 = zone_alerts(client, ZONE1)[-1]
            assert a1["status"] == "watch"
            assert "possible_ice" not in a1["inspector_flags"]  # 06:00 snow replaced the 04:30 ice state
        if kind == "report" and e["device_id"] == "dev-001":
            a1 = zone_alerts(client, ZONE1)[-1]
            assert a1["report_count"] == 1
        if kind == "signal" and e["timestamp"] == "2026-11-25T11:30:00Z":
            a1 = zone_alerts(client, ZONE1)[-1]
            assert a1["status"] == "open" and a1["contractor_id"] == "A"
            assert a1["opened_at"] == "2026-11-25T11:00:00Z"
            ids_a = [a["id"] for a in contractor_alerts(client, "A")]
            assert a1["id"] in ids_a
        if kind == "signal" and e["timestamp"] == "2026-11-25T14:30:00Z":
            a1 = zone_alerts(client, ZONE1)[-1]
            assert a1["status"] == "reopened" and a1["reopened_count"] == 1 and a1["flagged_for_council"]
    run_until(engine, clock, parse_ts("2026-11-25T21:00:00Z"))

    # 04:30 possible_ice went straight to the inspector
    first = results[("signal", "2026-11-25T04:30:00Z", ZONE1)]
    assert first["alert_id"] is not None

    # mock_cam_1:crossing: watch -> open -> done_reported -> reopened -> verified
    a1 = zone_alerts(client, ZONE1)
    assert len(a1) == 1
    d1 = client.get(f"/alerts/{a1[0]['id']}", params={"role": "inspector"}).json()
    path = [h["to_status"] for h in d1["history"]]
    assert path == ["watch", "open", "done_reported", "reopened", "verified"], path
    assert d1["status"] == "verified" and d1["verified_at"] == "2026-11-25T17:00:00Z"
    assert d1["response_hours"] == 6.0  # 11:00 -> 17:00
    assert d1["urgency_level"] == "high"
    assert d1["report_count"] == 2  # two residents merged into the camera alert (<30 m)
    assert {r["passable"] for r in d1["reports"]} == {"no", "partly"}
    assert d1["before_frame_url"] and d1["after_frame_url"] and d1["before_frame_url"] != d1["after_frame_url"]

    # mock_cam_2:sidewalk cleared in time -> never dispatched
    side = zone_alerts(client, SIDEWALK)
    assert len(side) == 1 and side[0]["status"] == "verified" and side[0]["opened_at"] is None
    assert all(a["zone_id"] != SIDEWALK for a in contractor_alerts(client, "B"))

    # mock_cam_2:square: open for B, verified at 18:00; 20:30 night frame is a new inspector-only alert
    sq = zone_alerts(client, SQUARE)
    assert len(sq) == 2
    assert sq[0]["status"] == "verified" and sq[0]["contractor_id"] == "B" and sq[0]["opened_at"]
    assert sq[1]["status"] == "watch" and "low_confidence" in sq[1]["inspector_flags"]
    b_ids = [a["id"] for a in contractor_alerts(client, "B")]
    assert sq[0]["id"] in b_ids and sq[1]["id"] not in b_ids

    # bus-stop report: own alert, no camera, capped at medium, goes to B by nearest camera
    alerts = client.get("/alerts", params={"role": "inspector"}).json()["alerts"]
    stop = [a for a in alerts if a["zone_id"] is None]
    assert len(stop) == 1
    assert stop[0]["place_type"] == "stop" and stop[0]["urgency_level"] == "medium"
    assert stop[0]["district"] == "demo-north" and stop[0]["status"] == "open"
    assert stop[0]["urgency_score"] == 4  # "no" 3 + stop 1; one unconfirmed report never exceeds medium

    # irrelevant photo -> stored as reject, no alert
    rejected = client.get("/reports", params={"role": "inspector", "relevant": "reject"}).json()
    assert len(rejected) == 1 and rejected[0]["alert_id"] is None

    # privacy: the contractor's raw JSON never contains full frames or device ids
    for c in ("A", "B"):
        raw = client.get("/alerts", params={"role": "contractor", "contractor": c}).text
        assert "frame_url" not in raw and "/frames/" not in raw and "dev-00" not in raw
        for a in contractor_alerts(client, c):
            det = client.get(f"/alerts/{a['id']}", params={"role": "contractor", "contractor": c}).text
            assert "frame_url" not in det and "/frames/" not in det and "dev-00" not in det
    # and cannot open another district's alert
    assert client.get(f"/alerts/{a1[0]['id']}", params={"role": "contractor", "contractor": "B"}).status_code == 404

    # response stats
    st = client.get("/stats/response").json()
    by = {r["id"]: r for r in st["by_contractor"]}
    assert by["A"]["verified"] == 1 and by["A"]["reopened_times"] == 1
    assert by["A"]["avg_response_hours"] == 6.0
    assert by["B"]["opened"] == 2  # square + bus stop

    # open-data exports
    gj = client.get("/export.geojson").json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == len(alerts)
    assert "frame_url" not in json.dumps(gj)
    csv = client.get("/export.csv").text.splitlines()
    assert csv[0].startswith("id,status") and len(csv) == len(alerts) + 1


def test_one_device_one_vote_and_review(make_client, mock_dir):
    client, engine, clock, verdicts = make_client()
    clock.set(parse_ts("2026-11-25T12:00:00Z"))
    client.post("/settings", json={"snowfall_end": "2026-11-25T05:00:00Z", "hour_seconds": 3600})
    photo = (mock_dir / "photos" / "report_snow_1.jpg").read_bytes()

    def report(device, passable="no", name="a.jpg", lat=56.9600, lon=24.1300):
        r = client.post("/reports", data={"lat": lat, "lon": lon, "passable": passable, "device_id": device,
                                          "place_type": "sidewalk"},
                        files={"photo": (name, photo, "image/jpeg")})
        assert r.status_code == 201, r.text
        return r.json()

    r1 = report("dev-x")
    r2 = report("dev-x")
    assert r2["alert_id"] == r1["alert_id"] and r2["duplicate"]
    a = client.get(f"/alerts/{r1['alert_id']}").json()
    assert a["report_count"] == 1 and a["status"] == "open"  # deadline long passed -> straight to contractor
    verdicts["unsure.jpg"] = "review"
    r3 = report("dev-y", name="unsure.jpg")
    a = client.get(f"/alerts/{r3['alert_id']}").json()
    assert a["report_count"] == 1 and "review_report" in a["inspector_flags"]
    m = client.post(f"/reports/{r3['report_id']}/moderate", json={"decision": "accept"})
    assert m.status_code == 200
    a = client.get(f"/alerts/{r3['alert_id']}").json()
    assert a["report_count"] == 2 and "review_report" not in a["inspector_flags"]
    assert a["urgency_score"] == 3 + 1  # passable=no + one confirmation

    # ticket status for the resident
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
    clear = client.post("/signals", json={"camera_id": "mock_cam_1", "zone_id": ZONE1, "lat": 1, "lon": 1,
                                          "timestamp": "2026-11-25T10:00:00Z", "hazard_class": "clear",
                                          "blocked_share": 0, "confidence": 0.9})
    assert clear.status_code == 201 and clear.json() == {"alert_id": None}
