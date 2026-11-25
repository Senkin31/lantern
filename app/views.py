"""What each role may see. The contractor filter lives here, on the server:
full frames (frame_url) and device ids never leave in a contractor response."""
import csv
import io
import json
from typing import Optional

from .engine import ACTIVE, DISPATCHED, Engine
from .timeutil import fmt_ts, parse_ts


def _photo_url(path: Optional[str]) -> Optional[str]:
    return f"/media/{path}" if path else None


def _seconds(a: Optional[str], b: Optional[str]) -> Optional[float]:
    if not a or not b:
        return None
    return (parse_ts(b) - parse_ts(a)).total_seconds()


class Views:
    def __init__(self, engine: Engine):
        self.e = engine
        self.db = engine.db

    # ------------------------------------------------------------------ alerts
    def contractor_districts(self, district: Optional[str], contractor: Optional[str]) -> list:
        if contractor:
            return self.e.registry.districts_of(contractor)
        return [district] if district else []

    def alert_rows(self, role: str, districts: Optional[list] = None, status: Optional[str] = None,
                   include_closed: bool = True) -> list:
        sql, args = "SELECT * FROM alerts WHERE 1 = 1", []
        if role == "contractor":
            if not districts:
                return []
            sql += f" AND district IN ({','.join('?' * len(districts))})"
            args += districts
            # contractor sees dispatched work, and closed work that had been dispatched
            sql += " AND (status IN ('open', 'done_reported', 'reopened') OR (status = 'verified' AND opened_at IS NOT NULL))"
        if status:
            sql += " AND status = ?"
            args.append(status)
        if not include_closed:
            sql += " AND status != 'verified'"
        sql += " ORDER BY id"
        return self.db.q(sql, args)

    def alert(self, a, role: str, detail: bool = False) -> dict:
        hour = self.e.runtime()["hour_seconds"]
        low = self.e.cfg.low_confidence
        sigs = self.db.q("SELECT * FROM signals WHERE alert_id = ? ORDER BY timestamp, id", (a["id"],))
        reps = self.db.q("SELECT * FROM reports WHERE alert_id = ? AND relevant != 'reject' "
                         "ORDER BY timestamp, id", (a["id"],))
        if role == "contractor":
            sigs = [s for s in sigs if s["confidence"] >= low]  # low-confidence frames: inspector only
        response = _seconds(a["opened_at"], a["verified_at"])
        notify = _seconds(a["detected_at"], a["notified_at"])
        first, last = (sigs[0], sigs[-1]) if sigs else (None, None)
        hazard_sigs = [s for s in sigs if s["hazard_class"] != "clear"]
        before = hazard_sigs[0] if hazard_sigs else first
        devices = {r["device_id"] for r in reps if r["counted"]}
        out = {
            "id": a["id"],
            "status": a["status"],
            "zone_id": a["zone_id"],
            "camera_id": a["camera_id"],
            "district": a["district"],
            "contractor_id": a["contractor_id"],
            "contractor_name": self.e.registry.contractor_name(a["contractor_id"]),
            "lat": a["lat"],
            "lon": a["lon"],
            "polygon": json.loads(a["polygon"]) if a["polygon"] else None,
            "place_type": a["place_type"],
            "near_sensitive": bool(a["near_sensitive"]),
            "urgency_score": a["urgency_score"],
            "urgency_level": a["urgency_level"],
            "urgency_reasons": json.loads(a["urgency_reasons"] or "[]"),
            "hazard_now": a["hazard_now"],
            "first_seen_at": a["first_seen_at"],
            "last_evidence_at": a["last_evidence_at"],
            "detected_at": a["detected_at"],
            "opened_at": a["opened_at"],
            "notified_at": a["notified_at"],
            "done_reported_at": a["done_reported_at"],
            "verified_at": a["verified_at"],
            "reopened_count": a["reopened_count"],
            "flagged_for_council": bool(a["flagged_for_council"]),
            "response_seconds": response,
            "response_hours": response / hour if response is not None else None,
            "report_count": len(devices),
            "signal_count": len(sigs),
            "source_types": (["camera"] if sigs else []) + (["resident"] if reps else []),
            "latest_crop_url": last["crop_url"] if last else None,
            "before_crop_url": before["crop_url"] if before else None,
            "after_crop_url": last["crop_url"] if last and last is not before else None,
            "report_photos": [_photo_url(r["photo_path"]) for r in reps if r["photo_path"]][:4],
            "updated_at": a["updated_at"],
        }
        if role == "inspector":
            out.update({
                "inspector_flags": json.loads(a["inspector_flags"] or "[]"),
                "notify_seconds": notify,
                "latest_frame_url": last["frame_url"] if last else None,
                "before_frame_url": before["frame_url"] if before else None,
                "after_frame_url": last["frame_url"] if last and last is not before else None,
                "latest_confidence": last["confidence"] if last else None,
            })
        if detail:
            out["signals"] = [self.signal(s, role) for s in sigs]
            out["reports"] = [self.report(r, role) for r in reps]
            out["history"] = [dict(h) for h in self.db.q(
                "SELECT from_status, to_status, actor, at, note FROM status_history WHERE alert_id = ? ORDER BY id",
                (a["id"],))]
        return out

    def signal(self, s, role: str) -> dict:
        d = {k: s[k] for k in ("id", "zone_id", "timestamp", "hazard_class", "blocked_share", "confidence",
                               "crop_url")}
        if role == "inspector":
            d["frame_url"] = s["frame_url"]
            d["camera_id"] = s["camera_id"]
        return d

    def report(self, r, role: str) -> dict:
        d = {
            "id": r["id"], "timestamp": r["timestamp"], "photo_url": _photo_url(r["photo_path"]),
            "lat": r["lat"], "lon": r["lon"], "passable": r["passable"], "hazard": r["hazard"],
            "place_type": r["place_type"], "comment": r["comment"],
        }
        if role == "inspector":
            d.update({
                "alert_id": r["alert_id"], "channel": r["channel"], "relevant": r["relevant"],
                "ai_score": r["ai_score"], "ai_hint": r["ai_hint"], "ai_note": r["ai_note"],
                "counted": bool(r["counted"]), "duplicate": bool(r["duplicate"]),
                "moderated_by": r["moderated_by"], "device": (r["device_id"] or "")[:8],
                "same_photo_as": r["reuse_of"],
            })
        return d

    # ------------------------------------------------------------------ inspector lists
    def inspection_today(self, limit: int = 10) -> list:
        rows = [a for a in self.db.q("SELECT * FROM alerts WHERE status != 'verified'")
                if a["status"] in DISPATCHED or json.loads(a["inspector_flags"] or "[]")]

        def key(a):
            return (-a["urgency_score"], -int(a["status"] == "reopened"), -int(a["status"] == "done_reported"),
                    parse_ts(a["first_seen_at"]))

        rows.sort(key=key)
        out = []
        for a in rows[:limit]:
            d = self.alert(a, "inspector")
            why = []
            if a["status"] == "reopened":
                why.append("reopened")
            if a["status"] == "done_reported":
                why.append("check_done")
            why += d["inspector_flags"]
            if a["urgency_level"] == "high":
                why.append("high")
            d["why"] = why
            out.append(d)
        return out

    def reports_list(self, relevant: Optional[str] = None) -> list:
        sql, args = "SELECT * FROM reports", []
        if relevant and relevant != "all":
            sql += " WHERE relevant = ?"
            args.append(relevant)
        sql += " ORDER BY id DESC"
        return [self.report(r, "inspector") for r in self.db.q(sql, args)]

    # ------------------------------------------------------------------ stats (KPI)
    def response_stats(self, within_hours: float = 6.0) -> dict:
        rt = self.e.runtime()
        hour = rt["hour_seconds"]
        kpi_seconds = self.e.cfg.notify_kpi_minutes / 60.0 * hour
        groups: dict = {}
        for a in self.db.q("SELECT * FROM alerts WHERE opened_at IS NOT NULL"):
            for key in (("contractor", a["contractor_id"] or "-"), ("district", a["district"] or "-")):
                g = groups.setdefault(key, {"opened": 0, "verified": 0, "active": 0, "responses": [],
                                            "reopened": 0, "reopened_alerts": 0, "notify": []})
                g["opened"] += 1
                g["reopened"] += a["reopened_count"]
                g["reopened_alerts"] += 1 if a["reopened_count"] else 0
                r = _seconds(a["opened_at"], a["verified_at"])
                if a["status"] == "verified" and r is not None:
                    g["verified"] += 1
                    g["responses"].append(r)
                else:
                    g["active"] += 1
                n = _seconds(a["detected_at"], a["notified_at"])
                if n is not None:
                    g["notify"].append(n)

        def summarize(kind):
            out = []
            for (k, ident), g in sorted(groups.items()):
                if k != kind:
                    continue
                resp = g["responses"]
                within = sum(1 for r in resp if r <= within_hours * hour)
                row = {
                    "id": ident,
                    "opened": g["opened"], "verified": g["verified"], "active": g["active"],
                    "avg_response_hours": (sum(resp) / len(resp) / hour) if resp else None,
                    "max_response_hours": (max(resp) / hour) if resp else None,
                    "share_within": (within / g["opened"]) if g["opened"] else None,
                    "reopened_times": g["reopened"], "reopened_alerts": g["reopened_alerts"],
                    "avg_notify_minutes": (sum(g["notify"]) / len(g["notify"]) / hour * 60) if g["notify"] else None,
                    "share_notify_kpi": (sum(1 for n in g["notify"] if n <= kpi_seconds) / len(g["notify"]))
                    if g["notify"] else None,
                }
                if kind == "contractor":
                    row["name"] = self.e.registry.contractor_name(ident) or ident
                out.append(row)
            return out

        return {"within_hours": within_hours, "hour_seconds": hour,
                "notify_kpi_minutes": self.e.cfg.notify_kpi_minutes,
                "by_contractor": summarize("contractor"), "by_district": summarize("district")}

    # ------------------------------------------------------------------ open-data export
    EXPORT_FIELDS = ("id", "status", "urgency_level", "urgency_score", "district", "contractor_id", "place_type",
                     "hazard_now", "first_seen_at", "detected_at", "opened_at", "notified_at", "done_reported_at",
                     "verified_at", "response_hours", "reopened_count", "report_count", "signal_count", "lat", "lon")

    def _export_rows(self) -> list:
        return [self.alert(a, "contractor") for a in self.db.q("SELECT * FROM alerts ORDER BY id")]

    def export_geojson(self) -> dict:
        feats = []
        for d in self._export_rows():
            props = {k: d[k] for k in self.EXPORT_FIELDS if k not in ("lat", "lon")}
            if d["polygon"]:
                ring = list(d["polygon"])
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                geom = {"type": "Polygon", "coordinates": [ring]}
            else:
                geom = {"type": "Point", "coordinates": [d["lon"], d["lat"]]}
            feats.append({"type": "Feature", "geometry": geom, "properties": props})
        return {"type": "FeatureCollection", "generated_at": fmt_ts(self.e.clock.now()), "features": feats}

    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(self.EXPORT_FIELDS)
        for d in self._export_rows():
            w.writerow(["" if d[k] is None else d[k] for k in self.EXPORT_FIELDS])
        return buf.getvalue()

    # ------------------------------------------------------------------ resident ticket
    def ticket_status(self, ticket: str) -> Optional[dict]:
        r = self.db.one("SELECT * FROM reports WHERE ticket = ?", (ticket,))
        if r is None:
            return None
        out = {"ticket": r["ticket"], "received_at": r["received_at"], "relevant": r["relevant"],
               "state": "rejected" if r["relevant"] == "reject" else ("in_review" if r["relevant"] == "review"
                                                                      else "accepted")}
        if r["alert_id"] and r["relevant"] != "reject":
            a = self.e.alert(r["alert_id"])
            others = self.db.one("SELECT COUNT(DISTINCT device_id) AS n FROM reports WHERE alert_id = ? "
                                 "AND counted = 1 AND device_id != ?", (a["id"], r["device_id"]))["n"]
            out.update({"alert_status": a["status"], "urgency_level": a["urgency_level"],
                        "other_reports": others, "camera_confirmed": a["zone_id"] is not None,
                        "updated_at": a["updated_at"]})
        return out
