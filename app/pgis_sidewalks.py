"""Riga's real sidewalk maintenance map (pGIS, hagberg.pgis.lv) as our sidewalk file, 1:1.

    python -m app.pgis_sidewalks                  # -> data/pgis_sidewalks.geojson (git-ignored)
    python -m app.pgis_sidewalks --out other.geojson

The city's winter maintenance system shows exactly which sidewalks are maintained (categories 1-3,
season 24/25) and which are not: every maintained stretch is its own line object, one per side of
the street, with real gaps where nothing is maintained. The council named it the example to follow,
so the app can draw the same objects: the same area (all of Riga), the same lines, the same gaps.

The data belongs to Riga / the pGIS operator, not to us, so it is NOT committed to the public repo:
this script downloads it from the public map's own API (one request for lines, one for polygons, the
same requests the dashboard makes when it opens) into data/, which git ignores. When the file is there,
the app uses it instead of config/riga_sidewalks.geojson (OpenStreetMap, central Riga only).

Each object keeps its pGIS id (pgis_obj = "p<id>"); a MULTILINESTRING becomes one LineString per part.
The Old Riga zones ("Vecrīgas zonējums") are polygons there, so they are areas (kind=square) here.

Sections: a pGIS object can be 2 km of one street (Brīvības iela), so a red line says little about
where the problem is. Every line is cut into sections between crossings (cut_sections): where a street
meets it (OSM junctions, committed in config/), where another maintained sidewalk runs across it, and
evenly where a stretch is still longer than MAX_SECTION_M. Each section is its own object, so an alert
colours only its block. The cut is lossless: the sections together are exactly the pGIS line, with the
same gaps. --no-cut keeps the objects whole.
Uses only the standard library; the cutting downloads nothing.
"""
import argparse
import json
import math
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from .config import ROOT

API = "https://hagberg.pgis.lv/api/v1"
CITY = {"minx": 2555605, "miny": 7608663, "maxx": 2826192, "maxy": 7866317}  # all of Riga, EPSG:3857
# the layers the public dashboard switches on: 13553 left bank and 13532 right bank (season 24/25,
# "RD KK 1.; 2.; 3. kategorijas ietves 24/25"), 10261 the centre, 10606 the Old Riga zones
CLASSIFIERS = [13554, 13555, 13556, 13557, 13558, 13559, 13560, 13561, 13562, 13563, 13564, 13565, 13566, 13567,
               13568, 13533, 13534, 13535, 13536, 13537, 13538, 13539, 13540, 13541, 13542, 13543, 13544, 13545,
               13546, 13547, 13548, 13549, 13550, 13551, 13552, 10290, 10291, 10292, 10293, 10294, 10295, 10296,
               10297, 10298, 10299, 10300, 10301, 10606]
NO_NAME = {"imported line", "imported polygon", ""}
ATTRIBUTION = "Ietves: Rīgas valstspilsēta / pGIS (hagberg.pgis.lv)"
R = 6378137.0

# sections (cut_sections)
CUT_NEAR_M = 25.0      # a street junction or another sidewalk's end this close to the line cuts it there
CUT_ACROSS = 0.707     # ...another sidewalk only if it runs across the line (more than 45°), not alongside it
CUT_CLUSTER_M = 30.0   # cuts closer together than this are one crossing: cut once, in its middle
CUT_END_M = 20.0       # no cut this close to a line's own ends (no stubs)
CUT_MIN_M = 40.0       # nor this close to the cut before it (a wide junction's crosswalks are one crossing)
MAX_SECTION_M = 200.0  # a stretch with no known crossing is still cut, evenly, into pieces at most this long
CROSSINGS = ROOT / "config" / "riga_crossings.json"     # OSM street junctions + crosswalks, all of Riga
OSM_BLOCKS = ROOT / "config" / "riga_sidewalks.geojson"  # OSM blocks of the centre: 3+ street ends = a junction
_KY = 111320.0
_KX = _KY * math.cos(math.radians(56.95))
_G = 50.0  # grid cell, m


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{API}/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "sidewalk-map-script/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def layer_names() -> dict:
    """classId -> layer (district) name, e.g. 13562 -> "Imanta"."""
    req = urllib.request.Request(f"{API}/classifiers/layers", headers={"User-Agent": "sidewalk-map-script/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        tree = json.load(r)
    names = {}

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            if isinstance(n.get("id"), int) and n.get("id") in CLASSIFIERS and (n.get("name") or n.get("title")):
                names[n["id"]] = n.get("name") or n.get("title")
            for k, v in n.items():
                if k != "geomStyle" and isinstance(v, (list, dict)):
                    walk(v)
    walk(tree)
    return names


def to_lonlat(x: float, y: float) -> list:
    lon = x / R * 180 / math.pi
    lat = (2 * math.atan(math.exp(y / R)) - math.pi / 2) * 180 / math.pi
    return [round(lon, 7), round(lat, 7)]


def parse_wkt(wkt: str):
    """(type, parts): LINESTRING / MULTILINESTRING -> list of lines; POLYGON / MULTIPOLYGON -> list of
    outer rings. Coordinates are converted from EPSG:3857 to [lon, lat]."""
    kind, _, rest = wkt.strip().partition("(")
    kind = kind.strip().upper()
    body = "(" + rest

    def ring(text: str) -> list:
        return [to_lonlat(*map(float, p.split()[:2])) for p in text.strip(" ()").split(",") if p.strip()]
    if kind == "MULTIPOLYGON":     # each polygon's outer ring
        parts = [ring(re.split(r"\)\s*,\s*\(", p)[0]) for p in re.split(r"\)\)\s*,\s*\(\(", body)]
    else:
        parts = [ring(r) for r in re.split(r"\)\s*,\s*\(", body)]
        if kind == "POLYGON":
            parts = parts[:1]      # outer ring only
    return kind, [p for p in parts if len(p) >= 2]


# bytes their import lost or changed (a "?" left behind): best guess for the Latvian letter
LOST = {"Å?": "š", "Ä¨": "č", "Ä?": "Č", "ÅR": "Ū"}


def fix_name(s):
    """Some names were imported as UTF-8 read as Windows-1252 ("BaloÅ¾u iela" -> "Baložu iela",
    "MurjÄ\\x81Å†u iela" -> "Murjāņu iela"). Names that are fine are returned as they are."""
    if not s or not any(c in s for c in "ÃÄÅ"):
        return s
    out, i = bytearray(), 0
    while i < len(s):
        if s[i:i + 2] in LOST:
            out += LOST[s[i:i + 2]].encode("utf-8")
            i += 2
            continue
        ch = s[i]
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            out += bytes([ord(ch)]) if ord(ch) < 256 else ch.encode("utf-8")
        i += 1
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return s


def convert(lines: dict, polygons: dict, layers: dict) -> list:
    feats = []
    for f in lines.get("features", []) + polygons.get("features", []):
        kind, parts = parse_wkt(f["geom"])
        name = fix_name((f.get("name") or "").strip())
        name = None if name.lower() in NO_NAME else name
        district = layers.get(f.get("classId"))
        obj = f"p{f['id']}"
        area = kind in ("POLYGON", "MULTIPOLYGON")
        for k, part in enumerate(parts, 1):
            fid = obj if len(parts) == 1 else f"{obj}~{k}"
            props = {"id": fid, "obj": obj, "name": name or (district if area else None), "district": district,
                     "kind": "square" if area else "sidewalk", "source": "pgis", "class_id": f.get("classId")}
            if area:
                if part[0] != part[-1]:
                    part = part + [part[0]]
                geom = {"type": "Polygon", "coordinates": [part]}
            else:
                geom = {"type": "LineString", "coordinates": part}
            feats.append({"type": "Feature", "properties": props, "geometry": geom})
    return feats


def _xy(c) -> tuple:
    return ((c[0] - 24.0) * _KX, (c[1] - 56.95) * _KY)  # metres around Riga, good to a few cm here


def load_streets() -> tuple:
    """Where streets are, from committed OpenStreetMap files (reads files only, downloads nothing):
    crossing points [lon, lat] (config/riga_crossings.json: the street junctions and crosswalks of all of
    Riga, made by python -m app.osm_sidewalks --crossings; plus the ends shared by 3+ street blocks of the
    centre) and the street centre lines of the centre (config/riga_sidewalks.geojson), which cut a
    sidewalk where they run across it, even where the main road itself is not in the file."""
    pts, streets = [], []
    if CROSSINGS.is_file():
        pts += json.loads(CROSSINGS.read_text(encoding="utf-8")).get("points", [])
    if OSM_BLOCKS.is_file():
        ends = Counter()
        for f in json.loads(OSM_BLOCKS.read_text(encoding="utf-8")).get("features", []):
            if f["properties"].get("kind") == "street" and f["geometry"]["type"] == "LineString":
                c = f["geometry"]["coordinates"]
                streets.append(c)
                for e in (c[0], c[-1]):
                    ends[(round(e[0], 6), round(e[1], 6))] += 1
        pts += [list(p) for p, n in ends.items() if n >= 3]
    return pts, streets


def _unit(dx: float, dy: float) -> tuple:
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n else (0.0, 0.0)


def _end_dir(xy: list, cum: list, at_start: bool) -> tuple:
    """Which way a line runs where it ends (measured over its last ~10 m, outwards)."""
    if at_start:
        i = next((k for k in range(1, len(xy)) if cum[k] >= 10.0), len(xy) - 1)
        return _unit(xy[0][0] - xy[i][0], xy[0][1] - xy[i][1])
    i = next((k for k in range(len(xy) - 2, -1, -1) if cum[-1] - cum[k] >= 10.0), 0)
    return _unit(xy[-1][0] - xy[i][0], xy[-1][1] - xy[i][1])


def _cut_offsets(cuts: list, total: float, max_m: float) -> list:
    """Raw cuts (offset along the line, strong) -> the final cut positions. Cuts within CUT_CLUSTER_M of
    each other are one crossing, cut once: on the street if one is there (strong: OSM), else in the middle
    of the sidewalk ends. No cut near the line's ends; of two cuts closer than CUT_MIN_M, the one on a
    street stays (else the first). Then every part still longer than max_m is split evenly."""
    groups = []
    for c in sorted(cuts):
        if groups and c[0] - groups[-1][0][0] <= CUT_CLUSTER_M:
            groups[-1].append(c)
        else:
            groups.append([c])
    kept = []  # (offset, on a street)
    for g in groups:
        strong = [o for o, s in g if s]
        pick = strong or [o for o, _ in g]
        at = sum(pick) / len(pick)
        if not CUT_END_M <= at <= total - CUT_END_M:
            continue
        if kept and at - kept[-1][0] < CUT_MIN_M:
            if strong and not kept[-1][1]:
                kept[-1] = (at, True)
            continue
        kept.append((at, bool(strong)))
    marks = [0.0] + [o for o, _ in kept] + [total]
    out = []
    for a, b in zip(marks, marks[1:]):
        n = max(1, math.ceil((b - a) / max_m - 1e-9))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return out[:-1]  # the last mark is the line's end


def _split_at(coords: list, cum: list, offs: list) -> list:
    """Cut a line at these distances along it. The cut point is added on the line, so the parts together
    are exactly the original line."""
    parts, cur, k = [], [coords[0]], 0
    for i in range(1, len(coords)):
        while k < len(offs) and offs[k] < cum[i] - 1e-6:
            t = (offs[k] - cum[i - 1]) / (cum[i] - cum[i - 1])
            if t > 1e-9:
                cur.append([round(a + (b - a) * t, 7) for a, b in zip(coords[i - 1], coords[i])])
            parts.append(cur)
            cur, k = [cur[-1]], k + 1
        cur.append(coords[i])
    parts.append(cur)
    return parts


def cut_sections(feats: list, junctions: list = (), streets: list = (), max_m: float = MAX_SECTION_M) -> list:
    """Cut every line into sections between crossings, so one alert colours one block, not a whole street.
    A line is cut where a street meets it (a junction within CUT_NEAR_M), where a street centre line or
    another maintained sidewalk runs across it (crosses it, or ends within CUT_NEAR_M at more than 45°:
    a side street), and evenly where a part is still longer than max_m. Areas stay whole; gaps stay gaps.
    Each section is its own object (obj = its id); pgis_obj keeps the pGIS object it belongs to."""
    lines = {}
    sources = [(n, f["geometry"]["coordinates"], True) for n, f in enumerate(feats) if f["geometry"]["type"] == "LineString"]
    sources += [(("street", k), c, False) for k, c in enumerate(streets)]  # they cut, but are not cut
    for n, coords, target in sources:
        if len(coords) < 2:
            continue
        xy = [_xy(c) for c in coords]
        cum = [0.0]
        for i in range(len(xy) - 1):
            cum.append(cum[-1] + math.dist(xy[i], xy[i + 1]))
        lines[n] = {"xy": xy, "cum": cum, "cuts": [], "target": target}
    grid = defaultdict(list)  # cell -> (line, segment) of every segment within CUT_NEAR_M of the cell
    for n, ln in lines.items():
        xy = ln["xy"]
        for i in range(len(xy) - 1):
            (ax, ay), (bx, by) = xy[i], xy[i + 1]
            for gx in range(int((min(ax, bx) - CUT_NEAR_M) // _G), int((max(ax, bx) + CUT_NEAR_M) // _G) + 1):
                for gy in range(int((min(ay, by) - CUT_NEAR_M) // _G), int((max(ay, by) + CUT_NEAR_M) // _G) + 1):
                    grid[(gx, gy)].append((n, i))

    def near(p) -> dict:
        """line -> (offset along it, its direction there) at its closest point to p, if within CUT_NEAR_M"""
        best = {}
        for n, i in grid.get((int(p[0] // _G), int(p[1] // _G)), ()):
            ln = lines[n]
            (ax, ay), (bx, by) = ln["xy"][i], ln["xy"][i + 1]
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
            d = math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)
            if d <= CUT_NEAR_M and (n not in best or d < best[n][0]):
                best[n] = (d, ln["cum"][i] + t * math.sqrt(l2), _unit(dx, dy))
        return {n: (off, u) for n, (d, off, u) in best.items() if lines[n]["target"]}

    for j in junctions:  # 1. streets meeting the line
        for n, (off, _) in near(_xy(j)).items():
            lines[n]["cuts"].append((off, True))
    for m, other in lines.items():  # 2. side streets (or their sidewalks) ending at it
        street = not other["target"]
        for at_start in (True, False):
            end = other["xy"][0] if at_start else other["xy"][-1]
            ux, uy = _end_dir(other["xy"], other["cum"], at_start)
            for n, (off, (sx, sy)) in near(end).items():
                if n != m and abs(ux * sx + uy * sy) < CUT_ACROSS:
                    lines[n]["cuts"].append((off, street))
    seen = set()  # 3. streets or sidewalks crossing it
    for items in grid.values():
        for x in range(len(items)):
            for y in range(x + 1, len(items)):
                (n, i), (m, k) = items[x], items[y]
                if n == m or (items[x], items[y]) in seen or not (lines[n]["target"] or lines[m]["target"]):
                    continue
                seen.add((items[x], items[y]))
                a, b = lines[n]["xy"][i], lines[n]["xy"][i + 1]
                c, d = lines[m]["xy"][k], lines[m]["xy"][k + 1]
                r, s = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
                den = r[0] * s[1] - r[1] * s[0]
                lr, ls = math.hypot(*r), math.hypot(*s)
                if not lr or not ls or abs(den) / (lr * ls) < math.sin(math.acos(CUT_ACROSS)):
                    continue  # parallel or at a shallow angle: not a crossing
                t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
                u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
                if 0 < t < 1 and 0 < u < 1:
                    if lines[n]["target"]:
                        lines[n]["cuts"].append((lines[n]["cum"][i] + t * lr, not lines[m]["target"]))
                    if lines[m]["target"]:
                        lines[m]["cuts"].append((lines[m]["cum"][k] + u * ls, not lines[n]["target"]))

    out = []
    for n, f in enumerate(feats):
        if n not in lines:
            out.append(f)
            continue
        ln = lines[n]
        parts = _split_at(f["geometry"]["coordinates"], ln["cum"], _cut_offsets(ln["cuts"], ln["cum"][-1], max_m))
        for k, part in enumerate(parts, 1):
            p = dict(f["properties"])
            p["id"] = f"{p['id']}.{k}" if len(parts) > 1 else p["id"]
            p["pgis_obj"], p["obj"] = p.get("obj") or f["properties"]["id"], p["id"]
            out.append({"type": "Feature", "properties": p, "geometry": {"type": "LineString", "coordinates": part}})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/pgis_sidewalks.geojson")
    ap.add_argument("--no-cut", action="store_true", help="keep each pGIS object whole (no sections)")
    ap.add_argument("--max-section", type=float, default=MAX_SECTION_M, help="longest section with no crossing, m")
    a = ap.parse_args()
    body = {**CITY, "classifiers": CLASSIFIERS, "geometriesLoaded": [], "objectFilter": None, "zoom": 11}
    lines, polygons = post("geoms/lines", body), post("geoms/polygons", body)
    try:
        layers = layer_names()
    except Exception as exc:  # names are a nice-to-have
        print("layer names not loaded:", exc)
        layers = {}
    feats = convert(lines, polygons, layers)
    pieces = sum(1 for f in feats if f["geometry"]["type"] == "LineString")
    if not a.no_cut:
        junctions, streets = load_streets()
        feats = cut_sections(feats, junctions, streets, a.max_section)
        lens = sorted(sum(math.dist(_xy(c[i]), _xy(c[i + 1])) for i in range(len(c) - 1))
                      for c in (f["geometry"]["coordinates"] for f in feats if f["geometry"]["type"] == "LineString"))
        print(f"{pieces} pGIS line pieces cut at crossings ({len(junctions)} OSM junctions and crosswalks, {len(streets)} OSM street "
              f"blocks, the sidewalks themselves) -> {len(lens)} sections "
              f"(median {lens[len(lens) // 2]:.0f} m, longest {lens[-1]:.0f} m)")
    out = Path(a.out) if Path(a.out).is_absolute() else ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    fc = {"type": "FeatureCollection", "source": "pgis", "attribution": ATTRIBUTION, "features": feats}
    out.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kinds = Counter(f["properties"]["kind"] for f in feats)
    print(f"{len(lines.get('features', []))} lines + {len(polygons.get('features', []))} areas -> "
          f"{len(feats)} features ({dict(kinds)}) -> {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
