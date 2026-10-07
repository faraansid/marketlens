"""Model -> JSON (camelCase) serializers shared by the API routers."""
from __future__ import annotations

from datetime import datetime

from app.db.models import BreakoutSignal, EquitySnapshot, JobRun, MarketInstrument, PatternDetection

PATTERN_LABELS = {
    "uptrend": "Uptrend",
    "downtrend": "Downtrend",
    "falling_wedge": "Falling Wedge",
    "vcp": "VCP",
    "breakout": "Breakout",
}


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def snapshot_out(s: EquitySnapshot) -> dict:
    return {
        "symbol": s.symbol,
        "name": s.name,
        "price": s.price,
        "prevClose": s.prev_close,
        "oneDayChange": s.change_1d_pct,
        "oneWeekChange": s.change_1w_pct,
        "oneMonthChange": s.change_1m_pct,
        "volume": s.volume_1d,
        "avgVolumeWeek": s.avg_volume_1w,
        "avgVolume50d": s.avg_volume_50d,
        "volumeRatio": s.volume_ratio,
        "marketCap": s.market_cap,
        "high52w": s.high_52w,
        "low52w": s.low_52w,
        "rsRating": s.rs_rating,
        "trend": s.trend,
        "trendScore": s.trend_score,
        "signals": s.signals or [],
        "lastBarDate": s.last_bar_date.isoformat() if s.last_bar_date else None,
        "asOf": iso(s.as_of),
    }


def detection_out(d: PatternDetection, snap: EquitySnapshot | None = None,
                  signal: BreakoutSignal | None = None) -> dict:
    out = {
        "id": d.id,
        "symbol": d.symbol,
        "name": snap.name if snap else None,
        "pattern": d.pattern,
        "patternLabel": PATTERN_LABELS.get(d.pattern, d.pattern),
        "status": d.status,
        "confidenceScore": d.confidence,
        "currentPrice": d.current_price,
        "support": d.support,
        "resistance": d.resistance,
        "breakoutLevel": d.breakout_level,
        "volumeCurrent": d.volume_current,
        "volumeAvg": d.volume_avg,
        "volumeRatio": d.volume_ratio,
        "trend": d.trend,
        "metrics": d.metrics or {},
        "chart": d.chart or [],
        "detectedAt": iso(d.detected_at),
        "marketCap": snap.market_cap if snap else None,
        "oneDayChange": snap.change_1d_pct if snap else None,
    }
    if signal is not None:
        out["signal"] = {
            "firstDetectedAt": iso(signal.first_detected_at),
            "confirmedAt": iso(signal.confirmed_at),
            "failedAt": iso(signal.failed_at),
            "lastSeenAt": iso(signal.last_seen_at),
        }
    return out


def instrument_out(m: MarketInstrument) -> dict:
    return {
        "key": m.key,
        "name": m.name,
        "symbol": m.provider_symbol,
        "category": m.category,
        "unit": m.unit,
        "value": m.value,
        "prevClose": m.prev_close,
        "change": m.change,
        "changePct": m.change_pct,
        "sparkline": m.sparkline or [],
        "sparklineLabel": m.sparkline_label,
        "marketTime": iso(m.market_time),
        "updatedAt": iso(m.updated_at),
        "stale": bool(m.error),
    }


def job_out(j: JobRun | None, include_error: bool = False) -> dict | None:
    if j is None:
        return None
    return {
        "id": j.id,
        "status": j.status,
        "trigger": j.trigger,
        "startedAt": iso(j.started_at),
        "finishedAt": iso(j.finished_at),
        "symbolsOk": j.symbols_ok,
        "symbolsFailed": j.symbols_failed,
        "detections": j.detections,
        "message": j.message,
        # Raw errors are only shown to admins; users get a friendly status.
        "error": j.error if include_error else (None if not j.error else "Some data sources failed during this update."),
    }
