"""Street sections (app/segments.py): the council sees a piece of street, not only dots."""
import json

from app.segments import Sidewalks, sections

# a straight 200 m block along Kaļķu iela-ish, and a parallel sidewalk 10 m north of it
STREET = [[24.1100, 56.9500], [24.1133, 56.9500]]
SIDEWALK = [[24.1100, 56.95009], [24.1133, 56.95009]]


def walks(with_sidewalk=False):
    feats = [{"type": "Feature", "properties": {"id": "s1", "name": "Test iela", "kind": "street"},
              "geometry": {"type": "LineString", "coordinates": STREET}}]
    if with_sidewalk:
        feats.append({"type": "Feature", "properties": {"id": "w1", "name": "Test iela", "kind": "sidewalk"},
                      "geometry": {"type": "LineString", "coordinates": SIDEWALK}})
    return Sidewalks(feats)


def alert(i, lat, lon, zone=None, level="medium", status="open"):
    return {"id": i, "lat": lat, "lon": lon, "zone_id": zone, "urgency_level": level, "status": status}


def test_snapping_prefers_the_mapped_sidewalk():
    w = walks(with_sidewalk=True)
    assert w.nearest(56.95006, 24.1110)["id"] == "w1"       # 3 m from the sidewalk, 7 m from the street
    assert w.nearest(56.95001, 24.1110)["id"] == "w1"       # sidewalk within 15 m wins
    assert w.nearest(56.9510, 24.1110) is None              # 100 m away: no block


def test_camera_lights_a_block_one_resident_does_not():
    w = walks()
    one = sections([alert(1, 56.95005, 24.1110)], {1: {"dev-a"}}, w)
    assert one == []                                        # a single complaint stays a dot
    cam = sections([alert(2, 56.95005, 24.1120, zone="cam:sidewalk", level="high")], {}, w)
    assert len(cam) == 1 and cam[0]["camera"] and cam[0]["name"] == "Test iela" and cam[0]["urgency_level"] == "high"
    assert 190 <= cam[0]["length_m"] <= 210


def test_two_residents_on_one_block_light_it_in_the_worst_colour():
    w = walks()
    alerts = [alert(1, 56.95005, 24.1105, level="low"), alert(2, 56.94996, 24.1125, level="medium"),
              alert(3, 56.9550, 24.1200, level="high")]      # far away, not on the block
    s = sections(alerts, {1: {"dev-a"}, 2: {"dev-b"}, 3: {"dev-c"}}, w)
    assert len(s) == 1 and s[0]["alert_ids"] == [1, 2] and s[0]["residents"] == 2
    assert s[0]["urgency_level"] == "medium" and not s[0]["camera"]
    same = sections(alerts[:2], {1: {"dev-a"}, 2: {"dev-a"}}, w)
    assert same == []                                       # one person, two dots: still one vote


def test_reopened_wins_and_fallback_without_street_data():
    w = walks()
    s = sections([alert(1, 56.95005, 24.1105, zone="c:z", level="high"),
                  alert(2, 56.95005, 24.1115, level="low", status="reopened")], {}, w)
    assert s[0]["status"] == "reopened"
    pts = [alert(1, 56.9500, 24.1100), alert(2, 56.9500, 24.1110), alert(3, 56.9500, 24.1105)]
    c = sections(pts, {1: {"a"}, 2: {"b"}, 3: {"c"}}, None)  # no OSM file: join dots within 80 m
    assert len(c) == 1 and c[0]["source"] == "cluster"
    assert [p[1] for p in c[0]["coords"]] in ([24.1100, 24.1105, 24.1110], [24.1110, 24.1105, 24.1100])


def test_sections_endpoint(make_client, tmp_path, monkeypatch, mock_dir):
    from app.main import settings
    f = tmp_path / "walks.geojson"
    crossing = [[24.10495, 56.94980], [24.10545, 56.94980]]   # through the mock crossing zone
    f.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": "x1", "name": "Demo iela", "kind": "sidewalk"},
         "geometry": {"type": "LineString", "coordinates": crossing}}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "sidewalks_file", f)
    client, engine, clock, _ = make_client()
    from app.timeutil import parse_ts
    clock.set(parse_ts("2026-11-25T07:00:00Z"))
    client.post("/snowfalls", json={"start": "2026-11-24T22:00:00Z", "end": "2026-11-25T01:00:00Z"})
    r = client.post("/signals", json={"camera_id": "mock_cam_1", "zone_id": "mock_cam_1:crossing", "lat": 56.9498,
                                      "lon": 24.1052, "timestamp": "2026-11-25T07:00:00Z", "hazard_class": "blocked",
                                      "blocked_share": 0.8, "confidence": 0.86})
    al = r.json()["alert_id"]
    body = client.get("/sections").json()
    assert body["source"] == "osm" and body["sections"][0]["alert_ids"] == [al]
    assert body["sections"][0]["name"] == "Demo iela"
    assert client.get("/sections", params={"role": "contractor"}).status_code == 403


def _f(fid, coords, name="A iela", kind="street"):
    return {"type": "Feature", "properties": {"id": fid, "name": name, "kind": kind},
            "geometry": {"type": "LineString", "coordinates": coords}}


def test_pieces_are_glued_junction_to_junction():
    from app.osm_sidewalks import merge_chains
    # A iela in three pieces (cut where a dropped crosswalk touched it), B iela crossing at the far end
    feats = [_f("a1", [[24.1000, 56.95], [24.1005, 56.95]]), _f("a3", [[24.1015, 56.95], [24.1010, 56.95]]),
             _f("a2", [[24.1005, 56.95], [24.1010, 56.95]]),
             _f("b1", [[24.1015, 56.9495], [24.1015, 56.95]], name="B iela"),
             _f("b2", [[24.1015, 56.95], [24.1015, 56.9505]], name="B iela")]
    out = merge_chains(feats)
    a = [f for f in out if f["properties"]["name"] == "A iela"]
    assert len(a) == 1 and len(a[0]["geometry"]["coordinates"]) == 4      # one block, in order
    assert sorted(c[0] for c in a[0]["geometry"]["coordinates"]) == [24.1000, 24.1005, 24.1010, 24.1015]
    assert len([f for f in out if f["properties"]["name"] == "B iela"]) == 2   # a real junction (3 ends) stays


def test_short_section_grows_along_the_same_street():
    # 30 m stub of A iela at a junction; A iela goes on straight, C iela turns off
    w = Sidewalks([_f("s", [[24.1000, 56.95], [24.1005, 56.95]]), _f("n", [[24.1005, 56.95], [24.1015, 56.95]]),
                   _f("c", [[24.1005, 56.95], [24.1005, 56.951]], name="C iela")])
    s = sections([alert(1, 56.95003, 24.1002, zone="cam:z")], {}, w)
    assert s[0]["block_m"] < 40 and s[0]["length_m"] >= 80                  # painted as a street, not a dot
    assert all(p[0] == 56.95 for p in s[0]["coords"])                        # it went on along A iela


# a ~65 x 55 m square with the street running past its south edge
SQUARE = [[24.1100, 56.9502], [24.1111, 56.9502], [24.1111, 56.9507], [24.1100, 56.9507], [24.1100, 56.9502]]


def test_alert_inside_a_square_paints_the_whole_square():
    feats = [{"type": "Feature", "properties": {"id": "s1", "name": "Test iela", "kind": "street"},
              "geometry": {"type": "LineString", "coordinates": STREET}},
             {"type": "Feature", "properties": {"id": "w9", "name": "Test laukums", "kind": "square"},
              "geometry": {"type": "Polygon", "coordinates": [SQUARE]}}]
    w = Sidewalks(feats)
    assert w.nearest(56.95045, 24.1105)["id"] == "w9"        # in the middle of the square
    assert w.nearest(56.95001, 24.1105)["id"] == "s1"        # on the street, outside it
    s = sections([alert(1, 56.95045, 24.1105, zone="cam:sq", level="high")], {}, w)
    assert len(s) == 1 and s[0]["shape"] == "area" and s[0]["kind"] == "square"
    assert s[0]["name"] == "Test laukums" and 3000 <= s[0]["area_m2"] <= 4500
    assert s[0]["coords"][0] == [56.9502, 24.1100]          # ring in lat, lon for Leaflet
    line = sections([alert(2, 56.95001, 24.1120, zone="cam:st")], {}, w)
    assert line[0]["shape"] == "line"


def test_square_outlines_leave_the_lines_and_unnamed_squares_get_a_name():
    from app.osm_sidewalks import with_squares
    lines = [_f("w5-1", [[24.1101, 56.9503], [24.1105, 56.9503]], name="Iekšā iela"),   # inside the square
             _f("w7", SQUARE[:2], name="Malas iela")]                                     # the square's own outline
    sq = {"type": "Feature", "properties": {"id": "w7", "name": None, "kind": "square"},
          "geometry": {"type": "Polygon", "coordinates": [SQUARE]}}
    out = with_squares(lines, [sq], {7})
    assert [f["properties"]["id"] for f in out] == ["w5-1", "w7"]
    assert out[1]["properties"]["name"] == "Iekšā iela"
