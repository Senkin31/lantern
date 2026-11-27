"""The sidewalk network (app/segments.py network / network_status): every stretch of sidewalk is a thin
line coloured by its latest alert, like Riga's pGIS map - blue none, red registered, yellow started,
green finished - and every alert's dot sits on its line."""
import json

from app.segments import Sidewalks, network_status
from app.tests.test_sections import SIDEWALK, STREET, alert
from app.tests.test_trust import send, setup

LONELY = [[24.1200, 56.9550], [24.1233, 56.9550]]   # a street with no sidewalk mapped beside it


def feats():
    return [{"type": "Feature", "properties": {"id": "s1", "name": "Test iela", "kind": "street"},
             "geometry": {"type": "LineString", "coordinates": STREET}},
            {"type": "Feature", "properties": {"id": "w1", "name": "Test iela", "kind": "sidewalk"},
             "geometry": {"type": "LineString", "coordinates": SIDEWALK}},
            {"type": "Feature", "properties": {"id": "s2", "name": "Cita iela", "kind": "street"},
             "geometry": {"type": "LineString", "coordinates": LONELY}}]


def test_a_street_with_its_sidewalk_mapped_is_drawn_once():
    w = Sidewalks(feats())
    assert w.drawn_ids() == {"w1", "s2"}                    # not the centre line s1 between them
    assert [b["id"] for b in w.network()] == ["w1", "s2"]
    # the drawn set is the snappable set: a point in the road goes to the sidewalk line, not the hidden centre
    assert w.nearest(56.94990, 24.1110, 25, drawn_only=True)["id"] == "w1"
    assert w.nearest(56.94990, 24.1110, 25)["id"] == "s1"   # the old /sections snapping is unchanged


def test_lines_inside_a_square_are_not_drawn():
    """An alert inside a square colours the whole square, so a path across it would stay blue forever."""
    square = [[24.1210, 56.9545], [24.1225, 56.9545], [24.1225, 56.9555], [24.1210, 56.9555], [24.1210, 56.9545]]
    path = [[24.1212, 56.9550], [24.1223, 56.9550]]
    w = Sidewalks(feats() + [
        {"type": "Feature", "properties": {"id": "q1", "name": "Test laukums", "kind": "square"},
         "geometry": {"type": "Polygon", "coordinates": [square]}},
        {"type": "Feature", "properties": {"id": "w2", "name": None, "kind": "sidewalk"},
         "geometry": {"type": "LineString", "coordinates": path}}])
    assert "w2" not in w.drawn_ids() and {"w1", "s2"} <= w.drawn_ids()
    assert [b["id"] for b in w.network()][-1] == "q1"
    st = network_status([alert(1, 56.9550, 24.1218, status="open")], w)
    assert st["blocks"]["q1"]["state"] == "registered"


def test_status_colours_follow_the_latest_task_like_pgis():
    w = Sidewalks(feats())
    st = network_status([alert(1, 56.95005, 24.1105, status="open")], w)
    assert st["blocks"]["w1"]["state"] == "registered" and st["blocks"]["w1"]["alert_ids"] == [1]
    assert st["points"][1] == [56.95009, 24.1105]           # the dot sits on the sidewalk line
    assert "s2" not in st["blocks"]                           # no task: blue

    for status, state in (("watch", "started"), ("done_reported", "started"), ("reopened", "registered"),
                          ("verified", "finished"), ("cleared_in_time", "finished")):
        assert network_status([alert(1, 56.95005, 24.1105, status=status)], w)["blocks"]["w1"]["state"] == state


def test_an_open_problem_is_never_hidden_by_a_finished_one():
    w = Sidewalks(feats())
    old_open = dict(alert(1, 56.95005, 24.1105, status="open"), updated_at="2026-11-25T08:00:00Z")
    new_done = dict(alert(2, 56.95005, 24.1120, status="verified"), updated_at="2026-11-25T10:00:00Z")
    b = network_status([new_done, old_open], w)["blocks"]["w1"]
    assert b["state"] == "registered" and b["alert_id"] == 1 and b["alert_ids"] == [1, 2]
    # finished work earlier, a new problem later: red again; two finished: the latest one
    old_done = dict(alert(3, 56.95005, 24.1105, status="verified"), updated_at="2026-11-24T08:00:00Z")
    assert network_status([old_done, new_done], w)["blocks"]["w1"]["alert_id"] == 2
    watch = dict(alert(4, 56.95005, 24.1110, status="watch"), updated_at="2026-11-25T11:00:00Z")
    assert network_status([old_open, watch], w)["blocks"]["w1"]["state"] == "registered"
    assert network_status([], None) == {"blocks": {}, "points": {}}


def test_map_endpoints(make_client, tmp_path, monkeypatch):
    from app.main import settings
    f = tmp_path / "walks.geojson"
    f.write_text(json.dumps({"type": "FeatureCollection", "features": feats()}), encoding="utf-8")
    monkeypatch.setattr(settings, "sidewalks_file", f)
    client, _, _ = setup(make_client)

    r = client.get("/map/network", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers["content-encoding"] == "gzip"
    body = r.json()
    assert [b["id"] for b in body["blocks"]] == ["w1", "s2"] and "OpenStreetMap" in body["attribution"]
    assert body["blocks"][0]["coords"][0] == [56.95009, 24.11]
    assert client.get("/map/network", headers={"Accept-Encoding": "identity"}).json() == body

    rep = send(client, "dev-1", 56.95005, 24.1105, 1)
    st = client.get("/map/status").json()
    assert st["blocks"]["w1"]["alert_ids"] == [rep["alert_id"]]
    assert st["blocks"]["w1"]["state"] in ("registered", "started")
    assert st["points"][str(rep["alert_id"])] == [56.95009, 24.1105]
    assert client.get("/map/status", params={"role": "contractor"}).status_code == 400
    assert client.get("/map/status", params={"role": "contractor", "contractor": "A"}).status_code == 200
