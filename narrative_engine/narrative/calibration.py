"""Cross-view calibration of narrative expected-return views (vendored).

All three levers (neutral band, macro/micro rebalance, return-scale) are no-ops at their
default settings, so enabling them is opt-in.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List, Sequence

import numpy as np
import pandas as pd

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.models import NarrativeView


def calibrate_view_returns(
    frame: pd.DataFrame,
    *,
    neutral_band: float = 0.0,
    macro_view_weight: float = 1.0,
    target_return_std: float = 0.0,
) -> pd.DataFrame:
    """Return a copy of `frame` with `Qi` calibrated and neutral-band views removed."""

    if frame.empty or "Qi" not in frame.columns:
        return frame.copy()

    result = frame.copy()
    si = pd.to_numeric(result.get("Si"), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    sentiment_signal = np.tanh(si)

    if neutral_band > 0.0:
        keep = np.abs(sentiment_signal) >= neutral_band
        result = result.loc[keep].reset_index(drop=True)
        if result.empty:
            return result

    qi = pd.to_numeric(result["Qi"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

    if macro_view_weight != 1.0:
        is_macro = result["view_type"].astype(str).str.strip().str.lower().to_numpy() == "macro"
        qi = np.where(is_macro, qi * macro_view_weight, qi)

    if target_return_std > 0.0 and qi.size > 1:
        current_std = float(np.std(qi, ddof=0))
        if current_std > 0.0:
            qi = qi * (target_return_std / current_std)

    result["Qi"] = qi
    return result


def apply_view_calibration(
    views: Sequence[NarrativeView], settings: NarrativePipelineSettings
) -> List[NarrativeView]:
    """Apply `calibrate_view_returns` to a list of `NarrativeView` objects."""

    if not views:
        return list(views)

    neutral_band = getattr(settings, "view_neutral_band", 0.0)
    macro_view_weight = getattr(settings, "view_macro_weight", 1.0)
    target_return_std = getattr(settings, "view_target_return_std", 0.0)
    if neutral_band <= 0.0 and macro_view_weight == 1.0 and target_return_std <= 0.0:
        return list(views)

    frame = pd.DataFrame(
        {
            "_index": list(range(len(views))),
            "view_type": [view.view_type for view in views],
            "Si": [view.Si for view in views],
            "Qi": [view.Qi for view in views],
        }
    )
    calibrated = calibrate_view_returns(
        frame,
        neutral_band=neutral_band,
        macro_view_weight=macro_view_weight,
        target_return_std=target_return_std,
    )
    return [replace(views[int(row["_index"])], Qi=float(row["Qi"])) for _, row in calibrated.iterrows()]
