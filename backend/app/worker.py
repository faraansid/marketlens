"""Standalone background worker: `python -m app.worker`.

Use this in production (with RUN_SCHEDULER_IN_API=false on the API) so that
API processes stay lightweight and can be scaled independently.
`python -m app.worker --once` runs a single refresh and exits (useful for
cron/systemd timers or a first manual load).
"""
from __future__ import annotations

import argparse
import logging
import signal
import threading

from app.config import get_settings
from app.db.session import init_db
from app.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="MarketLens market-data worker")
    parser.add_argument("--once", action="store_true", help="run one refresh and exit")
    args = parser.parse_args()

    s = get_settings()
    setup_logging(s.log_level)
    init_db()
    from app.bootstrap import run_bootstrap

    run_bootstrap()
    log = logging.getLogger("worker")

    if args.once:
        from app.pipeline.refresh import run_market_refresh

        run_market_refresh(trigger="manual")
        return

    from app.pipeline.scheduler import build_scheduler

    sched = build_scheduler()
    sched.start()
    log.info("Worker started; refreshing every %d minutes", s.refresh_interval_minutes)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    while not stop.wait(1):  # short waits keep Ctrl+C responsive on Windows
        pass
    sched.shutdown(wait=False)
    log.info("Worker stopped")


if __name__ == "__main__":
    main()
