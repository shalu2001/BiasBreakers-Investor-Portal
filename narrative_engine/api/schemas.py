"""Pydantic request/response models for the prediction API."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Request body for POST /predict."""

    as_of_date: date = Field(..., description="Prediction anchor date (looks back N days of news from here).")
    lookback_days: Optional[int] = Field(
        default=None, ge=1, le=365, description="Override the news lookback window in days (default 30)."
    )
    use_macro_overrides: Optional[bool] = Field(
        default=None, description="Override whether LLM macro-to-ticker basket mapping is applied (default true)."
    )


class Prediction(BaseModel):
    """Per-ticker Black-Litterman output."""

    ticker: str
    posterior: Optional[float] = Field(None, description="BL posterior expected return (annualized).")
    prior: Optional[float] = Field(None, description="Market-implied equilibrium prior return (annualized).")
    tilt: Optional[float] = Field(None, description="Narrative signal = posterior - prior.")


class NarrativeViewOut(BaseModel):
    """An underlying narrative view behind the predictions."""

    view_id: str
    view_type: str
    company: Optional[str] = None
    topic_name: str
    Qi: Optional[float] = None
    Si: Optional[float] = None
    Si_normalized: Optional[float] = None
    persistence: Optional[float] = None
    attention: Optional[int] = None
    cluster_size: Optional[int] = None
    sentiment_std: Optional[float] = None
    diffusion_k: Optional[float] = None
    diffusion_c: Optional[float] = None
    diffusion_fitted: Optional[bool] = None
    confidence: Optional[float] = None
    mapped_tickers: Optional[List[Any]] = None


class PredictResponse(BaseModel):
    """Response body for POST /predict."""

    as_of: str
    lookback_days: int
    universe: List[str]
    predictions: List[Prediction]
    views: List[NarrativeViewOut]
    meta: Dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    mongo: str
