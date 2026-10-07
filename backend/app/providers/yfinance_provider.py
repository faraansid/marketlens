"""yfinance-backed price provider (Yahoo Finance data for NSE tickers: SYMBOL.NS)."""
from __future__ import annotations

import logging
import warnings
from datetime import datetime, timezone

import pandas as pd

from app.config import Settings
from app.providers.base import InstrumentQuote, PriceProvider, ProviderError
from app.providers.resilience import RateLimiter, with_retry

log = logging.getLogger(__name__)
warnings.filterwarnings("ignore", module="yfinance")

_COLS = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}


def _normalize(df: pd.DataFrame, daily: bool, drop_zero_volume: bool = False) -> pd.DataFrame:
    """Rename to lowercase OHLCV, drop empty rows, validate values.

    `drop_zero_volume` removes zero-volume daily rows. Yahoo emits such rows
    for exchange holidays (e.g. a bar on Gandhi Jayanti carrying the previous
    close), which would otherwise appear as fake flat sessions. Only used for
    equities: indices legitimately report zero volume.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=list(_COLS.values()))
    out = df.rename(columns=_COLS)
    missing = {"open", "high", "low", "close"} - set(out.columns)
    if missing:
        raise ValueError(f"provider frame missing columns {missing}")
    if "volume" not in out.columns:
        out["volume"] = float("nan")
    out = out[list(_COLS.values())].dropna(subset=["close", "high", "low"])
    out["open"] = out["open"].fillna(out["close"])
    # Validation: prices must be positive and internally consistent.
    out = out[(out["close"] > 0) & (out["high"] > 0) & (out["low"] > 0)]
    out = out[out["high"] >= out["low"]]
    if drop_zero_volume:
        out = out[out["volume"].fillna(0) > 0]
    if daily:
        idx = pd.DatetimeIndex(out.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        out.index = idx.normalize()
        out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


class YFinanceProvider(PriceProvider):
    name = "yfinance"

    def __init__(self, settings: Settings):
        import yfinance as yf  # imported lazily so other providers don't need it

        self.yf = yf
        self.s = settings
        self.limiter = RateLimiter(settings.provider_min_interval_seconds)

    def to_provider_symbol(self, exchange_symbol: str) -> str:
        return f"{exchange_symbol}.NS"

    # -- bulk daily ----------------------------------------------------------
    def daily_history(self, provider_symbols: list[str], period: str,
                      equities: bool = True) -> dict[str, pd.DataFrame]:
        result: dict[str, pd.DataFrame] = {}
        bs = max(1, self.s.download_batch_size)
        for i in range(0, len(provider_symbols), bs):
            batch = provider_symbols[i : i + bs]
            try:
                raw = with_retry(
                    lambda b=batch: self.yf.download(
                        b,
                        period=period,
                        interval="1d",
                        group_by="ticker",
                        auto_adjust=False,  # keep traded prices; corporate actions handled by re-backfill
                        actions=False,
                        threads=self.s.download_threads,
                        progress=False,
                    ),
                    limiter=self.limiter,
                    retries=self.s.provider_max_retries,
                    backoff=self.s.provider_backoff_seconds,
                    what=f"download batch {i // bs + 1} ({len(batch)} symbols)",
                )
            except ProviderError as exc:
                log.error("Daily batch failed permanently: %s", exc)
                continue
            n_batches = (len(provider_symbols) + bs - 1) // bs
            if (i // bs + 1) % 5 == 0 or i // bs + 1 == n_batches:
                log.info("Daily download %s: batch %d/%d", period, i // bs + 1, n_batches)
            if raw is None or raw.empty:
                continue
            for sym in batch:
                try:
                    if isinstance(raw.columns, pd.MultiIndex):
                        if sym not in raw.columns.get_level_values(0):
                            continue
                        df = raw[sym]
                    else:  # single-ticker download
                        df = raw
                    norm = _normalize(df, daily=True, drop_zero_volume=equities)
                    if not norm.empty:
                        result[sym] = norm
                except Exception as exc:  # noqa: BLE001
                    log.debug("Skipping %s: %s", sym, exc)
        return result

    # -- intraday --------------------------------------------------------------
    def intraday_history(self, provider_symbol: str, period: str, interval: str) -> pd.DataFrame:
        df = with_retry(
            lambda: self.yf.Ticker(provider_symbol).history(period=period, interval=interval, auto_adjust=False),
            limiter=self.limiter,
            retries=2,
            backoff=self.s.provider_backoff_seconds,
            what=f"intraday {provider_symbol} {period}/{interval}",
        )
        return _normalize(df, daily=False)

    # -- fundamentals ------------------------------------------------------------
    def shares_outstanding(self, provider_symbol: str) -> float | None:
        def _get():
            v = self.yf.Ticker(provider_symbol).fast_info.shares
            return float(v) if v else None

        try:
            v = with_retry(_get, limiter=self.limiter, retries=2,
                           backoff=self.s.provider_backoff_seconds, what=f"shares {provider_symbol}")
        except ProviderError as exc:
            log.debug("No share count for %s: %s", provider_symbol, exc)
            return None
        return v if v and v > 0 else None

    # -- instruments ---------------------------------------------------------------
    def instrument_quote(self, provider_symbol: str) -> InstrumentQuote:
        daily = with_retry(
            lambda: self.yf.Ticker(provider_symbol).history(period="1mo", interval="1d", auto_adjust=False),
            limiter=self.limiter,
            retries=self.s.provider_max_retries,
            backoff=self.s.provider_backoff_seconds,
            what=f"instrument {provider_symbol}",
        )
        if daily is None or daily.empty or len(daily) < 2:
            raise ProviderError(f"insufficient data for {provider_symbol}")
        closes = daily["Close"].dropna()
        value, prev_close = float(closes.iloc[-1]), float(closes.iloc[-2])
        market_time = None

        # The latest intraday bar gives an accurate "as of" time (daily bars are
        # stamped at midnight) and a fresher value while the market is open.
        try:
            intra = self.yf.Ticker(provider_symbol).history(period="5d", interval="15m", auto_adjust=False)
            intra = intra.dropna(subset=["Close"]) if intra is not None else None
        except Exception:  # noqa: BLE001 - fall back to daily data
            intra = None
        if intra is not None and not intra.empty:
            ts = intra.index[-1]
            market_time = ts.to_pydatetime().astimezone(timezone.utc)
            value = float(intra["Close"].iloc[-1])
            intra_day = ts.tz_convert(closes.index.tz).date() if closes.index.tz is not None else ts.date()
            if closes.index[-1].date() == intra_day:
                prev_close = float(closes.iloc[-2])
            else:  # daily bar for the current session not published yet
                prev_close = float(closes.iloc[-1])
                closes = pd.concat([closes, pd.Series([value], index=[closes.index[-1] + pd.Timedelta(days=1)])])
            closes.iloc[-1] = value
        else:
            ts = closes.index[-1].to_pydatetime()
            market_time = (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

        return InstrumentQuote(
            value=value,
            prev_close=prev_close,
            market_time=market_time,
            sparkline=[round(float(x), 4) for x in closes.tolist()],
            sparkline_label="1M",
        )

    def benchmark_daily(self, provider_symbol: str, period: str) -> pd.DataFrame:
        df = with_retry(
            lambda: self.yf.Ticker(provider_symbol).history(period=period, interval="1d", auto_adjust=False),
            limiter=self.limiter,
            retries=self.s.provider_max_retries,
            backoff=self.s.provider_backoff_seconds,
            what=f"benchmark {provider_symbol}",
        )
        return _normalize(df, daily=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
