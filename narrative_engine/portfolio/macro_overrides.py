"""LLM macro-view → ticker-basket override generation (in-memory).

Lifts the macro-mapping loop from the research ``scripts/run_bl_month.py`` into a reusable
function that returns the overrides ``{view_id: [(ticker, weight), ...]}`` directly (no JSON
file round-trip) plus an audit dict. Overrides feed
``black_litterman.build_view_specs_from_narratives`` to replace a macro view's default
equal-weight basket with a targeted, market-cap-weighted one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.portfolio.macro_mapping import (
    TickerInfoRecord,
    build_macro_mapping_prompt,
    filter_valid_allocations,
    infer_macro_view_kind,
    normalize_macro_allocations,
    parse_macro_mapping_response,
    select_candidate_records,
)

try:  # pragma: no cover - optional runtime dependency
    import openai
except ImportError:  # pragma: no cover
    openai = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _call_llm(model: str, api_key: str, system_prompt: str, user_prompt: str, seed: int) -> Tuple[str, Any]:
    if openai is None:
        raise RuntimeError("openai package is not available.")
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        seed=seed,
    )
    content = response.choices[0].message.content or ""
    return content, getattr(response, "system_fingerprint", None)


def generate_macro_overrides(
    views_df: pd.DataFrame,
    ticker_info_records: Sequence[TickerInfoRecord],
    market_caps: Mapping[str, float],
    settings: NarrativePipelineSettings,
) -> Tuple[Dict[str, List[Tuple[str, float]]], Dict[str, Any]]:
    """Generate market-cap-weighted ticker baskets for macro views via an LLM.

    Returns ``(overrides, audit)`` where overrides maps ``view_id -> [(ticker, weight)]``.
    Views that cannot be mapped (LLM error, empty result) are simply omitted, in which
    case the BL stage falls back to the default equal-weight macro basket for them.
    """

    overrides: Dict[str, List[Tuple[str, float]]] = {}
    audit: Dict[str, Any] = {}

    if views_df is None or views_df.empty or not ticker_info_records:
        return overrides, audit

    api_key = settings.macro_llm_api_key
    if not api_key:
        logger.warning("Macro overrides requested but no OpenAI API key is configured; skipping.")
        return overrides, audit
    if openai is None:
        logger.warning("openai package unavailable; skipping macro overrides.")
        return overrides, audit

    macro_views = views_df[views_df["view_type"].astype(str).str.lower().eq("macro")].copy()
    if macro_views.empty:
        return overrides, audit

    all_tickers = [record.ticker for record in ticker_info_records]

    for _, row in macro_views.iterrows():
        view = row.to_dict()
        view_id = str(view.get("view_id", "")).strip()
        if not view_id:
            continue

        candidate_records = select_candidate_records(
            f"{view.get('topic_name', '')} {view.get('Qi', '')} {view.get('Si', '')}",
            ticker_info_records,
            limit=settings.macro_candidate_limit,
        )
        system_prompt, user_prompt = build_macro_mapping_prompt(
            view, candidate_records, max_allocations=settings.macro_max_allocations
        )
        try:
            raw_content, system_fingerprint = _call_llm(
                settings.macro_llm_model, api_key, system_prompt, user_prompt, settings.macro_llm_seed
            )
            parsed = parse_macro_mapping_response(raw_content)
            view_kind = parsed.get("view_kind") or infer_macro_view_kind(view)
            allocations = filter_valid_allocations(
                normalize_macro_allocations(parsed["allocations"], view_kind, market_caps),
                all_tickers,
                max_allocations=settings.macro_max_allocations,
            )
            audit[view_id] = {
                "view_kind": view_kind,
                "rationale": parsed.get("rationale"),
                "model": settings.macro_llm_model,
                "seed": settings.macro_llm_seed,
                "system_fingerprint": system_fingerprint,
                "candidate_count": len(candidate_records),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:  # pragma: no cover - runtime guard for LLM issues
            logger.warning("Failed to generate macro mapping for %s: %s", view_id, exc)
            allocations = []

        if allocations:
            overrides[view_id] = allocations

    return overrides, audit
