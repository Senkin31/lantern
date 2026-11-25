"""Settings from the environment (.env in the repo root is read if present).

All durations are ordinary hours on the app clock (clock.now()). The demo speeds the
clock up with POST /demo/clock instead of shrinking the rules (brief v3).
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
        elif " #" in value or "\t#" in value:  # inline comment after an unquoted value
            value = value.split(" #")[0].split("\t#")[0].rstrip()
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

        # clearing deadline: 08:00 / 22:00 Riga time from POST /snowfalls (app/rules.py), no CLEARING_HOURS
        self.fix_hours = env_float("FIX_HOURS", 24.0)                  # act or notice: 24 h to fix
        self.act_confidence = env_float("ACT_CONFIDENCE", 0.7)         # camera evidence strong enough for an act
        self.problem_place_days = env_float("PROBLEM_PLACE_DAYS", 30.0)  # reopened here recently -> check list
        self.inspection_hours = env("INSPECTION_HOURS", "08:30-17:00")
        self.demo_endpoints = env("DEMO_ENDPOINTS", "1") not in ("0", "false", "no")

        self.merge_radius_m = env_float("MERGE_RADIUS_M", 30.0)
        self.merge_window_hours = env_float("MERGE_WINDOW_HOURS", 6.0)
        self.reopen_after_minutes = env_float("REOPEN_AFTER_MINUTES", 0.0)  # snow after "done" -> reopened
        self.low_confidence = env_float("LOW_CONFIDENCE", 0.5)
        self.notify_kpi_minutes = env_float("NOTIFY_KPI_MINUTES", 15.0)

        self.tile_url = env("TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.tile_attribution = env(
            "TILE_ATTRIBUTION", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors')
        self.images_credit = env("IMAGES_CREDIT", "Images: Fintraffic / digitraffic.fi, CC BY 4.0")
        self.source_url = env("SOURCE_URL", "https://github.com/Senkin31/lantern")
        self.tick_seconds = env_float("TICK_SECONDS", 1.0)

        # spam protection (app/spam.py); windows run on the app clock like every other rule
        self.rate_device_hour = int(env_float("RATE_DEVICE_HOUR", 6))
        self.rate_device_day = int(env_float("RATE_DEVICE_DAY", 20))
        self.rate_ip_hour = int(env_float("RATE_IP_HOUR", 30))
        self.auto_block_rejects = int(env_float("AUTO_BLOCK_REJECTS", 3))
        self.auto_block_duplicates = int(env_float("AUTO_BLOCK_DUPLICATES", 5))
        self.auto_block_hours = env_float("AUTO_BLOCK_HOURS", 24.0)
        self.same_photo_days = env_float("SAME_PHOTO_DAYS", 7.0)
        self.dhash_distance = int(env_float("DHASH_DISTANCE", 5))
        # lat_min,lon_min,lat_max,lon_max - reports outside are refused; empty = no check. Default: Riga
        area = env("SERVICE_AREA", "56.85,23.90,57.10,24.35")
        try:
            self.service_area = tuple(float(x) for x in area.split(",")) if area.strip() else None
            if self.service_area is not None and len(self.service_area) != 4:
                self.service_area = None
        except ValueError:
            self.service_area = None
        # callers allowed to pass their own device_id (bot, replay script on this machine)
        self.trusted_hosts = {h.strip() for h in env("TRUSTED_HOSTS", "127.0.0.1,::1").split(",") if h.strip()}
        self.internal_api_key = env("INTERNAL_API_KEY", "")


settings = Settings()
