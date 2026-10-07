"""Rate limiting + retry helpers shared by providers."""
from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from app.providers.base import ProviderError, RateLimitError

log = logging.getLogger(__name__)
T = TypeVar("T")


class RateLimiter:
    """Minimum spacing between calls (thread-safe). Simple and predictable,
    which is what free endpoints need."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0
        self._penalty_until = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            target = max(self._last + self.min_interval, self._penalty_until)
            if target > now:
                time.sleep(target - now)
            self._last = time.monotonic()

    def penalize(self, seconds: float) -> None:
        """Back off globally after a rate-limit response."""
        with self._lock:
            self._penalty_until = max(self._penalty_until, time.monotonic() + seconds)


def is_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    name = type(exc).__name__
    text = str(exc).lower()
    return "ratelimit" in name.lower() or "too many requests" in text or "429" in text


def with_retry(
    fn: Callable[[], T],
    *,
    limiter: RateLimiter | None,
    retries: int,
    backoff: float,
    what: str,
) -> T:
    """Run `fn` with rate limiting and exponential backoff (+ jitter).

    Rate-limit errors back off longer and also slow down every other caller
    sharing the limiter.
    """
    attempt = 0
    while True:
        if limiter:
            limiter.wait()
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - providers raise many exception types
            attempt += 1
            rl = is_rate_limit(exc)
            if attempt > retries:
                if rl:
                    raise RateLimitError(f"{what}: rate limited after {retries} retries") from exc
                raise ProviderError(f"{what}: {exc}") from exc
            delay = backoff * (2 ** (attempt - 1)) * (3 if rl else 1) + random.uniform(0, 0.5)
            if rl and limiter:
                limiter.penalize(delay)
            log.warning("%s failed (attempt %d/%d, %s); retrying in %.1fs", what, attempt, retries,
                        "rate-limited" if rl else type(exc).__name__, delay)
            time.sleep(delay)
