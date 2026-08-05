"""Micro narrative clustering pipeline (vendored; scatter-export IO removed)."""

from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd

from narrative_engine.config import NarrativePipelineSettings
from narrative_engine.models import NarrativeView
from narrative_engine.narrative.statistics import build_narrative_view
from narrative_engine.pipeline.filters import group_micro_by_company
from narrative_engine.pipeline.topic_modeler import BerTopicModeler


def run_micro_pipeline(
    dataframe: pd.DataFrame,
    settings: NarrativePipelineSettings,
    analysis_start: datetime,
    analysis_end: datetime,
) -> List[NarrativeView]:
    """Cluster each company independently for micro narratives."""

    if dataframe.empty:
        return []

    modeler: BerTopicModeler | None = None
    views: List[NarrativeView] = []
    for company_name, company_frame in group_micro_by_company(dataframe):
        if modeler is None:
            modeler = BerTopicModeler(settings)
        clusters, _ = modeler.cluster_dataframe(company_frame, view_type="micro", company=company_name)
        for index, cluster in enumerate(clusters, start=1):
            cluster_documents = pd.DataFrame(cluster.documents)
            views.append(build_narrative_view(cluster, cluster_documents, settings, index, analysis_start, analysis_end))
    return views
