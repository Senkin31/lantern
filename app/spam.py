"""Spam protection for resident reports (web form, Telegram, any future channel).

Checks run BEFORE the photo goes to /analyze, so spam costs no model calls:

1. Blocked sender      - device blocked by the inspector or automatically (see 4)   -> HTTP 429
2. Rate limits         - per device per hour / per day, per IP per hour             -> HTTP 429
3. Same photo again    - exact (SHA-256) or near copy (64-bit difference hash, survives
                         re-compression/resizing). Stored, but never counted as a new
                         confirmation and not re-analysed.
4. Auto-block          - a device with too many rejected photos or duplicates in 24 h
                         is muted for AUTO_BLOCK_HOURS.

Identity: Telegram/WhatsApp send a stable hashed user id. The web form gets a random cookie,
which a spammer can clear, so the per-IP limit is the backstop there. Client-supplied
device_id is only trusted from TRUSTED_HOSTS (the bot and the replay script on this machine)
or with the INTERNAL_API_KEY header. IPs are stored only as salted hashes.

All limits use real time (not the demo's compressed "rule hours").
"""
import hashlib
import io
import secrets
from datetime import timedelta
from typing import Optional

from .timeutil import fmt_ts

try:
    from PIL import Image  # optional: without Pillow only exact copies are detected
except ImportError:  # pragma: no cover
    Image = None


def photo_hashes(data: bytes) -> tuple:
    """(sha256 hex, 64-bit dHash hex or None)."""
    sha = hashlib.sha256(data).hexdigest()
    if Image is None:
        return sha, None
    try:
        with Image.open(io.BytesIO(data)) as im:
            g = im.convert("L").resize((9, 8))
            px = g.tobytes()  # 72 grayscale bytes, row by row
    except Exception:  # HEIC or a broken file: exact hash only
        return sha, None
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return sha, f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


class SpamGuard:
    def __init__(self, db, cfg, clock):
        self.db = db
        self.cfg = cfg
        self.clock = clock

    # ------------------------------------------------------------------ identity
    def _salt(self) -> str:
        row = self.db.one("SELECT value FROM settings WHERE key = 'ip_salt'")
        if row and row["value"]:
            return row["value"]
        salt = secrets.token_hex(16)
        self.db.run("INSERT INTO settings(key, value) VALUES('ip_salt', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (salt,))
        return salt

    def ip_hash(self, ip: Optional[str]) -> str:
        return hashlib.sha256(f"{self._salt()}:{ip or '-'}".encode()).hexdigest()[:16]

    def trusted(self, host: Optional[str], key: Optional[str]) -> bool:
        if self.cfg.internal_api_key and key and secrets.compare_digest(key, self.cfg.internal_api_key):
            return True
        return (host or "") in self.cfg.trusted_hosts

    # ------------------------------------------------------------------ checks before analysis
    def _since(self, **kw) -> str:
        return fmt_ts(self.clock.now() - timedelta(**kw))

    def blocked(self, device_id: str):
        return self.db.one("SELECT * FROM devices WHERE device_id = ? AND blocked_until > ?",
                           (device_id, fmt_ts(self.clock.now())))

    def check(self, device_id: str, ip_hash: str, trusted: bool) -> Optional[dict]:
        """None if the report may go on, else {"reason", "retry_after"}."""
        cfg = self.cfg
        b = self.blocked(device_id)
        if b:
            left = (self._parse(b["blocked_until"]) - self.clock.now()).total_seconds()
            return {"reason": "blocked", "retry_after": max(60, int(left))}
        n_hour = self.db.one("SELECT COUNT(*) AS n FROM reports WHERE device_id = ? AND received_at >= ?",
                             (device_id, self._since(hours=1)))["n"]
        if n_hour >= cfg.rate_device_hour:
            return {"reason": "device_hourly_limit", "retry_after": 3600}
        n_day = self.db.one("SELECT COUNT(*) AS n FROM reports WHERE device_id = ? AND received_at >= ?",
                            (device_id, self._since(days=1)))["n"]
        if n_day >= cfg.rate_device_day:
            return {"reason": "device_daily_limit", "retry_after": 6 * 3600}
        if not trusted:
            n_ip = self.db.one("SELECT COUNT(*) AS n FROM reports WHERE ip_hash = ? AND received_at >= ?",
                               (ip_hash, self._since(hours=1)))["n"]
            if n_ip >= cfg.rate_ip_hour:
                return {"reason": "ip_hourly_limit", "retry_after": 3600}
        return None

    def in_service_area(self, lat: float, lon: float) -> bool:
        box = self.cfg.service_area
        if not box:
            return True
        lat_min, lon_min, lat_max, lon_max = box
        return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max

    def same_photo(self, sha: str, dhash: Optional[str]):
        """An earlier report (last SAME_PHOTO_DAYS) with the same or nearly the same photo."""
        since = self._since(days=self.cfg.same_photo_days)
        row = self.db.one("SELECT * FROM reports WHERE photo_sha256 = ? AND received_at >= ? ORDER BY id LIMIT 1",
                          (sha, since))
        if row or not dhash:
            return row
        for r in self.db.q("SELECT * FROM reports WHERE photo_dhash IS NOT NULL AND received_at >= ? ORDER BY id",
                           (since,)):
            if hamming(dhash, r["photo_dhash"]) <= self.cfg.dhash_distance:
                return r
        return None

    # ------------------------------------------------------------------ after the fact
    def event(self, device_id: str, ip_hash: str, reason: str) -> None:
        self.db.run("INSERT INTO spam_events(device_id, ip_hash, reason, at) VALUES(?, ?, ?, ?)",
                    (device_id, ip_hash, reason, fmt_ts(self.clock.now())))

    def strike(self, device_id: str) -> Optional[str]:
        """Called after a reject or a duplicate; auto-blocks a device that keeps doing it."""
        since = self._since(days=1)
        rejects = self.db.one("SELECT COUNT(*) AS n FROM reports WHERE device_id = ? AND relevant = 'reject' "
                              "AND received_at >= ?", (device_id, since))["n"]
        dups = self.db.one("SELECT COUNT(*) AS n FROM reports WHERE device_id = ? AND (duplicate = 1 OR reuse_of "
                           "IS NOT NULL) AND received_at >= ?", (device_id, since))["n"]
        reason = None
        if rejects >= self.cfg.auto_block_rejects:
            reason = f"auto: {rejects} rejected photos in 24 h"
        elif dups >= self.cfg.auto_block_duplicates:
            reason = f"auto: {dups} repeated reports in 24 h"
        if reason and not self.blocked(device_id):
            self.block(device_id, self.cfg.auto_block_hours, "system", reason)
        return reason

    def block(self, device_id: str, hours: float, by: str, reason: str) -> None:
        until = fmt_ts(self.clock.now() + timedelta(hours=hours))
        self.db.run("INSERT INTO devices(device_id, blocked_until, blocked_by, reason, at) VALUES(?, ?, ?, ?, ?) "
                    "ON CONFLICT(device_id) DO UPDATE SET blocked_until = excluded.blocked_until, "
                    "blocked_by = excluded.blocked_by, reason = excluded.reason, at = excluded.at",
                    (device_id, until, by, reason, fmt_ts(self.clock.now())))
        self.event(device_id, "", "blocked")

    def unblock(self, device_id: str) -> bool:
        row = self.blocked(device_id)
        self.db.run("UPDATE devices SET blocked_until = ? WHERE device_id = ?",
                    (fmt_ts(self.clock.now()), device_id))
        return row is not None

    def summary(self, hours: float = 24) -> dict:
        since = self._since(hours=hours)
        events = {r["reason"]: r["n"] for r in self.db.q(
            "SELECT reason, COUNT(*) AS n FROM spam_events WHERE at >= ? GROUP BY reason", (since,))}
        events["duplicate_place"] = self.db.one(
            "SELECT COUNT(*) AS n FROM reports WHERE duplicate = 1 AND received_at >= ?", (since,))["n"]
        events["same_photo"] = self.db.one(
            "SELECT COUNT(*) AS n FROM reports WHERE reuse_of IS NOT NULL AND received_at >= ?", (since,))["n"]
        blocked = [dict(r) for r in self.db.q(
            "SELECT device_id, blocked_until, blocked_by, reason, at FROM devices WHERE blocked_until > ? "
            "ORDER BY at DESC", (fmt_ts(self.clock.now()),))]
        cfg = self.cfg
        return {"window_hours": hours, "events": events, "blocked": blocked,
                "limits": {"device_per_hour": cfg.rate_device_hour, "device_per_day": cfg.rate_device_day,
                           "ip_per_hour": cfg.rate_ip_hour, "auto_block_rejects": cfg.auto_block_rejects,
                           "auto_block_duplicates": cfg.auto_block_duplicates,
                           "auto_block_hours": cfg.auto_block_hours, "service_area": cfg.service_area}}

    @staticmethod
    def _parse(ts):
        from .timeutil import parse_ts
        return parse_ts(ts)
