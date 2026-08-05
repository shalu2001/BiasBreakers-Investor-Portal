"""Cluster-level narrative statistics and view construction (vendored)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.models import NarrativeView, TopicCluster
from narrative_engine.narrative.attention import compute_attention
from narrative_engine.narrative.expected_returns import compute_qi
from narrative_engine.narrative.persistence import compute_persistence, compute_window_days


@dataclass(frozen=True)
class NarrativeClusterStats:
    """Statistics summarizing one narrative cluster."""

    Si: float
    Si_normalized: float
    sentiment_std: float
    positive_ratio: float
    negative_ratio: float
    Pi: float
    Ai: int
    start_date: str
    end_date: str
    document_count: int


@dataclass(frozen=True)
class DiffusionFitResult:
    """Fitted logistic diffusion parameters and diagnostics."""

    k: float
    c: float
    fitted: bool
    fit_points: int
    status: str


def _logistic_curve(x: np.ndarray, k: float, c: float) -> np.ndarray:
    exponent = np.clip(-k * (x - c), -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(exponent))


def _normalized_cumulative_series(valid_dates: pd.Series, analysis_start: datetime, analysis_end: datetime) -> np.ndarray:
    days = pd.date_range(start=analysis_start.date(), end=analysis_end.date(), freq="D")
    if len(days) <= 0:
        return np.array([], dtype=float)

    daily = pd.Series(1.0, index=valid_dates.dt.normalize()).groupby(level=0).sum()
    reindexed = daily.reindex(days, fill_value=0.0)
    cumulative = reindexed.cumsum().to_numpy(dtype=float)
    max_value = float(cumulative.max()) if cumulative.size else 0.0
    if max_value <= 0.0:
        return np.array([], dtype=float)
    return cumulative / max_value


def fit_logistic_diffusion(
    valid_dates: pd.Series,
    analysis_start: datetime,
    analysis_end: datetime,
    settings: NarrativePipelineSettings,
) -> DiffusionFitResult:
    """Fit per-topic logistic diffusion parameters from cumulative daily counts."""

    normalized = _normalized_cumulative_series(valid_dates, analysis_start, analysis_end)
    if normalized.size < settings.macro_diffusion_min_points:
        return DiffusionFitResult(
            k=settings.macro_diffusion_default_k,
            c=settings.macro_diffusion_default_c,
            fitted=False,
            fit_points=int(normalized.size),
            status="fallback_insufficient_points",
        )

    if float(np.std(normalized)) < 1e-9:
        return DiffusionFitResult(
            k=settings.macro_diffusion_default_k,
            c=settings.macro_diffusion_default_c,
            fitted=False,
            fit_points=int(normalized.size),
            status="fallback_degenerate_series",
        )

    x = np.linspace(0.0, 1.0, num=normalized.size, dtype=float)
    try:
        params, _ = curve_fit(
            _logistic_curve,
            x,
            normalized,
            p0=(settings.macro_diffusion_default_k, settings.macro_diffusion_default_c),
            bounds=([0.1, 0.0], [50.0, 1.0]),
            maxfev=20000,
        )
        return DiffusionFitResult(
            k=float(params[0]),
            c=float(params[1]),
            fitted=True,
            fit_points=int(normalized.size),
            status="fitted",
        )
    except Exception:
        return DiffusionFitResult(
            k=settings.macro_diffusion_default_k,
            c=settings.macro_diffusion_default_c,
            fitted=False,
            fit_points=int(normalized.size),
            status="fallback_fit_error",
        )


def summarize_cluster(cluster_documents: pd.DataFrame, analysis_start: datetime, analysis_end: datetime) -> NarrativeClusterStats:
    """Summarize cluster sentiment, attention, and persistence."""

    scores = pd.to_numeric(cluster_documents["final_sentiment_score"], errors="coerce").dropna()
    sentiments = scores.to_numpy(dtype=float)
    sentiment_mean = float(np.mean(sentiments)) if sentiments.size else 0.0
    sentiment_std = float(np.std(sentiments, ddof=0)) if sentiments.size else 0.0
    positive_ratio = float((sentiments > 0).mean()) if sentiments.size else 0.0
    negative_ratio = float((sentiments < 0).mean()) if sentiments.size else 0.0
    normalized_sentiment = float(np.tanh(sentiment_mean))

    valid_dates = pd.to_datetime(cluster_documents["published_date"], errors="coerce").dropna()
    window_days = compute_window_days(analysis_start, analysis_end)
    persistence = compute_persistence(valid_dates.tolist(), window_days)

    start_date = valid_dates.min().date().isoformat() if not valid_dates.empty else analysis_start.date().isoformat()
    end_date = valid_dates.max().date().isoformat() if not valid_dates.empty else analysis_end.date().isoformat()

    return NarrativeClusterStats(
        Si=sentiment_mean,
        Si_normalized=normalized_sentiment,
        sentiment_std=sentiment_std,
        positive_ratio=positive_ratio,
        negative_ratio=negative_ratio,
        Pi=persistence,
        Ai=compute_attention(len(cluster_documents)),
        start_date=start_date,
        end_date=end_date,
        document_count=int(len(cluster_documents)),
    )


def build_narrative_view(
    cluster: TopicCluster,
    cluster_documents: pd.DataFrame,
    settings: NarrativePipelineSettings,
    view_index: int,
    analysis_start: datetime,
    analysis_end: datetime,
) -> NarrativeView:
    """Build a single final view row from a topic cluster."""

    stats = summarize_cluster(cluster_documents, analysis_start, analysis_end)
    valid_dates = pd.to_datetime(cluster_documents["published_date"], errors="coerce").dropna()

    diffusion_result = DiffusionFitResult(
        k=settings.macro_diffusion_default_k,
        c=settings.macro_diffusion_default_c,
        fitted=False,
        fit_points=0,
        status="not_applicable",
    )

    # Both micro and macro views shape persistence with the diffusion-fitted logistic
    # (k, c); when the fit is unavailable the result carries the settings defaults.
    fit_diffusion = bool(settings.macro_diffusion_enabled)
    if fit_diffusion:
        diffusion_result = fit_logistic_diffusion(valid_dates, analysis_start, analysis_end, settings)

    qi = compute_qi(
        settings.alpha,
        stats.Si_normalized,
        settings.lambda_,
        stats.Pi,
        stats.Ai,
        k=diffusion_result.k,
        c=diffusion_result.c,
    )
    view_id = f"{cluster.view_type}-{cluster.company or 'macro'}-{cluster.topic_id}-{view_index}"

    return NarrativeView(
        view_id=view_id,
        view_type=cluster.view_type,
        company=cluster.company,
        topic_id=cluster.topic_id,
        topic_name=cluster.topic_name,
        Qi=qi,
        Si=stats.Si,
        Pi=stats.Pi,
        Ai=stats.Ai,
        cluster_size=cluster.cluster_size,
        sentiment_std=stats.sentiment_std,
        start_date=stats.start_date,
        end_date=stats.end_date,
        document_count=stats.document_count,
        diffusion_k=diffusion_result.k if fit_diffusion else None,
        diffusion_c=diffusion_result.c if fit_diffusion else None,
        diffusion_fitted=diffusion_result.fitted if fit_diffusion else None,
        diffusion_fit_points=diffusion_result.fit_points if fit_diffusion else None,
        diffusion_fit_status=diffusion_result.status if fit_diffusion else None,
    )
