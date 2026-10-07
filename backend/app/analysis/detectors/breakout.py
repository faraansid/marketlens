"""Horizontal-resistance Breakout detector.

Methodology
-----------
Resistance at bar b is the highest high in the `resistance_lookback` bars
before b, using only bars at least `min_resistance_age` old (so the level is
an established ceiling, not yesterday's high).

* A breakout event is the most recent bar (within `fail_window`) whose close
  first exceeds its resistance by `breakout_buffer_pct`.
* confirmed  - breakout-bar volume >= `volume_multiple` x 50-day average and
               price is still at/above the level.
* potential  - (a) a breakout without volume confirmation, (b) a breakout
               that is back testing its level, or (c) no breakout yet but price
               is within `near_pct` below resistance with contracting
               volatility (ATR10/ATR50 <= `atr_contraction_max`) or rising
               volume, and the trend is not down.
* failed     - a breakout within `fail_window` bars after which price closed
               back below the level by more than `fail_buffer_pct`.
* Breakouts already more than `max_extension_pct` above the level are
  dropped: the move has happened and the level no longer defines the risk.

Confidence blends volume expansion, close location within the bar's range,
trend score, relative strength, margin/proximity to the level and how long
the resistance had held (base length).
"""
from __future__ import annotations

from app.analysis.base import AnalysisContext, Detection, Detector, r
from app.analysis.indicators import atr, lin_score, swing_points

DOWN_TRENDS = {"Downtrend", "Strong Downtrend"}


class BreakoutDetector(Detector):
    name = "breakout"

    def detect(self, ctx: AnalysisContext) -> list[Detection]:
        cfg = ctx.config.breakout
        df = ctx.df
        n = len(df)
        L, age = cfg.resistance_lookback, cfg.min_resistance_age
        if n < L + cfg.fail_window + 5:
            return []
        high, low, close = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
        up = 1 + cfg.breakout_buffer_pct / 100

        def resistance(b: int) -> tuple[float, int]:
            seg = high[b - L : b - age + 1]
            p = int(seg.argmax())
            return float(seg[p]), b - (b - L + p)  # level, bars since the high

        event = None
        for b in range(n - 1, n - 1 - cfg.fail_window, -1):
            lvl, lvl_age = resistance(b)
            if close[b] > lvl * up and close[b - 1] <= lvl * up:
                event = (b, lvl, lvl_age)
                break

        c = float(close[-1])
        trend_label = ctx.trend.label if ctx.trend else None
        status: str | None = None
        if event:
            b, level, level_age = event
            if (c / level - 1) * 100 > cfg.max_extension_pct:
                return []  # already far above the level: no longer an actionable setup
            bars_ago = n - 1 - b
            vr_bo = ctx.volume_ratio(b)
            if c < level * (1 - cfg.fail_buffer_pct / 100):
                status = "failed"
            elif c >= level and vr_bo is not None and vr_bo >= cfg.volume_multiple:
                status = "confirmed"
            else:
                status = "potential"
            ref_bar = b
        else:
            level, level_age = resistance(n - 1)
            bars_ago, vr_bo, ref_bar = None, None, n - 1
            dist = (c / level - 1) * 100
            a = atr(df, 10).iloc[-1] / atr(df, 50).iloc[-1] if n > 60 else None
            vr_now = ctx.volume_ratio()
            contracting = a is not None and a <= cfg.atr_contraction_max
            vol_pickup = vr_now is not None and vr_now >= 1.2
            if -cfg.near_pct <= dist <= cfg.breakout_buffer_pct and trend_label not in DOWN_TRENDS and (
                contracting or vol_pickup
            ):
                status = "potential"
        if status is None:
            return []

        dist = (c / level - 1) * 100
        rng = high[ref_bar] - low[ref_bar]
        close_loc = (close[ref_bar] - low[ref_bar]) / rng if rng > 0 else 0.5
        vr_ref = vr_bo if vr_bo is not None else ctx.volume_ratio()
        margin = lin_score(dist, 0, 3) if event else lin_score(dist, -cfg.near_pct, 0)
        score = 100 * (
            0.25 * lin_score(vr_ref, 1.0, 3.0)
            + 0.10 * close_loc
            + 0.20 * (lin_score(ctx.trend.score, -25, 75) if ctx.trend else 0.3)
            + 0.15 * (lin_score(ctx.rs_rating, 40, 95) if ctx.rs_rating is not None else 0.4)
            + 0.15 * margin
            + 0.15 * lin_score(level_age, age, 40)
        )
        if score < cfg.min_confidence and status != "failed":
            return []

        swings = swing_points(df.iloc[-60:], k=3)
        lows = [p.price for p in swings if p.kind == "L" and p.price < c]
        support = max(lows) if lows else float(df["low"].iloc[-20:].min())

        return [
            Detection(
                symbol=ctx.symbol,
                pattern=self.name,
                confidence=round(score, 1),
                status=status,
                current_price=r(c),
                support=r(support),
                resistance=r(level),
                breakout_level=r(level),
                volume_current=ctx.last_volume,
                volume_avg=r(ctx.avg_volume_50, 0),
                volume_ratio=r(ctx.volume_ratio()),
                trend=trend_label,
                metrics={
                    "resistanceLookbackBars": L,
                    "resistanceAgeBars": level_age,
                    "distanceToLevelPct": r(dist),
                    "breakoutBarsAgo": bars_ago,
                    "breakoutVolumeRatio": r(vr_bo),
                    "closeLocation": r(close_loc, 3),
                    "rsRating": ctx.rs_rating,
                    "trendScore": ctx.trend.score if ctx.trend else None,
                    "sessionPartial": ctx.session_partial,
                },
            )
        ]
