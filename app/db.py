"""SQLite storage. One connection guarded by a lock: enough for the pilot."""
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id          TEXT,               -- camera zone, NULL for report-only alerts
    camera_id        TEXT,
    district         TEXT,
    contractor_id    TEXT,
    lat              REAL NOT NULL,
    lon              REAL NOT NULL,
    polygon          TEXT,               -- JSON [[lon, lat], ...] or NULL
    place_type       TEXT,
    near_sensitive   INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL,      -- watch | open | done_reported | verified | reopened
    urgency_score    INTEGER NOT NULL DEFAULT 0,
    urgency_level    TEXT NOT NULL DEFAULT 'low',
    urgency_reasons  TEXT,               -- JSON list
    inspector_flags  TEXT,               -- JSON list: possible_ice, low_confidence, ice_report, review_report
    hazard_now       TEXT,               -- latest reliable state
    first_seen_at    TEXT NOT NULL,
    last_evidence_at TEXT NOT NULL,
    detected_at      TEXT,               -- when the violation was known (frame time / deadline)
    opened_at        TEXT,
    notified_at      TEXT,
    done_reported_at TEXT,
    verified_at      TEXT,
    reopened_count   INTEGER NOT NULL DEFAULT 0,
    flagged_for_council INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_zone ON alerts(zone_id, status);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);

CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id      INTEGER REFERENCES alerts(id),
    source        TEXT NOT NULL,
    camera_id     TEXT NOT NULL,
    zone_id       TEXT NOT NULL,
    lat           REAL NOT NULL,
    lon           REAL NOT NULL,
    timestamp     TEXT NOT NULL,
    hazard_class  TEXT NOT NULL,
    blocked_share REAL NOT NULL,
    confidence    REAL NOT NULL,
    frame_url     TEXT,
    crop_url      TEXT,
    received_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_alert ON signals(alert_id);

CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id      INTEGER REFERENCES alerts(id),
    ticket        TEXT NOT NULL UNIQUE,  -- random code the resident can check
    channel       TEXT NOT NULL,         -- web | telegram | replay
    photo_path    TEXT,
    lat           REAL NOT NULL,
    lon           REAL NOT NULL,
    passable      TEXT NOT NULL,         -- no | partly | yes
    hazard        TEXT,                  -- snow | ice | icicles | other
    place_type    TEXT,                  -- sidewalk | crossing | ramp | stop | other
    comment       TEXT,
    device_id     TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    relevant      TEXT NOT NULL,         -- accept | review | reject
    ai_score      REAL,
    ai_hint       TEXT,
    ai_note       TEXT,
    counted       INTEGER NOT NULL DEFAULT 0,  -- counts towards urgency (accepted, first vote of device)
    duplicate     INTEGER NOT NULL DEFAULT 0,  -- same device already voted on this alert
    moderated_by  TEXT,
    received_at   TEXT NOT NULL,
    photo_sha256  TEXT,                  -- spam: exact copy
    photo_dhash   TEXT,                  -- spam: near copy (64-bit difference hash)
    ip_hash       TEXT,                  -- spam: salted hash, never the raw IP
    reuse_of      INTEGER                -- same photo as this earlier report
);
CREATE INDEX IF NOT EXISTS idx_reports_alert ON reports(alert_id);

CREATE TABLE IF NOT EXISTS status_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id    INTEGER NOT NULL REFERENCES alerts(id),
    from_status TEXT,
    to_status   TEXT NOT NULL,
    actor       TEXT NOT NULL,     -- system | inspector:<name> | contractor:<id>
    at          TEXT NOT NULL,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_alert ON status_history(alert_id);

CREATE TABLE IF NOT EXISTS devices (      -- blocked senders (spam)
    device_id     TEXT PRIMARY KEY,
    blocked_until TEXT NOT NULL,
    blocked_by    TEXT,
    reason        TEXT,
    at            TEXT
);

CREATE TABLE IF NOT EXISTS spam_events (  -- refused attempts (no photo kept)
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT,
    ip_hash   TEXT,
    reason    TEXT NOT NULL,
    at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spam_at ON spam_events(at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if str(self.path) != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        self._migrate(conn)
        return conn

    # columns added after the first release; ALTER keeps existing databases working
    MIGRATIONS = (("reports", "photo_sha256", "TEXT"), ("reports", "photo_dhash", "TEXT"),
                  ("reports", "ip_hash", "TEXT"), ("reports", "reuse_of", "INTEGER"))

    def _migrate(self, conn) -> None:
        for table, col, typ in self.MIGRATIONS:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_device ON reports(device_id, received_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_sha ON reports(photo_sha256)")

    def reset(self) -> None:
        with self.lock:
            self.conn.executescript(
                "DROP TABLE IF EXISTS status_history; DROP TABLE IF EXISTS signals;"
                "DROP TABLE IF EXISTS spam_events; DROP TABLE IF EXISTS devices;"
                "DROP TABLE IF EXISTS reports; DROP TABLE IF EXISTS alerts;")
            self.conn.executescript(SCHEMA)
            self._migrate(self.conn)

    def q(self, sql: str, args=()) -> list:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql: str, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchone()

    def run(self, sql: str, args=()) -> int:
        with self.lock:
            return self.conn.execute(sql, args).lastrowid
