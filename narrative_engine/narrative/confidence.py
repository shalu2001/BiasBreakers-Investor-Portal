"""View confidence scoring for Black-Litterman narrative views (vendored)."""

from __future__ import annotations

from typing import Optional

import numpy as np


def compute_view_confidence(
    view_type: str,
    cluster_size: Optional[float],
    sentiment_std: Optional[float],
    diffusion_fitted: Optional[bool],
    *,
    macro_size_reference: float = 40.0,
    micro_size_reference: float = 6.0,
    macro_min_confidence: float = 0.05,
    micro_min_confidence: float = 0.15,
    max_confidence: float = 0.9,
    fallback_fit_penalty: float = 0.8,
) -> float:
    """Score how much a narrative view should be trusted in a Black-Litterman blend.

    Confidence combines sample size (`cluster_size`, saturating), agreement
    (`sentiment_std`), and diffusion fit quality (macro only). Returns a value in
    [min_confidence, max_confidence] (min depends on view type).
    """

    is_macro = str(view_type).strip().lower() == "macro"
    size_reference = macro_size_reference if is_macro else micro_size_reference
    min_confidence = macro_min_confidence if is_macro else micro_min_confidence

    size = float(cluster_size) if cluster_size is not None and cluster_size == cluster_size else 0.0
    std = float(sentiment_std) if sentiment_std is not None and sentiment_std == sentiment_std else 1.0

    denominator = size + size_reference
    size_term = size / denominator if denominator > 0 else 0.0
    agreement_term = max(0.0, 1.0 - min(std, 1.0))

    if diffusion_fitted is True:
        fit_term = 1.0
    elif diffusion_fitted is False:
        fit_term = fallback_fit_penalty
    else:
        fit_term = 1.0  # not applicable: micro views, or diffusion fitting disabled

    raw_confidence = size_term * agreement_term * fit_term
    return float(np.clip(raw_confidence, min_confidence, max_confidence))
