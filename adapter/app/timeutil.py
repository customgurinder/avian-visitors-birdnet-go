"""Date/time helpers shared by the transform layer.

The container's local clock (set TZ in compose) is the station clock, matching
how the original PHP facade used SQLite's localtime for day boundaries.
"""
from __future__ import annotations

from datetime import datetime, timedelta

FMT_DT = "%Y-%m-%d %H:%M:%S"
FMT_DATE = "%Y-%m-%d"


def now() -> datetime:
    return datetime.now()


def valid_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, FMT_DATE)
        return True
    except (ValueError, TypeError):
        return False


def normalize_dt(value: str | None) -> str | None:
    """Coerce a BirdNET-Go datetime/timestamp into 'YYYY-MM-DD HH:MM:SS'.

    Accepts RFC3339 ('2024-05-01T06:12:33+01:00'), space-separated, or
    date-only strings. Returns None for empty input.
    """
    if not value:
        return None
    s = str(value).strip().replace("T", " ")
    # drop timezone offset / Z and fractional seconds
    for cut in ("+", "Z"):
        if cut in s:
            s = s.split(cut)[0]
    if "." in s:
        s = s.split(".")[0]
    s = s.strip()
    if len(s) == 10:  # date only
        return f"{s} 00:00:00"
    return s[:19]


def date_of(value: str | None) -> str | None:
    n = normalize_dt(value)
    return n[:10] if n else None


def parse_dt(value: str | None) -> datetime | None:
    n = normalize_dt(value)
    if not n:
        return None
    try:
        return datetime.strptime(n, FMT_DT)
    except ValueError:
        try:
            return datetime.strptime(n[:10], FMT_DATE)
        except ValueError:
            return None


def date_context(date_param: str | None) -> dict:
    """Reproduce birdnet-api.php's dateContext().

    A stats date is interpreted in the station clock. 'today' ends at the
    current second; a historical date ends at 23:59:59.
    """
    today_dt = now()
    today = today_dt.strftime(FMT_DATE)
    asked = (date_param or "").strip() or None
    if asked is not None:
        if not valid_iso_date(asked) or asked > today:
            raise ValueError("bad date")
    date = asked or today
    is_today = date == today
    if is_today:
        anchor = today_dt
    else:
        anchor = datetime.strptime(f"{date} 23:59:59", FMT_DT)
    return {"date": date, "today": today, "is_today": is_today, "anchor": anchor}


def days_ago(anchor: datetime, days: int) -> str:
    return (anchor - timedelta(days=days)).strftime(FMT_DATE)
