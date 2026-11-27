"""What each role may see. The contractor filter lives here, on the server:
full frames (frame_url), the evidence package and device ids never leave in a contractor response."""
import csv
import io
import json
from datetime import timedelta
from typing import Optional

from .engine import CLOSED, DISPATCHED, NOT_CLOSED_SQL, SNOW, Engine
from .registry import haversine_m
from .rules import fmt_riga
from .segments import sections as street_sections
from .timeutil import fmt_ts, parse_ts


def _photo_url(path: Optional[str]) -> Optional[str]:
    return f"/media/{path}" if path else None


def _seconds(a: Optional[str], b: Optional[str]) -> Optional[float]:
    if not a or not b:
        return None
    return (parse_ts(b) - parse_ts(a)).total_seconds()


def _hours(sec: Optional[float]) -> Optional[float]:
    return sec / 3600.0 if sec is not None else None


class Views:
    def __init__(self, engine: Engine):
        self.e = engine
        self.sidewalks = None  # app.segments.Sidewalks, set by build_app
        self._points = {}      # (lat, lon) -> camera alert's dot on the street (or None)
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
            # work in open / done_reported / reopened; closed work only if it had been dispatched
            sql += " AND (status IN ('open', 'done_reported', 'reopened') OR (status = 'verified' AND opened_at IS NOT NULL))"
        if status:
            sql += " AND status = ?"
            args.append(status)
        if not include_closed:
            sql += f" AND {NOT_CLOSED_SQL}"
        sql += " ORDER BY id"
        return self.db.q(sql, args)

    def overdue(self, a) -> bool:
        """clock.now() > fix_due_at and not verified -> red mark for the inspector and in contractor stats."""
        return bool(a["fix_due_at"] and a["status"] in DISPATCHED
                    and self.e.clock.now() > parse_ts(a["fix_due_at"]))

    def notify_seconds(self, a) -> Optional[float]:
        """KPI 2: notified_at - max(detected_at, deadline_at), should be <= 15 min."""
        if not a["notified_at"]:
            return None
        ref = [parse_ts(x) for x in (a["detected_at"], a["deadline_at"]) if x]
        if not ref:
            return None
        return max(0.0, (parse_ts(a["notified_at"]) - max(ref)).total_seconds())

    def map_point(self, a) -> Optional[list]:
        """Where a camera alert's dot goes: on the nearest street block, not the zone's centre (often a roof).
        None for reports (their own spot is exact), inside a square, or with no street nearby."""
        if not a["zone_id"] or self.sidewalks is None:
            return None
        key = (a["lat"], a["lon"])
        if key not in self._points:
            from .segments import SNAP_CAMERA_M
            b = self.sidewalks.nearest(a["lat"], a["lon"], SNAP_CAMERA_M)
            self._points[key] = self.sidewalks.snap(b, *key) if b and b["kind"] != "square" else None
        return self._points[key]

    def alert(self, a, role: str, detail: bool = False) -> dict:
        low = self.e.cfg.low_confidence
        sigs = self.db.q("SELECT * FROM signals WHERE alert_id = ? ORDER BY timestamp, id", (a["id"],))
        reps = self.db.q("SELECT * FROM reports WHERE alert_id = ? AND relevant != 'reject' "
                         "ORDER BY timestamp, id", (a["id"],))
        if role == "contractor":
            sigs = [s for s in sigs if s["confidence"] >= low]  # low-confidence frames: inspector only
        response = _seconds(a["notified_at"], a["verified_at"])
        first, last = (sigs[0], sigs[-1]) if sigs else (None, None)
        hazard_sigs = [s for s in sigs if s["hazard_class"] != "clear"]
        before = hazard_sigs[0] if hazard_sigs else first
        devices = {r["device_id"] for r in reps if r["counted"]}
        fix_left = _seconds(fmt_ts(self.e.clock.now()), a["fix_due_at"]) if a["fix_due_at"] else None
        out = {
            "id": a["id"],
            "status": a["status"],
            "severity": a["severity"] or "notice",
            "zone_id": a["zone_id"],
            "camera_id": a["camera_id"],
            "district": a["district"],
            "contractor_id": a["contractor_id"],
            "contractor_name": self.e.registry.contractor_name(a["contractor_id"]),
            "lat": a["lat"],
            "lon": a["lon"],
            "map_point": self.map_point(a),
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
            "deadline_at": a["deadline_at"],
            "opened_at": a["opened_at"],
            "notified_at": a["notified_at"],
            "fix_due_at": a["fix_due_at"],
            "fix_left_seconds": fix_left if a["status"] in DISPATCHED else None,
            "overdue": self.overdue(a),
            "done_reported_at": a["done_reported_at"],
            "verified_at": a["verified_at"],
            "reopened_count": a["reopened_count"],
            "flagged_for_council": bool(a["flagged_for_council"]),
            "response_seconds": response,
            "response_hours": _hours(response),
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
                "severity_suggested": a["severity_suggested"],
                "severity_manual": a["severity_manual"],
                "severity_reason": a["severity_reason"],
                "false_alarm": bool(a["false_alarm"]),
                "snowfall_id": a["snowfall_id"],
                "inspector_flags": json.loads(a["inspector_flags"] or "[]"),
                "notify_seconds": self.notify_seconds(a),
                "latest_frame_url": last["frame_url"] if last else None,
                "before_frame_url": before["frame_url"] if before else None,
                "after_frame_url": last["frame_url"] if last and last is not before else None,
                "latest_confidence": last["confidence"] if last else None,
                "registration_nos": [r["registration_no"] for r in reps if r["registration_no"]],
                "evidence_url": f"/alerts/{a['id']}/evidence?role=inspector" if a["opened_at"] else None,
            })
        if detail:
            out["signals"] = [self.signal(s, role) for s in sigs]
            out["reports"] = [self.report(r, role) for r in reps]
            out["history"] = self.history(a["id"], role)
        return out

    def history(self, alert_id: int, role: str) -> list:
        rows = [dict(h) for h in self.db.q(
            "SELECT from_status, to_status, actor, at, note FROM status_history WHERE alert_id = ? ORDER BY id",
            (alert_id,))]
        if role == "contractor":  # the contractor never saw the watch phase
            rows = [h for h in rows if h["to_status"] not in ("watch", "cleared_in_time")]
        return rows

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
            "lat": r["lat"], "lon": r["lon"], "passable": r["passable"], "passable_by": r["passable_by"],
            "loc_source": r["loc_source"], "capture": r["capture"], "flags": json.loads(r["flags"]) if r["flags"] else [],
            "hazard": r["hazard"],
            "place_type": r["place_type"], "comment": r["comment"],
        }
        if role == "inspector":
            d.update({
                "alert_id": r["alert_id"], "channel": r["channel"], "relevant": r["relevant"],
                "ai_score": r["ai_score"], "ai_hint": r["ai_hint"], "ai_note": r["ai_note"],
                "counted": bool(r["counted"]), "duplicate": bool(r["duplicate"]),
                "moderated_by": r["moderated_by"], "device": (r["device_id"] or "")[:8],
                "same_photo_as": r["reuse_of"], "registration_no": r["registration_no"],
            })
        return d

    # ------------------------------------------------------------------ inspector check list
    def problem_place(self, a) -> bool:
        """Reopened at this place (same zone, or within the merge radius) in the last 30 days."""
        since = fmt_ts(self.e.clock.now() - timedelta(days=self.e.cfg.problem_place_days))
        for o in self.db.q("SELECT id, zone_id, lat, lon FROM alerts WHERE reopened_count > 0 AND updated_at >= ?",
                           (since,)):
            if o["id"] == a["id"]:
                return True
            if (a["zone_id"] and o["zone_id"] == a["zone_id"]) or \
                    haversine_m(a["lat"], a["lon"], o["lat"], o["lon"]) <= self.e.cfg.merge_radius_m:
                return True
        return False

    def sections(self) -> list:
        """Active alerts snapped to street blocks; see app/segments.py for when a block is painted."""
        alerts = self.db.q(f"SELECT * FROM alerts WHERE {NOT_CLOSED_SQL}")
        devices: dict = {}
        for r in self.db.q("SELECT alert_id, device_id FROM reports WHERE counted = 1 AND alert_id IS NOT NULL"):
            devices.setdefault(r["alert_id"], set()).add(r["device_id"])
        return street_sections(alerts, devices, self.sidewalks)

    def inspection_today(self, limit: int = 10) -> list:
        """Check list for the inspector's day (08:30-17:00), in the brief's order:
        act -> overdue fix_due_at -> unconfirmed complaints without a camera -> problem places
        (reopened within 30 days) -> urgency."""
        rows = []
        for a in self.db.q(f"SELECT * FROM alerts WHERE {NOT_CLOSED_SQL}"):
            flags = json.loads(a["inspector_flags"] or "[]")
            no_camera = a["zone_id"] is None
            if not (a["status"] in DISPATCHED or flags or no_camera):
                continue  # a camera alert still in watch: nothing to check before the deadline
            rows.append((a, flags, no_camera, self.problem_place(a), self.overdue(a)))

        def key(item):
            a, flags, no_camera, problem, overdue = item
            act = a["severity"] == "act" and a["status"] in DISPATCHED
            return (0 if act else 1, 0 if overdue else 1, 0 if no_camera else 1, 0 if problem else 1,
                    -a["urgency_score"], parse_ts(a["first_seen_at"]))

        rows.sort(key=key)
        out = []
        for a, flags, no_camera, problem, overdue in rows[:limit]:
            d = self.alert(a, "inspector")
            why = []
            if a["severity"] == "act" and a["status"] in DISPATCHED:
                why.append("act")
            if overdue:
                why.append("overdue")
            if no_camera:
                why.append("no_camera")
            if problem:
                why.append("problem_place")
            if a["status"] == "reopened":
                why.append("reopened")
            if a["status"] == "done_reported":
                why.append("check_done")
            why += flags
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
    def response_stats(self, within_hours: Optional[float] = None) -> dict:
        """Response time = verified_at - notified_at, per contractor (and district): average,
        share closed within 24 h, reopened, overdue, and KPI 2 (notification <= 15 min)."""
        within = within_hours or self.e.cfg.fix_hours
        kpi_seconds = self.e.cfg.notify_kpi_minutes * 60.0
        groups: dict = {}
        for a in self.db.q("SELECT * FROM alerts WHERE notified_at IS NOT NULL AND COALESCE(false_alarm, 0) = 0"):
            for key in (("contractor", a["contractor_id"] or "-"), ("district", a["district"] or "-")):
                g = groups.setdefault(key, {"opened": 0, "verified": 0, "active": 0, "responses": [],
                                            "reopened": 0, "reopened_alerts": 0, "notify": [], "overdue": 0,
                                            "act": 0, "notice": 0})
                g["opened"] += 1
                g["reopened"] += a["reopened_count"]
                g["reopened_alerts"] += 1 if a["reopened_count"] else 0
                g["overdue"] += 1 if self.overdue(a) else 0
                g["act" if a["severity"] == "act" else "notice"] += 1
                r = _seconds(a["notified_at"], a["verified_at"])
                if a["status"] == "verified" and r is not None:
                    g["verified"] += 1
                    g["responses"].append(r)
                else:
                    g["active"] += 1
                n = self.notify_seconds(a)
                if n is not None:
                    g["notify"].append(n)

        def summarize(kind):
            out = []
            for (k, ident), g in sorted(groups.items()):
                if k != kind:
                    continue
                resp = g["responses"]
                ok = sum(1 for r in resp if r <= within * 3600)
                row = {
                    "id": ident,
                    "opened": g["opened"], "verified": g["verified"], "active": g["active"],
                    "act": g["act"], "notice": g["notice"], "overdue": g["overdue"],
                    "avg_response_hours": _hours(sum(resp) / len(resp)) if resp else None,
                    "max_response_hours": _hours(max(resp)) if resp else None,
                    "share_within": (ok / g["opened"]) if g["opened"] else None,
                    "reopened_times": g["reopened"], "reopened_alerts": g["reopened_alerts"],
                    "avg_notify_minutes": (sum(g["notify"]) / len(g["notify"]) / 60) if g["notify"] else None,
                    "share_notify_kpi": (sum(1 for n in g["notify"] if n <= kpi_seconds) / len(g["notify"]))
                    if g["notify"] else None,
                }
                if kind == "contractor":
                    row["name"] = self.e.registry.contractor_name(ident) or ident
                out.append(row)
            return out

        return {"within_hours": within, "notify_kpi_minutes": self.e.cfg.notify_kpi_minutes,
                "kpi": self.kpi(), "by_contractor": summarize("contractor"), "by_district": summarize("district")}

    def kpi(self) -> dict:
        """The three KPIs from the challenge, for the inspector screen.
        KPI 1: jobs the inspector closed as a false alarm / hours of camera work (first to last signal per camera).
        KPI 2: share of jobs that reached the contractor <= 15 min after max(snow seen, deadline).
        KPI 3: share of signals with an exact location (cameras always; resident reports located by the
        phone's GPS or sent by a trusted caller; a picked pin, typed coordinates or a map tap is approximate)."""
        hours = 0.0
        for c in self.db.q("SELECT MIN(timestamp) AS a, MAX(timestamp) AS b FROM signals GROUP BY camera_id"):
            hours += (_seconds(c["a"], c["b"]) or 0) / 3600.0
        false_jobs = self.db.one("SELECT COUNT(*) AS n FROM alerts WHERE false_alarm = 1 "
                                 "AND notified_at IS NOT NULL")["n"]
        false_all = self.db.one("SELECT COUNT(*) AS n FROM alerts WHERE false_alarm = 1")["n"]
        kpi_s = self.e.cfg.notify_kpi_minutes * 60.0
        notify = [n for n in (self.notify_seconds(a) for a in self.db.q(
            "SELECT * FROM alerts WHERE notified_at IS NOT NULL AND COALESCE(false_alarm, 0) = 0")) if n is not None]
        sig = self.db.one("SELECT COUNT(*) AS n, SUM(lat IS NOT NULL AND lon IS NOT NULL) AS p FROM signals")
        rep = self.db.one("SELECT COUNT(*) AS n, SUM(lat IS NOT NULL AND (loc_source IS NULL OR loc_source = 'gps')) "
                          "AS p FROM reports WHERE relevant != 'reject'")
        total, precise = sig["n"] + rep["n"], (sig["p"] or 0) + (rep["p"] or 0)
        return {
            "false_alarms_per_hour": round(false_jobs / hours, 3) if hours else None,
            "false_alarm_jobs": false_jobs, "false_alarms_all": false_all, "camera_hours": round(hours, 1),
            "notify_share": (sum(1 for n in notify if n <= kpi_s) / len(notify)) if notify else None,
            "notify_ok": sum(1 for n in notify if n <= kpi_s), "notify_total": len(notify),
            "notify_minutes": self.e.cfg.notify_kpi_minutes,
            "precise_share": (precise / total) if total else None, "precise": precise, "signals_total": total,
        }

    # ------------------------------------------------------------------ evidence package (inspector only)
    def evidence(self, a) -> dict:
        """Frame + time + place + history: what the council needs to prove a violation."""
        e = self.e
        deadline = parse_ts(a["deadline_at"])
        sigs = self.db.q("SELECT * FROM signals WHERE alert_id = ? AND confidence >= ? ORDER BY timestamp, id",
                         (a["id"], e.cfg.low_confidence))
        after = [s for s in sigs if deadline is None or parse_ts(s["timestamp"]) >= deadline]
        snow_after = [s for s in after if s["hazard_class"] in SNOW]
        clear_after = [s for s in after if s["hazard_class"] == "clear"
                       and (not snow_after or parse_ts(s["timestamp"]) > parse_ts(snow_after[0]["timestamp"]))]

        def frame(s, label):
            if s is None:
                return None
            ts = parse_ts(s["timestamp"])
            return {"label": label, "timestamp": s["timestamp"], "riga_time": fmt_riga(ts),
                    "frame_url": s["frame_url"], "crop_url": s["crop_url"], "hazard_class": s["hazard_class"],
                    "blocked_share": s["blocked_share"], "confidence": s["confidence"], "camera_id": s["camera_id"],
                    "zone_id": s["zone_id"]}

        sf = self.db.one("SELECT * FROM snowfalls WHERE id = ?", (a["snowfall_id"],)) if a["snowfall_id"] else None
        reps = self.db.q("SELECT * FROM reports WHERE alert_id = ? AND relevant != 'reject' ORDER BY timestamp, id",
                         (a["id"],))
        cam = e.registry.cameras.get(a["camera_id"]) if a["camera_id"] else None
        history = []
        for h in self.history(a["id"], "inspector"):
            history.append({**h, "riga_time": fmt_riga(parse_ts(h["at"]))})
        return {
            "alert_id": a["id"],
            "status": a["status"],
            "severity": a["severity"],
            "severity_reason": a["severity_reason"],
            "generated_at": fmt_ts(e.clock.now()),
            "generated_riga": fmt_riga(e.clock.now()),
            "place": {"lat": a["lat"], "lon": a["lon"], "polygon": json.loads(a["polygon"]) if a["polygon"] else None,
                      "zone_id": a["zone_id"], "camera_id": a["camera_id"],
                      "camera_name": (cam or {}).get("name"), "place_type": a["place_type"],
                      "district": a["district"], "contractor_id": a["contractor_id"],
                      "contractor_name": e.registry.contractor_name(a["contractor_id"])},
            "deadline": {"deadline_at": a["deadline_at"], "riga_time": fmt_riga(deadline),
                         "snowfall": None if sf is None else {
                             "start": sf["start"], "end": sf["end"],
                             "start_riga": fmt_riga(parse_ts(sf["start"])), "end_riga": fmt_riga(parse_ts(sf["end"]))},
                         "rule": "RD-24-270-sn: snowfall ended before 08:00 -> 08:00, 08:00-22:00 -> 22:00, "
                                 "after 22:00 -> 08:00 next day, unknown -> 08:00 of the day the snow was seen"},
            "times": {k: {"utc": a[k], "riga_time": fmt_riga(parse_ts(a[k]))} for k in
                      ("detected_at", "notified_at", "fix_due_at", "done_reported_at", "verified_at")},
            "overdue": self.overdue(a),
            "frames": [f for f in (
                frame(snow_after[0] if snow_after else None, "first_snow_after_deadline"),
                frame(snow_after[-1] if len(snow_after) > 1 else None, "last_snow"),
                frame(clear_after[0] if clear_after else None, "clear"),
            ) if f],
            "resident_photos": [{"photo_url": _photo_url(r["photo_path"]), "timestamp": r["timestamp"],
                                 "riga_time": fmt_riga(parse_ts(r["timestamp"])), "passable": r["passable"],
                                 "passable_by": r["passable_by"],
                                 "hazard": r["hazard"], "comment": r["comment"],
                                 "registration_no": r["registration_no"]}
                                for r in reps if r["photo_path"]],  # no device ids
            "history": history,
            "reopened_count": a["reopened_count"],
            "footer": "Сформировано Lantern; кадры камер города, обработка на сервере думы",
        }

    # ------------------------------------------------------------------ open-data export
    EXPORT_FIELDS = ("id", "status", "severity", "urgency_level", "urgency_score", "district", "contractor_id",
                     "place_type", "hazard_now", "first_seen_at", "detected_at", "deadline_at", "notified_at",
                     "fix_due_at", "done_reported_at", "verified_at", "response_hours", "overdue", "reopened_count",
                     "report_count", "signal_count", "lat", "lon")

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
