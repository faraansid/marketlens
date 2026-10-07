"""VCP (Volatility Contraction Pattern) detector.

Methodology (after Mark Minervini's description of the pattern)
-------------------------------------------------------------
1. Trend template - the stock should already be in a Stage-2 uptrend. Checks:
     a. close > SMA150 and close > SMA200
     b. SMA150 > SMA200
     c. SMA200 rising over the last 20 bars
     d. SMA50 > SMA150 and SMA50 > SMA200
     e. close > SMA50
     f. close >= 1.30 x 52-week low
     g. close >= 0.75 x 52-week high
     h. relative-strength rating >= 70 (skipped if RS is unavailable)
   At least `min_template_criteria` must pass (one fewer if RS is unavailable).

2. Base & contractions - the base starts at the highest high of the last
   `base_lookback` bars (excluding the most recent bars, so a fresh breakout
   does not become the base's own peak). Swing points after that peak are
   paired into pullbacks (swing high -> following swing low); each pullback's
   depth is (H - L) / H. An in-progress final pullback is included. We keep
   the longest recent run where every depth is <= previous depth x
   `contraction_tolerance`, and require:
     * at least `min_contractions` pullbacks;
     * first depth <= `max_first_depth_pct`, final depth <= `max_final_depth_pct`;
     * final depth <= 75% of the first (the volatility genuinely contracted).

3. Volume dry-up - average volume during the final contraction relative to
   the 50-day average (lower is better; <= `volume_dryup_ratio` scores well).

4. Pivot - the high of the final contraction. Status (forming / potential /
   confirmed / failed) is classified with the shared lifecycle rules.

Confidence (0-100) blends trend-template strength, contraction quality, final
tightness, volume dry-up, relative strength and proximity to the pivot.
"""
from __future__ import annotations

import pandas as pd

from app.analysis.base import AnalysisContext, Detection, Detector, evaluate_level, r
from app.analysis.indicators import Swing, last, lin_score, sma, swing_points

STATUS_SCORE = {"confirmed": 1.0, "potential": 0.8, "failed": 0.0}


def trend_template(ctx: AnalysisContext) -> tuple[int, int, dict]:
    close = ctx.df["close"]
    c = float(close.iloc[-1])
    s50, s150 = last(sma(close, 50)), last(sma(close, 150))
    s200_series = sma(close, 200)
    s200 = last(s200_series)
    s200_prev = float(s200_series.iloc[-21]) if len(s200_series) > 21 and not pd.isna(s200_series.iloc[-21]) else None
    window = ctx.df.iloc[-252:]
    hi52, lo52 = float(window["high"].max()), float(window["low"].min())

    checks: dict[str, bool | None] = {}
    if None in (s50, s150, s200, s200_prev):
        return 0, 8, {"insufficientHistory": True}
    checks["aboveMA150and200"] = c > s150 and c > s200
    checks["ma150AboveMA200"] = s150 > s200
    checks["ma200Rising"] = s200 > s200_prev
    checks["ma50AboveMA150and200"] = s50 > s150 and s50 > s200
    checks["aboveMA50"] = c > s50
    checks["30pctAbove52wLow"] = c >= 1.30 * lo52
    checks["within25pctOf52wHigh"] = c >= 0.75 * hi52
    checks["rsAtLeast70"] = None if ctx.rs_rating is None else ctx.rs_rating >= 70
    evaluated = [v for v in checks.values() if v is not None]
    return sum(evaluated), len(evaluated), checks


class VCPDetector(Detector):
    name = "vcp"

    def detect(self, ctx: AnalysisContext) -> list[Detection]:
        cfg = ctx.config.vcp
        df = ctx.df
        n = len(df)
        if n < max(cfg.base_lookback, 220):
            return []

        passed, total, checks = trend_template(ctx)
        required = cfg.min_template_criteria - (1 if total < 8 else 0)
        if cfg.require_trend_template and passed < required:
            return []

        # --- locate base -------------------------------------------------------
        recent_exclude = ctx.config.status.fail_window
        base_start = n - cfg.base_lookback
        search = df["high"].iloc[base_start : n - recent_exclude]
        if search.empty:
            return []
        peak_pos = base_start + int(search.to_numpy().argmax())
        if n - peak_pos < cfg.min_base_bars:
            return []

        seg = df.iloc[peak_pos:]
        swings = swing_points(df.iloc[max(0, peak_pos - cfg.swing_k) :], k=cfg.swing_k)
        offset = max(0, peak_pos - cfg.swing_k)
        swings = [s for s in swings if s.idx + offset >= peak_pos]
        if not swings or swings[0].kind != "H":
            # Ensure the base peak itself starts the sequence.
            swings = [Swing(peak_pos - offset, float(df["high"].iloc[peak_pos]), "H")] + [
                s for s in swings if s.kind == "L" or s.idx + offset > peak_pos
            ]

        contractions: list[dict] = []
        for i, s in enumerate(swings):
            if s.kind != "H":
                continue
            nxt = next((t for t in swings[i + 1 :] if t.kind == "L"), None)
            if nxt is not None:
                lo, lo_idx = nxt.price, nxt.idx + offset
            else:
                # In-progress final pullback (not yet a confirmed swing low).
                tail = df["low"].iloc[s.idx + offset + 1 :]
                if len(tail) < 3:
                    continue
                lo, lo_idx = float(tail.min()), s.idx + offset + 1 + int(tail.to_numpy().argmin())
            depth = (s.price - lo) / s.price * 100
            if depth <= 0:
                continue
            contractions.append({"high": s.price, "highIdx": s.idx + offset, "low": lo,
                                 "lowIdx": lo_idx, "depthPct": depth})
        if len(contractions) < cfg.min_contractions:
            return []
        contractions = contractions[-cfg.max_contractions :]

        # Longest recent run of (approximately) decreasing depths.
        run = [contractions[-1]]
        for c in reversed(contractions[:-1]):
            if run[0]["depthPct"] <= c["depthPct"] * cfg.contraction_tolerance:
                run.insert(0, c)
            else:
                break
        if len(run) < cfg.min_contractions:
            return []
        first, final = run[0]["depthPct"], run[-1]["depthPct"]
        if first > cfg.max_first_depth_pct or final > cfg.max_final_depth_pct or final > first * 0.75:
            return []

        pivot = run[-1]["high"]
        support = run[-1]["low"]

        avg50 = ctx.avg_volume_50
        final_vol = df["volume"].iloc[run[-1]["highIdx"] : n - 1].dropna()
        dryup = float(final_vol.mean() / avg50) if avg50 and len(final_vol) >= 3 else None

        status = evaluate_level(ctx, lambda i: pivot, ctx.config.status)
        if status.status == "extended":
            return []

        tight10 = float((df["high"].iloc[-10:].max() - df["low"].iloc[-10:].min()) / ctx.close * 100)
        prox = STATUS_SCORE.get(status.status) or lin_score(status.distance_pct, -15, 0)
        score = 100 * (
            0.20 * (passed / total if total else 0)
            + 0.20 * (0.5 * lin_score(len(run), 1, 4) + 0.5 * lin_score(final / first, 0.8, 0.2))
            + 0.15 * lin_score(final, cfg.max_final_depth_pct, 3)
            + 0.15 * (lin_score(dryup, 1.0, 0.5) if dryup is not None else 0.3)
            + 0.15 * (lin_score(ctx.rs_rating, 50, 95) if ctx.rs_rating is not None else 0.4)
            + 0.15 * prox
        )
        if score < cfg.min_confidence:
            return []

        dates = df.index
        return [
            Detection(
                symbol=ctx.symbol,
                pattern=self.name,
                confidence=round(score, 1),
                status=status.status,
                current_price=r(ctx.close),
                support=r(support),
                resistance=r(pivot),
                breakout_level=r(pivot),
                volume_current=ctx.last_volume,
                volume_avg=r(avg50, 0),
                volume_ratio=r(ctx.volume_ratio()),
                trend=ctx.trend.label if ctx.trend else None,
                metrics={
                    "contractions": [
                        {"depthPct": r(c["depthPct"]), "high": r(c["high"]), "low": r(c["low"]),
                         "from": dates[c["highIdx"]].date().isoformat(),
                         "to": dates[min(c["lowIdx"], n - 1)].date().isoformat()}
                        for c in run
                    ],
                    "contractionCount": len(run),
                    "firstDepthPct": r(first),
                    "finalDepthPct": r(final),
                    "baseLengthBars": n - peak_pos,
                    "volumeDryUp": r(dryup),
                    "tightness10dPct": r(tight10),
                    "pivot": r(pivot),
                    "distanceToPivotPct": r(status.distance_pct),
                    "trendTemplate": f"{passed}/{total}",
                    "trendTemplateChecks": checks,
                    "rsRating": ctx.rs_rating,
                    "breakoutBarsAgo": status.breakout_bars_ago,
                    "breakoutVolumeRatio": r(status.breakout_volume_ratio),
                },
            )
        ]
