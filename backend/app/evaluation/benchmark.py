"""Benchmark + experiments A-D. Every number is computed by executing the pipeline on data/benchmark/benchmark_incidents.json.

Experiment A: no RAG        - classifier only; root cause guessed from the symptom category (LLM-without-RAG baseline)
Experiment B: RAG, no temporal weighting  - hybrid retrieval with temporal weight 0; root cause by score-weighted vote of retrieved incidents
Experiment C: RAG + temporal weighting    - as B with the configured temporal weight
Experiment D: full pipeline (RAG + temporal + topology + MCP evidence + hypothesis engine)

Metrics
  classification_accuracy / severity_accuracy : exact match with expected labels
  precision_at_k  : relevant retrieved / K            (relevant = historical incidents of the scenario's failure pattern)
  recall_at_k     : relevant retrieved / min(K, |relevant|)   (normalised, because |relevant| > K)
  historical_similarity : mean semantic similarity of the retrieved incidents
  sop_hit_rate    : share of expected SOP codes found among retrieved SOP references
  tool_selection_f1 : F1 between planned and expected tools (D only)
  root_cause_agreement : predicted root-cause category == expected (inconclusive counts as disagreement)
  evidence_coverage : share of expected evidence tags present among the evidence actually gathered
  avg_time_s : mean wall-clock seconds per incident
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.classifier import classify
from app.ai.llm import BaseLLMProvider
from app.config import Settings
from app.database.models import Incident, IncidentEvent, Investigation, InvestigationEvidence, ToolExecution
from app.investigation.orchestrator import InvestigationOrchestrator
from app.mcp.client import MCPClient
from app.rag.embeddings import Embedder
from app.rag.retriever import RetrievalQuery, Retriever

UTC = timezone.utc  # datetime.UTC only exists on Python 3.11+

logger = logging.getLogger(__name__)
EXPERIMENTS = [
    ("A", "LLM tanpa RAG", "Classifier only; root cause = symptom category (no retrieval, no tools)"),
    ("B", "RAG tanpa temporal weighting", "Hybrid retrieval with temporal weight = 0; vote over retrieved incidents"),
    ("C", "RAG + temporal weighting", "Hybrid retrieval with temporal decay; vote over retrieved incidents"),
    ("D", "RAG + temporal + topology + MCP evidence", "Full investigation pipeline with hypothesis scoring"),
]


def mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def f1(pred: set[str], gold: set[str]) -> float:
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    p, r = tp / len(pred), tp / len(gold)
    return 0.0 if tp == 0 else 2 * p * r / (p + r)


def vote(hits: list[Any]) -> str | None:
    w: dict[str, float] = defaultdict(float)
    for h in hits:
        w[h.payload["root_cause_category"]] += h.score
    return max(w, key=lambda k: w[k]) if w else None


def purge(session: Session) -> None:
    ids = [i for i in session.scalars(select(Incident.id).where(Incident.ticket_number.like("BENCH-%")))]
    if not ids:
        return
    inv_ids = [i for i in session.scalars(select(Investigation.id).where(Investigation.incident_id.in_(ids)))]
    if inv_ids:
        session.execute(delete(ToolExecution).where(ToolExecution.investigation_id.in_(inv_ids)))
        session.execute(delete(InvestigationEvidence).where(InvestigationEvidence.investigation_id.in_(inv_ids)))
    session.execute(delete(IncidentEvent).where(IncidentEvent.incident_id.in_(ids)))
    if inv_ids:
        session.execute(delete(Investigation).where(Investigation.id.in_(inv_ids)))
    session.execute(delete(Incident).where(Incident.id.in_(ids)))
    session.commit()


def run_benchmark(
    session_factory: sessionmaker[Session],
    settings: Settings,
    mcp: MCPClient,
    embedder: Embedder,
    llm: BaseLLMProvider | None = None,
    *,
    limit: int | None = None,
    k: int | None = None,
    write: bool = True,
) -> dict[str, Any]:
    k = k or settings.top_k
    items = json.loads((settings.data_dir / "benchmark" / "benchmark_incidents.json").read_text(encoding="utf-8"))
    if limit:
        items = items[:limit]
    orch = InvestigationOrchestrator(session_factory, settings, mcp, llm, embedder)
    acc: dict[str, dict[str, list[float]]] = {e[0]: defaultdict(list) for e in EXPERIMENTS}
    details: list[dict[str, Any]] = []
    with session_factory() as s:
        purge(s)
        retr = Retriever(s, embedder, settings)
        for n, it in enumerate(items, start=1):
            T = datetime.fromisoformat(it["occurred_at"])
            gold_rel, gold_sop, gold_tags, gold_tools = (
                set(it["relevant_historical_ids"]),
                set(it["expected_sop"]),
                set(it["expected_evidence_tags"]),
                set(it["expected_tools"]),
            )
            det: dict[str, Any] = {
                "id": it["id"],
                "scenario": it["scenario_id"],
                "description": it["description"],
                "expected": {
                    "category": it["expected_category"],
                    "severity": it["expected_severity"],
                    "root_cause": it["expected_root_cause_category"],
                },
            }
            t0 = time.perf_counter()
            cls = classify(it["description"], llm)
            t_cls = time.perf_counter() - t0
            q = RetrievalQuery(
                text=f"{it['description']} Unit: {cls.unit or ''}. Layanan: {cls.affected_service or ''}",
                incident_time=T,
                category=cls.category,
                secondary_category=cls.secondary_category,
                service=cls.affected_service,
                unit=cls.unit,
            )
            # ---- A
            a = acc["A"]
            a["classification_accuracy"].append(float(cls.category == it["expected_category"]))
            a["severity_accuracy"].append(float(cls.severity == it["expected_severity"]))
            a["root_cause_agreement"].append(float(cls.category == it["expected_root_cause_category"]))
            a["evidence_coverage"].append(0.0)
            a["avg_time_s"].append(t_cls)
            det["A"] = {"category": cls.category, "severity": cls.severity, "root_cause": cls.category}
            # ---- B, C
            for eid, temporal in (("B", False), ("C", True)):
                t0 = time.perf_counter()
                hits = retr.retrieve_historical(q, top_k=k, use_temporal=temporal)
                sops, _ = retr.retrieve_sops(q, top_k=k)
                dt = time.perf_counter() - t0 + t_cls
                ids = {h.payload["incident_key"] for h in hits}
                rel_hit = len(ids & gold_rel)
                e = acc[eid]
                e["classification_accuracy"].append(float(cls.category == it["expected_category"]))
                e["severity_accuracy"].append(float(cls.severity == it["expected_severity"]))
                e["precision_at_k"].append(rel_hit / k)
                e["recall_at_k"].append(rel_hit / min(k, len(gold_rel)) if gold_rel else 0.0)
                e["historical_similarity"].append(sum(h.payload["similarity"] for h in hits) / len(hits) if hits else 0.0)
                got_sop = {h.payload["sop_code"] for h in sops}
                e["sop_hit_rate"].append(len(got_sop & gold_sop) / len(gold_sop) if gold_sop else 0.0)
                rc = vote(hits)
                e["root_cause_agreement"].append(float(rc == it["expected_root_cause_category"]))
                have_tags = {f"historical_similar_{h.payload['root_cause_category']}" for h in hits[:3]} | (
                    {"sop_reference"} if sops else set()
                )
                e["evidence_coverage"].append(len(have_tags & gold_tags) / len(gold_tags) if gold_tags else 0.0)
                e["avg_time_s"].append(dt)
                det[eid] = {"root_cause": rc, "precision_at_k": round(rel_hit / k, 3)}
            # ---- D
            inc = Incident(
                ticket_number=f"BENCH-{n:03d}",
                title=it["description"].split(".")[0][:200],
                description=it["description"],
                status="benchmark",
                occurred_at=T,
            )
            s.add(inc)
            s.commit()
            inv = orch.create(s, inc)
            inc.status = "benchmark"
            s.commit()
            orch.run(inv.id)
            s.expire_all()
            inv_done = s.get(Investigation, inv.id)
            d = acc["D"]
            if inv_done is None or inv_done.status != "completed" or not inv_done.report:
                det["D"] = {"status": inv_done.status if inv_done else "missing", "error": inv_done.error_message if inv_done else None}
                for key in (
                    "classification_accuracy",
                    "severity_accuracy",
                    "precision_at_k",
                    "recall_at_k",
                    "historical_similarity",
                    "sop_hit_rate",
                    "tool_selection_f1",
                    "root_cause_agreement",
                    "evidence_coverage",
                ):
                    d[key].append(0.0)
                continue
            r = inv_done.report
            hist_ids = {h["incident_key"] for h in r["historical_incidents"]}
            rel_hit = len(hist_ids & gold_rel)
            d["classification_accuracy"].append(float(r["classification"]["category"] == it["expected_category"]))
            d["severity_accuracy"].append(float(r["classification"]["severity"] == it["expected_severity"]))
            d["precision_at_k"].append(rel_hit / k)
            d["recall_at_k"].append(rel_hit / min(k, len(gold_rel)) if gold_rel else 0.0)
            d["historical_similarity"].append(
                sum(h["similarity"] for h in r["historical_incidents"]) / max(1, len(r["historical_incidents"]))
            )
            d["sop_hit_rate"].append(len({x["sop_code"] for x in r["sop_reference"]} & gold_sop) / len(gold_sop) if gold_sop else 0.0)
            d["tool_selection_f1"].append(f1({t["tool"] for t in r["tools_executed"]}, gold_tools))
            conclusive = r["root_cause_conclusion"]["status"] == "most_supported"
            pred_rc = r["root_cause_hypotheses"][0]["category"] if conclusive else None
            d["root_cause_agreement"].append(float(pred_rc == it["expected_root_cause_category"]))
            tags = {t for e in r["evidence"] if e["kind"] != "UNKNOWN" for t in e["tags"]}
            d["evidence_coverage"].append(len(tags & gold_tags) / len(gold_tags) if gold_tags else 0.0)
            d["avg_time_s"].append((inv_done.duration_ms or 0) / 1000.0)
            det["D"] = {
                "category": r["classification"]["category"],
                "root_cause": pred_rc,
                "top_hypothesis": r["root_cause_hypotheses"][0]["id"],
                "confidence": r["root_cause_hypotheses"][0]["confidence"],
                "conclusive": conclusive,
                "missing_tags": sorted(gold_tags - tags),
            }
            details.append(det) if False else None
            details.append(det)
        purge(s)
    experiments = []
    for eid, name, desc in EXPERIMENTS:
        m = {key: mean(vals) for key, vals in acc[eid].items()}
        experiments.append({"id": eid, "name": name, "description": desc, "n": len(items), "metrics": m})
    result = {
        "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
        "benchmark_size": len(items),
        "k": k,
        "embedding": embedder.name,
        "classifier": ("llm" if (llm is not None and llm.is_available()) else "rule-based"),
        "mcp_transport": settings.mcp_transport,
        "retrieval_weights": settings.retrieval_weights,
        "experiments": experiments,
        "items": details,
        "notes": [
            "Synthetic benchmark: 50 incident descriptions = 10 paraphrases of each of 5 temporal scenarios; infrastructure state per scenario is shared, so D's scores are optimistic for unseen failure types.",
            "Expected labels were written before the classifier/engine and were not tuned afterwards.",
            "Precision/Recall@K relevance = historical incidents of the scenario's failure pattern; temporal weighting can lower precision when recent incidents belong to other patterns.",
            "Historical incidents and benchmark descriptions were authored from the same vocabulary, so retrieval-only root-cause agreement (B/C) is optimistic; D additionally gathers direct evidence (see evidence_coverage, tool_selection_f1).",
            "Metrics not applicable to an experiment (e.g. retrieval in A, tool selection in A-C) are null, not zero.",
        ],
    }
    if write:
        out = settings.data_dir / "processed"
        out.mkdir(parents=True, exist_ok=True)
        (out / "benchmark_results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
