"""Universe provider: NSE's official list of listed equities (EQUITY_L.csv).

That file only contains ordinary equity shares of listed companies. ETFs,
REITs, InvITs, mutual funds, bonds and other instruments are published in
separate files, so they are excluded by construction. We additionally filter
on the SERIES column (default EQ and BE) and drop any name that looks like a
non-company instrument, as a defensive second check.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime

import httpx

from app.config import Settings
from app.providers.base import ProviderError, UniverseEntry, UniverseProvider
from app.providers.resilience import with_retry

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
}

# Defensive exclusion of instrument-like names that should never be in this file.
_NON_COMPANY = re.compile(r"\b(ETF|REIT|INVIT|INFRASTRUCTURE INVESTMENT TRUST|MUTUAL FUND|BEES|FUND)\b", re.I)


class NSEEquityListProvider(UniverseProvider):
    name = "nse_equity_list"

    def __init__(self, settings: Settings):
        self.s = settings

    def _download(self) -> str:
        with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
            r = client.get(self.s.nse_equity_list_url)
            if r.status_code == 429:
                raise ProviderError("429 Too Many Requests")
            r.raise_for_status()
            return r.text

    def fetch_universe(self) -> list[UniverseEntry]:
        text = with_retry(self._download, limiter=None, retries=self.s.provider_max_retries,
                          backoff=self.s.provider_backoff_seconds, what="NSE equity list")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ProviderError("NSE equity list: empty file")
        # Header names in this file contain stray spaces (" SERIES").
        reader.fieldnames = [f.strip().upper() for f in reader.fieldnames]
        required = {"SYMBOL", "NAME OF COMPANY", "SERIES"}
        if not required.issubset(reader.fieldnames):
            raise ProviderError(f"NSE equity list: unexpected columns {reader.fieldnames}")

        allowed = set(self.s.series_list)
        out: list[UniverseEntry] = []
        for row in reader:
            row = {k: (v or "").strip() for k, v in row.items() if k}
            sym, name, series = row["SYMBOL"], row["NAME OF COMPANY"], row["SERIES"].upper()
            if not sym or not name or series not in allowed or _NON_COMPANY.search(name):
                continue
            listed = None
            if row.get("DATE OF LISTING"):
                try:
                    listed = datetime.strptime(row["DATE OF LISTING"], "%d-%b-%Y").date()
                except ValueError:
                    pass
            out.append(UniverseEntry(symbol=sym, name=name, series=series,
                                     isin=row.get("ISIN NUMBER") or None, listing_date=listed))
        if len(out) < 500:  # sanity check: NSE lists ~2,000+ EQ companies
            raise ProviderError(f"NSE equity list looks truncated ({len(out)} rows)")
        log.info("Universe provider returned %d listed equities", len(out))
        return out
