"""APScheduler setup for the 30-minute market refresh.

The job runs in a background thread (the pipeline is blocking I/O + pandas).
`max_instances=1` and `coalesce=True` prevent overlapping/duplicated runs in
this process; the `job_runs` table lock prevents overlap across processes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import get_settings
from app.db.models import JobRun
from app.db.session import session_scope
from app.pipeline.refresh import run_market_refresh

log = logging.getLogger("scheduler")


def _data_is_stale(minutes: int) -> bool:
    with session_scope() as db:
        last = db.scalars(
            select(JobRun).where(JobRun.status.in_(("success", "partial")))
            .order_by(JobRun.finished_at.desc()).limit(1)
        ).first()
        return last is None or last.finished_at < datetime.now(timezone.utc) - timedelta(minutes=minutes)


def _on_event(event) -> None:
    if event.code == EVENT_JOB_ERROR:
        log.error("Scheduled job %s raised: %s", event.job_id, event.exception)
    elif event.code == EVENT_JOB_MISSED:
        log.warning("Scheduled job %s missed its run time", event.job_id)


def build_scheduler() -> BackgroundScheduler:
    s = get_settings()
    sched = BackgroundScheduler(timezone="Asia/Kolkata", job_defaults={"coalesce": True, "max_instances": 1,
                                                                       "misfire_grace_time": 600})
    minute = f"*/{s.refresh_interval_minutes}" if s.refresh_interval_minutes < 60 else "0"
    sched.add_job(run_market_refresh, CronTrigger(minute=minute), id="market_refresh",
                  kwargs={"trigger": "schedule"}, replace_existing=True)
    if s.run_on_startup_if_stale and _data_is_stale(s.refresh_interval_minutes):
        log.info("Data is stale or missing; scheduling an immediate refresh")
        sched.add_job(run_market_refresh, id="market_refresh_startup", kwargs={"trigger": "startup"},
                      next_run_time=datetime.now(timezone.utc) + timedelta(seconds=3))
    sched.add_listener(_on_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    return sched
