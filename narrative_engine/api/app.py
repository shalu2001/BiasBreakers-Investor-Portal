"""FastAPI application exposing the narrative prediction engine.

Run with::

    uvicorn narrative_engine.api.app:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /health   -> liveness + Cosmos ping
    POST /predict  -> run the full narrative → Black-Litterman prediction for an as_of date

A full run performs BERTopic clustering plus OpenAI calls and is therefore multi-second;
requests are handled synchronously with a small in-memory LRU cache keyed by the request
parameters. For high-throughput use, front this with an async job queue.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from threading import Lock
from typing import Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool

from narrative_engine.api.schemas import HealthResponse, PredictRequest, PredictResponse
from narrative_engine.config import get_settings
from narrative_engine.data.mongo import MongoConnection
from narrative_engine.engine import NarrativePredictionEngine, PredictionResult

logger = logging.getLogger(__name__)

_CACHE_MAX_SIZE = 64


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

    return PredictResponse(
        as_of=result.as_of,
        lookback_days=result.lookback_days,
        universe=result.universe,
        predictions=result.predictions,
        views=result.views,
        meta=result.meta,
    )
