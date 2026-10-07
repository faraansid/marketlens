from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.serializers import instrument_out, iso, job_out
from app.auth.deps import require_admin, require_user
from app.config import get_settings
from app.db.models import EquitySnapshot, JobRun, MarketInstrument, PatternDetection, User
from app.db.session import get_db
from app.pipeline.refresh import latest_successful_run, run_market_refresh
from app.services.market_hours import IST, market_status

router = APIRouter(prefix="/api", tags=["market"])
log = logging.getLogger(__name__)


def _next_run(now: datetime) -> datetime:
    step = get_settings().refresh_interval_minutes
    ist = now.astimezone(IST).replace(second=0, microsecond=0)
    minutes = (ist.minute // step + 1) * step
    return (ist.replace(minute=0) + timedelta(minutes=minutes)).astimezone(timezone.utc)


@router.get("/market/status")
def get_market_status(db: Session = Depends(get_db), user: User = Depends(require_user)):
    nifty = db.get(MarketInstrument, "NIFTY50")
    last_ok = latest_successful_run(db)
    last_run = db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(1)).first()
    now = datetime.now(timezone.utc)
    return {
        "market": market_status(nifty.market_time if nifty else None, now),
        "lastSuccessfulUpdate": iso(last_ok.finished_at) if last_ok else None,
        "lastRun": job_out(last_run, include_error=user.is_admin),
        "isRefreshing": bool(last_run and last_run.status == "running"),
        "nextScheduledRun": iso(_next_run(now)),
        "refreshIntervalMinutes": get_settings().refresh_interval_minutes,
        "serverTime": iso(now),
    }


@router.get("/market/overview")
def get_market_overview(db: Session = Depends(get_db), _: User = Depends(require_user)):
    instruments = db.scalars(select(MarketInstrument).order_by(MarketInstrument.sort_order)).all()
    breadth = db.execute(
        select(
            func.count(),
            func.sum(case((EquitySnapshot.change_1d_pct > 0, 1), else_=0)),
            func.sum(case((EquitySnapshot.change_1d_pct < 0, 1), else_=0)),
            func.max(EquitySnapshot.as_of),
        )
    ).one()
    patterns = dict(
        db.execute(
            select(PatternDetection.pattern, func.count())
            .where(PatternDetection.is_active.is_(True)).group_by(PatternDetection.pattern)
        ).all()
    )
    return {
        "instruments": [instrument_out(m) for m in instruments],
        "breadth": {
            "total": breadth[0] or 0,
            "advancers": int(breadth[1] or 0),
            "decliners": int(breadth[2] or 0),
            "asOf": iso(breadth[3]),
        },
        "patternCounts": patterns,
    }


_manual_lock = threading.Lock()


@router.post("/jobs/refresh", status_code=202)
def trigger_refresh(_: User = Depends(require_admin)):
    """Admin-only: start a refresh now (runs in a background thread)."""
    if not _manual_lock.acquire(blocking=False):
        return {"message": "A refresh is already starting."}

    def _run():
        try:
            run_market_refresh(trigger="manual")
        finally:
            _manual_lock.release()

    threading.Thread(target=_run, name="manual-refresh", daemon=True).start()
    return {"message": "Refresh started. Data will update when the job completes."}


@router.get("/jobs")
def list_jobs(limit: int = 20, db: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(min(limit, 100))).all()
    return [job_out(j, include_error=user.is_admin) for j in rows]
