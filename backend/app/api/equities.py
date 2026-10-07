from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.analysis.config import load_pattern_config
from app.analysis.detectors.trend import classify_trend
from app.api.serializers import detection_out, iso, snapshot_out
from app.auth.deps import require_user
from app.config import get_settings
from app.db.models import Company, EquitySnapshot, PatternDetection, PriceBar
from app.db.session import get_db
from app.pipeline.refresh import latest_successful_run
from app.providers.base import ProviderError
from app.providers.registry import get_price_provider

router = APIRouter(prefix="/api/equities", tags=["equities"], dependencies=[Depends(require_user)])
log = logging.getLogger(__name__)

SORTS = {
    "name": EquitySnapshot.name,
    "symbol": EquitySnapshot.symbol,
    "price": EquitySnapshot.price,
    "oneDayChange": EquitySnapshot.change_1d_pct,
    "oneWeekChange": EquitySnapshot.change_1w_pct,
    "volume": EquitySnapshot.volume_1d,
    "avgVolumeWeek": EquitySnapshot.avg_volume_1w,
    "marketCap": EquitySnapshot.market_cap,
    "trendScore": EquitySnapshot.trend_score,
    "rsRating": EquitySnapshot.rs_rating,
}
TRENDS = {"Strong Uptrend", "Uptrend", "Neutral", "Downtrend", "Strong Downtrend"}


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
def list_equities(
    search: str | None = Query(None, max_length=80),
    sort: str = Query("marketCap"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200, alias="pageSize"),
    trend: str | None = None,
    db: Session = Depends(get_db),
):
    col = SORTS.get(sort)
    if col is None:
        raise HTTPException(400, f"Unsupported sort field. Use one of: {', '.join(SORTS)}")
    q = select(EquitySnapshot)
    if search and search.strip():
        term = f"%{_escape_like(search.strip())}%"
        q = q.where(or_(EquitySnapshot.symbol.ilike(term, escape="\\"), EquitySnapshot.name.ilike(term, escape="\\")))
    if trend:
        if trend not in TRENDS:
            raise HTTPException(400, "Unknown trend filter.")
        q = q.where(EquitySnapshot.trend == trend)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    ordered = col.desc().nulls_last() if order == "desc" else col.asc().nulls_last()
    rows = db.scalars(q.order_by(ordered, EquitySnapshot.symbol).offset((page - 1) * page_size).limit(page_size)).all()
    last_ok = latest_successful_run(db)
    return {
        "items": [snapshot_out(r) for r in rows],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": max(1, math.ceil(total / page_size)),
        "lastUpdated": iso(last_ok.finished_at) if last_ok else None,
    }


def _daily_frame(db: Session, symbol: str, days: int) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    rows = db.execute(
        select(PriceBar.date, PriceBar.open, PriceBar.high, PriceBar.low, PriceBar.close, PriceBar.volume)
        .where(PriceBar.symbol == symbol, PriceBar.date >= since).order_by(PriceBar.date)
    ).all()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    return df


@router.get("/{symbol}")
def get_equity(symbol: str, db: Session = Depends(get_db)):
    symbol = symbol.upper()
    company = db.get(Company, symbol)
    if company is None:
        raise HTTPException(404, f"We couldn't find a listed company with symbol '{symbol}'.")
    snap = db.get(EquitySnapshot, symbol)
    dets = db.scalars(
        select(PatternDetection).where(PatternDetection.symbol == symbol, PatternDetection.is_active.is_(True))
        .order_by(PatternDetection.confidence.desc())
    ).all()
    # Trend components for this one symbol (cheap; the universe scan stays in the worker).
    trend = None
    df = _daily_frame(db, symbol, 500)
    if len(df) >= 60:
        t = classify_trend(df, load_pattern_config(get_settings().pattern_config_file).trend)
        if t:
            trend = {"label": t.label, "score": t.score, "components": t.components}
    return {
        "company": {
            "symbol": company.symbol,
            "name": company.name,
            "isin": company.isin,
            "series": company.series,
            "listingDate": company.listing_date.isoformat() if company.listing_date else None,
            "isEligible": company.is_eligible,
            "eligibilityNote": company.eligibility_note,
            "sharesOutstanding": company.shares_outstanding,
        },
        "snapshot": snapshot_out(snap) if snap else None,
        "technicals": {
            "sma20": snap.sma20 if snap else None,
            "sma50": snap.sma50 if snap else None,
            "sma200": snap.sma200 if snap else None,
            "atr14Pct": snap.atr14_pct if snap else None,
            "rsRating": snap.rs_rating if snap else None,
            "high52w": snap.high_52w if snap else None,
            "low52w": snap.low_52w if snap else None,
        },
        "trend": trend,
        "patterns": [detection_out(d, snap) for d in dets],
    }


# --- charts -----------------------------------------------------------------
_TF_DAILY = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "2Y": 731}
_TF_LIVE = {"INTRADAY": ("1d", "1m"), "1D": ("1d", "5m"), "1W": ("5d", "15m")}
_chart_cache: TTLCache = TTLCache(maxsize=512, ttl=120)
IST_OFFSET = 19800  # charts render epoch seconds as wall-clock; shift to IST


@router.get("/{symbol}/chart")
def get_chart(symbol: str, tf: str = Query("6M"), db: Session = Depends(get_db)):
    symbol, tf = symbol.upper(), tf.upper()
    company = db.get(Company, symbol)
    if company is None:
        raise HTTPException(404, f"We couldn't find a listed company with symbol '{symbol}'.")

    if tf in _TF_DAILY:
        df = _daily_frame(db, symbol, _TF_DAILY[tf])
        bars = [
            {"t": ts.date().isoformat(), "o": r.open, "h": r.high, "l": r.low, "c": r.close,
             "v": None if pd.isna(r.volume) else r.volume}
            for ts, r in df.iterrows()
        ]
        return {"timeframe": tf, "interval": "1d", "source": "stored", "bars": bars,
                "asOf": iso(datetime.now(timezone.utc))}

    if tf not in _TF_LIVE:
        raise HTTPException(400, "Unsupported timeframe. Use Intraday, 1D, 1W, 1M, 3M, 6M, 1Y or 2Y.")
    key = (symbol, tf)
    if key in _chart_cache:
        return _chart_cache[key]
    period, interval = _TF_LIVE[tf]
    try:
        df = get_price_provider().intraday_history(company.provider_symbol, period, interval)
    except ProviderError:
        log.warning("Intraday chart unavailable for %s %s", symbol, tf, exc_info=True)
        raise HTTPException(503, "Intraday data is temporarily unavailable from the market-data provider.")
    bars = [
        {"t": int(ts.timestamp()) + IST_OFFSET, "o": r.open, "h": r.high, "l": r.low, "c": r.close,
         "v": None if pd.isna(r.volume) else r.volume}
        for ts, r in df.iterrows()
    ]
    out = {"timeframe": tf, "interval": interval, "source": "live", "bars": bars,
           "asOf": iso(datetime.now(timezone.utc))}
    _chart_cache[key] = out
    return out
