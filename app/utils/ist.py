"""
India Standard Time, for anything a person reads.

Timestamps are stored in UTC and must stay that way: UTC is the only spelling
that survives a server moving, a clock changing, or two machines disagreeing.
But nothing a person reads should be in UTC, and until now the date printed
under a stamped signature was exactly that - a document signed at 09:00 in
Bengaluru carried "03:30" on its face, five and a half hours before it
happened.

So: store UTC, print IST, and convert in one place rather than in each caller.

`zoneinfo` is in the standard library from Python 3.9. On a Windows host
without the system zone database it needs `tzdata`, so a fixed +05:30 offset is
kept as a fallback - India has no daylight saving, which makes a fixed offset
exactly right here and nowhere else.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

try:                                    # pragma: no cover - depends on the host
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:                       # pragma: no cover
    IST = timezone(timedelta(hours=5, minutes=30), "IST")

DATE = "%d-%m-%Y"                       # 06-08-2026
DATE_LONG = "%d %b %Y"                  # 06 Aug 2026
DATE_TIME = "%d-%m-%Y, %H:%M"           # 06-08-2026, 14:30
DATE_TIME_LONG = "%d %b %Y, %H:%M"      # 06 Aug 2026, 14:30


def to_ist(value: Optional[datetime]) -> Optional[datetime]:
    """
    Move a stored timestamp into IST.

    A naive value is treated as UTC, because that is what the database holds -
    every writer uses `datetime.utcnow()`, which carries no zone. Guessing
    "local" instead would be right only on a server that happens to run in
    India, which is not a property worth relying on.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)


def now() -> datetime:
    """The current moment, in IST."""
    return datetime.now(IST)


def fmt(value: Optional[datetime], pattern: str = DATE, fallback: str = "") -> str:
    """Format a stored timestamp for somebody to read."""
    local = to_ist(value)
    return local.strftime(pattern) if local else fallback


def today() -> str:
    """Today's date in India, as DD-MM-YYYY."""
    return now().strftime(DATE)
