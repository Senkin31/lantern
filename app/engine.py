"""Alert rules: merging, clearing deadline, urgency, statuses (brief v2, "Правила заявок").

Everything that decides what an alert is lives here; the HTTP layer only validates
input and the views only filter output by role.
"""
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from .db import Database
from .registry import PRIORITY_PLACES, Registry, haversine_m, point_in_polygon
from .timeutil import Clock, fmt_ts, parse_ts

STATUSES = ("watch", "open", "done_reported", "verified", "reopened")
ACTIVE = ("watch", "open", "done_reported", "reopened")
DISPATCHED = ("open", "done_reported", "reopened")  # what a contractor sees as work
HAZARD_CLASSES = ("clear", "snow", "blocked", "possible_ice")
PLACE_TYPES = ("sidewalk", "crossing", "ramp", "stop", "path", "square", "other")
PASSABLE = ("no", "partly", "yes")
REPORT_HAZARDS = ("snow", "ice", "icicles", "other")
RELEVANT = ("accept", "review", "reject")


class RuleError(ValueError):
    """A status change that the rules do not allow."""


def camera_points(hazard_class: str, blocked_share: float) -> int:
    if hazard_class == "blocked":
        if blocked_share >= 0.6:
            return 3
        if blocked_share >= 0.3:
            return 2
        return 1
    if hazard_class == "possible_ice":
        return 2
    if hazard_class == "snow":
        return 1
    return 0


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

    # ------------------------------------------------------------------ runtime settings
    def _get(self, key: str) -> Optional[str]:
        row = self.db.one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else None

    def _put(self, key: str, value: Optional[str]) -> None:
        self.db.run("INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def runtime(self) -> dict:
        snow = self._get("snowfall_end")
        if snow is None:
            snow = self.cfg.snowfall_end or ""
        hour = self._get("hour_seconds")
        clearing = self._get("clearing_hours")
        return {
            "snowfall_end": snow or None,
            "hour_seconds": float(hour) if hour else self.cfg.hour_seconds,
            "clearing_hours": float(clearing) if clearing else self.cfg.clearing_hours,
        }

    def update_runtime(self, snowfall_end=..., hour_seconds=None, clearing_hours=None, actor="inspector") -> dict:
        if snowfall_end is not ...:
            if snowfall_end in (None, ""):
                self._put("snowfall_end", "")
            else:
                value = self.clock.now() if snowfall_end == "now" else parse_ts(snowfall_end)
                self._put("snowfall_end", fmt_ts(value))
        if hour_seconds is not None:
            if hour_seconds <= 0:
                raise RuleError("hour_seconds must be > 0")
            self._put("hour_seconds", repr(float(hour_seconds)))
        if clearing_hours is not None:
            if clearing_hours < 0:
                raise RuleError("clearing_hours must be >= 0")
            self._put("clearing_hours", repr(float(clearing_hours)))
        self.tick()
        return self.runtime_view()

    def hours(self, h: float) -> timedelta:
        return timedelta(seconds=h * self.runtime()["hour_seconds"])

    def deadline(self) -> Optional[datetime]:
        rt = self.runtime()
        end = parse_ts(rt["snowfall_end"]) if rt["snowfall_end"] else None
        if end is None:
            return None
        return end + timedelta(seconds=rt["clearing_hours"] * rt["hour_seconds"])

    def runtime_view(self) -> dict:
        rt = self.runtime()
        dl = self.deadline()
        now = self.clock.now()
        return {
            **rt,
            "clearing_seconds": rt["clearing_hours"] * rt["hour_seconds"],
            "deadline": fmt_ts(dl),
            "deadline_passed": bool(dl and now >= dl),
            "now": fmt_ts(now),
            "merge_radius_m": self.cfg.merge_radius_m,
            "merge_window_hours": self.cfg.merge_window_hours,
            "reopen_after_hours": self.cfg.reopen_after_hours,
            "low_confidence": self.cfg.low_confidence,
            "notify_kpi_minutes": self.cfg.notify_kpi_minutes,
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
            "urgency_reasons, inspector_flags) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'watch', ?, ?, ?, ?, '[]', '[]')",
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
            row = self.db.one("SELECT * FROM alerts WHERE zone_id = ? AND status != 'verified' "
                              "ORDER BY id DESC LIMIT 1", (s["zone_id"],))
            alert_id = row["id"] if row else None
            if alert_id is None and s["hazard_class"] != "clear":
                alert_id = self._alert_for_zone(s, ts)
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
            self._maybe_open(alert_id)
            return alert_id

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
        a = self.alert(alert_id)
        st, cls = a["status"], s["hazard_class"]
        now = fmt_ts(self.clock.now())
        if cls == "clear":
            if st == "watch":
                self._set_status(alert_id, "verified", "system", "camera: clear before the clearing deadline",
                                 verified_at=now)
            elif st in DISPATCHED:
                self._set_status(alert_id, "verified", "system", "camera: clear", verified_at=now)
        elif cls in ("snow", "blocked") and st == "done_reported":
            done = parse_ts(a["done_reported_at"])
            if done and ts >= done + self.hours(self.cfg.reopen_after_hours):
                self._set_status(alert_id, "reopened", "system",
                                 f"camera still sees {cls} ({s['blocked_share']:.0%}) after 'done'",
                                 reopened_count=a["reopened_count"] + 1, flagged_for_council=1)

    # ------------------------------------------------------------------ resident reports
    def find_merge_target(self, lat: float, lon: float, ts: datetime):
        window = self.hours(self.cfg.merge_window_hours)
        best, best_d = None, float("inf")
        for a in self.db.q("SELECT * FROM alerts WHERE status != 'verified'"):
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
                      ip_hash: Optional[str] = None, reuse_of: Optional[int] = None):
        """Store a resident report; rejected ones are kept but never become alerts.
        A photo that was already sent (reuse_of) is stored but never counts as a confirmation."""
        ts = parse_ts(r.get("timestamp")) or self.clock.now()
        now = fmt_ts(self.clock.now())
        relevant = analysis.get("relevant") if analysis.get("relevant") in RELEVANT else "review"
        with self.db.lock:
            alert_id = None
            duplicate = False
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
            counted = relevant == "accept" and not duplicate and reuse_of is None
            ticket = new_ticket()
            while self.db.one("SELECT 1 FROM reports WHERE ticket = ?", (ticket,)):
                ticket = new_ticket()
            report_id = self.db.run(
                "INSERT INTO reports(alert_id, ticket, channel, photo_path, lat, lon, passable, hazard, place_type, "
                "comment, device_id, timestamp, relevant, ai_score, ai_hint, ai_note, counted, duplicate, received_at, "
                "photo_sha256, photo_dhash, ip_hash, reuse_of) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (alert_id, ticket, channel, photo_path, r["lat"], r["lon"], r["passable"], r.get("hazard"),
                 r.get("place_type"), r.get("comment") or "", r["device_id"], fmt_ts(ts), relevant,
                 analysis.get("score"), analysis.get("hint"), analysis.get("note"),
                 1 if counted else 0, 1 if duplicate else 0, now, photo_sha256, photo_dhash, ip_hash, reuse_of))
            if alert_id is not None:
                self._bump_evidence(alert_id, ts)
                self.recompute(alert_id)
                self._maybe_open(alert_id)
            return self.db.one("SELECT * FROM reports WHERE id = ?", (report_id,))

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

    # ------------------------------------------------------------------ urgency
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
            flags.append("low_confidence")
        if hazard_now == "possible_ice":
            flags.append("possible_ice")
        if any(r["hazard"] in ("ice", "icicles") and r["relevant"] != "reject" for r in reps):
            flags.append("ice_report")
        if any(r["relevant"] == "review" and not r["moderated_by"] for r in reps):
            flags.append("review_report")

        self.db.run("UPDATE alerts SET urgency_score = ?, urgency_level = ?, urgency_reasons = ?, "
                    "inspector_flags = ?, hazard_now = ? WHERE id = ?",
                    (score, level, json.dumps(reasons), json.dumps(flags), hazard_now, alert_id))

    # ------------------------------------------------------------------ deadline
    def dispatchable(self, a) -> bool:
        """Snow is still there per reliable evidence, and someone can be sent."""
        if not a["contractor_id"]:
            return False
        hazard = a["hazard_now"]
        if hazard in ("snow", "blocked"):
            return True
        has_counted = self.db.one("SELECT 1 FROM reports WHERE alert_id = ? AND counted = 1",
                                  (a["id"],)) is not None
        return hazard in (None, "reported", "possible_ice") and has_counted

    def _maybe_open(self, alert_id: int) -> bool:
        a = self.alert(alert_id)
        if a["status"] != "watch":
            return False
        dl = self.deadline()
        now = self.clock.now()
        if dl is None or now < dl or not self.dispatchable(a):
            return False
        detected = max(dl, parse_ts(a["first_seen_at"]))
        self._set_status(alert_id, "open", "system",
                         "clearing deadline passed, hazard still there",
                         opened_at=fmt_ts(now), notified_at=fmt_ts(now), detected_at=fmt_ts(detected))
        return True

    def tick(self) -> int:
        """Called every second: watch -> open once the deadline has passed."""
        with self.db.lock:
            changed = 0
            for a in self.db.q("SELECT id FROM alerts WHERE status = 'watch'"):
                changed += self._maybe_open(a["id"])
            return changed

    # ------------------------------------------------------------------ manual status changes
    def change_status(self, alert_id: int, to: str, role: str, actor: str, note: str = "",
                      contractor_id: Optional[str] = None):
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
                        extra = {"opened_at": now, "notified_at": now, "detected_at": a["detected_at"] or now}
                    self._set_status(alert_id, "open", who, note or "dispatched by inspector", **extra)
                elif to == "verified":
                    if st == "verified":
                        raise RuleError("already verified")
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
