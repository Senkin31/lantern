"""UTC time helpers and the app clock (brief v3: every rule reads clock.now(), never datetime.now()).

The clock is real UTC time unless
- a test freezes it with set() / advance(), or
- the demo speeds it up with POST /demo/clock {scenario_start, real_start, factor}:
  now = scenario_start + (real now - real_start) * factor.
  With 1 scenario hour = 6 real seconds, factor = 600.
"""
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


def wall_now() -> datetime:
    return datetime.now(timezone.utc)


class Clock:
    """Real UTC time, a frozen time (tests), or an accelerated demo time (DemoClock)."""

    def __init__(self) -> None:
        self._fixed: Optional[datetime] = None
        self._demo: Optional[tuple] = None  # (scenario_start, real_start, factor)

    def now(self) -> datetime:
        if self._fixed is not None:
            return self._fixed
        if self._demo is not None:
            scenario_start, real_start, factor = self._demo
            return scenario_start + (wall_now() - real_start) * factor
        return wall_now()

    # tests
    def set(self, dt: Optional[datetime]) -> None:
        self._fixed = dt

    def advance(self, **kw) -> None:
        self._fixed = self.now() + timedelta(**kw)

    # demo (POST /demo/clock)
    def configure(self, scenario_start: datetime, real_start: Optional[datetime] = None,
                  factor: float = 1.0) -> None:
        if factor <= 0:
            raise ValueError("factor must be > 0")
        self._fixed = None
        self._demo = (scenario_start, real_start or wall_now(), float(factor))

    def reset(self) -> None:
        self._fixed = None
        self._demo = None

    def describe(self) -> dict:
        d = {"now": fmt_ts(self.now()), "mode": "real"}
        if self._fixed is not None:
            d["mode"] = "frozen"
        elif self._demo is not None:
            s, r, f = self._demo
            d.update({"mode": "demo", "scenario_start": fmt_ts(s), "real_start": fmt_ts(r), "factor": f})
        return d


clock = Clock()
