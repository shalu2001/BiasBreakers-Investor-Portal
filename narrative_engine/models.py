"""Dataclasses for narrative clustering and views (vendored from the research repo)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TopicCluster:
    """Intermediate BERTopic cluster output."""

    view_type: str
    company: Optional[str]
    topic_id: int
    topic_name: str
    cluster_size: int
    document_ids: List[str]
    documents: List[Dict[str, Any]]
    probabilities: Optional[List[float]] = None


@dataclass(frozen=True)
class NarrativeView:
    """Final narrative view row ready for Black-Litterman input."""

    view_id: str
    view_type: str
    company: Optional[str]
    topic_id: int
    topic_name: str
    Qi: float
    Si: float
    Pi: float
    Ai: int
    cluster_size: int
    sentiment_std: float
    start_date: str
    end_date: str
    document_count: int
    diffusion_k: Optional[float] = None
    diffusion_c: Optional[float] = None
    diffusion_fitted: Optional[bool] = None
    diffusion_fit_points: Optional[int] = None
    diffusion_fit_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the view to a serializable dictionary."""

        return asdict(self)
