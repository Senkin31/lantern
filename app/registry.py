"""Cameras (config/cameras.json, owned by the vision side) and contractors."""
import json
import math
from pathlib import Path
from typing import Optional

PRIORITY_PLACES = {"crossing", "ramp", "stop"}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_in_polygon(lon: float, lat: float, polygon) -> bool:
    """Ray casting; polygon is [[lon, lat], ...] as in GeoJSON."""
    if not polygon or len(polygon) < 3:
        return False
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def polygon_center(polygon) -> tuple:
    lons = [p[0] for p in polygon]
    lats = [p[1] for p in polygon]
    return sum(lats) / len(lats), sum(lons) / len(lons)


class Registry:
    def __init__(self, cameras_file: Path, cameras_fallback: Path, contractors_file: Path):
        # config/cameras.json (vision side) wins; the mock file adds the demo cameras it doesn't have
        self.camera_files = [p for p in (cameras_file, cameras_fallback) if p.is_file()]
        self.cameras: dict = {}
        self.zones: dict = {}
        for path in self.camera_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            for cam in data.get("cameras", []):
                if cam.get("source") == "skyfinder":  # training-only cameras, never on the map
                    continue
                if cam["camera_id"] in self.cameras:
                    continue
                self.cameras[cam["camera_id"]] = cam
                for z in cam.get("zones", []):
                    poly = z.get("map_polygon")
                    lat, lon = polygon_center(poly) if poly else (cam["lat"], cam["lon"])
                    self.zones[z["zone_id"]] = {"camera": cam, "zone": z, "lat": lat, "lon": lon}

        self.contractors: list = []
        self.district_to_contractor: dict = {}
        if contractors_file.is_file():
            data = json.loads(contractors_file.read_text(encoding="utf-8"))
            self.contractors = data.get("contractors", [])
            for c in self.contractors:
                for d in c.get("districts", []):
                    self.district_to_contractor[d] = c["id"]

    def contractor_for(self, district: Optional[str]) -> Optional[str]:
        return self.district_to_contractor.get(district or "")

    def contractor_name(self, contractor_id: Optional[str]) -> Optional[str]:
        for c in self.contractors:
            if c["id"] == contractor_id:
                return c.get("name", c["id"])
        return None

    def districts_of(self, contractor_id: str) -> list:
        for c in self.contractors:
            if c["id"] == contractor_id:
                return list(c.get("districts", []))
        return []

    def district_for_point(self, lat: float, lon: float) -> Optional[str]:
        """Zone polygon that contains the point, else the nearest camera's district."""
        for z in self.zones.values():
            if point_in_polygon(lon, lat, z["zone"].get("map_polygon")):
                return z["camera"].get("district")
        best, best_d = None, float("inf")
        for cam in self.cameras.values():
            d = haversine_m(lat, lon, cam["lat"], cam["lon"])
            if d < best_d:
                best, best_d = cam, d
        return best.get("district") if best else None

    def public_cameras(self) -> list:
        out = []
        for cam in self.cameras.values():
            out.append({
                "camera_id": cam["camera_id"], "name": cam.get("name"), "lat": cam["lat"], "lon": cam["lon"],
                "district": cam.get("district"), "place_type": cam.get("place_type"),
                "near_sensitive": bool(cam.get("near_sensitive")),
                "zones": [{"zone_id": z["zone_id"], "label": z.get("label"), "map_polygon": z.get("map_polygon")}
                          for z in cam.get("zones", [])],
            })
        return out
