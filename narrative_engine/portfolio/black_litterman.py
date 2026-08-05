"""Black-Litterman posterior returns (vendored math; file IO removed).

The research module read prices/market-caps/mapping/index from CSVs and persisted a CSV.
Here the same computation is exposed as a pure function, ``compute_posteriors``, that takes
in-memory inputs sourced from Cosmos and returns a DataFrame. The view-spec construction,
universe selection, Idzorek confidence omega, and posterior math are unchanged.
"""

from __future__ import annotations

import logging
from typing import Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.narrative.confidence import compute_view_confidence


logger = logging.getLogger(__name__)


class BLViewSpec:
    """A single Black-Litterman view row."""

    def __init__(
        self,
        view_id: str,
        q_value: float,
        tickers: Sequence[str],
        weights: Sequence[float],
        confidence: float = 0.5,
    ):
        self.view_id = view_id
        self.q_value = q_value
        self.tickers = tuple(tickers)
        self.weights = tuple(weights)
        self.confidence = confidence


def _normalize_company_name(value: object) -> str:
    text = " ".join(str(value or "").strip().split())
    return text.lower()


def _normalize_ticker(value: object) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _lookup_ticker(company: str, company_to_ticker: Mapping[str, str]) -> str:
    normalized_company = _normalize_company_name(company)
    if not normalized_company:
        return ""

    direct = company_to_ticker.get(normalized_company)
    if direct:
        return direct

    matches = [
        ticker
        for key, ticker in company_to_ticker.items()
        if key and (normalized_company in key or key in normalized_company)
    ]
    if len(matches) == 1:
        return matches[0]
    return ""


def _build_macro_view_spec(
    view_id: str, q_value: float, universe: Sequence[str], confidence: float = 0.5
) -> BLViewSpec:
    if not universe:
        raise ValueError("Cannot build a macro view without a covariance universe.")
    weight = 1.0 / len(universe)
    return BLViewSpec(
        view_id=view_id,
        q_value=q_value,
        tickers=universe,
        weights=[weight] * len(universe),
        confidence=confidence,
    )


def _build_p_row(spec: BLViewSpec, universe: Sequence[str]) -> np.ndarray:
    ticker_to_index = {ticker: index for index, ticker in enumerate(universe)}
    row = np.zeros(len(universe), dtype=float)
    for ticker, weight in zip(spec.tickers, spec.weights):
        index = ticker_to_index.get(ticker)
        if index is not None:
            row[index] = float(weight)
    if not np.any(row):
        raise ValueError(f"View '{spec.view_id}' does not overlap with the selected universe.")
    return row


def build_view_specs_from_narratives(
    narrative_views: pd.DataFrame,
    company_to_ticker: Mapping[str, str],
    universe: Sequence[str],
    llm_mapping_overrides: Optional[Mapping[str, Sequence[Tuple[str, float]]]] = None,
    settings: Optional[NarrativePipelineSettings] = None,
) -> list[BLViewSpec]:
    """Convert every narrative row into a BL view specification.

    Micro/company-linked rows become single-ticker views. Macro rows become equal-weight
    market-basket views across the selected universe (or the LLM override basket for that
    view_id). Every spec carries a confidence in [0, 1] used for Idzorek omega weighting.
    """

    if narrative_views.empty:
        return []

    if "Qi" not in narrative_views.columns:
        raise ValueError("Narrative views must include 'Qi' column.")

    confidence_kwargs: Dict[str, float] = {}
    if settings is not None:
        confidence_kwargs = dict(
            macro_size_reference=settings.bl_confidence_macro_size_reference,
            micro_size_reference=settings.bl_confidence_micro_size_reference,
            macro_min_confidence=settings.bl_confidence_macro_min,
            micro_min_confidence=settings.bl_confidence_micro_min,
            max_confidence=settings.bl_confidence_max,
            fallback_fit_penalty=settings.bl_confidence_fallback_fit_penalty,
        )

    frame = narrative_views.copy()
    frame["Qi"] = pd.to_numeric(frame["Qi"], errors="coerce")
    frame = frame.dropna(subset=["Qi"])

    specs: list[BLViewSpec] = []
    for _, row in frame.iterrows():
        view_id = str(row.get("view_id", "")).strip()
        view_type = str(row.get("view_type", "")).strip().lower()
        company = str(row.get("company") or row.get("matched_company_name") or "").strip()
        ticker_hint = _normalize_ticker(row.get("matched_symbol") or row.get("ticker") or "")
        q_value = float(row["Qi"])
        diffusion_fitted = row.get("diffusion_fitted")
        confidence = compute_view_confidence(
            view_type,
            row.get("cluster_size"),
            row.get("sentiment_std"),
            diffusion_fitted if pd.notna(diffusion_fitted) else None,
            **confidence_kwargs,
        )

        if llm_mapping_overrides and view_id in llm_mapping_overrides:
            mapped_tickers: list[str] = []
            mapped_weights: list[float] = []
            for ticker, weight in llm_mapping_overrides[view_id]:
                normalized_ticker = _normalize_ticker(ticker)
                if normalized_ticker in universe:
                    mapped_tickers.append(normalized_ticker)
                    mapped_weights.append(float(weight))
            if mapped_tickers:
                specs.append(
                    BLViewSpec(
                        view_id=view_id,
                        q_value=q_value,
                        tickers=mapped_tickers,
                        weights=mapped_weights,
                        confidence=confidence,
                    )
                )
                continue

        if view_type == "macro" or not company:
            specs.append(_build_macro_view_spec(view_id, q_value, universe, confidence=confidence))
            continue

        ticker = _lookup_ticker(company, company_to_ticker) if company else ""
        if not ticker and ticker_hint:
            ticker = ticker_hint
        if ticker and ticker in universe:
            specs.append(
                BLViewSpec(view_id=view_id, q_value=q_value, tickers=[ticker], weights=[1.0], confidence=confidence)
            )
        else:
            specs.append(_build_macro_view_spec(view_id, q_value, universe, confidence=confidence))

    return specs


def _select_covariance_universe(
    prices: pd.DataFrame,
    market_caps: Mapping[str, float],
    mapping_universe: Optional[Sequence[str]] = None,
    size: int = 20,
) -> list[str]:
    """Select the covariance universe used by BL.

    Preference order:
    1. Tickers from the mapping (the SL20 constituent set) present in prices and caps.
    2. Top market-cap names available in the price series, as a fallback proxy.
    """

    if mapping_universe:
        selected = [ticker for ticker in mapping_universe if ticker in prices.columns and ticker in market_caps]
        if selected:
            return selected[:size]

    ranked = sorted(market_caps.items(), key=lambda item: item[1], reverse=True)
    selected = [ticker for ticker, _ in ranked if ticker in prices.columns]
    return selected[:size]


def _resolve_risk_aversion(index_series: Optional[pd.Series], settings: NarrativePipelineSettings) -> float:
    """Return market-implied risk aversion from the index series, or the fallback."""

    from pypfopt import black_litterman

    if index_series is None or len(index_series) < 3:
        return settings.bl_risk_aversion_fallback
    prices = pd.to_numeric(pd.Series(index_series), errors="coerce").dropna()
    if prices.empty or len(prices) < 3:
        return settings.bl_risk_aversion_fallback
    try:
        delta = float(black_litterman.market_implied_risk_aversion(prices, risk_free_rate=settings.bl_risk_free_rate))
    except Exception:
        return settings.bl_risk_aversion_fallback
    if not np.isfinite(delta) or delta <= 0.0:
        logger.warning("Market-implied risk aversion was non-positive/degenerate (%s); using fallback.", delta)
        return settings.bl_risk_aversion_fallback
    return delta


def compute_posteriors(
    views_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    market_caps: Mapping[str, float],
    company_to_ticker: Mapping[str, str],
    settings: NarrativePipelineSettings,
    *,
    index_series: Optional[pd.Series] = None,
    llm_mapping_overrides: Optional[Mapping[str, Sequence[Tuple[str, float]]]] = None,
) -> pd.DataFrame:
    """Compute Black-Litterman posterior returns from in-memory inputs.

    Returns a DataFrame with columns ``ticker``, ``posterior_expected_return``, and
    ``prior_return`` (both annualized). The narrative *tilt* is ``posterior - prior``.
    """

    if prices_df is None or prices_df.empty:
        raise ValueError("No price data provided to the Black-Litterman stage.")
    if not market_caps:
        raise ValueError("No market caps provided to the Black-Litterman stage.")

    mapping_universe = list(dict.fromkeys(company_to_ticker.values()))
    universe = _select_covariance_universe(
        prices_df,
        market_caps,
        mapping_universe=mapping_universe,
        size=settings.bl_covariance_universe_size,
    )
    if not universe:
        raise ValueError("Could not select a covariance universe from prices and market caps.")

    view_specs = build_view_specs_from_narratives(
        views_df, company_to_ticker, universe, llm_mapping_overrides, settings=settings
    )
    if not view_specs:
        raise ValueError("No valid BL views were constructed from narrative outputs.")

    prices = prices_df[universe]
    market_caps = {ticker: market_caps[ticker] for ticker in universe}

    from pypfopt import black_litterman, risk_models

    covariance = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    delta = _resolve_risk_aversion(index_series, settings)
    priors = black_litterman.market_implied_prior_returns(market_caps, delta, covariance)

    q_vector = np.asarray([spec.q_value for spec in view_specs], dtype=float)
    p_matrix = np.vstack([_build_p_row(spec, universe) for spec in view_specs])
    model_kwargs = {
        "cov_matrix": covariance,
        "pi": priors,
        "P": p_matrix,
        "Q": q_vector,
    }
    if settings.bl_use_view_confidence:
        model_kwargs["omega"] = "idzorek"
        model_kwargs["view_confidences"] = np.asarray([spec.confidence for spec in view_specs], dtype=float)
    if settings.bl_tau is not None:
        model_kwargs["tau"] = settings.bl_tau

    model = black_litterman.BlackLittermanModel(**model_kwargs)
    posterior = model.bl_returns().sort_index()

    prior_aligned = pd.Series(priors).reindex(posterior.index)
    return pd.DataFrame(
        {
            "ticker": posterior.index,
            "posterior_expected_return": posterior.values,
            "prior_return": prior_aligned.values,
        }
    ).reset_index(drop=True)
