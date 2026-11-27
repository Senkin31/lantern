"""Alert rules: merging, clearing deadline, urgency, severity, statuses (brief v3, "Правила заявок").

Everything that decides what an alert is lives here; the HTTP layer only validates
input and the views only filter output by role. Every rule reads self.clock.now().
"""
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from .db import Database
from .registry import PRIORITY_PLACES, Registry, haversine_m, point_in_polygon
from .rules import clearing_deadline
from .timeutil import Clock, fmt_ts, parse_ts

STATUSES = ("watch", "cleared_in_time", "open", "done_reported", "verified", "reopened")
ACTIVE = ("watch", "open", "done_reported", "reopened")
CLOSED = ("verified", "cleared_in_time")
DISPATCHED = ("open", "done_reported", "reopened")  # what a contractor sees as work
SEVERITIES = ("act", "notice")
HAZARD_CLASSES = ("clear", "snow", "blocked", "possible_ice")
PLACE_TYPES = ("sidewalk", "crossing", "ramp", "stop", "path", "square", "other")
PASSABLE = ("no", "partly", "yes")
REPORT_HAZARDS = ("snow", "ice", "icicles", "other")
RELEVANT = ("accept", "review", "reject")
# where a report's location came from: the phone's GPS is exact; a pin someone picked, typed coordinates
# and a tap on the web map can point anywhere. None = a trusted API caller (demo, replay).
LOCATION_SOURCES = ("gps", "pin", "typed", "map", "coarse")
EXACT_LOCATION = (None, "gps")
# the model's note (or its optional "source") says this is not a photo taken on the street
SECONDHAND = re.compile(r"screen\s?shot|screen capture|photo of a (?:screen|monitor|display)|web\s?cam|"
                        r"web camera|cctv|surveillance|stock (?:photo|image)|watermark", re.I)
SNOW = ("snow", "blocked")
NOT_CLOSED_SQL = "status NOT IN ('verified', 'cleared_in_time')"


class RuleError(ValueError):
    """A status change that the rules do not allow."""


def camera_points(hazard_class: str, blocked_share: float) -> int:
    """v3 table: blocked or share >= 0.6 -> 3; share 0.3-0.6 -> 2; snow below 0.3 -> 1; possible_ice -> 2."""
    if hazard_class == "clear":
        return 0
    if hazard_class == "blocked" or blocked_share >= 0.6:
        return 3
    if hazard_class == "possible_ice":
        return 2
    if blocked_share >= 0.3:
        return 2
    return 1


def report_points(passable: str) -> int:
    return {"no": 3, "partly": 2, "yes": 1}.get(passable, 1)


def level_for(score: int) -> str:
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def new_ticket() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


class Engine:
    def __init__(self, db: Database, settings, clock: Clock, registry: Registry):
        self.db = db
        self.cfg = settings
        self.clock = clock
        self.registry = registry

    def hours(self, h: float) -> timedelta:
        return timedelta(hours=h)

    # ------------------------------------------------------------------ snowfalls and deadlines
    def add_snowfall(self, start: Optional[datetime], end: Optional[datetime], source: str = "api") -> dict:
        """POST /snowfalls: the end of a snowfall sets the clearing deadline (08:00 / 22:00 Riga)."""
        if start is None and end is None:
            raise RuleError("start or end is required")
        if start and end and end < start:
            raise RuleError("end is before start")
        with self.db.lock:
            ongoing = self.db.one("SELECT * FROM snowfalls WHERE end IS NULL ORDER BY id DESC LIMIT 1")
            if end is not None and ongoing is not None and parse_ts(ongoing["start"]) <= end \
                    and (start is None or start <= parse_ts(ongoing["start"]) + timedelta(hours=1)):
                # the end of the snowfall that is still going on: close it instead of adding a new one
                sid = ongoing["id"]
                self.db.run("UPDATE snowfalls SET end = ?, start = COALESCE(start, ?) WHERE id = ?",
                            (fmt_ts(end), fmt_ts(start), sid))
            else:
                sid = self.db.run("INSERT INTO snowfalls(start, end, source, created_at) VALUES(?, ?, ?, ?)",
                                  (fmt_ts(start), fmt_ts(end), source, fmt_ts(self.clock.now())))
            self.tick()
            return self.snowfall_view(self.db.one("SELECT * FROM snowfalls WHERE id = ?", (sid,)))

    def snowfall_view(self, row) -> Optional[dict]:
        if row is None:
            return None
        end = parse_ts(row["end"])
        return {"id": row["id"], "start": row["start"], "end": row["end"], "source": row["source"],
                "deadline_at": fmt_ts(clearing_deadline(end, end)) if end else None}

    def current_snowfall(self, at: Optional[datetime] = None):
        """The latest snowfall that has started by `at` (default now). Its end decides the deadline."""
        at_s = fmt_ts(at or self.clock.now())
        return self.db.one("SELECT * FROM snowfalls WHERE COALESCE(start, end) <= ? "
                           "ORDER BY COALESCE(end, start) DESC, id DESC LIMIT 1", (at_s,))

    def deadline_for(self, a) -> tuple:
        """(deadline, snowfall id) for an alert still in watch. Deadline is None while it is still snowing."""
        sf = self.current_snowfall()
        if sf is None:  # snowfall unknown: 08:00 of the day the snow was seen
            return clearing_deadline(None, parse_ts(a["first_seen_at"])), None
        end = parse_ts(sf["end"])
        if end is None:
            return None, sf["id"]
        return clearing_deadline(end, end), sf["id"]

    def runtime_view(self) -> dict:
        now = self.clock.now()
        sf = self.current_snowfall()
        if sf is None:
            dl = clearing_deadline(None, now)
        else:
            end = parse_ts(sf["end"])
            dl = clearing_deadline(end, end) if end else None
        return {
            "now": fmt_ts(now),
            "clock": self.clock.describe(),
            "snowfall": self.snowfall_view(sf),
            "snowfalls": [self.snowfall_view(r) for r in
                          self.db.q("SELECT * FROM snowfalls ORDER BY id DESC LIMIT 10")],
            "snowing": bool(sf is not None and not sf["end"]),
            "deadline": fmt_ts(dl),
            "deadline_passed": bool(dl and now >= dl),
            "fix_hours": self.cfg.fix_hours,
            "merge_radius_m": self.cfg.merge_radius_m,
            "merge_window_hours": self.cfg.merge_window_hours,
            "low_confidence": self.cfg.low_confidence,
            "notify_kpi_minutes": self.cfg.notify_kpi_minutes,
            "inspection_hours": self.cfg.inspection_hours,
            "timezone": "Europe/Riga",
        }

    # ------------------------------------------------------------------ helpers
    def alert(self, alert_id: int):
        return self.db.one("SELECT * FROM alerts WHERE id = ?", (alert_id,))

    def _history(self, alert_id: int, frm: Optional[str], to: str, actor: str, note: str = "") -> None:
        self.db.run("INSERT INTO status_history(alert_id, from_status, to_status, actor, at, note) "
                    "VALUES(?, ?, ?, ?, ?, ?)", (alert_id, frm, to, actor, fmt_ts(self.clock.now()), note))

    def _set_status(self, alert_id: int, to: str, actor: str, note: str = "", **fields) -> None:
        a = self.alert(alert_id)
        now = fmt_ts(self.clock.now())
        fields["status"] = to
        fields["updated_at"] = now
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.run(f"UPDATE alerts SET {cols} WHERE id = ?", (*fields.values(), alert_id))
        self._history(alert_id, a["status"], to, actor, note)

    def _create_alert(self, *, zone_id, camera_id, district, lat, lon, polygon, place_type,
                      near_sensitive, first_seen: datetime, actor: str, note: str) -> int:
        now = fmt_ts(self.clock.now())
        alert_id = self.db.run(
            "INSERT INTO alerts(zone_id, camera_id, district, contractor_id, lat, lon, polygon, place_type, "
            "near_sensitive, status, first_seen_at, last_evidence_at, created_at, updated_at, "
            "urgency_reasons, inspector_flags, severity) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'watch', ?, ?, ?, ?, '[]', '[]', 'notice')",
            (zone_id, camera_id, district, self.registry.contractor_for(district), lat, lon,
             json.dumps(polygon) if polygon else None, place_type, 1 if near_sensitive else 0,
             fmt_ts(first_seen), fmt_ts(first_seen), now, now))
        self._history(alert_id, None, "watch", actor, note)
        return alert_id

    def _bump_evidence(self, alert_id: int, ts: datetime) -> None:
        a = self.alert(alert_id)
        if parse_ts(a["last_evidence_at"]) < ts:
            self.db.run("UPDATE alerts SET last_evidence_at = ? WHERE id = ?", (fmt_ts(ts), alert_id))

    # ------------------------------------------------------------------ camera signals
    def ingest_signal(self, s: dict) -> Optional[int]:
        """Store one camera signal; returns the alert it went to (or None)."""
        ts = parse_ts(s["timestamp"])
        now = fmt_ts(self.clock.now())
        reliable = s["confidence"] >= self.cfg.low_confidence
        with self.db.lock:
            row = self.db.one(f"SELECT * FROM alerts WHERE zone_id = ? AND {NOT_CLOSED_SQL} "
                              "ORDER BY id DESC LIMIT 1", (s["zone_id"],))
            alert_id = row["id"] if row else None
            fresh = False
            if self.registry.is_inactive(s["camera_id"]):
                alert_id = None  # camera switched off in cameras.json: keep the row, never alert
            elif alert_id is None and s["hazard_class"] != "clear":
                alert_id = self._alert_for_zone(s, ts)
                fresh = True
            self.db.run(
                "INSERT INTO signals(alert_id, source, camera_id, zone_id, lat, lon, timestamp, hazard_class, "
                "blocked_share, confidence, frame_url, crop_url, received_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (alert_id, s.get("source", "camera"), s["camera_id"], s["zone_id"], s["lat"], s["lon"],
                 fmt_ts(ts), s["hazard_class"], s["blocked_share"], s["confidence"], s.get("frame_url"),
                 s.get("crop_url"), now))
            if alert_id is None:
                return None
            self._bump_evidence(alert_id, ts)
            if reliable:
                self._camera_transition(alert_id, s, ts)
            self.recompute(alert_id)
            self._maybe_open(alert_id, fresh=fresh)
            self._recompute_camera_siblings(alert_id)
            return alert_id

    def _recompute_camera_siblings(self, alert_id: int) -> None:
        """Severity 'act' can depend on snow in a neighbouring zone of the same camera."""
        a = self.alert(alert_id)
        if not a["camera_id"]:
            return
        for o in self.db.q(f"SELECT id FROM alerts WHERE camera_id = ? AND id != ? AND {NOT_CLOSED_SQL}",
                           (a["camera_id"], alert_id)):
            self.recompute(o["id"])

    def _alert_for_zone(self, s: dict, ts: datetime) -> int:
        z = self.registry.zones.get(s["zone_id"])
        cam = self.registry.cameras.get(s["camera_id"]) or (z["camera"] if z else None)
        if z:
            label = z["zone"].get("label")
            place = label if label in PLACE_TYPES else (cam or {}).get("place_type")
            polygon = z["zone"].get("map_polygon")
            lat, lon = z["lat"], z["lon"]
        else:
            place, polygon, lat, lon = (cam or {}).get("place_type"), None, s["lat"], s["lon"]
        district = (cam or {}).get("district") or self.registry.district_for_point(lat, lon)
        return self._create_alert(
            zone_id=s["zone_id"], camera_id=s["camera_id"], district=district, lat=lat, lon=lon,
            polygon=polygon, place_type=place or "sidewalk",
            near_sensitive=bool((cam or {}).get("near_sensitive")), first_seen=ts,
            actor="system", note=f"camera: {s['hazard_class']}")

    def _camera_transition(self, alert_id: int, s: dict, ts: datetime) -> None:
        """A clear frame closes the alert (not the contractor's button); snow after 'done' reopens it."""
        a = self.alert(alert_id)
        st, cls = a["status"], s["hazard_class"]
        now = fmt_ts(self.clock.now())
        if cls == "clear":
            if st == "watch":
                self._set_status(alert_id, "cleared_in_time", "system",
                                 "camera: clear before the clearing deadline", verified_at=now)
            elif st in DISPATCHED:
                self._set_status(alert_id, "verified", "system", "camera: clear", verified_at=now)
        elif cls in SNOW and st == "done_reported":
            done = parse_ts(a["done_reported_at"])
            if done and ts >= done + timedelta(minutes=self.cfg.reopen_after_minutes):
                self._set_status(alert_id, "reopened", "system",
                                 f"camera still sees {cls} ({s['blocked_share']:.0%}) after 'done'",
                                 reopened_count=a["reopened_count"] + 1, flagged_for_council=1)

    # ------------------------------------------------------------------ resident reports
    def find_merge_target(self, lat: float, lon: float, ts: datetime):
        window = self.hours(self.cfg.merge_window_hours)
        best, best_d = None, float("inf")
        for a in self.db.q(f"SELECT * FROM alerts WHERE {NOT_CLOSED_SQL}"):
            if parse_ts(a["last_evidence_at"]) < ts - window:
                continue
            poly = json.loads(a["polygon"]) if a["polygon"] else None
            d = 0.0 if point_in_polygon(lon, lat, poly) else haversine_m(lat, lon, a["lat"], a["lon"])
            if d <= self.cfg.merge_radius_m and d < best_d:
                best, best_d = a, d
        return best

    def device_duplicate(self, lat: float, lon: float, ts: datetime, device_id: str):
        """The earlier report of this device on the alert this one would join (one vote per device)."""
        target = self.find_merge_target(lat, lon, ts)
        if target is None:
            return None
        return self.db.one("SELECT * FROM reports WHERE alert_id = ? AND device_id = ? ORDER BY id LIMIT 1",
                           (target["id"], device_id))

    def ingest_report(self, r: dict, analysis: dict, photo_path: Optional[str], channel: str, *,
                      photo_sha256: Optional[str] = None, photo_dhash: Optional[str] = None,
                      ip_hash: Optional[str] = None, reuse_of: Optional[int] = None,
                      registration_no: Optional[str] = None):
        """Store a resident report; rejected ones are kept but never become alerts.
        A photo that was already sent (reuse_of) is stored but never counts as a confirmation."""
        ts = parse_ts(r.get("timestamp")) or self.clock.now()
        now = fmt_ts(self.clock.now())
        relevant = analysis.get("relevant") if analysis.get("relevant") in RELEVANT else "review"
        # --- anti-fake: these never block a report, they only make the inspector look first
        flags = []
        if r.get("loc_source") == "coarse":
            flags.append("coarse_location")  # the phone's own fix, but only to wifi / cell-tower accuracy
        elif r.get("loc_source") not in EXACT_LOCATION:
            flags.append("approx_location")  # cannot send the contractor alone (see dispatchable)
        if r.get("capture") == "picker":
            flags.append("picked_photo")  # Mini App camera was unavailable: the phone's file dialog was used
            if relevant == "accept":
                relevant = "review"  # that dialog may offer the gallery: the inspector looks first
        if relevant == "accept" and (analysis.get("source") in ("screenshot", "webcam", "stock", "screen")
                                     or SECONDHAND.search(analysis.get("note") or "")):
            relevant = "review"
            flags.append("not_street_photo")
        if relevant == "accept" and self.false_alarms_of(r["device_id"]) >= self.cfg.false_alarm_strikes:
            relevant = "review"
            flags.append("false_alarm_sender")
        with self.db.lock:
            alert_id = None
            duplicate = False
            fresh = False
            if relevant != "reject":
                target = self.find_merge_target(r["lat"], r["lon"], ts)
                if target is not None:
                    alert_id = target["id"]
                    duplicate = self.db.one("SELECT 1 FROM reports WHERE alert_id = ? AND device_id = ?",
                                            (alert_id, r["device_id"])) is not None
                else:
                    district = self.registry.district_for_point(r["lat"], r["lon"])
                    alert_id = self._create_alert(
                        zone_id=None, camera_id=None, district=district, lat=r["lat"], lon=r["lon"],
                        polygon=None, place_type=r.get("place_type") or "sidewalk", near_sensitive=False,
                        first_seen=ts, actor="system", note="resident report")
                    fresh = True
            counted = relevant == "accept" and not duplicate and reuse_of is None
            # a photo the model rejects gets no ticket: the row is kept (inspector's "rejected" list, spam
            # checks) under an internal lowercase reference that the uppercase ticket lookup never matches
            make = (lambda: "x" + secrets.token_hex(6)) if relevant == "reject" else new_ticket
            ticket = make()
            while self.db.one("SELECT 1 FROM reports WHERE ticket = ?", (ticket,)):
                ticket = make()
            report_id = self.db.run(
                "INSERT INTO reports(alert_id, ticket, channel, photo_path, lat, lon, passable, hazard, place_type, "
                "comment, device_id, timestamp, relevant, ai_score, ai_hint, ai_note, counted, duplicate, received_at, "
                "photo_sha256, photo_dhash, ip_hash, reuse_of, registration_no, passable_by, loc_source, flags, capture) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (alert_id, ticket, channel, photo_path, r["lat"], r["lon"], r["passable"], r.get("hazard"),
                 r.get("place_type"), r.get("comment") or "", r["device_id"], fmt_ts(ts), relevant,
                 analysis.get("score"), analysis.get("hint"), analysis.get("note"),
                 1 if counted else 0, 1 if duplicate else 0, now, photo_sha256, photo_dhash, ip_hash, reuse_of,
                 registration_no, r.get("passable_by") or "resident", r.get("loc_source"),
                 json.dumps(flags) if flags else None, r.get("capture")))
            if alert_id is not None:
                self._bump_evidence(alert_id, ts)
                self.recompute(alert_id)
                self._maybe_open(alert_id, fresh=fresh)
            return self.db.one("SELECT * FROM reports WHERE id = ?", (report_id,))

    def false_alarms_of(self, device_id: Optional[str]) -> int:
        """Alerts the inspector closed as "false alarm" that this sender had confirmed with a counted photo."""
        if not device_id:
            return 0
        return self.db.one("SELECT COUNT(DISTINCT a.id) AS n FROM alerts a JOIN reports r ON r.alert_id = a.id "
                           "WHERE a.false_alarm = 1 AND r.counted = 1 AND r.device_id = ?", (device_id,))["n"]

    def moderate_report(self, report_id: int, decision: str, actor: str):
        """Inspector decides on a `review` (or overrides a `reject`) report."""
        if decision not in ("accept", "reject"):
            raise RuleError("decision must be accept or reject")
        with self.db.lock:
            r = self.db.one("SELECT * FROM reports WHERE id = ?", (report_id,))
            if r is None:
                raise KeyError(report_id)
            alert_id = r["alert_id"]
            if decision == "reject":
                self.db.run("UPDATE reports SET relevant = 'reject', counted = 0, moderated_by = ? WHERE id = ?",
                            (actor, report_id))
            else:
                if alert_id is None:  # a rejected report the inspector rescues: merge it now
                    ts = parse_ts(r["timestamp"])
                    target = self.find_merge_target(r["lat"], r["lon"], ts)
                    if target is not None:
                        alert_id = target["id"]
                    else:
                        alert_id = self._create_alert(
                            zone_id=None, camera_id=None, district=self.registry.district_for_point(r["lat"], r["lon"]),
                            lat=r["lat"], lon=r["lon"], polygon=None, place_type=r["place_type"] or "sidewalk",
                            near_sensitive=False, first_seen=ts, actor=actor, note="report accepted by inspector")
                    self._bump_evidence(alert_id, ts)
                dup = self.db.one("SELECT 1 FROM reports WHERE alert_id = ? AND device_id = ? AND id != ? "
                                  "AND counted = 1", (alert_id, r["device_id"], report_id)) is not None
                self.db.run("UPDATE reports SET relevant = 'accept', alert_id = ?, counted = ?, duplicate = ?, "
                            "moderated_by = ? WHERE id = ?", (alert_id, 0 if dup else 1, 1 if dup else 0,
                                                             actor, report_id))
            if alert_id is not None:
                self.recompute(alert_id)
                self._maybe_open(alert_id)
            return self.db.one("SELECT * FROM reports WHERE id = ?", (report_id,))

    # ------------------------------------------------------------------ urgency and severity
    def recompute(self, alert_id: int) -> None:
        a = self.alert(alert_id)
        low = self.cfg.low_confidence
        ref = parse_ts(a["last_evidence_at"])
        start = ref - self.hours(self.cfg.merge_window_hours)
        sigs = self.db.q("SELECT * FROM signals WHERE alert_id = ? ORDER BY timestamp, id", (alert_id,))
        reps = self.db.q("SELECT * FROM reports WHERE alert_id = ? ORDER BY timestamp, id", (alert_id,))
        reliable = [s for s in sigs if s["confidence"] >= low]
        counted = [r for r in reps if r["counted"]]

        in_win = [s for s in reliable if parse_ts(s["timestamp"]) >= start] or \
                 [s for s in sigs if parse_ts(s["timestamp"]) >= start]
        reasons = []
        base, base_reason = 0, None
        for s in in_win:
            p = camera_points(s["hazard_class"], s["blocked_share"])
            if p > base:
                base = p
                base_reason = {"code": f"camera_{s['hazard_class']}", "share": s["blocked_share"],
                               "confidence": s["confidence"], "points": p}
        for r in counted:
            if parse_ts(r["timestamp"]) < start:
                continue
            p = report_points(r["passable"])
            if p > base:
                base = p
                base_reason = {"code": f"resident_{r['passable']}", "points": p}
        if base_reason:
            reasons.append(base_reason)
        score = base
        if a["place_type"] in PRIORITY_PLACES:
            score += 1
            reasons.append({"code": "place", "value": a["place_type"], "points": 1})
        if a["near_sensitive"]:
            score += 1
            reasons.append({"code": "near_sensitive", "points": 1})
        devices = {r["device_id"] for r in counted}
        sources = (1 if reliable else 0) + len(devices)
        conf = min(2, max(0, sources - 1))
        if conf:
            score += conf
            reasons.append({"code": "confirmations", "count": sources - 1, "points": conf})
        level = level_for(score)
        if not reliable and len(devices) <= 1 and level == "high":
            level = "medium"
            reasons.append({"code": "cap_unconfirmed"})

        hazard_now = reliable[-1]["hazard_class"] if reliable else ("reported" if counted else None)
        flags = []
        if sigs and sigs[-1]["confidence"] < low:
            # model v2: snow below 0.5 means "partly cleaned" - for the inspector, never the contractor
            flags.append("partly" if sigs[-1]["hazard_class"] in SNOW else "low_confidence")
        if hazard_now == "possible_ice":
            flags.append("possible_ice")
        if any(r["hazard"] in ("ice", "icicles") and r["relevant"] != "reject" for r in reps):
            flags.append("ice_report")
        if any(r["relevant"] == "review" and not r["moderated_by"] for r in reps):
            flags.append("review_report")

        suggested, why = self._suggest_severity(a, reliable, counted)
        severity = a["severity_manual"] or suggested
        self.db.run("UPDATE alerts SET urgency_score = ?, urgency_level = ?, urgency_reasons = ?, "
                    "inspector_flags = ?, hazard_now = ?, severity = ?, severity_suggested = ?, "
                    "severity_reason = ? WHERE id = ?",
                    (score, level, json.dumps(reasons), json.dumps(flags), hazard_now, severity, suggested, why,
                     alert_id))

    def _suggest_severity(self, a, reliable: list, counted: list) -> tuple:
        """act = candidate for a defect act; notice = letter to the contractor (both: 24 h to fix).
        Only a suggestion: the inspector changes it with one click."""
        snow = [s for s in reliable if s["hazard_class"] in SNOW]
        for s in snow:
            if (s["hazard_class"] == "blocked" or s["blocked_share"] >= 0.6) \
                    and s["confidence"] >= self.cfg.act_confidence:
                return "act", f"camera: {s['hazard_class']} {s['blocked_share']:.0%}, confidence {s['confidence']:.2f}"
        if snow and any(r["passable"] == "no" for r in counted):
            return "act", "camera snow + resident: impassable"
        snow_now = bool(reliable) and reliable[-1]["hazard_class"] in SNOW
        if snow_now and a["camera_id"]:
            other = self.db.one(f"SELECT zone_id FROM alerts WHERE camera_id = ? AND id != ? AND zone_id != ? "
                                f"AND {NOT_CLOSED_SQL} AND hazard_now IN ('snow', 'blocked')",
                                (a["camera_id"], a["id"], a["zone_id"] or ""))
            if other is not None:
                return "act", f"snow in two zones of one camera (+ {other['zone_id']})"
        return "notice", "partly cleared or a single source"

    # ------------------------------------------------------------------ deadline
    def dispatchable(self, a) -> bool:
        """Snow is still there per reliable evidence, and someone can be sent."""
        if not a["contractor_id"]:
            return False
        # residents can send the contractor when the place is certain: one report located by the phone's
        # GPS, or two different people. One picked / typed / tapped point alone waits for the inspector.
        counted = self.db.q("SELECT device_id, loc_source FROM reports WHERE alert_id = ? AND counted = 1",
                            (a["id"],))
        has_counted = (any(c["loc_source"] in EXACT_LOCATION for c in counted)
                       or len({c["device_id"] for c in counted}) >= 2)
        last = self.db.one("SELECT hazard_class, confidence FROM signals WHERE alert_id = ? "
                           "ORDER BY timestamp DESC, id DESC LIMIT 1", (a["id"],))
        if last and last["hazard_class"] in SNOW and last["confidence"] < self.cfg.low_confidence:
            # the zone's latest frame says "partly cleaned" (model v2): the camera alone never dispatches;
            # a resident's counted report still can
            return has_counted
        hazard = a["hazard_now"]
        if hazard in SNOW:
            return True
        return hazard in (None, "reported", "possible_ice") and has_counted

    def _open_fields(self, a, now: datetime, deadline: Optional[datetime]) -> dict:
        """detected_at = first snow frame; notified_at = contractor got it; fix_due_at = notified_at + 24 h."""
        first = self.db.one("SELECT timestamp FROM signals WHERE alert_id = ? AND confidence >= ? AND "
                            "hazard_class IN ('snow', 'blocked') ORDER BY timestamp, id LIMIT 1",
                            (a["id"], self.cfg.low_confidence))
        if first is None:
            first = self.db.one("SELECT timestamp FROM reports WHERE alert_id = ? AND counted = 1 "
                                "ORDER BY timestamp, id LIMIT 1", (a["id"],))
        detected = parse_ts(first["timestamp"]) if first else parse_ts(a["first_seen_at"])
        return {"opened_at": fmt_ts(now), "notified_at": fmt_ts(now), "detected_at": fmt_ts(detected),
                "fix_due_at": fmt_ts(now + timedelta(hours=self.cfg.fix_hours)),
                "deadline_at": fmt_ts(deadline) if deadline else a["deadline_at"]}

    def _maybe_open(self, alert_id: int, fresh: bool = False) -> bool:
        """watch -> open once the clearing deadline has passed and snow is still there.
        Snow first seen after the deadline goes straight to open, with no watch step (fresh=True)."""
        a = self.alert(alert_id)
        if a["status"] != "watch":
            return False
        deadline, sf_id = self.deadline_for(a)
        dl_text = fmt_ts(deadline)
        if dl_text != a["deadline_at"] or sf_id != a["snowfall_id"]:
            self.db.run("UPDATE alerts SET deadline_at = ?, snowfall_id = ? WHERE id = ?",
                        (dl_text, sf_id, alert_id))
            a = self.alert(alert_id)
        now = self.clock.now()
        if deadline is None or now < deadline or not self.dispatchable(a):
            return False
        fields = self._open_fields(a, now, deadline)
        if fresh:  # replace the creation row: the history shows the alert born open
            note = "seen after the clearing deadline"
            fields.update(status="open", updated_at=fmt_ts(now))
            cols = ", ".join(f"{k} = ?" for k in fields)
            self.db.run(f"UPDATE alerts SET {cols} WHERE id = ?", (*fields.values(), alert_id))
            self.db.run("UPDATE status_history SET to_status = 'open', note = COALESCE(note, '') || ' · ' || ? "
                        "WHERE alert_id = ? AND from_status IS NULL", (note, alert_id))
        else:
            self._set_status(alert_id, "open", "system", "clearing deadline passed, snow still there", **fields)
        self.recompute(alert_id)
        return True

    def tick(self) -> int:
        """Background check by clock.now(): watch -> open once the deadline has passed."""
        with self.db.lock:
            changed = 0
            for a in self.db.q("SELECT id FROM alerts WHERE status = 'watch'"):
                changed += self._maybe_open(a["id"])
            return changed

    # ------------------------------------------------------------------ manual changes
    def set_severity(self, alert_id: int, severity: str, actor: str, note: str = ""):
        """The inspector overrides the suggested level with one click; the change goes to history."""
        if severity not in SEVERITIES:
            raise RuleError("severity must be act or notice")
        with self.db.lock:
            a = self.alert(alert_id)
            if a is None:
                raise KeyError(alert_id)
            if a["severity"] != severity or a["severity_manual"] != severity:
                self.db.run("UPDATE alerts SET severity = ?, severity_manual = ?, updated_at = ? WHERE id = ?",
                            (severity, severity, fmt_ts(self.clock.now()), alert_id))
                self._history(alert_id, a["status"], a["status"], f"inspector:{actor or 'inspector'}",
                              (note + " · " if note else "") + f"severity {a['severity']} -> {severity}")
            return self.alert(alert_id)

    def send_warning(self, alert_id: int, message: str, actor: str = ""):
        """The inspector's written warning to the contractor of this alert (instead of a fine): the
        contractor sees it on the job, and it goes to the history as evidence."""
        message = " ".join((message or "").split())
        if not message:
            raise RuleError("the warning needs a message")
        with self.db.lock:
            a = self.alert(alert_id)
            if a is None:
                raise KeyError(alert_id)
            if a["status"] not in DISPATCHED or not a["contractor_id"]:
                raise RuleError(f"the contractor does not have this job (alert is {a['status']})")
            who = f"inspector:{actor or 'inspector'}"
            self.db.run("INSERT INTO warnings(alert_id, contractor_id, message, actor, at) VALUES(?, ?, ?, ?, ?)",
                        (alert_id, a["contractor_id"], message, who, fmt_ts(self.clock.now())))
            self._history(alert_id, a["status"], a["status"], who, f"warning to the contractor: {message}")
            return self.alert(alert_id)

    def change_status(self, alert_id: int, to: str, role: str, actor: str, note: str = "",
                      contractor_id: Optional[str] = None, false_alarm: bool = False):
        if to not in STATUSES:
            raise RuleError(f"unknown status {to}")
        with self.db.lock:
            a = self.alert(alert_id)
            if a is None:
                raise KeyError(alert_id)
            st = a["status"]
            now = fmt_ts(self.clock.now())
            if role == "contractor":
                if not contractor_id or a["contractor_id"] != contractor_id:
                    raise RuleError("this alert belongs to another contractor")
                if to != "done_reported" or st not in ("open", "reopened"):
                    raise RuleError(f"contractor can only report 'done' on open alerts (alert is {st})")
                self._set_status(alert_id, "done_reported", f"contractor:{contractor_id}", note or "marked as cleared",
                                 done_reported_at=now)
            elif role == "inspector":
                who = f"inspector:{actor or 'inspector'}"
                if to == "open":
                    if st not in ("watch", "done_reported", "reopened"):
                        raise RuleError(f"cannot dispatch an alert that is {st}")
                    if not a["contractor_id"]:
                        raise RuleError("no contractor for this district")
                    extra = {}
                    if not a["opened_at"]:
                        extra = self._open_fields(a, self.clock.now(), None)
                    self._set_status(alert_id, "open", who, note or "dispatched by inspector", **extra)
                elif to in ("verified", "cleared_in_time"):
                    if st in CLOSED:
                        raise RuleError(f"already closed ({st})")
                    if false_alarm:  # no snow on site: the model or the resident was wrong (KPI 1)
                        self._set_status(alert_id, "cleared_in_time" if st == "watch" else "verified", who,
                                         note or "false alarm: no snow on site", verified_at=now, false_alarm=1)
                    elif st == "watch":  # clean before the deadline: closed, never reached the contractor
                        self._set_status(alert_id, "cleared_in_time", who,
                                         note or "clean on site before the deadline", verified_at=now)
                    else:
                        self._set_status(alert_id, "verified", who, note or "confirmed on site", verified_at=now)
                elif to == "reopened":
                    if st not in ("done_reported", "verified") or not a["opened_at"]:
                        raise RuleError("only work reported or verified as done can be disputed")
                    self._set_status(alert_id, "reopened", who, note or "disputed by inspector",
                                     verified_at=None, reopened_count=a["reopened_count"] + 1,
                                     flagged_for_council=1)
                else:
                    raise RuleError(f"inspector cannot set {to}")
            else:
                raise RuleError("unknown role")
            self.recompute(alert_id)
            return self.alert(alert_id)
