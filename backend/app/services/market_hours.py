"""NSE session clock.

Regular session: 09:15-15:30 IST, Monday-Friday. Exchange holidays are not
hardcoded; instead `market_status` also checks whether the NIFTY 50 actually
printed recently, so a holiday shows as closed.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
OPEN, CLOSE = time(9, 15), time(15, 30)


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


def in_session_window(ts: datetime | None = None) -> bool:
    ts = (ts or now_ist()).astimezone(IST)
    return ts.weekday() < 5 and OPEN <= ts.time() <= CLOSE


def market_status(last_index_print: datetime | None, now: datetime | None = None) -> dict:
    """Return {'state': open|closed|pre_open, 'label': ...}."""
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    if now.weekday() >= 5:
        return {"state": "closed", "label": "Closed · Weekend"}
    if now.time() < OPEN:
        if now.time() >= time(9, 0):
            return {"state": "pre_open", "label": "Pre-open"}
        return {"state": "closed", "label": "Closed · Opens 09:15 IST"}
    if now.time() > CLOSE:
        return {"state": "closed", "label": "Closed · Session ended 15:30 IST"}
    # Inside session hours: confirm with data (holidays have no prints today).
    if last_index_print is not None and last_index_print.astimezone(IST).date() != now.date():
        if now - last_index_print.astimezone(IST) > timedelta(hours=2):
            return {"state": "closed", "label": "Closed · Exchange holiday"}
    return {"state": "open", "label": "Market open"}
