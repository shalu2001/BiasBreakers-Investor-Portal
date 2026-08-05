"""Ticker reference reader (Cosmos DB FinancialNewsDB.Ticker_Info).

Documents look like ``{Company, "CSE Ticker": "AEL.N0000", "CSE companyIds": 1141, ...}``.
Produces a ``TickerReference`` bundle with everything downstream needs:
  - ``company_to_ticker``: normalized company name → ticker (micro view resolution / BL)
  - ``records``: ``TickerInfoRecord`` list (LLM macro-to-basket mapping)
  - ``companyid_to_ticker``: CSE companyId (as str) → ticker (CSE announcement mapping)
  - ``ticker_to_company``: ticker → canonical Company name
  - ``universe``: set of tickers (the SL20 constituents)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.data.mongo import MongoConnection
from narrative_engine.portfolio.macro_mapping import (
    TickerInfoRecord,
    normalize_ticker,
    normalize_ticker_info_documents,
)

logger = logging.getLogger(__name__)

_COMPANY_FIELDS = ("Company", "company", "matched_company_name", "name", "NAME")
_TICKER_FIELDS = ("CSE Ticker", "matched_symbol", "ticker", "Ticker", "symbol", "Symbol")
_COMPANY_ID_FIELDS = ("CSE companyIds", "companyIds", "CSE_companyIds", "companyId")


def _normalize_company_name(value: object) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _iter_company_ids(value: Any):
    """Yield normalized string company ids from a scalar, list, or comma-string."""

    if value is None or value == "":
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_company_ids(item)
        return
    if isinstance(value, str):
        for part in value.replace(";", ",").split(","):
            part = part.strip()
            if part:
                yield part
        return
    try:
        yield str(int(value))
    except (TypeError, ValueError):
        yield str(value).strip()


@dataclass
class TickerReference:
    """Everything the engine needs from the ticker reference collection."""

    company_to_ticker: Dict[str, str] = field(default_factory=dict)
    records: List[TickerInfoRecord] = field(default_factory=list)
    companyid_to_ticker: Dict[str, str] = field(default_factory=dict)
    ticker_to_company: Dict[str, str] = field(default_factory=dict)
    universe: Set[str] = field(default_factory=set)


class TickerInfoRepository:
    """Load company→ticker mapping, companyId mapping, and normalized ticker records."""

    def __init__(self, connection: MongoConnection, settings: NarrativePipelineSettings):
        self.connection = connection
        self.settings = settings

    def load(self) -> TickerReference:
        collection = self.connection.collection(
            self.settings.ticker_info_database, self.settings.ticker_info_collection
        )
        documents = list(collection.find({}))

        reference = TickerReference(records=normalize_ticker_info_documents(documents))
        for document in documents:
            company = next((document.get(field_) for field_ in _COMPANY_FIELDS if document.get(field_)), None)
            raw_ticker = next((document.get(field_) for field_ in _TICKER_FIELDS if document.get(field_)), None)
            if not company or not raw_ticker:
                continue
            ticker = normalize_ticker(raw_ticker)
            if not ticker:
                continue
            reference.company_to_ticker[_normalize_company_name(company)] = ticker
            reference.ticker_to_company.setdefault(ticker, str(company).strip())
            reference.universe.add(ticker)
            raw_company_id = next(
                (document.get(field_) for field_ in _COMPANY_ID_FIELDS if document.get(field_) not in (None, "")), None
            )
            for company_id in _iter_company_ids(raw_company_id):
                reference.companyid_to_ticker[company_id] = ticker

        return reference
