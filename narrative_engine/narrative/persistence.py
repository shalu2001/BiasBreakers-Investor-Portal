"""Persistence helpers for narrative clusters (vendored)."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable


def compute_window_days(start_date: datetime, end_date: datetime) -> int:
    """Return the inclusive number of days in the analysis window."""

    delta_days = (end_date.date() - start_date.date()).days + 1
    return max(1, delta_days)


def compute_persistence(unique_dates: Iterable[datetime], window_days: int) -> float:
    """Compute the fraction of days on which the narrative appeared."""

    unique_day_count = len({date.date() for date in unique_dates if date is not None})
    if window_days <= 0:
        return 0.0
    return max(0.0, min(1.0, unique_day_count / window_days))
