import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_ml_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # yfinance / urllib3 are very chatty at INFO/DEBUG.
    for noisy in ("yfinance", "urllib3", "peewee", "apscheduler.executors.default", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._ml_configured = True  # type: ignore[attr-defined]
