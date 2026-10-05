"""Assemble the structured investigation report (JSON first, then rendered by the UI) + deterministic summary text."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.ai.classifier import Classification
from app.ai.hypothesis import Hypothesis
from app.investigation.correlation import CorrelationResult
from app.investigation.evidence import EvidenceStore
from app.investigation.temporal import temporal_relation

INCONCLUSIVE = "Root cause belum dapat ditentukan secara memadai."


def executive_summary(
    cls: Classification, incident: dict[str, Any], top: Hypothesis | None, conclusive: bool, second: Hypothesis | None
) -> str:
    scope = {
        "single_device": "satu perangkat",
        "single_unit": "satu unit",
        "multi_unit": "beberapa unit",
        "hospital_wide": "seluruh rumah sakit",
        "unknown": "cakupan belum jelas",
    }[cls.affected_scope]
    base = f"Laporan: {incident['title']}. Diklasifikasikan sebagai {cls.category} (severity {cls.severity}, cakupan {scope})."
    if not conclusive or top is None:
        return f"{base} {INCONCLUSIVE} Evidence tidak mencukupi untuk menyimpulkan penyebab; lihat bagian keterbatasan dan rekomendasi pengumpulan evidence."
    txt = f'{base} Hipotesis yang paling didukung evidence: "{top.description}" (evidence confidence score {top.confidence:.0%}, bukan probabilitas statistik).'
    if second and second.status == "plausible":
        txt += f' Hipotesis alternatif yang masih mungkin: "{second.description}" ({second.confidence:.0%}).'
    return txt + " Seluruh hasil merupakan rekomendasi yang harus diverifikasi IT Support."


def build_timeline(corr: CorrelationResult, store: EvidenceStore, incident_time: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "timestamp": incident_time.isoformat(),
            "source": "incident_report",
            "event": "Gangguan dilaporkan/dirasakan pengguna",
            "relevance": 0.6,
            "relation": "during_incident",
            "evidence_key": None,
        }
    ]
    for t in corr.timeline:
        ts = datetime.fromisoformat(t["timestamp"])
        items.append(
            {
                "timestamp": t["timestamp"],
                "source": t["source"],
                "event": t["event"],
                "relevance": t["relevance"],
                "relation": temporal_relation(ts, incident_time),
                "evidence_key": None,
                "domain": t["domain"],
            }
        )
    for e in store.items:
        if e.source_type == "mcp_tool" and e.timestamp and "tool_failed" not in e.tags and e.kind != "INFERENCE":
            items.append(
                {
                    "timestamp": e.timestamp.isoformat(),
                    "source": e.meta.get("tool", "mcp_tool"),
                    "event": e.content[:140],
                    "relevance": round(e.relevance, 2),
                    "relation": e.relation,
                    "evidence_key": e.key,
                    "domain": "diagnostic",
                }
            )
    items.sort(key=lambda x: (x["timestamp"], x["source"]))
    return items[:60]


def build_findings(store: EvidenceStore) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in store.sorted_items():
        if e.source_type in ("sop", "historical_recent", "historical_old", "incident_report") or (
            e.role == "context" and e.kind != "UNKNOWN" and "topology_path" in e.tags
        ):
            continue
        out.append(
            {
                "id": f"F{len(out) + 1:02d}",
                "statement": e.content,
                "type": (e.kind if e.kind in ("FACT", "INFERENCE", "UNKNOWN") else "FACT"),
                "evidence_refs": [e.key],
                "role": e.role,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
        )
        if len(out) >= 16:
            break
    return out


def explain(h: Hypothesis, store: EvidenceStore) -> dict[str, Any]:
    d = h.definition
    sup = [store.by_key(k) for k in h.supporting]
    con = [store.by_key(k) for k in h.contradicting]
    why = f"{len(h.hit_indicators)} dari {len(d.supports) if d else 0} indikator terpenuhi ({', '.join(h.hit_indicators) or 'tidak ada'})."
    if sup and sup[0]:
        why += " Contoh evidence: " + " | ".join(f"[{e.key}] {e.content}" for e in sup[:2] if e)
    return {
        "why": why,
        "supporting_sources": sorted({e.source_type for e in sup if e}),
        "contradicting": [f"[{e.key}] {e.content}" for e in con if e],
        "missing_indicators": h.missing_indicators,
        "next_diagnostic": d.next_diagnostic if d else "",
        "recommended_next_diagnostic": d.next_diagnostic if d else "",
    }


def build_report(
    *,
    incident: dict[str, Any],
    cls: Classification,
    status: str,
    store: EvidenceStore,
    hyps: list[Hypothesis],
    conclusive: bool,
    recs: dict[str, Any],
    sop_refs: list[dict[str, Any]],
    sop_decisions: list[dict[str, Any]],
    hist: list[dict[str, Any]],
    tool_runs: list[Any],
    plan: dict[str, Any],
    corr: CorrelationResult,
    topo_info: dict[str, Any],
    scope: Any,
    limitations: list[str],
    narrative: str | None,
    ai_mode: str,
    model: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    top = hyps[0] if hyps else None
    second = hyps[1] if len(hyps) > 1 else None
    hyp_out = []
    for h in hyps[:6]:
        hd = h.to_dict()
        hd["supporting_evidence"] = [
            {"key": ev.key, "text": ev.content, "source_type": ev.source_type} for ev in (store.by_key(k) for k in h.supporting) if ev
        ]
        hd["contradicting_evidence"] = [
            {"key": ev.key, "text": ev.content, "source_type": ev.source_type} for ev in (store.by_key(k) for k in h.contradicting) if ev
        ]
        hd["explainability"] = explain(h, store)
        hd["type"] = "HYPOTHESIS"
        hyp_out.append(hd)
    tools = [
        {
            "tool": r.name,
            "purpose": r.purpose,
            "arguments": r.arguments,
            "status": r.status,
            "execution_ms": r.execution_ms,
            "error": r.error,
            "summary": r.summary,
            "evidence_keys": r.evidence_keys,
        }
        for r in tool_runs
    ]
    return {
        "incident_summary": executive_summary(cls, incident, top, conclusive, second),
        "ai_narrative": narrative,
        "incident": incident,
        "classification": {
            "category": cls.category,
            "secondary_category": cls.secondary_category,
            "severity": cls.severity,
            "affected_scope": cls.affected_scope,
            "affected_service": cls.affected_service,
            "confidence": cls.confidence,
            "method": cls.method,
        },
        "investigation_status": status,
        "findings": build_findings(store),
        "root_cause_hypotheses": hyp_out,
        "root_cause_conclusion": (
            {
                "status": "most_supported",
                "hypothesis_id": top.id,
                "description": top.description,
                "confidence": top.confidence,
                "confidence_label": "evidence confidence score",
                "note": "Bukan probabilitas statistik; harus diverifikasi IT Support.",
            }
            if conclusive and top
            else {"status": "inconclusive", "description": INCONCLUSIVE, "confidence": top.confidence if top else 0.0}
        ),
        "recommended_actions": recs["actions"],
        "verification_steps": recs["verification"],
        "next_diagnostic": recs["next_diagnostic"],
        "sop_procedures": recs["sop_procedures"],
        "evidence": [e.to_dict() for e in store.sorted_items()],
        "sop_reference": sop_refs,
        "sop_version_decisions": sop_decisions,
        "historical_incidents": [{**h, "usage": "supporting evidence only (not proof of current root cause)"} for h in hist],
        "tools_executed": tools,
        "tool_plan": plan,
        "correlation": {
            "onsets": {k: v.isoformat() for k, v in corr.onsets.items()},
            "patterns": [
                {
                    "name": p.name,
                    "cause_domain": p.cause_domain,
                    "cause_onset": p.cause_onset.isoformat(),
                    "symptom_onset": p.symptom_onset.isoformat(),
                    "lag_seconds": p.lag_seconds,
                    "order_ok": p.order_ok,
                    "event_count": p.event_count,
                    "correlation_score": p.score,
                }
                for p in corr.patterns
            ],
            "impact_units": corr.impact_units,
            "affected_endpoints": corr.affected_endpoints,
            "counts": corr.counts,
        },
        "timeline": build_timeline(corr, store, datetime.fromisoformat(incident["occurred_at"])),
        "topology": {
            "path": topo_info.get("path", []),
            "access_switch": topo_info.get("access_switch"),
            "uplink": topo_info.get("uplink"),
            "affected_hosts": scope.affected_hosts,
            "shared_access_switch": scope.shared_access_switch,
            "scope_level": scope.scope_level,
            "impact_units": scope.units,
        },
        "decision_trace": {
            "classification": {"category": cls.category, "severity": cls.severity, "scope": cls.affected_scope, "method": cls.method},
            "reasoning_summary": cls.reasoning + [plan["reason"]],
            "selected_tools": [
                {
                    "tool": t["tool"],
                    "why": t["purpose"],
                    "status": t["status"],
                    "result_summary": t["summary"],
                    "evidence_generated": t["evidence_keys"],
                }
                for t in tools
            ],
        },
        "limitations": limitations,
        "label_legend": {
            "FACT": "observed in a tool result/log",
            "INFERENCE": "derived from facts",
            "HYPOTHESIS": "candidate cause",
            "RECOMMENDATION": "suggested next step",
            "UNKNOWN": "missing or failed evidence",
        },
        "ai_mode": ai_mode,
        "model_used": model,
        "config": config,
    }
