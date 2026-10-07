"""Scheduled market-data pipeline.

    Market Data Provider
            ↓  ingest_universe / ingest_prices / ingest_shares / ingest_instruments
    Validation                (provider frames are validated in the provider; bars
            ↓                  with discontinuities trigger a re-backfill here)
    Eligible Equity Filter    (listed company AND market cap >= MIN_MARKET_CAP_CR)
            ↓
    Metric Calculation        (returns, volumes, 52w range, MAs, RS rating, trend)
            ↓
    Technical Pattern Detection (PatternDetectionEngine)
            ↓
    Database                  (equity_snapshots, pattern_detections, breakout_signals)
            ↓
    Backend API → Frontend

Every step is isolated: a failing step is logged into the job's stats and the
run is marked `partial`, while previously stored data keeps being served.
"""
from __future__ import annotations

import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.analysis.config import load_pattern_config
from app.analysis.engine import PatternDetectionEngine, relative_performance
from app.analysis.indicators import atr, pct_change, sma
from app.config import get_settings
from app.db.models import (
    AppState,
    BreakoutSignal,
    Company,
    EquitySnapshot,
    JobRun,
    MarketInstrument,
    PatternDetection,
    PriceBar,
)
from app.db.session import session_scope
from app.db.upsert import bulk_upsert
from app.market_instruments import INSTRUMENTS
from app.providers.base import ProviderError
from app.providers.registry import get_price_provider, get_universe_provider
from app.services.market_hours import in_session_window, today_ist

log = logging.getLogger("pipeline")

ANALYSIS_BARS = 320  # bars loaded per symbol for metrics/patterns (>= 252 + margin)
BREAKOUT_PATTERNS = {"breakout", "vcp", "falling_wedge"}
BREAKOUT_STATUSES = {"potential", "confirmed", "failed"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Job bookkeeping / lock
# ---------------------------------------------------------------------------
def _acquire_job(trigger: str) -> int | None:
    s = get_settings()
    with session_scope() as db:
        running = db.scalars(
            select(JobRun).where(JobRun.status == "running").order_by(JobRun.started_at.desc())
        ).all()
        for job in running:
            if utcnow() - job.started_at < timedelta(minutes=s.job_stale_after_minutes):
                log.info("Refresh already running (job %s); skipping %s trigger", job.id, trigger)
                return None
            job.status, job.finished_at = "failed", utcnow()
            job.error = "Marked failed: worker stopped before completion (stale lock)."
        job = JobRun(job_type="market_refresh", trigger=trigger, status="running", started_at=utcnow())
        db.add(job)
        db.flush()
        return job.id


def _state_get(db: Session, key: str) -> dict | None:
    row = db.get(AppState, key)
    return row.value if row else None


def _state_set(db: Session, key: str, value: dict) -> None:
    row = db.get(AppState, key)
    if row:
        row.value = value
    else:
        db.add(AppState(key=key, value=value))


# ---------------------------------------------------------------------------
# Ingestion steps
# ---------------------------------------------------------------------------
def ingest_universe(force: bool = False) -> dict:
    """Refresh the listed-company universe at most once per UNIVERSE_REFRESH_HOURS."""
    s = get_settings()
    with session_scope() as db:
        st = _state_get(db, "universe_refreshed_at")
        has_rows = db.scalar(select(func.count()).select_from(Company)) or 0
        if not force and st and has_rows:
            last = datetime.fromisoformat(st["at"])
            if utcnow() - last < timedelta(hours=s.universe_refresh_hours):
                return {"skipped": True, "companies": has_rows}

    provider = get_universe_provider()
    price = get_price_provider()
    entries = provider.fetch_universe()
    seen = {e.symbol for e in entries}
    with session_scope() as db:
        existing = {c.symbol: c for c in db.scalars(select(Company)).all()}
        added = 0
        for e in entries:
            c = existing.get(e.symbol)
            if c is None:
                db.add(Company(symbol=e.symbol, name=e.name, isin=e.isin, series=e.series,
                               listing_date=e.listing_date, provider_symbol=price.to_provider_symbol(e.symbol),
                               is_listed=True))
                added += 1
            else:
                c.name, c.isin, c.series, c.listing_date, c.is_listed = (
                    e.name, e.isin, e.series, e.listing_date, True)
        delisted = 0
        for sym, c in existing.items():
            if sym not in seen and c.is_listed:
                c.is_listed, c.is_eligible, c.eligibility_note = False, False, "No longer in exchange list"
                delisted += 1
        _state_set(db, "universe_refreshed_at", {"at": utcnow().isoformat(), "count": len(entries)})
    log.info("Universe: %d listed (%d new, %d delisted)", len(entries), added, delisted)
    return {"listed": len(entries), "added": added, "delisted": delisted}


def _bars_rows(symbol: str, df: pd.DataFrame) -> list[dict]:
    now = utcnow()
    rows = []
    for ts, row in df.iterrows():
        vol = row["volume"]
        rows.append({
            "symbol": symbol, "date": ts.date(), "open": float(row["open"]), "high": float(row["high"]),
            "low": float(row["low"]), "close": float(row["close"]),
            "volume": None if pd.isna(vol) else float(vol), "updated_at": now,
        })
    return rows


def ingest_prices() -> dict:
    """Backfill full history for new symbols; incrementally update the rest.

    Known-ineligible (small) companies are only refreshed once a day so they
    can enter the universe if they cross the threshold, while eligible ones
    are refreshed every run.
    """
    s = get_settings()
    provider = get_price_provider()
    today = today_ist()
    with session_scope() as db:
        # One-time data migration: purge zero-volume holiday rows stored before
        # the provider started filtering them.
        if not _state_get(db, "migration_zero_volume_bars_v1"):
            n = db.execute(delete(PriceBar).where(PriceBar.volume == 0, PriceBar.symbol != s.benchmark_symbol)).rowcount
            _state_set(db, "migration_zero_volume_bars_v1", {"deleted": n, "at": utcnow().isoformat()})
            log.info("Removed %d zero-volume (non-trading) equity bars", n)
        companies = db.scalars(select(Company).where(Company.is_listed.is_(True))).all()
        backfill, incremental = [], []
        for c in companies:
            if c.history_end is None:
                backfill.append(c.provider_symbol)
            elif c.is_eligible or c.market_cap is None or c.market_cap >= 0.7 * s.min_market_cap_inr:
                incremental.append(c.provider_symbol)
            elif c.history_end < today - timedelta(days=1):
                incremental.append(c.provider_symbol)
        sym_by_provider = {c.provider_symbol: c.symbol for c in companies}

    stats = {"backfill_requested": len(backfill), "incremental_requested": len(incremental)}
    fetched: dict[str, pd.DataFrame] = {}
    t0 = time.time()
    if backfill:
        log.info("Backfilling %s history for %d symbols", s.history_period, len(backfill))
        fetched.update(provider.daily_history(backfill, s.history_period))
    if incremental:
        log.info("Incremental update for %d symbols", len(incremental))
        inc = provider.daily_history(incremental, "5d")
        # Validation: detect split/bonus discontinuities against stored closes and
        # re-backfill those symbols so history stays internally consistent.
        rebackfill = _find_discontinuities(inc, sym_by_provider)
        if rebackfill:
            log.info("Re-backfilling %d symbols after price discontinuity: %s", len(rebackfill),
                     ", ".join(rebackfill[:10]))
            full = provider.daily_history(rebackfill, s.history_period)
            with session_scope() as db:
                db.execute(delete(PriceBar).where(PriceBar.symbol.in_([sym_by_provider[p] for p in full])))
            inc.update(full)
        stats["rebackfilled"] = len(rebackfill)
        fetched.update(inc)

    ok = 0
    with session_scope() as db:
        for psym, df in fetched.items():
            sym = sym_by_provider.get(psym)
            if not sym or df.empty:
                continue
            bulk_upsert(db, PriceBar, _bars_rows(sym, df), ["symbol", "date"])
            ok += 1
        # Refresh per-company history bounds in one pass.
        bounds = db.execute(
            select(PriceBar.symbol, func.min(PriceBar.date), func.max(PriceBar.date)).group_by(PriceBar.symbol)
        ).all()
        bmap = {b[0]: (b[1], b[2]) for b in bounds}
        missing = 0
        for c in db.scalars(select(Company).where(Company.is_listed.is_(True))).all():
            if c.symbol in bmap:
                c.history_start, c.history_end = bmap[c.symbol]
                c.data_error = None
            elif c.provider_symbol in backfill:
                c.data_error = "No price data from provider"
                missing += 1
    stats.update({"symbols_updated": ok, "no_data": missing, "seconds": round(time.time() - t0, 1)})
    log.info("Prices: %s", stats)
    return stats


def _find_discontinuities(inc: dict[str, pd.DataFrame], sym_by_provider: dict[str, str]) -> list[str]:
    if not inc:
        return []
    with session_scope() as db:
        min_date = min(df.index.min().date() for df in inc.values() if not df.empty)
        stored = db.execute(
            select(PriceBar.symbol, PriceBar.date, PriceBar.close).where(PriceBar.date >= min_date)
        ).all()
    stored_map: dict[tuple[str, date], float] = {(r[0], r[1]): r[2] for r in stored}
    out = []
    for psym, df in inc.items():
        sym = sym_by_provider.get(psym)
        if not sym or len(df) < 2:
            continue
        # Compare all but the latest (possibly in-progress) bar.
        for ts, row in df.iloc[:-1].iterrows():
            old = stored_map.get((sym, ts.date()))
            if old and abs(row["close"] / old - 1) > 0.05:
                out.append(psym)
                break
    return out


def ingest_shares() -> dict:
    """Fetch shares outstanding for companies missing it or with stale values."""
    s = get_settings()
    provider = get_price_provider()
    cutoff = utcnow() - timedelta(days=s.shares_refresh_days)
    with session_scope() as db:
        have_any = db.scalar(select(func.count()).select_from(Company).where(Company.shares_updated_at.is_not(None)))
        limit = s.shares_steady_per_run if have_any else s.shares_max_per_run
        todo = db.scalars(
            select(Company)
            .where(Company.is_listed.is_(True), Company.history_end.is_not(None))
            .where((Company.shares_updated_at.is_(None)) | (Company.shares_updated_at < cutoff))
            # Never-fetched first, then the stalest.
            .order_by(Company.shares_updated_at.is_not(None), Company.shares_updated_at)
            .limit(limit)
        ).all()
        targets = [(c.symbol, c.provider_symbol) for c in todo]
    if not targets:
        return {"requested": 0}
    log.info("Fetching shares outstanding for %d companies", len(targets))
    t0 = time.time()
    results: dict[str, float | None] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(provider.shares_outstanding, p): sym for sym, p in targets}
        for f in as_completed(futs):
            try:
                results[futs[f]] = f.result()
            except Exception:  # noqa: BLE001
                results[futs[f]] = None
    now = utcnow()
    with session_scope() as db:
        for sym, shares in results.items():
            c = db.get(Company, sym)
            if c is None:
                continue
            c.shares_updated_at = now  # also on failure, so we retry after the refresh window
            if shares:
                c.shares_outstanding = shares
    got = sum(1 for v in results.values() if v)
    stats = {"requested": len(targets), "received": got, "seconds": round(time.time() - t0, 1)}
    log.info("Shares: %s", stats)
    return stats


def ingest_instruments() -> dict:
    provider = get_price_provider()
    ok, failed = 0, []
    now = utcnow()
    with session_scope() as db:
        for order, inst in enumerate(INSTRUMENTS):
            row = db.get(MarketInstrument, inst.key)
            if row is None:
                row = MarketInstrument(key=inst.key, name=inst.name, provider_symbol=inst.provider_symbol,
                                       category=inst.category, unit=inst.unit, sort_order=order)
                db.add(row)
            row.name, row.provider_symbol, row.category, row.unit, row.sort_order = (
                inst.name, inst.provider_symbol, inst.category, inst.unit, order)
            try:
                q = provider.instrument_quote(inst.provider_symbol)
            except ProviderError as exc:
                # Keep the last good value; just record the error.
                row.error = str(exc)[:250]
                failed.append(inst.key)
                continue
            row.value, row.prev_close = q.value, q.prev_close
            row.change = (q.value - q.prev_close) if q.value is not None and q.prev_close else None
            row.change_pct = (q.value / q.prev_close - 1) * 100 if q.value is not None and q.prev_close else None
            row.sparkline, row.sparkline_label = q.sparkline, q.sparkline_label
            row.market_time, row.updated_at, row.error = q.market_time, now, None
            ok += 1
    return {"ok": ok, "failed": failed}


def ingest_benchmark() -> dict:
    s = get_settings()
    provider = get_price_provider()
    df = provider.daily_history([s.benchmark_symbol], s.history_period, equities=False).get(s.benchmark_symbol)
    if df is None or df.empty:
        raise ProviderError(f"No benchmark data for {s.benchmark_symbol}")
    with session_scope() as db:
        bulk_upsert(db, PriceBar, _bars_rows(s.benchmark_symbol, df), ["symbol", "date"])
    return {"bars": len(df)}


# ---------------------------------------------------------------------------
# Metrics + patterns
# ---------------------------------------------------------------------------
def _load_bars(db: Session, symbols: list[str], since: date) -> dict[str, pd.DataFrame]:
    rows = db.execute(
        select(PriceBar.symbol, PriceBar.date, PriceBar.open, PriceBar.high, PriceBar.low,
               PriceBar.close, PriceBar.volume)
        .where(PriceBar.symbol.in_(symbols), PriceBar.date >= since)
        .order_by(PriceBar.symbol, PriceBar.date)
    ).all()
    if not rows:
        return {}
    frame = pd.DataFrame(rows, columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    frame["date"] = pd.to_datetime(frame["date"])
    return {sym: g.drop(columns="symbol").set_index("date") for sym, g in frame.groupby("symbol", sort=False)}


def _f(x) -> float | None:
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(x) or np.isinf(x)) else x


def compute_and_detect(run_id: int) -> dict:
    s = get_settings()
    cfg = load_pattern_config(s.pattern_config_file)
    engine = PatternDetectionEngine(cfg)
    since = today_ist() - timedelta(days=int(ANALYSIS_BARS * 1.6))
    session_partial = in_session_window()
    today = today_ist()

    with session_scope() as db:
        companies = db.scalars(
            select(Company).where(Company.is_listed.is_(True), Company.history_end.is_not(None))
        ).all()
        comp = {c.symbol: (c.name, c.shares_outstanding) for c in companies}
        symbols = list(comp)
        bars: dict[str, pd.DataFrame] = {}
        for i in range(0, len(symbols), 400):  # chunked IN() for SQLite parameter limits
            bars.update(_load_bars(db, symbols[i : i + 400], since))
        bench = _load_bars(db, [s.benchmark_symbol], since).get(s.benchmark_symbol)
    bench_close = bench["close"] if bench is not None else None

    # --- eligibility (market cap >= threshold) -------------------------------
    eligible: dict[str, float] = {}
    notes: dict[str, tuple[str, float | None]] = {}  # symbol -> (reason, market cap if known)
    for sym, (_, shares) in comp.items():
        df = bars.get(sym)
        if df is None or df.empty:
            notes[sym] = ("No price history", None)
            continue
        if not shares:
            notes[sym] = ("Market cap unavailable", None)
            continue
        mcap = shares * float(df["close"].iloc[-1])
        if mcap >= s.min_market_cap_inr:
            eligible[sym] = mcap
        else:
            notes[sym] = ("Below market-cap threshold", mcap)
    log.info("Eligible companies: %d of %d with history", len(eligible), len(comp))
    if not eligible:
        # Never replace a good dataset with an empty one (e.g. provider outage).
        raise ProviderError("No eligible companies could be evaluated; keeping previous results")

    # --- relative strength rating (1-99 percentile) -------------------------
    rs_raw = {sym: relative_performance(bars[sym]["close"], bench_close) for sym in eligible}
    valid = pd.Series({k: v for k, v in rs_raw.items() if v is not None}, dtype=float)
    rs_rating = (valid.rank(pct=True) * 98 + 1).round().to_dict() if not valid.empty else {}

    snapshots, detections = [], []
    now = utcnow()
    failed = 0
    for sym, mcap in eligible.items():
        df = bars[sym]
        try:
            close, vol = df["close"], df["volume"]
            trend = engine.trend(df)
            rs = rs_rating.get(sym)
            dets = engine.analyze(sym, df, trend=trend, rs_rating=rs, benchmark_close=bench_close,
                                  session_partial=session_partial and df.index[-1].date() == today)
            win52 = df.iloc[-252:]
            avg50 = vol.iloc[-51:-1].dropna()
            a14 = atr(df, 14).iloc[-1]
            signals = sorted({d.pattern if d.status == "active" else f"{d.pattern}:{d.status}"
                              for d in dets if d.pattern not in ("uptrend", "downtrend")})
            snapshots.append({
                "symbol": sym,
                "name": comp[sym][0],
                "price": _f(close.iloc[-1]),
                "prev_close": _f(close.iloc[-2]) if len(close) > 1 else None,
                "change_1d_pct": _f(pct_change(close, 1)),
                "change_1w_pct": _f(pct_change(close, 5)),
                "change_1m_pct": _f(pct_change(close, 21)),
                "volume_1d": _f(vol.iloc[-1]),
                "avg_volume_1w": _f(vol.iloc[-5:].mean()) if vol.iloc[-5:].notna().any() else None,
                "avg_volume_50d": _f(avg50.mean()) if len(avg50) else None,
                "volume_ratio": _f(vol.iloc[-1] / avg50.mean()) if len(avg50) and avg50.mean() > 0 else None,
                "market_cap": mcap,
                "high_52w": _f(win52["high"].max()),
                "low_52w": _f(win52["low"].min()),
                "sma20": _f(sma(close, 20).iloc[-1]),
                "sma50": _f(sma(close, 50).iloc[-1]),
                "sma200": _f(sma(close, 200).iloc[-1]),
                "atr14_pct": _f(a14 / close.iloc[-1] * 100),
                "rs_rating": _f(rs),
                "trend": trend.label if trend else None,
                "trend_score": trend.score if trend else None,
                "signals": signals,
                "last_bar_date": df.index[-1].date(),
                "as_of": now,
                "updated_at": now,
            })
            detections.extend(dets)
        except Exception:  # noqa: BLE001
            failed += 1
            log.exception("Metric computation failed for %s", sym)

    # --- persist --------------------------------------------------------------
    with session_scope() as db:
        for sym, (note, mcap) in notes.items():
            # Market cap is stored for ineligible companies too, so ingestion can
            # refresh clearly-small companies less often.
            db.execute(update(Company).where(Company.symbol == sym)
                       .values(is_eligible=False, eligibility_note=note, market_cap=mcap))
        for sym, mcap in eligible.items():
            db.execute(update(Company).where(Company.symbol == sym)
                       .values(is_eligible=True, eligibility_note=None, market_cap=mcap))
        bulk_upsert(db, EquitySnapshot, snapshots, ["symbol"])
        db.execute(delete(EquitySnapshot).where(EquitySnapshot.symbol.not_in(list(eligible) or [""])))

        db.execute(update(PatternDetection).where(PatternDetection.is_active.is_(True)).values(is_active=False))
        new_rows: list[PatternDetection] = []
        for d in detections:
            row = PatternDetection(
                run_id=run_id, symbol=d.symbol, pattern=d.pattern, status=d.status,
                confidence=d.confidence, current_price=d.current_price, support=d.support,
                resistance=d.resistance, breakout_level=d.breakout_level, volume_current=d.volume_current,
                volume_avg=d.volume_avg, volume_ratio=d.volume_ratio, trend=d.trend, metrics=d.metrics,
                chart=d.chart, detected_at=d.detected_at, is_active=True,
            )
            new_rows.append(row)
        db.add_all(new_rows)
        db.flush()
        _update_breakout_lifecycle(db, new_rows, now)
        # Keep detection history bounded (30 days).
        db.execute(delete(PatternDetection).where(PatternDetection.is_active.is_(False),
                                                  PatternDetection.detected_at < now - timedelta(days=30)))

    by_pattern: dict[str, int] = {}
    for d in detections:
        by_pattern[d.pattern] = by_pattern.get(d.pattern, 0) + 1
    return {"eligible": len(eligible), "snapshots": len(snapshots), "failed": failed,
            "detections": len(detections), "by_pattern": by_pattern}


def _update_breakout_lifecycle(db: Session, rows: list[PatternDetection], now: datetime) -> None:
    """Carry breakout state across runs: potential -> confirmed / failed."""
    open_signals = {(b.symbol, b.source_pattern): b for b in db.scalars(
        select(BreakoutSignal).where(BreakoutSignal.is_active.is_(True))).all()}
    seen = set()
    for d in rows:
        if d.pattern not in BREAKOUT_PATTERNS or d.status not in BREAKOUT_STATUSES:
            continue
        key = (d.symbol, d.pattern)
        seen.add(key)
        sig = open_signals.get(key)
        if sig is None:
            sig = BreakoutSignal(symbol=d.symbol, source_pattern=d.pattern, status=d.status,
                                 first_detected_at=now, last_seen_at=now, is_active=True)
            db.add(sig)
        sig.breakout_level, sig.confidence, sig.volume_ratio = d.breakout_level, d.confidence, d.volume_ratio
        sig.last_seen_at, sig.detection_id = now, d.id
        if d.status == "confirmed" and sig.confirmed_at is None:
            sig.confirmed_at = now
        if d.status == "failed" and sig.failed_at is None:
            sig.failed_at = now
        sig.status = d.status
    for key, sig in open_signals.items():
        if key not in seen:
            sig.is_active, sig.closed_at = False, now


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_market_refresh(trigger: str = "schedule") -> int | None:
    job_id = _acquire_job(trigger)
    if job_id is None:
        return None
    log.info("Market refresh job %s started (%s)", job_id, trigger)
    stats: dict = {}
    errors: list[str] = []

    def step(name: str, fn, *args):
        t0 = time.time()
        try:
            stats[name] = fn(*args)
        except Exception as exc:  # noqa: BLE001
            log.error("Step %s failed: %s\n%s", name, exc, traceback.format_exc())
            errors.append(f"{name}: {exc}")
            stats[name] = {"error": str(exc)[:300]}
        stats.setdefault("timings", {})[name] = round(time.time() - t0, 1)

    step("universe", ingest_universe)
    step("instruments", ingest_instruments)
    step("benchmark", ingest_benchmark)
    step("prices", ingest_prices)
    step("shares", ingest_shares)
    step("analysis", compute_and_detect, job_id)

    analysis = stats.get("analysis", {})
    if not errors:
        status = "success"
    elif "error" not in analysis and analysis.get("snapshots"):
        status = "partial"  # some ingestion failed but fresh analysis was produced
    else:
        status = "failed"
    with session_scope() as db:
        job = db.get(JobRun, job_id)
        job.status = status
        job.finished_at = utcnow()
        job.symbols_total = analysis.get("eligible", 0) or 0
        job.symbols_ok = analysis.get("snapshots", 0) or 0
        job.symbols_failed = analysis.get("failed", 0) or 0
        job.detections = analysis.get("detections", 0) or 0
        job.stats = stats
        job.error = "\n".join(errors) or None
        job.message = (f"{job.symbols_ok} equities analysed, {job.detections} detections"
                       if job.symbols_ok else "No equities analysed")
    log.info("Market refresh job %s finished: %s (%s)", job_id, status, stats.get("timings"))
    return job_id


def latest_successful_run(db: Session) -> JobRun | None:
    return db.scalars(
        select(JobRun).where(JobRun.status.in_(("success", "partial")))
        .order_by(JobRun.finished_at.desc()).limit(1)
    ).first()
