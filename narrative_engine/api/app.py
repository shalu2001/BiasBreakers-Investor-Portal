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

import logging
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool

from narrative_engine.api.schemas import (
    HealthResponse,
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
    """Single-value, thread-safe cache that recomputes after ``ttl`` seconds."""

    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._value: Any = None
        self._expires_at = 0.0
        self._lock = Lock()

    def get_or_load(self, loader):
        with self._lock:
            now = time.monotonic()
            if self._value is not None and now < self._expires_at:
                return self._value
            value = loader()
            self._value = value
            self._expires_at = now + self._ttl
            return value


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
    app.state.news_cache = _TTLCache(_FEED_CACHE_TTL_SECONDS)
    app.state.ticker_cache = _TTLCache(_FEED_CACHE_TTL_SECONDS)
    logger.info("Narrative prediction engine ready.")
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


@app.get("/news", response_model=list[NewsItemOut])
async def news() -> list[NewsItemOut]:
    cache: _TTLCache = app.state.news_cache
    try:
        return await run_in_threadpool(cache.get_or_load, _load_news_feed)
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("News load failed")
        raise HTTPException(status_code=500, detail=f"News load failed: {exc}") from exc


@app.get("/tickers", response_model=list[TickerOption])
async def tickers() -> list[TickerOption]:
    cache: _TTLCache = app.state.ticker_cache
    try:
        return await run_in_threadpool(cache.get_or_load, _load_ticker_options)
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("Ticker load failed")
        raise HTTPException(status_code=500, detail=f"Ticker load failed: {exc}") from exc
