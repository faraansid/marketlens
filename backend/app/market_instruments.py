"""Instruments shown in the market-overview bento grid.

These are indices / FX / commodities (not equities), so a configured list is
appropriate. Only tickers verified to return full daily history from the
current provider are included; others would produce misleading sparklines.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentDef:
    key: str
    name: str
    provider_symbol: str
    category: str  # index | volatility | fx | commodity
    unit: str | None = None


INSTRUMENTS: list[InstrumentDef] = [
    InstrumentDef("NIFTY50", "NIFTY 50", "^NSEI", "index"),
    InstrumentDef("SENSEX", "BSE SENSEX", "^BSESN", "index"),
    InstrumentDef("BANKNIFTY", "NIFTY Bank", "^NSEBANK", "index"),
    InstrumentDef("NIFTYIT", "NIFTY IT", "^CNXIT", "index"),
    InstrumentDef("NIFTYNEXT50", "NIFTY Next 50", "^NSMIDCP", "index"),
    InstrumentDef("INDIAVIX", "India VIX", "^INDIAVIX", "volatility"),
    InstrumentDef("USDINR", "USD / INR", "INR=X", "fx", "₹"),
    InstrumentDef("BRENT", "Brent Crude", "BZ=F", "commodity", "$/bbl"),
    InstrumentDef("WTI", "WTI Crude", "CL=F", "commodity", "$/bbl"),
    InstrumentDef("GOLD", "Gold", "GC=F", "commodity", "$/oz"),
    InstrumentDef("SILVER", "Silver", "SI=F", "commodity", "$/oz"),
]
