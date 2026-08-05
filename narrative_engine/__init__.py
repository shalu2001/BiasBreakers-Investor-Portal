"""Standalone narrative-intelligence Black-Litterman prediction engine.

Public API:
    >>> from narrative_engine import NarrativePredictionEngine, get_settings
    >>> engine = NarrativePredictionEngine(get_settings())
    >>> result = engine.predict("2026-07-15")
"""

from narrative_engine.config import NarrativePipelineSettings, get_settings
from narrative_engine.engine import NarrativePredictionEngine, PredictionResult

__all__ = [
    "NarrativePredictionEngine",
    "PredictionResult",
    "NarrativePipelineSettings",
    "get_settings",
]

__version__ = "0.1.0"
