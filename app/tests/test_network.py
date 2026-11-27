"""The sidewalk network (app/segments.py network / network_status): every stretch of sidewalk is a thin
line coloured by its latest alert, like Riga's pGIS map - blue none, red registered, yellow started,
green finished - and every alert's dot sits on its line."""
import json
import math

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


def _pgis_line(fid, coords):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"id": fid, "obj": fid, "name": "Test iela", "kind": "sidewalk", "source": "pgis"}}


def _len_m(coords):
    from app.pgis_sidewalks import _xy
    return sum(math.dist(_xy(coords[i]), _xy(coords[i + 1])) for i in range(len(coords) - 1))


def test_a_long_pgis_line_is_cut_into_blocks_at_its_cross_streets():
    from app.pgis_sidewalks import cut_sections
    main = _pgis_line("p1", [[24.1100, 56.95009], [24.1130, 56.95009], [24.1180, 56.95009]])   # ~486 m, east-west
    street = [[24.1125, 56.9498], [24.1125, 56.9504]]              # an OSM street crossing it at ~152 m
    side_a = _pgis_line("p2", [[24.11490, 56.95016], [24.11490, 56.95100]])   # the two sidewalks of a side
    side_b = _pgis_line("p3", [[24.11510, 56.95016], [24.11510, 56.95100]])   # street, ending 8 m from it
    across = _pgis_line("p4", [[24.1140, 56.94991], [24.1165, 56.94991]])     # the other side, 20 m away
    out = cut_sections([main, side_a, side_b, across], streets=[street])
    secs = [f for f in out if f["properties"]["pgis_obj"] == "p1"]
    assert [f["properties"]["id"] for f in secs] == ["p1.1", "p1.2", "p1.3"]   # one cut per cross street
    assert [f["properties"]["obj"] for f in secs] == ["p1.1", "p1.2", "p1.3"]  # each block is its own object
    lens = [_len_m(f["geometry"]["coordinates"]) for f in secs]
    assert abs(lens[0] - 152) < 2                      # on the street
    assert abs(lens[0] + lens[1] - 304) < 2            # between the two sidewalks of the side street
    # lossless: the blocks together are exactly the pGIS line
    joined = secs[0]["geometry"]["coordinates"] + [c for f in secs[1:] for c in f["geometry"]["coordinates"][1:]]
    assert [c for c in joined if c in main["geometry"]["coordinates"]] == main["geometry"]["coordinates"]
    assert abs(sum(lens) - _len_m(main["geometry"]["coordinates"])) < 0.01
    # the other side's sidewalk runs alongside (a gap end, not a cross street) and the short lines have no crossing
    assert [f["properties"]["id"] for f in out if f["properties"]["pgis_obj"] != "p1"] == ["p2", "p3", "p4"]


def test_every_section_is_named_after_the_street_it_runs_along():
    """The city's data names many lines only by the district ("Centrs") or not at all, some misspelt or
    with a route number. Each section takes the name of the street alongside (OSM)."""
    from app.pgis_sidewalks import name_sections

    def side(fid, lat, name, lon0=24.1100, lon1=24.1130):   # an east-west sidewalk, ~180 m
        f = _pgis_line(fid, [[lon0, lat], [lon1, lat]])
        f["properties"].update(name=name, district="Centrs")
        return f

    streets = [["Baznīcas iela", "road", [[24.1095, 56.95000], [24.1135, 56.95000]]],
               ["Krišjāņa Barona iela", "road", [[24.1095, 56.95020], [24.1135, 56.95020]]],   # 22 m north
               ["Ģertrūdes iela", "road", [[24.1115, 56.9490], [24.1115, 56.9510]]],          # across both
               ["Parka taka", "path", [[24.1095, 56.95008], [24.1135, 56.95008]]]]
    feats = [side("district", 56.95007, "Centrs"),                      # 8 m from Baznīcas, 14 m from Barona
             side("none", 56.95007, None),
             side("misspelt", 56.95007, "Baznicas iela (Marsruts Nr:1)"),
             side("city", 56.95013, "Baznīcas iela"),                   # nearer Barona, but the city says Baznīcas
             side("far", 56.96000, "Kupriču iela"),                     # no street mapped near it
             side("far_district", 56.96000, "Centrs")]
    stats = name_sections(feats, streets)
    got = {f["properties"]["id"]: (f["properties"]["name"], f["properties"]["name_src"]) for f in feats}
    assert got == {"district": ("Baznīcas iela", "osm"), "none": ("Baznīcas iela", "osm"),
                   "misspelt": ("Baznīcas iela", "osm"),
                   "city": ("Baznīcas iela", "osm"),                     # the city's own street wins when alongside
                   "far": ("Kupriču iela", "pgis"),                      # nothing alongside: the city's name stays
                   "far_district": (None, "none")}                       # a district is not a street name
    assert stats == {"osm": 4, "pgis": 1, "none": 1}
    assert feats[0]["properties"]["pgis_name"] == "Centrs"               # the city's name is kept
    assert feats[1]["properties"]["pgis_name"] is None
    # a street beats a named path alongside, and the cross street (not alongside) never names it
    assert all(n != "Parka taka" and n != "Ģertrūdes iela" for n, _ in got.values())
    # running it again on its own output gives the same names
    again = {f["properties"]["id"]: f["properties"]["name"] for f in feats}
    name_sections(feats, streets)
    assert {f["properties"]["id"]: f["properties"]["name"] for f in feats} == again


def test_a_wide_junction_is_one_cut_and_the_street_wins():
    from app.pgis_sidewalks import _cut_offsets
    # a crosswalk 35 m after a sidewalk end (two groups, closer than 40 m): one cut, on the street
    assert _cut_offsets([(100.0, False), (135.0, True)], 300.0, 200.0) == [135.0]
    assert _cut_offsets([(100.0, True), (135.0, True)], 300.0, 200.0) == [100.0]
    assert _cut_offsets([(10.0, True), (100.0, True), (290.0, True)], 300.0, 200.0) == [100.0]   # none at the ends


def test_a_stretch_with_no_crossing_is_still_cut_evenly_and_an_alert_colours_only_its_block():
    from app.pgis_sidewalks import MAX_SECTION_M, cut_sections
    line = _pgis_line("p5", [[24.1100, 56.95009], [24.1199, 56.95009]])        # ~601 m, nothing crosses it
    secs = cut_sections([line])
    lens = [_len_m(f["geometry"]["coordinates"]) for f in secs]
    assert len(secs) == math.ceil(sum(lens) / MAX_SECTION_M) and max(lens) - min(lens) < 0.5
    st = network_status([alert(1, 56.95005, 24.1105, status="open")], Sidewalks(secs))
    assert list(st["blocks"]) == ["p5.1"]                         # not the whole 600 m


def test_a_maintained_line_inside_an_old_riga_zone_still_takes_its_alert():
    zone = [[24.1095, 56.9495], [24.1160, 56.9495], [24.1160, 56.9510], [24.1095, 56.9510], [24.1095, 56.9495]]
    line = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[24.1100, 56.95009], [24.1120, 56.95009]]},
            "properties": {"id": "p7", "obj": "p7", "kind": "sidewalk", "source": "pgis"}}
    area = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [zone]},
            "properties": {"id": "p9", "obj": "p9", "kind": "square", "source": "pgis", "name": "Vecrīgas zonējums"}}
    w = Sidewalks([line, area])
    assert w.nearest(56.95005, 24.1105, drawn_only=True)["id"] == "p7"       # 5 m from the line: the line
    assert w.nearest(56.95040, 24.1150, drawn_only=True)["id"] == "p9"       # nowhere near it: the zone


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
