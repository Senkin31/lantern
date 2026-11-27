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

Each object keeps its pGIS id (obj = "p<id>"); a MULTILINESTRING becomes one LineString per part with
the same obj, and an alert on any part colours the whole object, as a task does in pGIS. The Old Riga
zones ("Vecrīgas zonējums") are polygons there, so they are areas (kind=square) here.
Uses only the standard library.
"""
import argparse
import json
import math
import re
import urllib.request
from collections import Counter
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


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{API}/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "lantern-hackathon-app/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def layer_names() -> dict:
    """classId -> layer (district) name, e.g. 13562 -> "Imanta"."""
    req = urllib.request.Request(f"{API}/classifiers/layers", headers={"User-Agent": "lantern-hackathon-app/0.1"})
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/pgis_sidewalks.geojson")
    a = ap.parse_args()
    body = {**CITY, "classifiers": CLASSIFIERS, "geometriesLoaded": [], "objectFilter": None, "zoom": 11}
    lines, polygons = post("geoms/lines", body), post("geoms/polygons", body)
    try:
        layers = layer_names()
    except Exception as exc:  # names are a nice-to-have
        print("layer names not loaded:", exc)
        layers = {}
    feats = convert(lines, polygons, layers)
    out = Path(a.out) if Path(a.out).is_absolute() else ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    fc = {"type": "FeatureCollection", "source": "pgis", "attribution": ATTRIBUTION, "features": feats}
    out.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kinds = Counter(f["properties"]["kind"] for f in feats)
    print(f"{len(lines.get('features', []))} lines + {len(polygons.get('features', []))} areas -> "
          f"{len(feats)} features ({dict(kinds)}) -> {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
