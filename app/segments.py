"""Street sections: the council sees a piece of street, not only a dot.

Every active alert is snapped to the nearest block of sidewalk or street (config/riga_sidewalks.geojson,
made by app/osm_sidewalks.py from OpenStreetMap). A block is painted when the evidence is about the street,
not one spot:
  - a camera alert lies on it (the camera zone covers a stretch of sidewalk), or
  - at least MIN_RESIDENTS different residents (counted reports, one vote per device) reported on it.
One complaint stays a dot. The block takes the colour of its worst alert.
Without the file, alerts within CLUSTER_M of each other are joined by a line instead (fallback).
"""
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Optional

SNAP_M = 25.0           # a report this close to a block belongs to it
SNAP_CAMERA_M = 40.0    # camera zones are drawn by hand: allow a little more
PREFER_SIDEWALK_M = 15  # a mapped sidewalk this close wins over the street centre line
CELL_M = 100.0
MIN_RESIDENTS = 2
CLUSTER_M = 80.0

RANK = {"reopened": 5, "high": 4, "medium": 3, "low": 2, "watch": 1}


def _severity_rank(a) -> int:
    if a["status"] == "reopened":
        return RANK["reopened"]
    if a["status"] == "watch":
        return RANK["watch"]
    return RANK.get(a["urgency_level"], 2)


class Sidewalks:
    """Blocks of sidewalk / street with a 100 m grid index; coordinates in metres around Riga."""

    def __init__(self, features: list):
        self.blocks = []
        lats = [c[1] for f in features for c in f["geometry"]["coordinates"]] or [56.95]
        self.lat0 = sum(lats) / len(lats)
        self.kx = 111_320 * math.cos(math.radians(self.lat0))
        self.ky = 111_320
        self.grid = defaultdict(list)
        for f in features:
            coords = f["geometry"]["coordinates"]
            if f["geometry"]["type"] != "LineString" or len(coords) < 2:
                continue
            p = f.get("properties", {})
            xy = [self.xy(lat, lon) for lon, lat in coords]
            length = sum(math.dist(xy[i], xy[i + 1]) for i in range(len(xy) - 1))
            idx = len(self.blocks)
            self.blocks.append({"id": p.get("id") or f"b{idx}", "name": p.get("name"), "kind": p.get("kind", "street"),
                                "latlon": [[lat, lon] for lon, lat in coords], "xy": xy, "length_m": length})
            cells = set()
            for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
                steps = max(1, int(math.dist((x1, y1), (x2, y2)) // (CELL_M / 2)))
                for k in range(steps + 1):
                    x, y = x1 + (x2 - x1) * k / steps, y1 + (y2 - y1) * k / steps
                    cells.add((int(x // CELL_M), int(y // CELL_M)))
            for c in cells:
                self.grid[c].append(idx)

    @classmethod
    def load(cls, path: Optional[Path]) -> Optional["Sidewalks"]:
        if not path or not Path(path).is_file():
            return None
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data.get("features", []))

    def xy(self, lat: float, lon: float):
        return ((lon - 24.0) * self.kx, (lat - self.lat0) * self.ky)

    @staticmethod
    def _seg_dist(p, a, b) -> float:
        (px, py), (ax, ay), (bx, by) = p, a, b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)

    def nearest(self, lat: float, lon: float, max_m: float = SNAP_M) -> Optional[dict]:
        p = self.xy(lat, lon)
        cx, cy = int(p[0] // CELL_M), int(p[1] // CELL_M)
        best, best_side = (None, float("inf")), (None, float("inf"))
        seen = set()
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for idx in self.grid.get((gx, gy), ()):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    xy = self.blocks[idx]["xy"]
                    d = min(self._seg_dist(p, xy[i], xy[i + 1]) for i in range(len(xy) - 1))
                    if d < best[1]:
                        best = (idx, d)
                    if self.blocks[idx]["kind"] == "sidewalk" and d < best_side[1]:
                        best_side = (idx, d)
        if best_side[0] is not None and best_side[1] <= min(PREFER_SIDEWALK_M, max_m):
            return self.blocks[best_side[0]]
        if best[0] is not None and best[1] <= max_m:
            return self.blocks[best[0]]
        return None


def _summary(group: list, devices: dict) -> dict:
    worst = max(group, key=_severity_rank)
    residents = set()
    for a in group:
        residents |= devices.get(a["id"], set())
    return {"alert_ids": sorted(a["id"] for a in group), "status": worst["status"],
            "urgency_level": worst["urgency_level"], "residents": len(residents),
            "camera": any(a["zone_id"] for a in group)}


def _lit(s: dict) -> bool:
    return s["camera"] or s["residents"] >= MIN_RESIDENTS


def sections(alerts: list, devices: dict, sidewalks: Optional[Sidewalks]) -> list:
    """alerts: active alert rows; devices: alert_id -> set of devices with a counted report."""
    out = []
    if sidewalks is not None:
        groups = defaultdict(list)
        blocks = {}
        for a in alerts:
            b = sidewalks.nearest(a["lat"], a["lon"], SNAP_CAMERA_M if a["zone_id"] else SNAP_M)
            if b:
                groups[b["id"]].append(a)
                blocks[b["id"]] = b
        for bid, group in groups.items():
            s = _summary(group, devices)
            if _lit(s):
                b = blocks[bid]
                out.append({"id": bid, "name": b["name"], "kind": b["kind"], "length_m": round(b["length_m"]),
                            "coords": b["latlon"], "source": "osm", **s})
        return out
    # fallback without street data: join alerts that lie within CLUSTER_M of each other
    parent = list(range(len(alerts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    kx = 111_320 * math.cos(math.radians(56.95))
    pts = [((a["lon"]) * kx, a["lat"] * 111_320) for a in alerts]
    for i in range(len(alerts)):
        for j in range(i + 1, len(alerts)):
            if math.dist(pts[i], pts[j]) <= CLUSTER_M:
                parent[find(i)] = find(j)
    clusters = defaultdict(list)
    for i in range(len(alerts)):
        clusters[find(i)].append(i)
    for members in clusters.values():
        if len(members) < 2:
            continue  # a single dot stays a dot
        group = [alerts[i] for i in members]
        s = _summary(group, devices)
        if not _lit(s):
            continue
        # order the points along their main direction so the line does not zigzag
        mx = sum(pts[i][0] for i in members) / len(members)
        my = sum(pts[i][1] for i in members) / len(members)
        sxx = sum((pts[i][0] - mx) ** 2 for i in members)
        syy = sum((pts[i][1] - my) ** 2 for i in members)
        sxy = sum((pts[i][0] - mx) * (pts[i][1] - my) for i in members)
        ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
        members.sort(key=lambda i: (pts[i][0] - mx) * math.cos(ang) + (pts[i][1] - my) * math.sin(ang))
        coords = [[alerts[i]["lat"], alerts[i]["lon"]] for i in members]
        length = sum(math.dist(pts[members[k]], pts[members[k + 1]]) for k in range(len(members) - 1))
        out.append({"id": "c" + "-".join(str(alerts[i]["id"]) for i in members), "name": None, "kind": "cluster",
                    "length_m": round(length), "coords": coords, "source": "cluster", **s})
    return out
