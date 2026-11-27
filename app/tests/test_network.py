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


# ---------------------------------------------------------------- Riga's pGIS objects (app/pgis_sidewalks.py)
def test_pgis_import_keeps_objects_gaps_and_names():
    from app.pgis_sidewalks import convert, fix_name, parse_wkt
    assert fix_name("BaloÅ¾u iela") == "Baložu iela"
    assert fix_name("MurjÄ\x81Å†u iela") == "Murjāņu iela"
    assert fix_name("Sergeja EizenÅ?teina iela") == "Sergeja Eizenšteina iela"
    assert fix_name("Brīvības iela") == "Brīvības iela"                  # a good name is left alone
    kind, parts = parse_wkt("MULTILINESTRING ((2683334 7749700, 2683434 7749800), (2683500 7749700, 2683600 7749800))")
    assert kind == "MULTILINESTRING" and len(parts) == 2 and parts[0][0] == [24.1047994, 56.9489909]
    feats = convert({"features": [{"id": 7, "name": "Imported line", "classId": 1,
                                   "geom": "MULTILINESTRING ((2683334 7749700, 2683434 7749800), (2683500 7749700, 2683600 7749800))"}]},
                    {"features": [{"id": 9, "name": "Imported polygon", "classId": 2,
                                   "geom": "POLYGON ((2683000 7749000, 2683100 7749000, 2683100 7749100, 2683000 7749000))"}]},
                    {1: "Centrs", 2: "Vecrīgas zonējums"})
    assert [f["properties"]["id"] for f in feats] == ["p7~1", "p7~2", "p9"]   # the gap stays a gap
    assert {f["properties"]["obj"] for f in feats[:2]} == {"p7"} and feats[0]["properties"]["name"] is None
    assert feats[0]["properties"]["district"] == "Centrs"
    assert feats[2]["properties"]["kind"] == "square" and feats[2]["properties"]["name"] == "Vecrīgas zonējums"


def test_an_alert_on_one_piece_colours_the_whole_pgis_object():
    piece = lambda fid, coords: {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                                 "properties": {"id": fid, "obj": "p7", "name": "Test iela", "kind": "sidewalk",
                                                "source": "pgis"}}
    w = Sidewalks([piece("p7~1", [[24.1100, 56.95009], [24.1120, 56.95009]]),
                   piece("p7~2", [[24.1130, 56.95009], [24.1150, 56.95009]])])   # 60 m gap between them
    st = network_status([alert(1, 56.95005, 24.1105, status="open")], w)
    assert set(st["blocks"]) == {"p7~1", "p7~2"} and st["blocks"]["p7~2"]["alert_ids"] == [1]
    assert {b["length_m"] for b in w.network()} == {round(w.blocks[0]["length_m"] + w.blocks[1]["length_m"])}
    # a report in the middle of the gap (30 m from both pieces) is on no maintained sidewalk: no colour
    assert network_status([alert(2, 56.95005, 24.1125, status="open")], w)["blocks"] == {}


def test_network_is_revalidated_with_an_etag(make_client, tmp_path, monkeypatch):
    from app.main import settings
    f = tmp_path / "walks.geojson"
    f.write_text(json.dumps({"type": "FeatureCollection", "attribution": "Ietves: test", "features": feats()}),
                 encoding="utf-8")
    monkeypatch.setattr(settings, "sidewalks_file", f)
    client, _, _ = setup(make_client)
    r = client.get("/map/network")
    assert r.json()["attribution"] == "Ietves: test" and r.headers["cache-control"] == "private, no-cache"
    assert client.get("/map/network", headers={"If-None-Match": r.headers["etag"]}).status_code == 304
