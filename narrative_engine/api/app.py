"""FastAPI application exposing the narrative prediction engine.

Run with::

    uvicorn narrative_engine.api.app:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /health   -> liveness + Cosmos ping
    POST /predict  -> run the full narrative → Black-Litterman prediction for an as_of date
    GET  /news     -> windowed news feed for the frontend (filtered client-side)
    GET  /tickers  -> SL20 ticker → company options for the news filter dropdown

A full run performs BERTopic clustering plus OpenAI calls and is therefore multi-second;
requests are handled synchronously with a small in-memory LRU cache keyed by the request
parameters. For high-throughput use, front this with an async job queue.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool

from narrative_engine.api.schemas import (
    HealthResponse,
    NarrativeItem,
    NarrativesResponse,
    NarrativeStock,
    NewsItemOut,
    PredictRequest,
    PredictResponse,
    TickerOption,
)
from narrative_engine.config import get_settings
from narrative_engine.data.mongo import MongoConnection
from narrative_engine.data.news_repository import NewsRepository
from narrative_engine.data.ticker_info_repository import TickerInfoRepository
from narrative_engine.engine import NarrativePredictionEngine, PredictionResult

logger = logging.getLogger(__name__)

_CACHE_MAX_SIZE = 64

# Time-to-live (seconds) for the cached /news and /tickers responses.
_FEED_CACHE_TTL_SECONDS = 300

# On-disk cache for prediction responses (narrative_engine/cache).
_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


class _TTLCache:
    """Thread-safe single-value cache with stale-while-revalidate semantics.

    Once warmed, ``get`` never blocks on a reload: a fresh value is returned
    immediately, and a stale one is returned while a single background thread
    refreshes it. Only the very first (cold) load, before any value exists,
    blocks the caller -- and ``warm`` runs that at startup so requests don't.
    """

    def __init__(self, ttl_seconds: float, loader):
        self._ttl = ttl_seconds
        self._loader = loader
        self._value: Any = None
        self._expires_at = 0.0
        self._refreshing = False
        self._lock = Lock()

    def _reload(self) -> Any:
        value = self._loader()
        with self._lock:
            self._value = value
            self._expires_at = time.monotonic() + self._ttl
            self._refreshing = False
        return value

    def get(self) -> Any:
        with self._lock:
            value = self._value
            fresh = value is not None and time.monotonic() < self._expires_at
            if fresh:
                return value
            if value is not None:
                # Stale: serve it now, refresh in the background (once).
                if not self._refreshing:
                    self._refreshing = True
                    Thread(target=self._safe_reload, daemon=True).start()
                return value
        # Cold: no value yet -- block this caller to populate it.
        return self._reload()

    def _safe_reload(self) -> None:
        try:
            self._reload()
        except Exception:  # pragma: no cover - background refresh guard
            logger.exception("Background cache refresh failed; keeping stale value")
            with self._lock:
                self._refreshing = False

    def warm(self) -> None:
        """Populate the cache eagerly (e.g. at startup) so the first request is fast."""
        try:
            self._reload()
        except Exception:  # pragma: no cover - startup guard
            logger.exception("Cache warm failed; will load lazily on first request")


def _write_response_cache(request: PredictRequest, response: PredictResponse) -> None:
    """Persist a prediction response to narrative_engine/cache as JSON."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        macro = "macro" if request.use_macro_overrides else "nomacro"
        filename = f"prediction_{response.as_of}_{response.lookback_days}d_{macro}.json"
        path = _CACHE_DIR / filename
        path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Wrote prediction response cache to %s", path)
    except Exception as exc:  # pragma: no cover - best-effort side write
        logger.warning("Failed to write prediction response cache: %s", exc)


class _ResultCache:
    """Tiny thread-safe LRU cache for prediction results."""

    def __init__(self, max_size: int = _CACHE_MAX_SIZE):
        self._store: "OrderedDict[Tuple, PredictionResult]" = OrderedDict()
        self._max_size = max_size
        self._lock = Lock()

    def get(self, key: Tuple) -> Optional[PredictionResult]:
        with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    def put(self, key: Tuple, value: PredictionResult) -> None:
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    app.state.settings = get_settings()
    app.state.engine = NarrativePredictionEngine(app.state.settings)
    app.state.cache = _ResultCache()
    app.state.news_cache = _TTLCache(_FEED_CACHE_TTL_SECONDS, _load_news_feed)
    app.state.ticker_cache = _TTLCache(_FEED_CACHE_TTL_SECONDS, _load_ticker_options)
    app.state.narrative_cache = _TTLCache(_FEED_CACHE_TTL_SECONDS, _load_narratives)
    logger.info("Narrative prediction engine ready.")
    # Warm the feed caches off the event loop so the first request is fast.
    # Ticker cache first: narratives resolves tickers -> company names through it.
    await run_in_threadpool(app.state.ticker_cache.warm)
    await run_in_threadpool(app.state.news_cache.warm)
    await run_in_threadpool(app.state.narrative_cache.warm)
    logger.info("News, ticker, and narrative caches warmed.")
    yield


app = FastAPI(
    title="Narrative Intelligence Prediction API",
    version="0.1.0",
    description="Narrative Black-Litterman posterior returns from a 30-day news lookback.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = app.state.settings
    mongo_status = "ok"
    connection = MongoConnection(settings)
    try:
        connection.client.admin.command("ping")
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Mongo health ping failed: %s", exc)
        mongo_status = f"error: {exc}"
    finally:
        connection.close()
    return HealthResponse(status="ok", mongo=mongo_status)


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest) -> PredictResponse:
    engine: NarrativePredictionEngine = app.state.engine
    cache: _ResultCache = app.state.cache

    key = (request.as_of_date.isoformat(), request.lookback_days, request.use_macro_overrides)
    result = cache.get(key)
    if result is None:
        try:
            result = await run_in_threadpool(
                engine.predict,
                request.as_of_date,
                lookback_days=request.lookback_days,
                use_macro_overrides=request.use_macro_overrides,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.exception("Prediction failed")
            raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}") from exc
        cache.put(key, result)

    response = PredictResponse(
        as_of=result.as_of,
        lookback_days=result.lookback_days,
        universe=result.universe,
        predictions=result.predictions,
        views=result.views,
        meta=result.meta,
    )
    _write_response_cache(request, response)
    return response


def _load_news_feed() -> list[NewsItemOut]:
    """Load the full news window and shape it for the frontend feed."""
    settings = app.state.settings
    connection = MongoConnection(settings)
    try:
        ticker_reference = TickerInfoRepository(connection, settings).load()
        news_df = NewsRepository(connection, settings).load(
            datetime.now(), settings.lookback_days, ticker_reference
        )
    finally:
        connection.close()

    if news_df.empty:
        return []

    # Newest first. The repository returns rows grouped by source collection,
    # so without this the latest stories are scattered through the list rather
    # than at the top.
    if "published_date" in news_df.columns:
        news_df = news_df.sort_values("published_date", ascending=False, na_position="last")

    items: list[NewsItemOut] = []
    for row in news_df.to_dict("records"):
        published = row.get("published_date")
        published_iso = None if published is None or pd.isna(published) else pd.Timestamp(published).isoformat()
        ticker = (row.get("matched_symbol") or "").strip() or None
        items.append(
            NewsItemOut(
                ticker=ticker,
                category=(row.get("market_classification") or "").strip(),
                headline=(row.get("headline") or "").strip(),
                content=(row.get("content") or "").strip(),
                source=(row.get("source") or "").strip(),
                published_date=published_iso,
            )
        )
    return items


def _load_ticker_options() -> list[TickerOption]:
    """Load the SL20 ticker → company mapping for the news filter dropdown."""
    settings = app.state.settings
    connection = MongoConnection(settings)
    try:
        reference = TickerInfoRepository(connection, settings).load()
    finally:
        connection.close()

    options = [
        TickerOption(ticker=ticker, name=reference.ticker_to_company.get(ticker, ticker))
        for ticker in sorted(reference.universe)
    ]
    return options


_CACHE_FILE_RE = re.compile(r"^prediction_(\d{4}-\d{2}-\d{2})_.*\.json$")

# Two narratives whose normalized topic text is at least this similar are treated
# as the same story. The engine can emit several near-identical topic clusters
# (e.g. multiple "rupee stable vs USD, bond yields steady" views); we keep only
# the highest-confidence one so the feed doesn't read as duplicates.
_NARRATIVE_DEDUP_THRESHOLD = 0.6


def _normalize_topic(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", str(text).lower()).split())


def _is_duplicate_topic(candidate: str, representatives: list[str]) -> bool:
    from difflib import SequenceMatcher

    return any(
        SequenceMatcher(None, candidate, rep).ratio() >= _NARRATIVE_DEDUP_THRESHOLD
        for rep in representatives
    )


def _latest_prediction_file() -> Optional[Path]:
    """Return the newest prediction cache file, chosen by the date in its name.

    Ties (same date, e.g. _macro vs _nomacro) break on most-recently-written.
    """
    candidates = []
    for path in _CACHE_DIR.glob("prediction_*.json"):
        match = _CACHE_FILE_RE.match(path.name)
        if match:
            candidates.append((match.group(1), path.stat().st_mtime, path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _load_narratives() -> NarrativesResponse:
    """Read the latest prediction cache file and shape its narratives + affected stocks.

    Ranked by the view's confidence (descending); confidence itself is not exposed.
    """
    path = _latest_prediction_file()
    if path is None:
        return NarrativesResponse(as_of="", narratives=[])

    data = json.loads(path.read_text(encoding="utf-8"))
    ticker_options = app.state.ticker_cache.get()
    ticker_names = {opt.ticker: opt.name for opt in ticker_options}
    # For micro views whose "company" is a name, not a ticker.
    name_to_ticker = {" ".join(opt.name.lower().split()): opt.ticker for opt in ticker_options}

    def stock(ticker: str) -> NarrativeStock:
        ticker = str(ticker).strip()
        return NarrativeStock(ticker=ticker, name=ticker_names.get(ticker, ticker))

    def stock_from_company(company: str) -> NarrativeStock:
        key = " ".join(str(company).lower().split())
        ticker = name_to_ticker.get(key)
        if ticker:
            return NarrativeStock(ticker=ticker, name=ticker_names.get(ticker, ticker))
        return NarrativeStock(ticker="", name=str(company).strip())

    views = data.get("views", [])
    # Rank by confidence desc; missing confidence sorts last.
    views_sorted = sorted(views, key=lambda v: (v.get("confidence") is None, -(v.get("confidence") or 0.0)))

    narratives: list[NarrativeItem] = []
    for view in views_sorted:
        mapped = view.get("mapped_tickers")
        if mapped:
            # [[ticker, weight], ...] -- keep all, ordered by influence weight.
            ranked = sorted(mapped, key=lambda pair: -(pair[1] or 0.0))
            stocks = [stock(pair[0]) for pair in ranked]
        elif view.get("company"):
            # Micro view: the affected stock is the company itself.
            stocks = [stock_from_company(view["company"])]
        else:
            stocks = []
        narratives.append(
            NarrativeItem(
                id=str(view.get("view_id", "")),
                type=str(view.get("view_type", "")),
                title=str(view.get("topic_name", "")).strip(),
                stocks=stocks,
            )
        )

    as_of = str(data.get("as_of") or (_CACHE_FILE_RE.match(path.name) or [None, ""])[1] or "")
    return NarrativesResponse(as_of=as_of, narratives=narratives)


@app.get("/news", response_model=list[NewsItemOut])
async def news() -> list[NewsItemOut]:
    cache: _TTLCache = app.state.news_cache
    try:
        return await run_in_threadpool(cache.get)
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("News load failed")
        raise HTTPException(status_code=500, detail=f"News load failed: {exc}") from exc


@app.get("/tickers", response_model=list[TickerOption])
async def tickers() -> list[TickerOption]:
    cache: _TTLCache = app.state.ticker_cache
    try:
        return await run_in_threadpool(cache.get)
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("Ticker load failed")
        raise HTTPException(status_code=500, detail=f"Ticker load failed: {exc}") from exc


@app.get("/narratives", response_model=NarrativesResponse)
async def narratives() -> NarrativesResponse:
    cache: _TTLCache = app.state.narrative_cache
    try:
        return await run_in_threadpool(cache.get)
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("Narratives load failed")
        raise HTTPException(status_code=500, detail=f"Narratives load failed: {exc}") from exc
