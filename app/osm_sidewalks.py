"""Fetch street and sidewalk lines for (central) Riga from OpenStreetMap and cut them into blocks.

    python -m app.osm_sidewalks                       # default box: central Riga -> config/riga_sidewalks.geojson
    python -m app.osm_sidewalks --bbox 56.935,24.08,56.975,24.16 --out config/riga_sidewalks.geojson

The app snaps alerts to these blocks and paints the block on the inspector map (app/segments.py).
A block = a piece of a way between two junctions, at most MAX_BLOCK_M long.
Data: (c) OpenStreetMap contributors, ODbL 1.0 - keep the attribution on the map.
Uses only the standard library. Sends nothing but the bounding box to the public Overpass API.
"""
import argparse
import json
import math
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from .config import ROOT

OVERPASS = "https://overpass-api.de/api/interpreter"
DEFAULT_BBOX = (56.935, 24.08, 56.975, 24.16)   # south, west, north, east: Old Town, Centrs, around the demo
MAX_BLOCK_M = 220.0
STREETS = "pedestrian|living_street|residential|unclassified|tertiary|secondary|primary"


def query(bbox) -> str:
    b = ",".join(f"{x:.5f}" for x in bbox)
    return (f'[out:json][timeout:90];('
            f'way["highway"="footway"]({b});'          # sidewalks, crossings (for the junctions), park paths
            f'way["highway"="path"]({b});'
            f'way["highway"~"^({STREETS})$"]({b});'
            f');out body geom;')


def fetch(bbox) -> dict:
    data = urllib.parse.urlencode({"data": query(bbox)}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "lantern-hackathon-app/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _dist_m(a, b) -> float:
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((b[0] - a[0]) * 111_320, (b[1] - a[1]) * 111_320 * math.cos(lat))


def _kind(tags: dict) -> str:
    if tags.get("footway") == "sidewalk":
        return "sidewalk"
    if tags.get("highway") in ("footway", "path"):
        return "path"
    return "street"


def _split_long(points: list) -> list:
    """Cut a block longer than MAX_BLOCK_M into roughly equal pieces (at existing vertices)."""
    total = sum(_dist_m(points[i], points[i + 1]) for i in range(len(points) - 1))
    if total <= MAX_BLOCK_M or len(points) < 3:
        return [points]
    n = math.ceil(total / MAX_BLOCK_M)
    step, out, cur, run = total / n, [], [points[0]], 0.0
    for i in range(1, len(points)):
        run += _dist_m(points[i - 1], points[i])
        cur.append(points[i])
        if run >= step and i < len(points) - 1:
            out.append(cur)
            cur, run = [points[i]], 0.0
    out.append(cur)
    return out


def blocks(osm: dict, keep_paths: bool = False) -> list:
    ways = [w for w in osm.get("elements", []) if w.get("type") == "way" and w.get("geometry")]
    uses = Counter(n for w in ways for n in set(w.get("nodes", [])))  # a node used by 2+ ways = junction
    feats = []
    for w in ways:
        tags = w.get("tags", {})
        if tags.get("footway") == "crossing" or (_kind(tags) == "path" and not keep_paths):
            continue  # crossings and park paths only help to find the junctions of sidewalks
        nodes, geom = w.get("nodes", []), [(g["lat"], g["lon"]) for g in w["geometry"]]
        if len(nodes) != len(geom):
            nodes = [None] * len(geom)
        piece, k = [geom[0]], 0
        for i in range(1, len(geom)):
            piece.append(geom[i])
            if (i < len(geom) - 1 and uses.get(nodes[i], 0) >= 2) or i == len(geom) - 1:
                for part in _split_long(piece):
                    if len(part) >= 2:
                        k += 1
                        feats.append({"type": "Feature", "properties": {
                            "id": f"w{w['id']}-{k}", "name": tags.get("name") or tags.get("street:name"),
                            "kind": _kind(tags), "highway": tags.get("highway")},
                            "geometry": {"type": "LineString",
                                         "coordinates": [[round(lon, 6), round(lat, 6)] for lat, lon in part]}})
                piece = [geom[i]]
    return feats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", default=",".join(map(str, DEFAULT_BBOX)), help="south,west,north,east")
    ap.add_argument("--out", default="config/riga_sidewalks.geojson")
    ap.add_argument("--keep-paths", action="store_true", help="also keep park and courtyard paths")
    a = ap.parse_args()
    bbox = tuple(float(x) for x in a.bbox.split(","))
    osm = fetch(bbox)
    feats = blocks(osm, a.keep_paths)
    out = Path(a.out) if Path(a.out).is_absolute() else ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    fc = {"type": "FeatureCollection",
          "attribution": "(c) OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright",
          "bbox": [bbox[1], bbox[0], bbox[3], bbox[2]], "features": feats}
    out.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kinds = Counter(f["properties"]["kind"] for f in feats)
    print(f"{len(feats)} blocks ({dict(kinds)}) -> {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
