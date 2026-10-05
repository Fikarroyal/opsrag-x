"""Lightweight deterministic reranker (no extra model download).

Applied after hybrid scoring on the top candidates:
    rerank_score = 0.88 * hybrid_score + 0.08 * lexical_overlap(query, text) + 0.04 * unit_match
The bonus terms only break near-ties; they never dominate the hybrid score.
"""

from __future__ import annotations

from typing import Any

from app.rag.embeddings import tokenize


def lexical_overlap(query: str, text: str) -> float:
    q, t = set(tokenize(query)), set(tokenize(text))
    return len(q & t) / len(q | t) if q and t else 0.0


def rerank(query: str, items: list[Any], *, unit: str | None = None) -> list[Any]:
    for it in items:
        overlap = lexical_overlap(query, it.text)
        unit_match = 1.0 if unit and it.payload.get("unit") and it.payload["unit"].lower() == unit.lower() else 0.0
        it.components["lexical"] = round(overlap, 4)
        it.components["unit_match"] = unit_match
        it.score = round(0.88 * it.score + 0.08 * overlap + 0.04 * unit_match, 6)
    return sorted(items, key=lambda x: x.score, reverse=True)
