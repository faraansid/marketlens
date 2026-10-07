"""Detector thresholds.

Every tunable parameter lives here, not in detector code. Defaults can be
overridden by pointing PATTERN_CONFIG_FILE at a JSON file with the same
structure, e.g. {"vcp": {"max_final_depth_pct": 8}}.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

log = logging.getLogger(__name__)


class TrendConfig(BaseModel):
    min_bars: int = 60
    swing_k: int = 5
    swing_lookback: int = 120
    ma_slope_lookback: int = 20
    ma_slope_full_scale_pct: float = 5.0  # SMA50 change over lookback that maps to full score
    return_lookback: int = 60
    return_full_scale_pct: float = 20.0
    atr_scale: float = 1.5  # MA distances of this many ATRs count as a full vote
    weights: dict[str, float] = {
        "price_vs_ma": 0.25,
        "ma_alignment": 0.20,
        "ma_slope": 0.20,
        "swing_structure": 0.20,
        "momentum": 0.15,
    }
    strong_threshold: float = 60.0
    trend_threshold: float = 25.0


class FallingWedgeConfig(BaseModel):
    lookbacks: list[int] = [40, 60, 90, 120]
    swing_k: int = 3
    min_touches_per_side: int = 3
    min_total_touches: int = 6
    max_upper_slope_pct: float = -0.05  # % of price per bar; upper line must fall at least this fast
    max_lower_slope_pct: float = 0.02  # lower line must be falling or ~flat
    max_slope_ratio: float = 0.75  # lower slope / upper slope: support must fall clearly slower
    max_width_ratio: float = 0.65  # width at end / width at start (convergence)
    min_start_width_atr: float = 3.0  # wedge must be meaningfully wide at its start
    min_containment: float = 0.85  # fraction of closes between the lines
    containment_tolerance_atr: float = 0.5
    min_fit_r2: float = 0.65
    min_confidence: float = 70.0


class VCPConfig(BaseModel):
    require_trend_template: bool = True
    min_template_criteria: int = 7  # of the 8 trend-template checks
    base_lookback: int = 120
    min_base_bars: int = 25
    swing_k: int = 3
    min_contractions: int = 2
    max_contractions: int = 5
    max_first_depth_pct: float = 35.0
    max_final_depth_pct: float = 12.0
    contraction_tolerance: float = 1.1  # each depth may be at most 10% larger than the previous one
    volume_dryup_ratio: float = 0.85  # recent volume / 50-day avg volume must be below this
    min_confidence: float = 45.0


class BreakoutConfig(BaseModel):
    resistance_lookback: int = 50
    min_resistance_age: int = 5  # bars since the high that defines resistance
    confirm_window: int = 3  # breakout must have happened within the last N bars
    fail_window: int = 10  # a breakout within this window that lost its level = failed
    breakout_buffer_pct: float = 0.5  # close must exceed resistance by this much
    fail_buffer_pct: float = 1.5  # close this far back below the level = failed
    near_pct: float = 3.0  # within this distance below resistance = potential
    volume_multiple: float = 1.5  # breakout-bar volume vs 50-day average for confirmation
    atr_contraction_max: float = 0.95  # ATR10/ATR50 below this supports a "potential" setup
    max_extension_pct: float = 12.0  # further above the level than this = no longer an actionable setup
    min_confidence: float = 40.0


class BreakoutStatusConfig(BaseModel):
    """Shared lifecycle rules for pattern pivots (VCP / wedge)."""

    near_pct: float = 3.0
    breakout_buffer_pct: float = 0.5
    fail_buffer_pct: float = 1.5
    fail_window: int = 10
    volume_multiple: float = 1.5
    max_extension_pct: float = 12.0  # beyond this above the pivot the setup is "extended"


class PatternConfig(BaseModel):
    trend: TrendConfig = TrendConfig()
    falling_wedge: FallingWedgeConfig = FallingWedgeConfig()
    vcp: VCPConfig = VCPConfig()
    breakout: BreakoutConfig = BreakoutConfig()
    status: BreakoutStatusConfig = BreakoutStatusConfig()
    chart_points: int = 90  # closes stored with each detection for the mini chart


@lru_cache
def load_pattern_config(path: str | None = None) -> PatternConfig:
    if not path:
        return PatternConfig()
    p = Path(path)
    if not p.exists():
        log.warning("PATTERN_CONFIG_FILE %s not found; using defaults", path)
        return PatternConfig()
    return PatternConfig.model_validate(json.loads(p.read_text(encoding="utf-8")))
