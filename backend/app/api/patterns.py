from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.serializers import PATTERN_LABELS, detection_out, iso
from app.auth.deps import require_user
from app.db.models import BreakoutSignal, EquitySnapshot, PatternDetection
from app.db.session import get_db
from app.pipeline.refresh import latest_successful_run

router = APIRouter(prefix="/api", tags=["patterns"], dependencies=[Depends(require_user)])

STATUSES = {"forming", "potential", "confirmed", "failed", "active"}
TRENDS = {"Strong Uptrend", "Uptrend", "Neutral", "Downtrend", "Strong Downtrend"}
SORTS = {
    "confidence": PatternDetection.confidence,
    "volumeRatio": PatternDetection.volume_ratio,
    "marketCap": EquitySnapshot.market_cap,
    "price": PatternDetection.current_price,
    "symbol": PatternDetection.symbol,
    "oneDayChange": EquitySnapshot.change_1d_pct,
}
BREAKOUT_PATTERNS = ("breakout", "vcp", "falling_wedge")


def _filtered(
    *,
    patterns: list[str] | None,
    statuses: list[str] | None,
    min_conf: float | None,
    trend: str | None,
    min_mcap: float | None,
    max_mcap: float | None,
    min_price: float | None,
    max_price: float | None,
    min_vr: float | None,
    search: str | None,
):
    q = (
        select(PatternDetection, EquitySnapshot, BreakoutSignal)
        .join(EquitySnapshot, EquitySnapshot.symbol == PatternDetection.symbol)
        .outerjoin(BreakoutSignal, and_(BreakoutSignal.symbol == PatternDetection.symbol,
                                        BreakoutSignal.source_pattern == PatternDetection.pattern,
                                        BreakoutSignal.is_active.is_(True)))
        .where(PatternDetection.is_active.is_(True))
    )
    if patterns:
        q = q.where(PatternDetection.pattern.in_(patterns))
    if statuses:
        q = q.where(PatternDetection.status.in_(statuses))
    if min_conf is not None:
        q = q.where(PatternDetection.confidence >= min_conf)
    if trend:
        q = q.where(PatternDetection.trend == trend)
    if min_mcap is not None:
        q = q.where(EquitySnapshot.market_cap >= min_mcap * 1e7)
    if max_mcap is not None:
        q = q.where(EquitySnapshot.market_cap <= max_mcap * 1e7)
    if min_price is not None:
        q = q.where(PatternDetection.current_price >= min_price)
    if max_price is not None:
        q = q.where(PatternDetection.current_price <= max_price)
    if min_vr is not None:
        q = q.where(PatternDetection.volume_ratio >= min_vr)
    if search and search.strip():
        term = f"%{search.strip().replace('%', '').replace('_', '')}%"
        q = q.where(or_(PatternDetection.symbol.ilike(term), EquitySnapshot.name.ilike(term)))
    return q


def _split(v: str | None, allowed: set[str], what: str) -> list[str] | None:
    if not v:
        return None
    items = [x.strip() for x in v.split(",") if x.strip()]
    bad = [x for x in items if x not in allowed]
    if bad:
        raise HTTPException(400, f"Unknown {what}: {', '.join(bad)}")
    return items


@router.get("/patterns")
def list_patterns(
    pattern: str | None = Query(None, description="comma-separated: uptrend,downtrend,falling_wedge,vcp,breakout"),
    status: str | None = Query(None, description="comma-separated statuses"),
    min_confidence: float | None = Query(None, alias="minConfidence", ge=0, le=100),
    trend: str | None = None,
    min_mcap_cr: float | None = Query(None, alias="minMarketCapCr", ge=0),
    max_mcap_cr: float | None = Query(None, alias="maxMarketCapCr", ge=0),
    min_price: float | None = Query(None, alias="minPrice", ge=0),
    max_price: float | None = Query(None, alias="maxPrice", ge=0),
    min_vr: float | None = Query(None, alias="minVolumeRatio", ge=0),
    search: str | None = Query(None, max_length=80),
    sort: str = "confidence",
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=6, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
):
    if trend and trend not in TRENDS:
        raise HTTPException(400, "Unknown trend filter.")
    col = SORTS.get(sort)
    if col is None:
        raise HTTPException(400, f"Unsupported sort field. Use one of: {', '.join(SORTS)}")
    q = _filtered(
        patterns=_split(pattern, set(PATTERN_LABELS), "pattern"),
        statuses=_split(status, STATUSES, "status"),
        min_conf=min_confidence, trend=trend, min_mcap=min_mcap_cr, max_mcap=max_mcap_cr,
        min_price=min_price, max_price=max_price, min_vr=min_vr, search=search,
    )
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    ordered = col.desc().nulls_last() if order == "desc" else col.asc().nulls_last()
    rows = db.execute(q.order_by(ordered, PatternDetection.symbol)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    last_ok = latest_successful_run(db)
    return {
        "items": [detection_out(d, s, b) for d, s, b in rows],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": max(1, math.ceil(total / page_size)),
        "lastUpdated": iso(last_ok.finished_at) if last_ok else None,
    }


@router.get("/patterns/summary")
def pattern_summary(db: Session = Depends(get_db)):
    rows = db.execute(
        select(PatternDetection.pattern, PatternDetection.status, func.count())
        .where(PatternDetection.is_active.is_(True))
        .group_by(PatternDetection.pattern, PatternDetection.status)
    ).all()
    out: dict[str, dict] = {}
    for p, s, n in rows:
        out.setdefault(p, {"total": 0, "byStatus": {}})
        out[p]["total"] += n
        out[p]["byStatus"][s] = n
    return out


@router.get("/patterns/{symbol}")
def patterns_for_symbol(symbol: str, db: Session = Depends(get_db)):
    symbol = symbol.upper()
    snap = db.get(EquitySnapshot, symbol)
    dets = db.scalars(
        select(PatternDetection).where(PatternDetection.symbol == symbol, PatternDetection.is_active.is_(True))
        .order_by(PatternDetection.confidence.desc())
    ).all()
    return {"symbol": symbol, "items": [detection_out(d, snap) for d in dets]}


@router.get("/breakouts")
def list_breakouts(
    status: str | None = Query(None, description="potential,confirmed,failed"),
    pattern: str | None = Query(None, description="breakout,vcp,falling_wedge"),
    min_confidence: float | None = Query(None, alias="minConfidence", ge=0, le=100),
    min_vr: float | None = Query(None, alias="minVolumeRatio", ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=6, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
):
    statuses = _split(status, {"potential", "confirmed", "failed"}, "status") or ["potential", "confirmed", "failed"]
    patterns = _split(pattern, set(BREAKOUT_PATTERNS), "pattern") or list(BREAKOUT_PATTERNS)
    q = _filtered(patterns=patterns, statuses=statuses, min_conf=min_confidence, trend=None, min_mcap=None,
                  max_mcap=None, min_price=None, max_price=None, min_vr=min_vr, search=None)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(q.order_by(PatternDetection.confidence.desc()).offset((page - 1) * page_size)
                      .limit(page_size)).all()
    return {
        "items": [detection_out(d, s, b) for d, s, b in rows],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": max(1, math.ceil(total / page_size)),
    }
