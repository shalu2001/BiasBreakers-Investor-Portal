"""Filtering and split helpers for narrative processing (vendored)."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


def ensure_required_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Ensure optional downstream columns exist."""

    result = dataframe.copy()
    defaults = {
        "headline": "",
        "content": "",
        "final_embedding": None,
        "final_sentiment_score": np.nan,
        "published_date": pd.NaT,
        "market_classification": "",
        "matched_company_name": "",
        "matched_symbol": "",
        "source": "",
        "collection_name": "",
    }
    for column, default_value in defaults.items():
        if column not in result.columns:
            result[column] = default_value
    return result


def deduplicate_articles(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove obvious duplicates while preserving repeated source reporting."""

    if dataframe.empty:
        return dataframe
    subset = [column for column in ["_id", "headline", "content", "published_date", "source"] if column in dataframe.columns]
    return dataframe.drop_duplicates(subset=subset, keep="first")


def is_valid_embedding(value: object) -> bool:
    """Validate a precomputed embedding."""

    if value is None:
        return False
    try:
        array = np.asarray(value, dtype=float).reshape(-1)
    except Exception:
        return False
    if array.size != 768 or np.isnan(array).any():
        return False
    # Reject degenerate all-zero vectors (e.g. CSE announcements with no extractable
    # content); a zero vector is meaningless for cosine-metric clustering.
    return bool(np.any(array != 0.0))


def filter_valid_articles(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove rows that violate the loading constraints."""

    if dataframe.empty:
        return dataframe.copy()

    result = dataframe.copy()
    result = result[result["content"].fillna("").astype(str).str.strip().ne("")]
    result = result[result["final_sentiment_score"].notna()]
    result = result[result["final_embedding"].apply(is_valid_embedding)]
    result = result[result["published_date"].notna()]
    return result.reset_index(drop=True)


def split_macro_micro(dataframe: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split cleaned records into macro and micro groups."""

    macro = dataframe[dataframe["market_classification"].eq("macro")].copy()
    micro = dataframe[dataframe["market_classification"].eq("micro")].copy()
    return macro.reset_index(drop=True), micro.reset_index(drop=True)


def group_micro_by_company(dataframe: pd.DataFrame) -> List[Tuple[str, pd.DataFrame]]:
    """Group micro narratives by company name."""

    groups: List[Tuple[str, pd.DataFrame]] = []
    if dataframe.empty:
        return groups

    for company_name, group in dataframe.groupby("matched_company_name", dropna=False):
        normalized_company = str(company_name or "").strip()
        if not normalized_company:
            continue
        groups.append((normalized_company, group.copy().reset_index(drop=True)))
    return groups
