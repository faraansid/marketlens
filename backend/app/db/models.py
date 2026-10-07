"""Database models.

Design notes
------------
* `price_bars` is the single source of historical OHLCV data. Volume lives on the
  bar row (no separate volume table) to avoid duplicating history.
* `equity_snapshots` holds the latest computed metrics per company (one row per
  symbol, overwritten each run). It is what the equity table queries, so its
  sortable columns are indexed.
* `pattern_detections` holds the output of the pattern engine for each run.
  Only rows with `is_active=True` belong to the latest successful scan.
* `breakout_signals` tracks the *lifecycle* of a breakout (potential ->
  confirmed / failed) across runs, which a single scan cannot know on its own.
* `job_runs` records every pipeline run and doubles as a coarse lock.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class UTCDateTime(TypeDecorator):
    """Stores datetimes as UTC and always returns timezone-aware UTC values
    (SQLite drops tzinfo otherwise)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Optional and not shown in the UI: sign-in is by username and passwords are
    # changed with the master password, so no feature depends on email.
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    remember: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------
class Company(Base):
    """Listed company from the universe provider (NSE equity list)."""

    __tablename__ = "companies"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)  # NSE symbol, e.g. RELIANCE
    name: Mapped[str] = mapped_column(String(255))
    isin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    series: Mapped[str | None] = mapped_column(String(8), nullable=True)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    provider_symbol: Mapped[str] = mapped_column(String(40))  # e.g. RELIANCE.NS
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)  # INR
    is_listed: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    eligibility_note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    history_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    history_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class PriceBar(Base):
    """Daily OHLCV bar. One row per (symbol, trading date). Also used for
    benchmark/index history (symbol = provider symbol such as ^NSEI)."""

    __tablename__ = "price_bars"

    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EquitySnapshot(Base):
    """Latest computed metrics for an eligible company (one row per symbol)."""

    __tablename__ = "equity_snapshots"

    symbol: Mapped[str] = mapped_column(ForeignKey("companies.symbol", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_1d_pct: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    change_1w_pct: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    change_1m_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_1d: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    avg_volume_1w: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    avg_volume_50d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    high_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_52w: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma20: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma50: Mapped[float | None] = mapped_column(Float, nullable=True)
    sma200: Mapped[float | None] = mapped_column(Float, nullable=True)
    atr14_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rs_rating: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    trend: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    signals: Mapped[list | None] = mapped_column(JSON, nullable=True)  # e.g. ["vcp","breakout:confirmed"]
    last_bar_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MarketInstrument(Base):
    """Index / FX / commodity shown in the market overview bento grid."""

    __tablename__ = "market_instruments"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    provider_symbol: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(24))  # index | fx | commodity | volatility
    unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sparkline: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sparkline_label: Mapped[str | None] = mapped_column(String(24), nullable=True)
    market_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ---------------------------------------------------------------------------
# Analysis output
# ---------------------------------------------------------------------------
class PatternDetection(Base):
    __tablename__ = "pattern_detections"
    __table_args__ = (
        Index("ix_pd_active_pattern", "is_active", "pattern", "confidence"),
        Index("ix_pd_symbol_active", "symbol", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("job_runs.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("companies.symbol", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(32))  # uptrend | downtrend | falling_wedge | vcp | breakout
    status: Mapped[str] = mapped_column(String(24), index=True)  # forming|potential|confirmed|failed|active
    confidence: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    support: Mapped[float | None] = mapped_column(Float, nullable=True)
    resistance: Mapped[float | None] = mapped_column(Float, nullable=True)
    breakout_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    trend: Mapped[str | None] = mapped_column(String(24), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    chart: Mapped[list | None] = mapped_column(JSON, nullable=True)  # recent closes for mini chart
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BreakoutSignal(Base):
    """Lifecycle of a breakout setup across scans (one open row per symbol+source)."""

    __tablename__ = "breakout_signals"
    __table_args__ = (Index("ix_bs_active", "is_active", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("companies.symbol", ondelete="CASCADE"), index=True)
    source_pattern: Mapped[str] = mapped_column(String(32))  # breakout | vcp | falling_wedge
    status: Mapped[str] = mapped_column(String(24))  # potential | confirmed | failed
    breakout_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    detection_id: Mapped[int | None] = mapped_column(
        ForeignKey("pattern_detections.id", ondelete="SET NULL"), nullable=True
    )


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), default="market_refresh")
    trigger: Mapped[str] = mapped_column(String(16), default="schedule")  # schedule|startup|manual
    status: Mapped[str] = mapped_column(String(16), index=True)  # running|success|partial|failed|skipped
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    symbols_total: Mapped[int] = mapped_column(Integer, default=0)
    symbols_ok: Mapped[int] = mapped_column(Integer, default=0)
    symbols_failed: Mapped[int] = mapped_column(Integer, default=0)
    detections: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AppState(Base):
    """Small key/value store (e.g. last universe refresh time)."""

    __tablename__ = "app_state"
    __table_args__ = (UniqueConstraint("key"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
