"""Trend classification + Uptrend / Downtrend detectors.

Methodology
-----------
The trend score is a weighted sum of five components, each scaled to [-1, +1],
multiplied by 100 to give a score in [-100, +100]:

1. price_vs_ma      Close relative to SMA50 and SMA200 (each worth +/-0.5).
                    Falls back to SMA20/SMA50 without enough history for SMA200.
2. ma_alignment     Ordering of SMA20 > SMA50 > SMA200 (+1 fully bullish,
                    -1 fully bearish, partial credit for partially ordered).
   For 1 and 2, each difference is divided by `atr_scale` x ATR14 and
   clipped to [-1, 1], so a price hugging a flat average in a range scores
   near zero instead of casting a full bullish/bearish vote.
3. ma_slope         Percent change of SMA50 over `ma_slope_lookback` bars,
                    scaled so `ma_slope_full_scale_pct` maps to +/-1.
4. swing_structure  Using confirmed fractal swing points over the last
                    `swing_lookback` bars, the share of higher highs and higher
                    lows (+) vs lower highs and lower lows (-) among the last
                    three pairs of swings — classic Dow-theory structure.
5. momentum         `return_lookback`-bar return scaled by
                    `return_full_scale_pct`.

Classification (thresholds are configurable):
    score >= strong        -> Strong Uptrend
    score >= trend         -> Uptrend
    score <= -strong       -> Strong Downtrend
    score <= -trend        -> Downtrend
    otherwise              -> Neutral
"""
from __future__ import annotations

import numpy as np

from app.analysis.base import AnalysisContext, Detection, Detector, TrendResult, r
from app.analysis.config import TrendConfig
from app.analysis.indicators import atr, last, pct_change, slope_pct, sma, swing_points

STRONG_UP, UP, NEUTRAL, DOWN, STRONG_DOWN = (
    "Strong Uptrend", "Uptrend", "Neutral", "Downtrend", "Strong Downtrend",
)


def _sign(x: float) -> float:
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


def classify_trend(df, cfg: TrendConfig) -> TrendResult | None:
    if len(df) < cfg.min_bars:
        return None
    close = df["close"]
    c = float(close.iloc[-1])
    s20, s50, s200 = last(sma(close, 20)), last(sma(close, 50)), last(sma(close, 200))
    comps: dict[str, float | None] = {}

    # Distances are measured in ATRs so that a price hovering a hair above or
    # below a flat average (a range) does not count as a full trend vote.
    a = last(atr(df, 14)) or c * 0.02
    unit = cfg.atr_scale * a

    def vote(diff: float) -> float:
        return float(np.clip(diff / unit, -1, 1))

    # 1. price vs moving averages
    long_ma = s200 if s200 is not None else s50
    short_ma = s50 if s200 is not None else s20
    comps["price_vs_ma"] = 0.5 * vote(c - short_ma) + 0.5 * vote(c - long_ma) if short_ma and long_ma else None

    # 2. moving-average alignment
    if s20 and s50 and s200:
        comps["ma_alignment"] = float(np.mean([vote(s20 - s50), vote(s50 - s200), vote(s20 - s200)]))
    elif s20 and s50:
        comps["ma_alignment"] = vote(s20 - s50) * 0.5
    else:
        comps["ma_alignment"] = None

    # 3. SMA50 slope
    sl = slope_pct(sma(close, 50), cfg.ma_slope_lookback)
    comps["ma_slope"] = float(np.clip(sl / cfg.ma_slope_full_scale_pct, -1, 1)) if sl is not None else None

    # 4. swing structure (HH/HL vs LH/LL)
    window = df.iloc[-cfg.swing_lookback :]
    swings = swing_points(window, k=cfg.swing_k)
    highs = [p.price for p in swings if p.kind == "H"][-4:]
    lows = [p.price for p in swings if p.kind == "L"][-4:]
    votes = [_sign(b - a) for a, b in zip(highs, highs[1:])] + [_sign(b - a) for a, b in zip(lows, lows[1:])]
    comps["swing_structure"] = float(np.mean(votes)) if votes else None

    # 5. momentum
    ret = pct_change(close, cfg.return_lookback)
    comps["momentum"] = float(np.clip(ret / cfg.return_full_scale_pct, -1, 1)) if ret is not None else None

    total_w = sum(cfg.weights[k] for k, v in comps.items() if v is not None)
    if total_w == 0:
        return None
    score = 100 * sum(cfg.weights[k] * v for k, v in comps.items() if v is not None) / total_w

    if score >= cfg.strong_threshold:
        label = STRONG_UP
    elif score >= cfg.trend_threshold:
        label = UP
    elif score <= -cfg.strong_threshold:
        label = STRONG_DOWN
    elif score <= -cfg.trend_threshold:
        label = DOWN
    else:
        label = NEUTRAL
    comps.update({"sma20": r(s20), "sma50": r(s50), "sma200": r(s200), "return_pct": r(ret)})
    return TrendResult(label=label, score=round(score, 1), components=comps)


def _trend_levels(ctx: AnalysisContext) -> tuple[float | None, float | None]:
    """Nearest confirmed swing low below price (support) and swing high above
    price (resistance) over the last ~6 months."""
    swings = swing_points(ctx.df.iloc[-130:], k=3)
    c = ctx.close
    lows = [p.price for p in swings if p.kind == "L" and p.price < c]
    highs = [p.price for p in swings if p.kind == "H" and p.price > c]
    support = max(lows) if lows else None
    resistance = min(highs) if highs else None
    return support, resistance


class _TrendDetectorBase(Detector):
    labels: tuple[str, ...] = ()

    def detect(self, ctx: AnalysisContext) -> list[Detection]:
        t = ctx.trend
        if t is None or t.label not in self.labels:
            return []
        support, resistance = _trend_levels(ctx)
        return [
            Detection(
                symbol=ctx.symbol,
                pattern=self.name,
                confidence=min(100.0, abs(t.score)),
                status="active",
                current_price=r(ctx.close),
                support=r(support),
                resistance=r(resistance),
                breakout_level=None,
                volume_current=ctx.last_volume,
                volume_avg=r(ctx.avg_volume_50, 0),
                volume_ratio=r(ctx.volume_ratio()),
                trend=t.label,
                metrics={
                    "trendScore": t.score,
                    **{k: (r(v, 3) if isinstance(v, float) else v) for k, v in t.components.items()},
                    "rsRating": ctx.rs_rating,
                },
            )
        ]


class UptrendDetector(_TrendDetectorBase):
    name = "uptrend"
    labels = (STRONG_UP, UP)


class DowntrendDetector(_TrendDetectorBase):
    name = "downtrend"
    labels = (STRONG_DOWN, DOWN)
