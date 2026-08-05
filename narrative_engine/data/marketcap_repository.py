"""Market-cap reader (Cosmos DB SPSL20_DB.marketcap_2026).

Documents are ``{ticker, date:"YYYY-MM-DD", marketcap: float}``. Returns
``{ticker: marketcap}`` using each ticker's latest-dated point on/before ``as_of``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.data.mongo import MongoConnection
from narrative_engine.portfolio.macro_mapping import normalize_ticker

logger = logging.getLogger(__name__)

_TICKER_CANDIDATES = ("ticker", "Ticker", "symbol", "COMPANY CODE", "company code", "COMPANY ID")
_CAP_CANDIDATES = ("marketcap", "market_cap", "MARKET CAP (Rs.)", "market cap (rs.)", "Market Cap")
_DATE_CANDIDATES = ("date", "Date", "as_of", "trading_date")


def _resolve_column(columns, candidates) -> Optional[str]:
    lowered = {str(col).lower().strip(): col for col in columns}
    for candidate in candidates:
        key = candidate.lower().strip()
        if key in lowered:
            return lowered[key]
    return None


class MarketCapRepository:
    """Load latest-dated market caps as {ticker: value}."""

    def __init__(self, connection: MongoConnection, settings: NarrativePipelineSettings):
        self.connection = connection
        self.settings = settings

    def load(self, as_of: datetime) -> Dict[str, float]:
        collection = self.connection.collection(self.settings.market_database, self.settings.marketcap_collection)
        as_of_str = as_of.strftime("%Y-%m-%d")

        frame = pd.DataFrame(list(collection.find({})))
        if frame.empty:
            return {}

        ticker_col = _resolve_column(frame.columns, _TICKER_CANDIDATES)
        cap_col = _resolve_column(frame.columns, _CAP_CANDIDATES)
        date_col = _resolve_column(frame.columns, _DATE_CANDIDATES)
        if ticker_col is None or cap_col is None:
            raise ValueError(
                f"Market cap documents missing ticker/marketcap fields. Found columns: {list(frame.columns)}"
            )

        frame[ticker_col] = frame[ticker_col].map(normalize_ticker)
        frame[cap_col] = pd.to_numeric(
            frame[cap_col].astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce"
        )
        frame = frame.dropna(subset=[ticker_col, cap_col])
        frame = frame[(frame[ticker_col] != "") & (frame[cap_col] > 0.0)]

        if date_col is not None:
            frame["_parsed_date"] = pd.to_datetime(frame[date_col], errors="coerce")
            as_of_ts = pd.Timestamp(as_of_str)
            # Keep only points on/before as_of when a date is available; if that removes
            # everything (e.g. all caps dated after as_of), fall back to all rows.
            on_or_before = frame[frame["_parsed_date"].isna() | (frame["_parsed_date"] <= as_of_ts)]
            usable = on_or_before if not on_or_before.empty else frame
            usable = usable.sort_values("_parsed_date")
            latest = usable.groupby(ticker_col, as_index=False).last()
            return {row[ticker_col]: float(row[cap_col]) for _, row in latest.iterrows()}

        grouped = frame.groupby(ticker_col, as_index=False)[cap_col].last()
        return {row[ticker_col]: float(row[cap_col]) for _, row in grouped.iterrows()}
