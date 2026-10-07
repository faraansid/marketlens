"""Indicator primitives used by the detectors.

All functions take pandas Series/DataFrames indexed by date with lowercase
columns open/high/low/close/volume and never look ahead (except `swing_points`,
which by definition needs `k` bars on the right to confirm a pivot).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder-style average true range."""
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def pct_change(s: pd.Series, periods: int) -> float | None:
    if len(s) <= periods:
        return None
    base = s.iloc[-1 - periods]
    if not base or np.isnan(base):
        return None
    return float((s.iloc[-1] / base - 1) * 100)


def last(s: pd.Series) -> float | None:
    if s is None or s.empty:
        return None
    v = s.iloc[-1]
    return None if pd.isna(v) else float(v)


def slope_pct(s: pd.Series, lookback: int) -> float | None:
    """Percent change of a (smoothed) series over `lookback` bars."""
    s = s.dropna()
    if len(s) <= lookback:
        return None
    a, b = s.iloc[-1 - lookback], s.iloc[-1]
    return float((b / a - 1) * 100) if a else None


@dataclass(frozen=True)
class Swing:
    idx: int  # positional index into the frame
    price: float
    kind: str  # "H" or "L"


def swing_points(df: pd.DataFrame, k: int = 3) -> list[Swing]:
    """Fractal pivots: a swing high is a bar whose high is the maximum of the
    window [i-k, i+k] (leftmost bar wins ties); a swing low is defined symmetrically. Pivots therefore
    need `k` bars to their right before they are confirmed, which avoids
    repainting. Consecutive pivots of the same kind are merged, keeping the
    more extreme one, so the result alternates H/L."""
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    raw: list[Swing] = []
    for i in range(k, n - k):
        win_h = highs[i - k : i + k + 1]
        win_l = lows[i - k : i + k + 1]
        # argmax/argmin return the first occurrence, so equal highs/lows (common
        # in real data) yield a single pivot at the leftmost bar.
        if int(win_h.argmax()) == k:
            raw.append(Swing(i, float(highs[i]), "H"))
        if int(win_l.argmin()) == k:
            raw.append(Swing(i, float(lows[i]), "L"))
    raw.sort(key=lambda p: (p.idx, p.kind))
    merged: list[Swing] = []
    for p in raw:
        if merged and merged[-1].kind == p.kind:
            prev = merged[-1]
            better = (p.price > prev.price) if p.kind == "H" else (p.price < prev.price)
            if better:
                merged[-1] = p
        else:
            merged.append(p)
    return merged


@dataclass(frozen=True)
class Line:
    slope: float  # price units per bar
    intercept: float
    r2: float
    n: int

    def at(self, x: float) -> float:
        return self.slope * x + self.intercept


def fit_line(xs: list[int] | np.ndarray, ys: list[float] | np.ndarray) -> Line | None:
    """Least-squares trendline through pivot points."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if len(xs) < 2 or np.ptp(xs) == 0:
        return None
    slope, intercept = np.polyfit(xs, ys, 1)
    pred = slope * xs + intercept
    ss_res = float(((ys - pred) ** 2).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum())
    r2 = 1.0 if ss_tot == 0 else max(0.0, 1 - ss_res / ss_tot)
    return Line(float(slope), float(intercept), r2, len(xs))


def clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def lin_score(x: float | None, lo: float, hi: float) -> float:
    """Map x linearly onto [0, 1] between lo and hi (works for lo > hi too)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return clip01((x - lo) / (hi - lo))
