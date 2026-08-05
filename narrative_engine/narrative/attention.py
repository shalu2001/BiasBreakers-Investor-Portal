"""Attention score helpers for narrative clusters (vendored)."""

from __future__ import annotations


def compute_attention(document_count: int) -> int:
    """Attention is the total number of articles in the cluster."""

    return int(document_count)
