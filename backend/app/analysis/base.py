"""Common types for detectors and the shared breakout-lifecycle rules."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.analysis.config import BreakoutStatusConfig, PatternConfig


@dataclass
class TrendResult:
    label: str  # Strong Uptrend | Uptrend | Neutral | Downtrend | Strong Downtrend
    score: float  # -100 .. +100
    components: dict[str, float | None] = field(default_factory=dict)


@dataclass
class AnalysisContext:
    """Everything a detector may use for one symbol. Built once per symbol by the engine."""

    symbol: str
    df: pd.DataFrame  # daily OHLCV, oldest -> newest
    config: PatternConfig
    trend: TrendResult | None = None
    rs_rating: float | None = None  # 1..99 percentile of 6-month relative performance
    benchmark_close: pd.Series | None = None
    session_partial: bool = False  # last bar is an in-progress session

    @property
    def close(self) -> float:
        return float(self.df["close"].iloc[-1])

    @property
    def last_volume(self) -> float | None:
        v = self.df["volume"].iloc[-1]
        return None if pd.isna(v) else float(v)

    @property
    def avg_volume_50(self) -> float | None:
        """Average daily volume of the 50 sessions *before* the latest one."""
        v = self.df["volume"].iloc[-51:-1].dropna()
        return float(v.mean()) if len(v) >= 10 and v.mean() > 0 else None

    def volume_ratio(self, idx: int = -1) -> float | None:
        vol = self.df["volume"]
        pos = idx if idx >= 0 else len(vol) + idx
        base = vol.iloc[max(0, pos - 50) : pos].dropna()
        cur = vol.iloc[pos]
        if pd.isna(cur) or len(base) < 10 or base.mean() <= 0:
            return None
        return float(cur / base.mean())


@dataclass
class Detection:
    """Structured detector output (mirrors the API contract)."""

    symbol: str
    pattern: str
    confidence: float  # 0..100
    status: str  # forming | potential | confirmed | failed | active
    current_price: float
    support: float | None = None
    resistance: float | None = None
    breakout_level: float | None = None
    volume_current: float | None = None
    volume_avg: float | None = None
    volume_ratio: float | None = None
    trend: str | None = None
    metrics: dict = field(default_factory=dict)
    chart: list[float] | None = None  # attached by the engine
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "pattern": self.pattern,
            "confidenceScore": round(self.confidence, 1),
            "detectedAt": self.detected_at.isoformat(),
            "currentPrice": self.current_price,
            "support": self.support,
            "resistance": self.resistance,
            "breakoutLevel": self.breakout_level,
            "volumeRatio": self.volume_ratio,
            "trend": self.trend,
            "status": self.status,
        }


class Detector(ABC):
    """A pattern detector. Implementations must be pure (no I/O) and must
    return [] rather than raise when data is insufficient."""

    name: str = "abstract"

    @abstractmethod
    def detect(self, ctx: AnalysisContext) -> list[Detection]: ...


def r(x: float | None, nd: int = 2) -> float | None:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), nd)


@dataclass
class LevelStatus:
    status: str  # forming | potential | confirmed | failed | extended
    breakout_bars_ago: int | None = None
    breakout_volume_ratio: float | None = None
    distance_pct: float | None = None  # (close / level - 1) * 100


def evaluate_level(
    ctx: AnalysisContext,
    level_at: Callable[[int], float],
    cfg: BreakoutStatusConfig,
) -> LevelStatus:
    """Classify price action relative to a breakout level (which may slope,
    e.g. a wedge's upper trendline).

    * confirmed - closed above level (+buffer) within `fail_window` bars on a
                  breakout bar with volume >= volume_multiple x 50d average,
                  and is still above the level.
    * potential - closed above level without volume confirmation, OR is
                  within `near_pct` below the level (an approaching setup).
    * failed    - closed above the level within `fail_window` bars but has now
                  closed back below it by more than `fail_buffer_pct`.
    * extended  - broke out longer ago than `fail_window`, or is already more
                  than `max_extension_pct` above the level; no longer a setup.
    * forming   - none of the above (price still inside the structure).
    """
    close = ctx.df["close"].to_numpy()
    n = len(close)
    last_i = n - 1
    lvl = level_at(last_i)
    up = 1 + cfg.breakout_buffer_pct / 100
    dist = (close[last_i] / lvl - 1) * 100 if lvl > 0 else None

    above = [close[i] > level_at(i) * up for i in range(max(0, n - cfg.fail_window - 1), n)]
    offset = n - len(above)

    if above[-1]:
        # Walk back to the first bar of the current run above the level.
        j = len(above) - 1
        while j > 0 and above[j - 1]:
            j -= 1
        if j == 0 and offset > 0 and close[offset - 1] > level_at(offset - 1) * up:
            return LevelStatus("extended", distance_pct=dist)
        if dist is not None and dist > cfg.max_extension_pct:
            return LevelStatus("extended", distance_pct=dist)
        bo_idx = offset + j
        vr = ctx.volume_ratio(bo_idx)
        status = "confirmed" if (vr is not None and vr >= cfg.volume_multiple) else "potential"
        return LevelStatus(status, last_i - bo_idx, vr, dist)

    if any(above[:-1]) and close[last_i] < lvl * (1 - cfg.fail_buffer_pct / 100):
        idx = max(i for i, a in enumerate(above[:-1]) if a)
        return LevelStatus("failed", last_i - (offset + idx), ctx.volume_ratio(offset + idx), dist)

    if dist is not None and -cfg.near_pct <= dist <= cfg.breakout_buffer_pct:
        return LevelStatus("potential", distance_pct=dist)
    return LevelStatus("forming", distance_pct=dist)


def chart_tail(df: pd.DataFrame, n: int) -> list[float]:
    return [round(float(x), 2) for x in df["close"].iloc[-n:].tolist()]
