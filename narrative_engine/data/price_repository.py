"""Price reader (Cosmos DB SPSL20_DB.tickerdata_2020-2026).

Documents are ``{ticker, date:"YYYY-MM-DD", "closing price": float}``. This returns a wide
date x ticker close-price matrix over the trailing ``covariance_window_trading_days`` trading
dates on/before ``as_of``, matching the shape the research ``load_prices_matrix`` produced.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.data.mongo import MongoConnection

logger = logging.getLogger(__name__)

_TICKER_CANDIDATES = ("ticker", "Ticker", "symbol", "COMPANY ID", "company id")
_CLOSE_CANDIDATES = ("closing price", "closing_price", "close", "close price (rs.)", "price")
_DATE_CANDIDATES = ("date", "Date", "TRADING DATE", "trading_date")


def _resolve_column(columns, candidates) -> Optional[str]:
    lowered = {str(col).lower().strip(): col for col in columns}
    for candidate in candidates:
        key = candidate.lower().strip()
        if key in lowered:
            return lowered[key]
    return None


class PriceRepository:
    """Load a wide close-price matrix for the trailing trading-day window."""

    def __init__(self, connection: MongoConnection, settings: NarrativePipelineSettings):
        self.connection = connection
        self.settings = settings

    def load_matrix(self, as_of: datetime, window_trading_days: Optional[int] = None) -> pd.DataFrame:
        window = window_trading_days if window_trading_days is not None else self.settings.covariance_window_trading_days
        collection = self.connection.collection(self.settings.market_database, self.settings.price_collection)
        as_of_str = as_of.strftime("%Y-%m-%d")

        # Distinct trading dates on/before as_of, take the trailing `window` of them.
        all_dates = [d for d in collection.distinct("date", {"date": {"$lte": as_of_str}}) if d]
        if not all_dates:
            return pd.DataFrame()
        trailing_dates = sorted(str(d) for d in all_dates)[-int(window):]
        if not trailing_dates:
            return pd.DataFrame()

        cursor = collection.find({"date": {"$in": trailing_dates}})
        frame = pd.DataFrame(list(cursor))
        if frame.empty:
            return pd.DataFrame()

        ticker_col = _resolve_column(frame.columns, _TICKER_CANDIDATES)
        close_col = _resolve_column(frame.columns, _CLOSE_CANDIDATES)
        date_col = _resolve_column(frame.columns, _DATE_CANDIDATES)
        if ticker_col is None or close_col is None or date_col is None:
            raise ValueError(
                f"Price documents missing ticker/close/date fields. Found columns: {list(frame.columns)}"
            )

        return self._pivot(frame, ticker_col, close_col, date_col)

    @staticmethod
    def _pivot(frame: pd.DataFrame, ticker_col: str, close_col: str, date_col: str) -> pd.DataFrame:
        pivoted = frame.copy()
        pivoted[ticker_col] = pivoted[ticker_col].astype(str).str.strip().str.upper()
        pivoted[close_col] = pd.to_numeric(
            pivoted[close_col].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )
        pivoted[date_col] = pd.to_datetime(pivoted[date_col], errors="coerce")
        pivoted = pivoted.dropna(subset=[date_col, ticker_col, close_col])
        wide = pivoted.pivot_table(
            index=date_col,
            columns=ticker_col,
            values=close_col,
            aggfunc="last",
        ).sort_index()
        wide = wide.ffill().bfill().dropna(axis=1, how="any")
        return wide
