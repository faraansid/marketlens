"""PatternDetectionEngine: runs every registered detector over one symbol.

    PatternDetectionEngine
     ├── UptrendDetector
     ├── DowntrendDetector
     ├── FallingWedgeDetector
     ├── VCPDetector
     └── BreakoutDetector

Adding a pattern = implement `Detector` and append it to `DEFAULT_DETECTORS`.
A failing detector is logged and skipped; it never aborts the scan.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.analysis.base import AnalysisContext, Detection, Detector, TrendResult, chart_tail
from app.analysis.config import PatternConfig
from app.analysis.detectors.breakout import BreakoutDetector
from app.analysis.detectors.falling_wedge import FallingWedgeDetector
from app.analysis.detectors.trend import DowntrendDetector, UptrendDetector, classify_trend
from app.analysis.detectors.vcp import VCPDetector

log = logging.getLogger(__name__)

DEFAULT_DETECTORS: list[type[Detector]] = [
    UptrendDetector,
    DowntrendDetector,
    FallingWedgeDetector,
    VCPDetector,
    BreakoutDetector,
]


def relative_performance(close: pd.Series, bench: pd.Series | None) -> float | None:
    """IBD-style weighted relative performance vs. the benchmark:
    40% weight on the last 3 months, 20% each on the three quarters before
    (when history allows). Returned as a raw number; the pipeline converts the
    universe-wide values into a 1-99 percentile rating."""
    if bench is None or bench.empty or len(close) < 64:
        return None
    joined = pd.concat([close.rename("s"), bench.rename("b")], axis=1, join="inner").dropna()
    if len(joined) < 64:
        return None
    total, wsum = 0.0, 0.0
    for periods, w in ((63, 0.4), (126, 0.2), (189, 0.2), (252, 0.2)):
        if len(joined) > periods:
            s_ret = joined["s"].iloc[-1] / joined["s"].iloc[-1 - periods] - 1
            b_ret = joined["b"].iloc[-1] / joined["b"].iloc[-1 - periods] - 1
            total += w * (s_ret - b_ret)
            wsum += w
    return float(total / wsum * 100) if wsum else None


class PatternDetectionEngine:
    def __init__(self, config: PatternConfig, detectors: list[type[Detector]] | None = None):
        self.config = config
        self.detectors: list[Detector] = [d() for d in (detectors or DEFAULT_DETECTORS)]

    def trend(self, df: pd.DataFrame) -> TrendResult | None:
        return classify_trend(df, self.config.trend)

    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        *,
        trend: TrendResult | None = None,
        rs_rating: float | None = None,
        benchmark_close: pd.Series | None = None,
        session_partial: bool = False,
    ) -> list[Detection]:
        if df is None or len(df) < 30 or not np.isfinite(df["close"].iloc[-1]):
            return []
        ctx = AnalysisContext(
            symbol=symbol,
            df=df,
            config=self.config,
            trend=trend if trend is not None else self.trend(df),
            rs_rating=rs_rating,
            benchmark_close=benchmark_close,
            session_partial=session_partial,
        )
        out: list[Detection] = []
        chart = chart_tail(df, self.config.chart_points)
        for det in self.detectors:
            try:
                for d in det.detect(ctx):
                    d.chart = chart
                    out.append(d)
            except Exception:  # noqa: BLE001
                log.exception("Detector %s failed for %s", det.name, symbol)
        return out
