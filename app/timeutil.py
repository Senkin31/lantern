"""UTC time helpers and an overridable clock (tests and replays set it)."""
from datetime import datetime, timedelta, timezone
from typing import Optional


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z") or v.endswith("z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fmt_ts(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class Clock:
    """Real UTC time unless frozen with set()."""

    def __init__(self) -> None:
        self._fixed: Optional[datetime] = None

    def now(self) -> datetime:
        return self._fixed or datetime.now(timezone.utc)

    def set(self, dt: Optional[datetime]) -> None:
        self._fixed = dt

    def advance(self, **kw) -> None:
        self._fixed = self.now() + timedelta(**kw)


clock = Clock()
