"""Windowed, pre-enriched news reader (Cosmos DB, Mongo API).

Reads already-enriched articles (FinBERT sentiment, 768-d embeddings, macro/micro
classification) from every news collection in the news database except the excluded
reference collections, filtered to ``[as_of - lookback_days, as_of)``. Normalization
mirrors the research ``MongoNewsLoader``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.data.mongo import MongoConnection
from narrative_engine.data.ticker_info_repository import TickerReference
from narrative_engine.pipeline.filters import (
    deduplicate_articles,
    ensure_required_columns,
    filter_valid_articles,
)
from narrative_engine.portfolio.macro_mapping import normalize_ticker

logger = logging.getLogger(__name__)


DEFAULT_PROJECTION = {
    "_id": 1,
    "asset_id": 1,
    "headline": 1,
    "content": 1,
    "final_embedding": 1,
    "final_sentiment_score": 1,
    "final_sentiment_label": 1,
    "market_classification": 1,
    "matched_company_name": 1,
    "matched_symbol": 1,
    "published_date": 1,
    "source": 1,
    # CSE-announcement specific fields (null for other collections).
    "company": 1,
    "companyId": 1,
    "symbol": 1,
    "remarks": 1,
    "title": 1,
}


def _normalize_company_name(value: object) -> str:
    return " ".join(str(value or "").strip().split()).lower()


class NewsRepository:
    """Load and normalize windowed financial news from Cosmos DB."""

    def __init__(self, connection: MongoConnection, settings: NarrativePipelineSettings):
        self.connection = connection
        self.settings = settings

    def load(
        self,
        as_of: datetime,
        lookback_days: Optional[int] = None,
        ticker_reference: Optional[TickerReference] = None,
    ) -> pd.DataFrame:
        """Return cleaned, enriched news published in ``[as_of - lookback_days, as_of)``.

        ``ticker_reference`` enables the CSE-announcement adapter (see
        ``_apply_cse_adapter``); without it, CSE rows are left unclassified and dropped by
        the macro/micro split downstream, matching the other pre-enriched sources.
        """

        lookback = lookback_days if lookback_days is not None else self.settings.lookback_days
        start = as_of - timedelta(days=int(lookback))
        # published_date is stored as an ISO "YYYY-MM-DD" string; lexicographic range works.
        start_str = start.strftime("%Y-%m-%d")
        end_str = as_of.strftime("%Y-%m-%d")
        date_filter = {"published_date": {"$gte": start_str, "$lt": end_str}}

        database = self.connection.database(self.settings.database_name)
        excluded = set(self.settings.excluded_collections)
        collection_names = [name for name in database.list_collection_names() if name not in excluded]
        logger.info("Loading news collections %s for window [%s, %s)", collection_names, start_str, end_str)

        rows: List[Dict[str, Any]] = []
        for collection_name in collection_names:
            cursor = database[collection_name].find(date_filter, DEFAULT_PROJECTION)
            for document in cursor:
                row = dict(document)
                row["_id"] = str(row.get("_id", ""))
                row["collection_name"] = collection_name
                rows.append(row)

        dataframe = pd.DataFrame(rows)
        if dataframe.empty:
            return dataframe

        dataframe = self._normalize_dataframe(dataframe)
        dataframe = self._apply_cse_adapter(dataframe, ticker_reference)
        dataframe = deduplicate_articles(dataframe)
        dataframe = filter_valid_articles(dataframe)
        dataframe = ensure_required_columns(dataframe)
        return dataframe.reset_index(drop=True)

    def _apply_cse_adapter(
        self, dataframe: pd.DataFrame, ticker_reference: Optional[TickerReference]
    ) -> pd.DataFrame:
        """Turn raw CSE announcements into universe-scoped micro news.

        CSE docs are enriched (sentiment + embeddings) but carry no ``market_classification``
        and often empty content. For rows from the CSE collection we:
          1. drop zero-sentiment noise (``final_sentiment_score == 0``),
          2. recover text from ``remarks``/``title`` when ``content``/``headline`` are empty,
          3. resolve the ticker via companyId → symbol → company name (Ticker_Info),
          4. mark them ``micro`` with canonical ``matched_symbol``/``matched_company_name``,
          5. keep only tickers inside the SL20 universe.
        Non-CSE rows pass through untouched.
        """

        if "collection_name" not in dataframe.columns:
            return dataframe
        is_cse = dataframe["collection_name"] == self.settings.cse_collection
        if not is_cse.any():
            return dataframe

        others = dataframe[~is_cse].copy()
        if ticker_reference is None or not ticker_reference.universe:
            logger.warning("No ticker reference available; dropping CSE announcements.")
            return others.reset_index(drop=True)

        cse = dataframe[is_cse].copy()

        # 1. drop zero-sentiment noise
        cse = cse[pd.to_numeric(cse["final_sentiment_score"], errors="coerce").fillna(0.0) != 0.0]
        if cse.empty:
            return others.reset_index(drop=True)

        # 2. recover text from remarks/title
        content = cse["content"].fillna("").astype(str) if "content" in cse.columns else pd.Series("", index=cse.index)
        remarks = cse["remarks"].fillna("").astype(str) if "remarks" in cse.columns else pd.Series("", index=cse.index)
        cse["content"] = content.where(content.str.strip() != "", remarks)
        if "title" in cse.columns:
            headline = cse["headline"].fillna("").astype(str)
            title = cse["title"].fillna("").astype(str)
            cse["headline"] = title.where(title.str.strip() != "", headline)

        # 3. resolve ticker
        resolved = cse.apply(lambda row: self._resolve_cse_ticker(row, ticker_reference), axis=1)
        cse["matched_symbol"] = resolved
        cse["matched_company_name"] = resolved.map(lambda t: ticker_reference.ticker_to_company.get(t, ""))

        # 4. classify micro
        cse["market_classification"] = "micro"

        # 5. keep only universe tickers
        cse = cse[cse["matched_symbol"].isin(ticker_reference.universe)]

        combined = pd.concat([others, cse], ignore_index=True)
        logger.info("CSE adapter: kept %d universe-mapped micro announcements.", int(len(cse)))
        return combined

    @staticmethod
    def _resolve_cse_ticker(row: pd.Series, reference: TickerReference) -> str:
        """Resolve a CSE row to a ticker: companyId → symbol → company name."""

        company_id = row.get("companyId")
        if company_id not in (None, ""):
            try:
                key = str(int(company_id))
            except (TypeError, ValueError):
                key = str(company_id).strip()
            ticker = reference.companyid_to_ticker.get(key)
            if ticker:
                return ticker

        symbol = normalize_ticker(row.get("symbol"))
        if symbol and symbol in reference.universe:
            return symbol

        name = _normalize_company_name(row.get("company"))
        if name:
            direct = reference.company_to_ticker.get(name)
            if direct:
                return direct
            matches = {
                ticker
                for key, ticker in reference.company_to_ticker.items()
                if key and (name in key or key in name)
            }
            if len(matches) == 1:
                return next(iter(matches))
        return ""

    def _normalize_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        result = dataframe.copy()
        result["published_date"] = pd.to_datetime(self._series_or_default(result, "published_date"), errors="coerce")
        result["headline"] = self._series_or_default(result, "headline", "").fillna("").astype(str)
        result["content"] = self._series_or_default(result, "content", "").fillna("").astype(str)
        result["market_classification"] = (
            self._series_or_default(result, "market_classification", "").fillna("").astype(str).str.lower().str.strip()
        )
        result["matched_company_name"] = self._series_or_default(result, "matched_company_name", "").fillna("").astype(str).str.strip()
        result["matched_symbol"] = self._series_or_default(result, "matched_symbol", "").fillna("").astype(str).str.strip()
        result["source"] = self._series_or_default(result, "source", "").fillna("").astype(str).str.strip()
        result["final_sentiment_score"] = pd.to_numeric(self._series_or_default(result, "final_sentiment_score"), errors="coerce")
        result["final_sentiment_label"] = self._series_or_default(result, "final_sentiment_label", "").fillna("").astype(str).str.strip()
        result["final_embedding"] = self._series_or_default(result, "final_embedding").apply(self._normalize_embedding)
        return result

    @staticmethod
    def _series_or_default(dataframe: pd.DataFrame, column: str, default: Any = None) -> pd.Series:
        if column in dataframe.columns:
            return dataframe[column]
        return pd.Series([default] * len(dataframe), index=dataframe.index)

    @staticmethod
    def _normalize_embedding(value: Any) -> Optional[List[float]]:
        if value is None:
            return None
        array = np.asarray(value, dtype=float).reshape(-1)
        if array.size != 768:
            return None
        if np.isnan(array).any():
            return None
        return array.astype(float).tolist()
