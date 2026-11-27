"""Clearing deadline by regulation RD-24-270-sn (brief v3, "1. Срок уборки").

All times in the database and API are UTC; deadlines are counted on the Riga clock
(Europe/Riga, UTC+2 in winter: 08:00 Riga = 06:00 UTC).

    snowfall ended (Riga time)   ->  clearing deadline
    before 08:00                 ->  08:00 the same day
    08:00-22:00                  ->  22:00 the same day
    after 22:00                  ->  08:00 the next day
    snowfall unknown             ->  08:00 of the day the snow was seen

Kept small on purpose, so it can be compared line by line with mock/rules_reference.py.
"""
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

RIGA = ZoneInfo("Europe/Riga")
MORNING = time(8, 0)
EVENING = time(22, 0)


def to_riga(dt: datetime) -> datetime:
    return dt.astimezone(RIGA)


def _at(day, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=RIGA).astimezone(timezone.utc)


def deadline_after_snowfall(snowfall_end: datetime) -> datetime:
    local = to_riga(snowfall_end)
    if local.time() < MORNING:
        return _at(local.date(), MORNING)
    if local.time() < EVENING:
        return _at(local.date(), EVENING)
    return _at(local.date() + timedelta(days=1), MORNING)


def deadline_without_snowfall(seen_at: datetime) -> datetime:
    return _at(to_riga(seen_at).date(), MORNING)


def clearing_deadline(snowfall_end: Optional[datetime], seen_at: datetime) -> datetime:
    return deadline_after_snowfall(snowfall_end) if snowfall_end else deadline_without_snowfall(seen_at)


def fmt_riga(dt: Optional[datetime]) -> Optional[str]:
    return to_riga(dt).strftime("%d.%m.%Y %H:%M") if dt else None
