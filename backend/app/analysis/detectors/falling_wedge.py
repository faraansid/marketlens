"""Falling Wedge detector.

Methodology
-----------
A falling wedge is a contracting, downward-sloping price structure: both the
resistance line (through swing highs) and the support line (through swing
lows) decline, but resistance declines faster, so the range narrows toward an
apex. It is generally read as a bullish structure once price breaks above the
upper trendline on rising volume.

For each candidate window length in `lookbacks`:

1. Find confirmed fractal swing highs / lows (k bars each side).
2. Fit least-squares lines through the swing highs (upper) and lows (lower).
3. Require:
   * enough touches on each side (`min_touches_per_side`, `min_total_touches`);
   * upper slope <= `max_upper_slope_pct` (% of price per bar, i.e. falling);
   * lower slope <= `max_lower_slope_pct` (falling or roughly flat);
   * upper slope < lower slope (lines converge) and the apex lies ahead,
     with lower/upper slope ratio <= `max_slope_ratio` (rules out channels);
   * starting width >= `min_start_width_atr` x ATR (a real structure, not noise);
   * width at the end / width at the start <= `max_width_ratio`;
   * at least `min_containment` of closes lie between the lines
     (with an ATR-based tolerance);
   * trendline fit quality (R^2) >= `min_fit_r2` for sides with >= 3 points.
4. Score 0-100 from touches, fit quality, convergence, containment and volume
   contraction during the wedge (volume typically dries up in a wedge).
5. Classify breakout status against the *sloping* upper line using the shared
   lifecycle rules in `evaluate_level` (forming / potential / confirmed /
   failed). Breakouts that happened too long ago are dropped.

The best-scoring window is reported. Support / resistance are the lower /
upper line values at the latest bar; the breakout level is the upper line.
"""
from __future__ import annotations

import numpy as np

from app.analysis.base import AnalysisContext, Detection, Detector, evaluate_level, r
from app.analysis.indicators import atr, fit_line, lin_score, swing_points


class FallingWedgeDetector(Detector):
    name = "falling_wedge"

    def detect(self, ctx: AnalysisContext) -> list[Detection]:
        cfg = ctx.config.falling_wedge
        best: Detection | None = None
        for lb in cfg.lookbacks:
            if len(ctx.df) < lb + 20:
                continue
            det = self._evaluate(ctx, lb)
            if det and (best is None or det.confidence > best.confidence):
                best = det
        return [best] if best and best.confidence >= cfg.min_confidence else []

    def _evaluate(self, ctx: AnalysisContext, lb: int) -> Detection | None:
        cfg = ctx.config.falling_wedge
        df = ctx.df
        n = len(df)
        w = df.iloc[-lb:]
        start = n - lb  # positional offset of the window in df

        swings = swing_points(w, k=cfg.swing_k)
        hi = [(p.idx, p.price) for p in swings if p.kind == "H"]
        lo = [(p.idx, p.price) for p in swings if p.kind == "L"]
        if len(hi) < cfg.min_touches_per_side or len(lo) < cfg.min_touches_per_side:
            return None
        if len(hi) + len(lo) < cfg.min_total_touches:
            return None

        upper = fit_line([x for x, _ in hi], [y for _, y in hi])
        lower = fit_line([x for x, _ in lo], [y for _, y in lo])
        if upper is None or lower is None:
            return None

        p_mean = float(w["close"].mean())
        up_slope_pct = upper.slope / p_mean * 100
        lo_slope_pct = lower.slope / p_mean * 100
        if up_slope_pct > cfg.max_upper_slope_pct or lo_slope_pct > cfg.max_lower_slope_pct:
            return None
        if upper.slope >= lower.slope:  # not converging
            return None
        # Support must fall clearly slower than resistance (otherwise it is a
        # descending channel, not a wedge).
        if lower.slope < 0 and lower.slope / upper.slope > cfg.max_slope_ratio:
            return None

        x0 = min(hi[0][0], lo[0][0])
        x_end = lb - 1
        width_start = upper.at(x0) - lower.at(x0)
        width_end = upper.at(x_end) - lower.at(x_end)
        if width_start <= 0 or width_end <= 0:
            return None
        width_ratio = width_end / width_start
        if width_ratio > cfg.max_width_ratio:
            return None
        apex_x = (lower.intercept - upper.intercept) / (upper.slope - lower.slope)
        bars_to_apex = apex_x - x_end
        if bars_to_apex <= 0:
            return None

        a = atr(df, 14).iloc[start:].to_numpy()
        atr_x0 = a[x0] if not np.isnan(a[x0]) else np.nanmean(a)
        if not atr_x0 or width_start < cfg.min_start_width_atr * atr_x0:
            return None  # too narrow to be a meaningful structure

        # Containment (exclude the last few bars, which may be breaking out).
        closes = w["close"].to_numpy()
        check_to = max(x0 + 5, x_end - 3)
        xs = np.arange(x0, check_to + 1)
        tol = np.nan_to_num(a[xs], nan=0.0) * cfg.containment_tolerance_atr
        inside = (closes[xs] <= upper.slope * xs + upper.intercept + tol) & (
            closes[xs] >= lower.slope * xs + lower.intercept - tol
        )
        containment = float(inside.mean()) if len(xs) else 0.0
        if containment < cfg.min_containment:
            return None

        r2s = [ln.r2 for ln in (upper, lower) if ln.n >= 3]
        fit = float(np.mean(r2s)) if r2s else 0.7
        if r2s and fit < cfg.min_fit_r2:
            return None

        vols = w["volume"].iloc[x0 : x_end - 2].dropna().to_numpy()
        vol_contraction = None
        if len(vols) >= 9:
            third = len(vols) // 3
            early, late = vols[:third].mean(), vols[-third:].mean()
            vol_contraction = float(late / early) if early > 0 else None

        status = evaluate_level(ctx, lambda i: upper.at(i - start), ctx.config.status)
        if status.status == "extended":
            return None

        touches = len(hi) + len(lo)
        score = 100 * (
            0.20 * lin_score(touches, 4, 8)
            + 0.20 * fit
            + 0.20 * lin_score(width_ratio, 0.9, 0.3)
            + 0.20 * lin_score(containment, 0.8, 1.0)
            + 0.10 * (lin_score(vol_contraction, 1.1, 0.6) if vol_contraction is not None else 0.3)
            + 0.10 * {"confirmed": 1.0, "potential": 0.7, "forming": 0.4, "failed": 0.0}[status.status]
        )

        dates = w.index
        res_now, sup_now = upper.at(x_end), lower.at(x_end)
        return Detection(
            symbol=ctx.symbol,
            pattern=self.name,
            confidence=round(score, 1),
            status=status.status,
            current_price=r(ctx.close),
            support=r(sup_now),
            resistance=r(res_now),
            breakout_level=r(res_now),
            volume_current=ctx.last_volume,
            volume_avg=r(ctx.avg_volume_50, 0),
            volume_ratio=r(ctx.volume_ratio()),
            trend=ctx.trend.label if ctx.trend else None,
            metrics={
                "lookbackBars": lb,
                "upperSlopePctPerBar": r(up_slope_pct, 3),
                "lowerSlopePctPerBar": r(lo_slope_pct, 3),
                "widthRatio": r(width_ratio, 3),
                "barsToApex": r(bars_to_apex, 1),
                "touchesUpper": len(hi),
                "touchesLower": len(lo),
                "fitR2": r(fit, 3),
                "containment": r(containment, 3),
                "volumeContraction": r(vol_contraction, 3),
                "distanceToBreakoutPct": r(status.distance_pct),
                "breakoutBarsAgo": status.breakout_bars_ago,
                "breakoutVolumeRatio": r(status.breakout_volume_ratio),
                "rsRating": ctx.rs_rating,
                "lines": {
                    "upper": [[dates[x0].date().isoformat(), r(upper.at(x0))],
                              [dates[x_end].date().isoformat(), r(res_now)]],
                    "lower": [[dates[x0].date().isoformat(), r(lower.at(x0))],
                              [dates[x_end].date().isoformat(), r(sup_now)]],
                },
            },
        )
