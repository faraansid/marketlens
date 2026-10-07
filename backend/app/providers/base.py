"""Provider interfaces.

The rest of the application only depends on these abstract classes, never on
yfinance/NSE directly, so a provider can be swapped (e.g. for a paid feed) by
implementing these two classes and registering it in `registry.py`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd


class ProviderError(Exception):
    """Generic provider failure (network, bad payload...)."""


class RateLimitError(ProviderError):
    """Provider signalled throttling (HTTP 429 or equivalent)."""


@dataclass(slots=True)
class UniverseEntry:
    symbol: str  # exchange symbol (RELIANCE)
    name: str
    series: str | None
    isin: str | None
    listing_date: date | None


@dataclass(slots=True)
class InstrumentQuote:
    value: float | None
    prev_close: float | None
    market_time: datetime | None
    sparkline: list[float]
    sparkline_label: str


class UniverseProvider(ABC):
    """Source of the list of listed companies (equity universe)."""

    name: str = "abstract"

    @abstractmethod
    def fetch_universe(self) -> list[UniverseEntry]: ...


class PriceProvider(ABC):
    """Source of prices, volumes and share counts.

    OHLCV frames returned by this interface must have a `DatetimeIndex`
    (tz-naive dates for daily data) and columns: open, high, low, close, volume.
    """

    name: str = "abstract"

    @abstractmethod
    def to_provider_symbol(self, exchange_symbol: str) -> str:
        """Map an exchange symbol (RELIANCE) to this provider's ticker (RELIANCE.NS)."""

    @abstractmethod
    def daily_history(self, provider_symbols: list[str], period: str,
                      equities: bool = True) -> dict[str, pd.DataFrame]:
        """Daily bars for many symbols. Missing symbols are simply absent from the result.
        With `equities=True` non-trading (zero-volume) rows must be removed."""

    @abstractmethod
    def intraday_history(self, provider_symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Intraday bars for one symbol (index is tz-aware)."""

    @abstractmethod
    def shares_outstanding(self, provider_symbol: str) -> float | None:
        """Shares outstanding, or None if the provider does not have it."""

    @abstractmethod
    def instrument_quote(self, provider_symbol: str) -> InstrumentQuote:
        """Latest value, previous close and a short sparkline for an index/FX/commodity."""
