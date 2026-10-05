"""Hybrid retrieval over SOP chunks and historical incidents.

final_score = w_sem * semantic + w_temp * temporal + w_cat * category + w_svc * service + w_src * source_reliability

* semantic  : cosine(query, item) mapped to [0, 1] (negative cosine clipped to 0).
              PostgreSQL: pgvector `<=>` (HNSW) preselects candidates, exact cosine rescoring in Python.
              Fallback: numpy cosine (SQLite) or TF-IDF keyword scoring when embeddings are unavailable.
* temporal  : exp(-lambda * dt) (see investigation/temporal.py). Historical incidents use the age at incident
              time (half-life default 30 d). SOP chunks use the age of the version's effective date (180 d).
* category  : 1.0 exact category match, 0.5 match on secondary category / root-cause category, else 0.
* service   : 1.0 same affected service, else 0.
* source    : reliability prior of the source (historical recent 0.7, older 0.5, SOP 0.65).
Weights are configurable (SEMANTIC_WEIGHT, TEMPORAL_WEIGHT, ...) and normalised to sum to 1.

SOP retrieval is VERSION-AWARE: only the version effective on the incident date is searched, so a
newer SOP that is not yet in force is never used for an older incident.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database.models import HistoricalIncident, SopChunk, SopDocument, SopVersion
from app.investigation.temporal import SECONDS_PER_DAY, temporal_score
from app.rag.embeddings import Embedder, get_embedder
from app.rag.reranker import rerank

logger = logging.getLogger(__name__)

SOURCE_RELIABILITY = {"sop": 0.65, "historical_recent": 0.70, "historical_old": 0.50}


@dataclass
class Retrieved:
    kind: str  # sop_chunk | historical_incident
    id: str
    score: float
    text: str
    components: dict[str, float] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "score": round(self.score, 4), "components": self.components, **self.payload}


@dataclass
class RetrievalQuery:
    text: str
    incident_time: datetime
    category: str | None = None
    secondary_category: str | None = None
    service: str | None = None
    unit: str | None = None


def combine(components: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted sum; components and weights share keys semantic/temporal/category/service/source."""
    return float(sum(weights[k] * components.get(k, 0.0) for k in weights))


def _as_vec(v: Any) -> np.ndarray | None:
    return None if v is None else np.asarray(v, dtype=np.float64)


def _semantic(qvec: np.ndarray, vec: Any) -> float:
    v = _as_vec(vec)
    if v is None:
        return 0.0
    n = np.linalg.norm(v) * np.linalg.norm(qvec)
    return max(0.0, float(np.dot(v, qvec) / n)) if n else 0.0


def _tfidf_scores(query: str, texts: list[str]) -> list[float]:
    if not texts:
        return []
    try:
        vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), sublinear_tf=True)
        m = vec.fit_transform(texts + [query])
        sims = (m[:-1] @ m[-1].T).toarray().ravel()
        return [float(s) for s in sims]
    except ValueError:
        return [0.0] * len(texts)


class Retriever:
    def __init__(self, session: Session, embedder: Embedder | None = None, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.embedder = embedder or get_embedder()
        self.weights = self.settings.retrieval_weights
        self.last_mode = "vector"

    # ------------------------------------------------------------------ helpers
    def _embed_query(self, text: str) -> np.ndarray | None:
        try:
            return self.embedder.embed([text])[0]
        except Exception as exc:  # embedding failure -> keyword fallback (never crash)
            logger.warning("query embedding failed (%s); using keyword fallback", exc)
            return None

    def _candidates(self, model: Any, qvec: np.ndarray | None, extra_where: list[Any], limit: int) -> list[Any]:
        stmt = select(model).where(*extra_where)
        if qvec is not None and self.session.get_bind().dialect.name == "postgresql":
            stmt = stmt.where(model.embedding.is_not(None), model.embedding_model == self.embedder.name)
            stmt = stmt.order_by(model.embedding.cosine_distance(qvec.tolist())).limit(limit)
        return list(self.session.scalars(stmt))

    # ------------------------------------------------------------------ SOP (version-aware)
    def applicable_sop_versions(self, incident_time: datetime) -> tuple[list[SopVersion], list[dict[str, Any]]]:
        """Per SOP code, pick the newest version whose effective_date <= incident date. Returns (versions, decisions)."""
        day = incident_time.date()
        versions = list(
            self.session.scalars(
                select(SopVersion)
                .join(SopDocument)
                .where(SopDocument.doc_type == "sop")
                .order_by(SopVersion.sop_code, SopVersion.effective_date)
            )
        )
        by_code: dict[str, list[SopVersion]] = {}
        for v in versions:
            by_code.setdefault(v.sop_code, []).append(v)
        chosen: list[SopVersion] = []
        decisions: list[dict[str, Any]] = []
        for code, vs in by_code.items():
            eligible = [v for v in vs if v.effective_date <= day]
            pick = eligible[-1] if eligible else None
            if pick:
                chosen.append(pick)
            for v in vs:
                if pick and v.id == pick.id:
                    reason = "effective at incident time (selected)"
                elif v.effective_date > day:
                    reason = f"not yet effective at incident time (effective {v.effective_date.isoformat()})"
                else:
                    reason = "superseded by a newer version effective at incident time"
                decisions.append(
                    {
                        "sop_code": code,
                        "version": v.version,
                        "effective_date": v.effective_date.isoformat(),
                        "selected": bool(pick and v.id == pick.id),
                        "reason": reason,
                    }
                )
        return chosen, decisions

    def retrieve_sops(self, q: RetrievalQuery, top_k: int | None = None) -> tuple[list[Retrieved], list[dict[str, Any]]]:
        top_k = top_k or self.settings.top_k
        versions, decisions = self.applicable_sop_versions(q.incident_time)
        if not versions:
            return [], decisions
        by_id = {v.id: v for v in versions}
        chunks = list(self.session.scalars(select(SopChunk).where(SopChunk.version_id.in_(list(by_id)))))
        qvec = self._embed_query(q.text)
        usable = qvec is not None and all(c.embedding is not None and c.embedding_model == self.embedder.name for c in chunks)
        self.last_mode = "vector" if usable else "keyword"
        sems = (
            [_semantic(qvec, c.embedding) for c in chunks]
            if usable and qvec is not None
            else _tfidf_scores(q.text, [c.text for c in chunks])
        )
        out: list[Retrieved] = []
        for c, sem in zip(chunks, sems, strict=True):
            v = by_id[c.version_id]
            age_s = (q.incident_time.date() - v.effective_date).days * SECONDS_PER_DAY
            comp = {
                "semantic": sem,
                "temporal": temporal_score(age_s, self.settings.sop_half_life_days * SECONDS_PER_DAY),
                "category": (
                    1.0
                    if q.category and c.meta.get("category") == q.category
                    else (0.5 if q.secondary_category and c.meta.get("category") == q.secondary_category else 0.0)
                ),
                "service": (1.0 if q.service and q.service.lower() in c.text.lower() else 0.0),
                "source": SOURCE_RELIABILITY["sop"],
            }
            out.append(
                Retrieved(
                    "sop_chunk",
                    str(c.id),
                    combine(comp, self.weights),
                    c.text,
                    {k: round(x, 4) for k, x in comp.items()},
                    {
                        "sop_code": c.sop_code,
                        "version": v.version,
                        "effective_date": v.effective_date.isoformat(),
                        "section": c.section,
                        "title": v.document.title,
                        "category": c.meta.get("category"),
                        "unit": None,
                    },
                )
            )
        ranked = rerank(q.text, sorted(out, key=lambda x: x.score, reverse=True)[: max(top_k * 3, 12)], unit=q.unit)
        return ranked[:top_k], decisions

    # ------------------------------------------------------------------ historical incidents
    def retrieve_historical(
        self, q: RetrievalQuery, top_k: int | None = None, *, use_temporal: bool = True, weights: dict[str, float] | None = None
    ) -> list[Retrieved]:
        top_k = top_k or self.settings.top_k
        w = dict(weights or self.weights)
        if not use_temporal:
            w = {**w, "temporal": 0.0}
            total = sum(w.values()) or 1.0
            w = {k: v / total for k, v in w.items()}
        qvec = self._embed_query(q.text)
        rows = self._candidates(HistoricalIncident, qvec, [HistoricalIncident.timestamp < q.incident_time], max(top_k * 12, 120))
        if not rows:
            return []
        usable = qvec is not None and all(r.embedding is not None and r.embedding_model == self.embedder.name for r in rows)
        self.last_mode = "vector" if usable else "keyword"
        texts = [self.hist_text(r) for r in rows]
        sems = [_semantic(qvec, r.embedding) for r in rows] if usable and qvec is not None else _tfidf_scores(q.text, texts)
        out: list[Retrieved] = []
        for r, sem, txt in zip(rows, sems, texts, strict=True):
            age_s = (q.incident_time - r.timestamp).total_seconds()
            recent = age_s <= 90 * SECONDS_PER_DAY
            comp = {
                "semantic": sem,
                "temporal": temporal_score(age_s, self.settings.history_half_life_days * SECONDS_PER_DAY),
                "category": (
                    1.0
                    if q.category and r.category == q.category
                    else (
                        0.5
                        if (q.secondary_category and r.category == q.secondary_category)
                        or (q.category and r.root_cause_category == q.category)
                        else 0.0
                    )
                ),
                "service": (1.0 if q.service and r.affected_service == q.service else 0.0),
                "source": SOURCE_RELIABILITY["historical_recent" if recent else "historical_old"],
            }
            res = r.resolution
            out.append(
                Retrieved(
                    "historical_incident",
                    str(r.id),
                    combine(comp, w),
                    txt,
                    {k: round(x, 4) for k, x in comp.items()},
                    {
                        "incident_key": r.incident_key,
                        "timestamp": r.timestamp.isoformat(),
                        "unit": r.unit,
                        "device": r.device,
                        "description": r.description,
                        "category": r.category,
                        "severity": r.severity,
                        "affected_service": r.affected_service,
                        "root_cause": r.root_cause,
                        "root_cause_category": r.root_cause_category,
                        "pattern": r.pattern,
                        "resolution": res.resolution if res else None,
                        "resolution_time_minutes": (res.resolution_time_minutes if res else None),
                        "similarity": round(sem, 4),
                        "age_days": round(age_s / SECONDS_PER_DAY, 1),
                    },
                )
            )
        ranked = rerank(q.text, sorted(out, key=lambda x: x.score, reverse=True)[: max(top_k * 3, 24)], unit=q.unit)
        return ranked[:top_k]

    @staticmethod
    def hist_text(r: HistoricalIncident) -> str:
        """Symptom-side text used for embedding (root cause is stored, but deliberately not embedded)."""
        return f"{r.description} Unit: {r.unit or ''}. Layanan: {r.affected_service or ''}. Kategori: {r.category}."
