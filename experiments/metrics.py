from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetrievalMetrics:
    precision_at_k: float
    recall_at_k: float
    mrr: float


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    hits = sum(1 for item in top if item in relevant)
    return hits / float(k)


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = retrieved[:k]
    hits = sum(1 for item in top if item in relevant)
    return hits / float(len(relevant))


def mean_reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for idx, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / float(idx)
    return 0.0
