"""Dates, times and spans as people read them, in UTC like the rest of MINT."""
import calendar
from datetime import datetime, timedelta, timezone

_UNITS = ((86400, "day"), (3600, "hour"), (60, "minute"))
# In English like the rest of MINT: strftime's %b follows the system locale, which Qt sets on Linux.
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def date(moment: datetime, now: datetime) -> str:
    """"5 Nov", with the year when it is not this one: "29 Oct 2024"."""
    moment = _utc(moment)
    text = f"{moment.day} {MONTHS[moment.month - 1][:3]}"
    return text if moment.year == _utc(now).year else f"{text} {moment.year}"


def at(moment: datetime, now: datetime) -> str:
    """"today at 08:43 UTC", "yesterday at 08:43 UTC", "5 Nov at 09:06 UTC"."""
    moment, now = _utc(moment), _utc(now)
    days = (now.date() - moment.date()).days
    day = {0: "today", 1: "yesterday"}.get(days) or date(moment, now)
    return f"{day} at {moment:%H:%M} UTC"


def span(start: datetime, end: datetime, now: datetime) -> str:
    """A time range: "3 Nov 08:00 → 4 Nov 20:00 UTC", "10 Nov 02:44 → 08:44 UTC", "3 Nov, all day UTC",
    "November 2026"."""
    start, end = _utc(start), _utc(end)
    midnight = start.time() == end.time() == datetime.min.time()
    if midnight and start.day == 1 and end - start == timedelta(days=calendar.monthrange(start.year, start.month)[1]):
        return f"{MONTHS[start.month - 1]} {start.year}"
    if midnight and end - start == timedelta(days=1):
        return f"{date(start, now)}, all day UTC"
    until = f"{end:%H:%M}" if end.date() == start.date() else f"{date(end, now)} {end:%H:%M}"
    return f"{date(start, now)} {start:%H:%M} → {until} UTC"


def _count(count: int, unit: str) -> str:
    return f"{count} {unit}{'' if count == 1 else 's'}"


def duration(seconds: float) -> str:
    """"6 hours", "1 day", "90 minutes": in the largest unit it is a whole number of; past an hour, "about 24 hours"."""
    seconds = round(seconds)
    for size, unit in _UNITS:
        if seconds >= size and seconds % size == 0:
            return _count(seconds // size, unit)
    return "about " + _count(round(seconds / 3600), "hour") if seconds >= 3600 else _count(seconds, "second")


def period(seconds: float) -> str:
    """A duration as said after "the last" or "the": "hour", "6 hours", "day"."""
    text = duration(seconds)
    return text[2:] if text.startswith("1 ") else text
