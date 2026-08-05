"""End-to-end narrative prediction orchestrator.

Given an ``as_of`` date, the engine:
  1. loads pre-enriched news over the trailing ``lookback_days`` window,
  2. splits macro/micro and clusters each into narrative views (LLM topic labels),
  3. calibrates the views,
  4. loads prices / market caps / index / ticker reference from Cosmos,
  5. (optionally) maps macro views to market-cap-weighted ticker baskets via an LLM,
  6. runs Black-Litterman to get per-ticker posterior/prior/tilt,
  7. returns the predictions plus the underlying narrative views and run metadata.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from narrative_engine.config import NarrativePipelineSettings, get_settings
from narrative_engine.data.index_repository import IndexRepository
from narrative_engine.data.marketcap_repository import MarketCapRepository
from narrative_engine.data.mongo import MongoConnection
from narrative_engine.data.news_repository import NewsRepository
from narrative_engine.data.price_repository import PriceRepository
from narrative_engine.data.ticker_info_repository import TickerInfoRepository
from narrative_engine.narrative.calibration import apply_view_calibration
from narrative_engine.narrative.confidence import compute_view_confidence
from narrative_engine.pipeline.filters import split_macro_micro
from narrative_engine.pipeline.macro_pipeline import run_macro_pipeline
from narrative_engine.pipeline.micro_pipeline import run_micro_pipeline
from narrative_engine.portfolio.black_litterman import compute_posteriors
from narrative_engine.portfolio.macro_overrides import generate_macro_overrides

logger = logging.getLogger(__name__)

DateLike = Union[str, date, datetime]


@dataclass
class PredictionResult:
    """Structured prediction output for the API layer."""

    as_of: str
    lookback_days: int
    universe: List[str]
    predictions: List[Dict[str, Any]]
    views: List[Dict[str, Any]]
    meta: Dict[str, Any] = field(default_factory=dict)


def _coerce_datetime(value: DateLike) -> datetime:
    if isinstance(value, datetime):
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    parsed = pd.to_datetime(str(value), errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid as_of date: {value!r}")
    return parsed.to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)


def _clean_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


class NarrativePredictionEngine:
    """Reusable engine that runs the full narrative → Black-Litterman prediction."""

    def __init__(self, settings: Optional[NarrativePipelineSettings] = None):
        self.settings = settings or get_settings()

    def predict(
        self,
        as_of: DateLike,
        *,
        lookback_days: Optional[int] = None,
        use_macro_overrides: Optional[bool] = None,
    ) -> PredictionResult:
        as_of_dt = _coerce_datetime(as_of)
        lookback = int(lookback_days if lookback_days is not None else self.settings.lookback_days)
        macro_overrides_enabled = (
            self.settings.use_macro_overrides if use_macro_overrides is None else bool(use_macro_overrides)
        )

        connection = MongoConnection(self.settings)
        try:
            return self._run(connection, as_of_dt, lookback, macro_overrides_enabled)
        finally:
            connection.close()

    def _run(
        self,
        connection: MongoConnection,
        as_of_dt: datetime,
        lookback: int,
        macro_overrides_enabled: bool,
    ) -> PredictionResult:
        as_of_str = as_of_dt.strftime("%Y-%m-%d")
        window_start = as_of_dt - timedelta(days=lookback)

        # Ticker reference is loaded first so the CSE-announcement adapter can map
        # companyId/symbol/company → ticker while loading news.
        ticker_reference = TickerInfoRepository(connection, self.settings).load()
        company_to_ticker = ticker_reference.company_to_ticker
        ticker_info_records = ticker_reference.records

        # 1. News window (CSE announcements mapped to micro views via ticker_reference)
        news_df = NewsRepository(connection, self.settings).load(as_of_dt, lookback, ticker_reference)
        if news_df.empty:
            return self._empty_result(as_of_str, lookback, window_start, "No enriched news found in the lookback window.")

        # 2/3. Narrative views
        macro_frame, micro_frame = split_macro_micro(news_df)
        analysis_start, analysis_end = self.settings.analysis_window(window_start, as_of_dt)
        macro_settings = self.settings.macro_variant()
        micro_settings = self.settings.micro_variant()

        macro_views = run_macro_pipeline(macro_frame, macro_settings, analysis_start, analysis_end)
        micro_views = run_micro_pipeline(micro_frame, micro_settings, analysis_start, analysis_end)
        all_views = apply_view_calibration([*macro_views, *micro_views], self.settings)
        if not all_views:
            return self._empty_result(
                as_of_str, lookback, window_start, "No narrative views could be constructed from the news window."
            )

        views_df = pd.DataFrame([view.to_dict() for view in all_views])

        # 4. Market data
        prices_df = PriceRepository(connection, self.settings).load_matrix(as_of_dt)
        market_caps = MarketCapRepository(connection, self.settings).load(as_of_dt)
        index_series = IndexRepository(connection, self.settings).load_series(as_of_dt)

        # 5. Optional LLM macro overrides
        overrides: Dict[str, Any] = {}
        macro_audit: Dict[str, Any] = {}
        if macro_overrides_enabled:
            overrides, macro_audit = generate_macro_overrides(
                views_df, ticker_info_records, market_caps, self.settings
            )

        # 6. Black-Litterman posteriors
        posteriors_df = compute_posteriors(
            views_df,
            prices_df,
            market_caps,
            company_to_ticker,
            self.settings,
            index_series=index_series,
            llm_mapping_overrides=overrides or None,
        )

        # 7. Assemble output
        predictions = self._build_predictions(posteriors_df)
        universe = [row["ticker"] for row in predictions]
        views_out = self._build_views(all_views, overrides)

        meta = {
            "window_start": window_start.strftime("%Y-%m-%d"),
            "window_end": as_of_str,
            "news_article_count": int(len(news_df)),
            "macro_view_count": int(len(macro_views)),
            "micro_view_count": int(len(micro_views)),
            "total_view_count": int(len(all_views)),
            "universe_size": len(universe),
            "macro_overrides_enabled": macro_overrides_enabled,
            "macro_overrides_applied": sorted(overrides.keys()) if overrides else [],
            "macro_override_audit": macro_audit,
            "covariance_window_trading_days": self.settings.covariance_window_trading_days,
            "price_trading_days_loaded": int(prices_df.shape[0]),
            "bl_use_view_confidence": self.settings.bl_use_view_confidence,
            "alpha": self.settings.alpha,
            "lambda": self.settings.lambda_,
        }

        return PredictionResult(
            as_of=as_of_str,
            lookback_days=lookback,
            universe=universe,
            predictions=predictions,
            views=views_out,
            meta=meta,
        )

    def _build_predictions(self, posteriors_df: pd.DataFrame) -> List[Dict[str, Any]]:
        predictions: List[Dict[str, Any]] = []
        for _, row in posteriors_df.iterrows():
            posterior = _clean_float(row.get("posterior_expected_return"))
            prior = _clean_float(row.get("prior_return"))
            tilt = None
            if posterior is not None and prior is not None:
                tilt = posterior - prior
            predictions.append(
                {
                    "ticker": str(row.get("ticker")),
                    "posterior": posterior,
                    "prior": prior,
                    "tilt": tilt,
                }
            )
        predictions.sort(key=lambda item: (item["tilt"] is None, -(item["tilt"] or 0.0)))
        return predictions

    def _build_views(self, all_views, overrides: Dict[str, Any]) -> List[Dict[str, Any]]:
        views_out: List[Dict[str, Any]] = []
        for view in all_views:
            confidence = compute_view_confidence(
                view.view_type,
                view.cluster_size,
                view.sentiment_std,
                view.diffusion_fitted,
                macro_size_reference=self.settings.bl_confidence_macro_size_reference,
                micro_size_reference=self.settings.bl_confidence_micro_size_reference,
                macro_min_confidence=self.settings.bl_confidence_macro_min,
                micro_min_confidence=self.settings.bl_confidence_micro_min,
                max_confidence=self.settings.bl_confidence_max,
                fallback_fit_penalty=self.settings.bl_confidence_fallback_fit_penalty,
            )
            mapped = overrides.get(view.view_id) if overrides else None
            views_out.append(
                {
                    "view_id": view.view_id,
                    "view_type": view.view_type,
                    "company": view.company,
                    "topic_name": view.topic_name,
                    "Qi": _clean_float(view.Qi),
                    "Si": _clean_float(view.Si),
                    "Si_normalized": _clean_float(math.tanh(view.Si)) if view.Si is not None else None,
                    "persistence": _clean_float(view.Pi),
                    "attention": view.Ai,
                    "cluster_size": view.cluster_size,
                    "sentiment_std": _clean_float(view.sentiment_std),
                    "diffusion_k": _clean_float(view.diffusion_k),
                    "diffusion_c": _clean_float(view.diffusion_c),
                    "diffusion_fitted": view.diffusion_fitted,
                    "confidence": confidence,
                    "mapped_tickers": [[t, w] for t, w in mapped] if mapped else None,
                }
            )
        return views_out

    @staticmethod
    def _empty_result(as_of_str: str, lookback: int, window_start, message: str) -> PredictionResult:
        return PredictionResult(
            as_of=as_of_str,
            lookback_days=lookback,
            universe=[],
            predictions=[],
            views=[],
            meta={
                "window_start": window_start.strftime("%Y-%m-%d"),
                "window_end": as_of_str,
                "message": message,
            },
        )
