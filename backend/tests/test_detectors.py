"""Detector tests on synthetic price series with known shapes."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-0123456789")

import numpy as np
import pandas as pd
import pytest

from app.analysis.config import PatternConfig
from app.analysis.detectors.trend import classify_trend
from app.analysis.engine import PatternDetectionEngine

CFG = PatternConfig()
rng = np.random.default_rng(7)


def frame(closes, vols=None, spread=0.01) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    high = closes * (1 + spread)
    low = closes * (1 - spread)
    opens = np.r_[closes[0], closes[:-1]]
    vols = np.full(len(closes), 1_000_000.0) if vols is None else np.asarray(vols, dtype=float)
    return pd.DataFrame({"open": opens, "high": np.maximum(high, opens), "low": np.minimum(low, opens),
                         "close": closes, "volume": vols}, index=idx)


def patterns(df, **kw):
    return {d.pattern: d for d in PatternDetectionEngine(CFG).analyze("TEST", df, **kw)}


def test_strong_uptrend():
    closes = np.linspace(100, 220, 300) * (1 + 0.03 * np.sin(np.arange(300) / 4))
    t = classify_trend(frame(closes), CFG.trend)
    assert t is not None and t.label in ("Strong Uptrend", "Uptrend") and t.score > 25
    assert "uptrend" in patterns(frame(closes))


def test_strong_downtrend():
    closes = np.linspace(220, 100, 300) * (1 + 0.03 * np.sin(np.arange(300) / 4))
    t = classify_trend(frame(closes), CFG.trend)
    assert t is not None and t.label in ("Strong Downtrend", "Downtrend") and t.score < -25
    assert "downtrend" in patterns(frame(closes))


def test_neutral_range():
    # Trendless noise around a flat level.
    closes = 100 + np.random.default_rng(3).normal(0, 0.8, 300)
    t = classify_trend(frame(closes), CFG.trend)
    assert t is not None and t.label == "Neutral"


def test_confirmed_breakout_with_volume():
    base = 97 + 2.5 * np.sin(np.arange(120) / 3)  # range ~94.5-99.5
    closes = np.r_[np.linspace(80, 97, 150), base, 103.0]
    vols = np.r_[np.full(270, 1e6), 3.2e6]
    d = patterns(frame(closes, vols)).get("breakout")
    assert d is not None and d.status == "confirmed"
    assert d.breakout_level == pytest.approx(99.5 * 1.01, rel=0.02)
    assert d.volume_ratio > 3


def test_breakout_without_volume_is_potential():
    base = 97 + 2.5 * np.sin(np.arange(120) / 3)
    closes = np.r_[np.linspace(80, 97, 150), base, 103.0]
    d = patterns(frame(closes)).get("breakout")
    assert d is not None and d.status == "potential"


def test_failed_breakout():
    base = 97 + 2.5 * np.sin(np.arange(120) / 3)
    closes = np.r_[np.linspace(80, 97, 150), base, 103, 102, 99, 96, 93.0]
    vols = np.r_[np.full(270, 1e6), 3e6, 1e6, 1e6, 1e6, 1e6]
    d = patterns(frame(closes, vols)).get("breakout")
    assert d is not None and d.status == "failed"


def test_extended_breakout_is_dropped():
    base = 97 + 2.5 * np.sin(np.arange(120) / 3)
    closes = np.r_[np.linspace(80, 97, 150), base, 103, 110, 118.0]  # +18% above the level
    vols = np.r_[np.full(270, 1e6), 3e6, 2e6, 2e6]
    assert "breakout" not in patterns(frame(closes, vols))


def test_zero_volume_holiday_rows_are_dropped():
    from app.providers.yfinance_provider import _normalize

    idx = pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"])
    raw = pd.DataFrame({"Open": [10, 10.5, 10.6], "High": [11, 10.5, 11], "Low": [9.5, 10.5, 10.2],
                        "Close": [10.5, 10.5, 10.8], "Volume": [1000, 0, 1200]}, index=idx)
    assert list(_normalize(raw, daily=True, drop_zero_volume=True).index.day) == [1, 5]
    assert len(_normalize(raw, daily=True, drop_zero_volume=False)) == 3  # indices keep them


def test_falling_wedge():
    n = 90
    x = np.arange(n)
    upper = 150 - 0.45 * x  # resistance falls faster
    lower = 120 - 0.15 * x  # support falls slower -> converging
    mid, half = (upper + lower) / 2, (upper - lower) / 2
    wedge = mid + 0.92 * half * np.sin(x * 2 * np.pi / 15)
    closes = np.r_[np.linspace(170, 136, 150), wedge]
    d = patterns(frame(closes, spread=0.004)).get("falling_wedge")
    assert d is not None, "falling wedge not detected"
    assert d.metrics["upperSlopePctPerBar"] < d.metrics["lowerSlopePctPerBar"] < 0.05
    assert d.resistance > d.support


def test_no_wedge_in_rising_channel():
    x = np.arange(240)
    closes = 100 + 0.3 * x + 4 * np.sin(x * 2 * np.pi / 15)
    assert "falling_wedge" not in patterns(frame(closes, spread=0.004))


def _vcp_series():
    up = np.linspace(50, 100, 230)  # stage-2 advance
    legs = [
        np.linspace(100, 80, 10), np.linspace(80, 99, 12),  # -20%
        np.linspace(99, 89, 8), np.linspace(89, 98.5, 9),  # ~-10%
        np.linspace(98.5, 93.5, 6), np.linspace(93.5, 98, 6),  # ~-5%
        np.linspace(98, 95.5, 4), np.linspace(95.5, 97.6, 4),  # ~-2.5%
    ]
    closes = np.r_[up, np.concatenate(legs)]
    vols = np.r_[np.full(230, 2e6), np.linspace(1.8e6, 0.7e6, len(closes) - 230)]
    return closes, vols


def test_vcp_detected():
    closes, vols = _vcp_series()
    d = patterns(frame(closes, vols, spread=0.004), rs_rating=90).get("vcp")
    assert d is not None, "VCP not detected"
    depths = [c["depthPct"] for c in d.metrics["contractions"]]
    assert len(depths) >= 2 and depths[-1] < depths[0]
    assert d.status in ("potential", "forming")


def test_vcp_rejected_in_downtrend():
    closes, vols = _vcp_series()
    closes = closes[::-1].copy()
    assert "vcp" not in patterns(frame(closes, vols, spread=0.004))


def test_short_history_is_safe():
    assert PatternDetectionEngine(CFG).analyze("TEST", frame(np.linspace(10, 12, 20))) == []
