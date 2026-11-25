"""Settings from the environment (.env in the repo root is read if present).

All rule durations are written in "rule hours". On the demo the camera replay
compresses time, so one rule hour can be a few real seconds: set CLEARING_SECONDS
(printed by mock/send_signals.py) or HOUR_SECONDS and every rule scales with it.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _path(name: str, default: str) -> Path:
    p = Path(env(name, default))
    return p if p.is_absolute() else ROOT / p


class Settings:
    def __init__(self) -> None:
        self.db_path = _path("APP_DB", "data/lantern.db")
        self.upload_dir = _path("UPLOAD_DIR", "data/uploads")
        self.mock_dir = _path("MOCK_DIR", "mock")
        self.cameras_file = _path("CAMERAS_FILE", "config/cameras.json")
        self.cameras_fallback = _path("CAMERAS_FALLBACK", "mock/cameras_mock.json")
        self.contractors_file = _path("CONTRACTORS_FILE", "config/contractors.json")

        self.analyze_url = env("ANALYZE_URL", "")  # empty -> built-in stub (always accept)
        self.analyze_timeout = env_float("ANALYZE_TIMEOUT", 10.0)

        self.clearing_hours = env_float("CLEARING_HOURS", 6.0)
        clearing_seconds = env_float("CLEARING_SECONDS", 0.0)
        hour_seconds = env_float("HOUR_SECONDS", 0.0)
        if hour_seconds <= 0:
            hour_seconds = clearing_seconds / self.clearing_hours if clearing_seconds > 0 else 3600.0
        self.hour_seconds = hour_seconds
        self.snowfall_end = env("SNOWFALL_END", "")  # ISO 8601 UTC, or empty

        self.merge_radius_m = env_float("MERGE_RADIUS_M", 30.0)
        self.merge_window_hours = env_float("MERGE_WINDOW_HOURS", 6.0)
        self.reopen_after_hours = env_float("REOPEN_AFTER_HOURS", 1.0)
        self.low_confidence = env_float("LOW_CONFIDENCE", 0.5)
        self.notify_kpi_minutes = env_float("NOTIFY_KPI_MINUTES", 15.0)

        self.tile_url = env("TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.tile_attribution = env(
            "TILE_ATTRIBUTION", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors')
        self.images_credit = env("IMAGES_CREDIT", "Images: Fintraffic / digitraffic.fi, CC BY 4.0")
        self.source_url = env("SOURCE_URL", "https://github.com/Senkin31/lantern")
        self.tick_seconds = env_float("TICK_SECONDS", 1.0)


settings = Settings()
