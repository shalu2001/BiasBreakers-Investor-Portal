"""Market-index reader (Cosmos DB SPSL20_DB.sp_sl20_index).

Documents are ``{date:"YYYY-MM-DD", sp_sl20_close: float}``. Returns a close-price Series
over the same trailing ``covariance_window_trading_days`` window used for prices, so the
market-implied risk aversion is computed on the same horizon.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.data.mongo import MongoConnection

logger = logging.getLogger(__name__)

_CLOSE_CANDIDATES = ("sp_sl20_close", "close", "sp_sl20", "index_close", "value")
_DATE_CANDIDATES = ("date", "Date", "trading_date")


def _resolve_column(columns, candidates) -> Optional[str]:
    lowered = {str(col).lower().strip(): col for col in columns}
    for candidate in candidates:
        key = candidate.lower().strip()
        if key in lowered:
            return lowered[key]
    return None


class IndexRepository:
    """Load the market-index close Series for the trailing window."""

    def __init__(self, connection: MongoConnection, settings: NarrativePipelineSettings):
        self.connection = connection
        self.settings = settings

    def load_series(self, as_of: datetime, window_trading_days: Optional[int] = None) -> pd.Series:
        window = window_trading_days if window_trading_days is not None else self.settings.covariance_window_trading_days
        collection = self.connection.collection(self.settings.market_database, self.settings.index_collection)
        as_of_str = as_of.strftime("%Y-%m-%d")

        frame = pd.DataFrame(list(collection.find({"date": {"$lte": as_of_str}})))
        if frame.empty:
            return pd.Series(dtype=float)

        close_col = _resolve_column(frame.columns, _CLOSE_CANDIDATES)
        date_col = _resolve_column(frame.columns, _DATE_CANDIDATES)
        if close_col is None or date_col is None:
            raise ValueError(
                f"Index documents missing close/date fields. Found columns: {list(frame.columns)}"
            )

        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
        frame[close_col] = pd.to_numeric(frame[close_col], errors="coerce")
        frame = frame.dropna(subset=[date_col, close_col]).sort_values(date_col)
        series = pd.Series(frame[close_col].to_numpy(), index=frame[date_col])
        return series.tail(int(window))
