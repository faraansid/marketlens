"""Provider registry: pick implementations by name from configuration.

To add a provider: implement `PriceProvider` / `UniverseProvider` from
`app.providers.base` and add a factory entry below. Nothing else changes.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.base import PriceProvider, UniverseProvider


def _yfinance(settings):
    from app.providers.yfinance_provider import YFinanceProvider

    return YFinanceProvider(settings)


def _nse_list(settings):
    from app.providers.nse_universe import NSEEquityListProvider

    return NSEEquityListProvider(settings)


PRICE_PROVIDERS = {"yfinance": _yfinance}
UNIVERSE_PROVIDERS = {"nse_equity_list": _nse_list}


@lru_cache
def get_price_provider() -> PriceProvider:
    s = get_settings()
    try:
        return PRICE_PROVIDERS[s.price_provider](s)
    except KeyError as exc:
        raise RuntimeError(f"Unknown PRICE_PROVIDER '{s.price_provider}'. Options: {list(PRICE_PROVIDERS)}") from exc


@lru_cache
def get_universe_provider() -> UniverseProvider:
    s = get_settings()
    try:
        return UNIVERSE_PROVIDERS[s.universe_provider](s)
    except KeyError as exc:
        raise RuntimeError(
            f"Unknown UNIVERSE_PROVIDER '{s.universe_provider}'. Options: {list(UNIVERSE_PROVIDERS)}"
        ) from exc
