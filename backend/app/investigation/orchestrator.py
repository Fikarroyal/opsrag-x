"""InvestigationOrchestrator: the central multi-step investigation workflow.

Receive incident -> normalise -> classify -> severity -> SOP retrieval (version-aware) -> historical retrieval
-> topology inspection -> tool planning -> read-only MCP execution -> log collection -> temporal correlation
-> evidence assembly -> hypotheses -> scoring -> remediation -> report -> save (with full audit trail).

Every stage is written to `incident_events`; the `investigations.stages` JSON drives the UI progress view.
The incident's `scenario_id` (demo label) is NEVER read here: results come only from retrieval, tools and logs.
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.classifier import classify
from app.ai.formatter import build_report
from app.ai.hypothesis import evaluate
from app.ai.investigator import llm_narrative, plan_tools, refine_plan_with_llm
from app.ai.llm import BaseLLMProvider, get_llm
from app.config import Settings, get_settings
from app.database.models import Device, Incident, Investigation, InvestigationEvidence, ToolExecution, utcnow
from app.investigation.correlation import correlate
from app.investigation.evidence import EvidenceStore
from app.investigation.evidence_builders import (
    BuildContext,
    ToolRun,
    derive_aggregates,
    evidence_from_correlation,
    evidence_from_report,
    evidence_from_tool,
    evidence_from_topology,
)
from app.investigation.recommendation import build_recommendations
from app.investigation.topology import analyze_scope, load_topology
from app.logging_config import log_event, request_id_var
from app.mcp.client import MCPClient
from app.rag.embeddings import Embedder, get_embedder
from app.rag.retriever import RetrievalQuery, Retriever
from app.services import incident_service as isvc
from app.services import log_service
from app.services.inventory_service import host_maps

logger = logging.getLogger(__name__)

STAGES = [
    "classification",
    "sop_retrieval",
    "historical_search",
    "topology_inspection",
    "mcp_diagnostics",
    "log_correlation",
    "root_cause_analysis",
    "recommendation",
]
AS_OF_TOOLS = {"get_server_status", "check_http", "check_dns", "ping_host", "query_service_status", "get_network_interface_status"}
FORBIDDEN = ("patient", "pasien", "rekam medis pasien")


def config_snapshot(settings: Settings, embedder: Embedder, llm: BaseLLMProvider) -> dict[str, Any]:
    return {
        "retrieval_weights": settings.retrieval_weights,
        "hypothesis_weights": settings.hypothesis_weights,
        "top_k": settings.top_k,
        "history_half_life_days": settings.history_half_life_days,
        "sop_half_life_days": settings.sop_half_life_days,
        "log_half_life_minutes": settings.log_half_life_minutes,
        "correlation_window_minutes": settings.correlation_window_minutes,
        "tool_snapshot_offset_minutes": settings.tool_snapshot_offset_minutes,
        "min_confidence_for_root_cause": settings.min_confidence_for_root_cause,
        "embedding": embedder.name,
        "llm": {"provider": llm.name, "model": llm.model},
        "demo_mode": settings.demo_mode,
        "mcp_transport": settings.mcp_transport,
    }


class InvestigationOrchestrator:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings | None = None,
        mcp: MCPClient | None = None,
        llm: BaseLLMProvider | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.sf = session_factory
        self.settings = settings or get_settings()
        self.mcp = mcp or MCPClient(settings=self.settings)
        self.llm = llm if llm is not None else get_llm(self.settings)
        self.embedder = embedder or get_embedder()

    # ------------------------------------------------------------------ public API
    def create(self, session: Session, incident: Incident, parent_id: uuid.UUID | None = None) -> Investigation:
        inv = Investigation(
            incident_id=incident.id,
            parent_investigation_id=parent_id,
            status="queued",
            stages={s: {"status": "pending"} for s in STAGES},
            request_id=request_id_var.get(),
            config_snapshot=config_snapshot(self.settings, self.embedder, self.llm),
            input_snapshot={
                "title": incident.title,
                "description": incident.description,
                "affected_unit": incident.affected_unit,
                "affected_device": incident.affected_device,
                "affected_service": incident.affected_service,
                "occurred_at": incident.occurred_at.isoformat(),
            },
            model_used=None,
            started_at=utcnow(),
        )
        session.add(inv)
        session.flush()
        isvc.add_event(
            session,
            incident.id,
            inv.id,
            "investigation_queued",
            "Investigation queued" + (" (replay)" if parent_id else ""),
            meta={"parent": str(parent_id) if parent_id else None},
        )
        if incident.status == "open":
            incident.status = "investigating"
        session.commit()
        return inv

    def run(self, investigation_id: uuid.UUID) -> None:
        with self.sf() as s:
            inv = s.get(Investigation, investigation_id)
            if inv is None:
                logger.error("investigation %s not found", investigation_id)
                return
            started = time.perf_counter()
            try:
                self._execute(s, inv, started)
            except Exception as exc:  # any failure is recorded; never crashes the worker
                s.rollback()
                inv = s.get(Investigation, investigation_id)
                assert inv is not None
                inv.status, inv.error_message, inv.completed_at = ("failed", f"{type(exc).__name__}: {str(exc)[:300]}", utcnow())
                inv.duration_ms = round((time.perf_counter() - started) * 1000, 1)
                isvc.add_event(
                    s,
                    inv.incident_id,
                    inv.id,
                    "investigation_failed",
                    f"Investigation failed: {type(exc).__name__}",
                    status="error",
                    meta={"error": str(exc)[:300]},
                )
                s.commit()
                log_event(
                    logger,
                    "investigation_failed",
                    incident_id=inv.incident_id,
                    investigation_id=inv.id,
                    started=started,
                    status="error",
                    level=logging.ERROR,
                )
                logger.error("investigation failed\n%s", traceback.format_exc())

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _stage(s: Session, inv: Investigation, name: str, status: str, detail: str | None = None, top_status: str | None = None) -> None:
        stages = dict(inv.stages or {})
        entry = dict(stages.get(name, {}))
        now = utcnow().isoformat()
        entry["status"] = status
        if status == "running":
            entry["started_at"] = now
        else:
            entry["finished_at"] = now
        if detail:
            entry["detail"] = detail
        stages[name] = entry
        inv.stages = stages
        if top_status:
            inv.status = top_status
        s.commit()

    def _event(
        self,
        s: Session,
        inv: Investigation,
        event: str,
        message: str,
        t0: float,
        *,
        status: str = "ok",
        meta: dict[str, Any] | None = None,
        log_name: str | None = None,
    ) -> None:
        isvc.add_event(
            s, inv.incident_id, inv.id, event, message, status=status, duration_ms=round((time.perf_counter() - t0) * 1000, 2), meta=meta
        )
        log_event(logger, log_name or event, incident_id=inv.incident_id, investigation_id=inv.id, started=t0, status=status)
        s.commit()

    # ------------------------------------------------------------------ pipeline
    def _execute(self, s: Session, inv: Investigation, started: float) -> None:
        cfg = self.settings
        inc = s.get(Incident, inv.incident_id)
        assert inc is not None
        T = inc.occurred_at
        text = f"{inc.title}. {inc.description}"
        inv.status = "running"
        s.commit()
        self._event(
            s,
            inv,
            "investigation_started",
            f"Investigation started for {inc.ticket_number}",
            time.perf_counter(),
            log_name="investigation_started",
        )
        hosts, ip_unit, unit_devices = host_maps(s)
        topo = load_topology(str(cfg.raw_dir / "network_topology.json"))
        audit: dict[str, Any] = {"incident": inv.input_snapshot, "config": inv.config_snapshot, "embedding": self.embedder.name}

        # 1-2. classification & severity
        t0 = time.perf_counter()
        self._stage(s, inv, "classification", "running")
        cls = classify(text, self.llm, unit_hint=inc.affected_unit, device_hint=inc.affected_device, service_hint=inc.affected_service)
        unit = cls.unit if cls.unit else (inc.affected_unit if inc.affected_unit != "Semua Unit" else None)
        ai_mode = "llm" if cls.method == "llm" else "fallback"
        audit["classification"] = cls.to_dict()
        self._stage(s, inv, "classification", "done", f"{cls.category}/{cls.severity}/{cls.affected_scope} via {cls.method}")
        self._event(
            s,
            inv,
            "classification_completed",
            f"Classified as {cls.category}, severity {cls.severity}, scope {cls.affected_scope} ({cls.method}, confidence {cls.confidence})",
            t0,
            meta=cls.to_dict(),
            log_name="classification_completed",
        )
        if inc.category is None:
            inc.category = cls.category
        if inc.severity is None:
            inc.severity = cls.severity

        # 3. SOP retrieval (version-aware)
        t0 = time.perf_counter()
        self._stage(s, inv, "sop_retrieval", "running", top_status="collecting_evidence")
        retr = Retriever(s, self.embedder, cfg)
        rq = RetrievalQuery(
            text=f"{text} Unit: {unit or ''}. Layanan: {cls.affected_service or ''}",
            incident_time=T,
            category=cls.category,
            secondary_category=cls.secondary_category,
            service=cls.affected_service,
            unit=unit,
        )
        sop_hits, sop_decisions = retr.retrieve_sops(rq, cfg.top_k)
        sop_mode = retr.last_mode
        applicable, _ = retr.applicable_sop_versions(T)
        sop_versions = {v.sop_code: v for v in applicable}
        by_code: dict[str, dict[str, Any]] = {}
        for h in sop_hits:
            p = h.payload
            entry = by_code.setdefault(
                p["sop_code"],
                {
                    "sop_code": p["sop_code"],
                    "title": p["title"],
                    "version": p["version"],
                    "effective_date": p["effective_date"],
                    "relevance": round(h.score, 4),
                    "matched_sections": [],
                    "selection_reason": f"version effective at incident time ({T.date().isoformat()})",
                },
            )
            entry["matched_sections"].append(p["section"])
        sop_refs = sorted(by_code.values(), key=lambda x: x["relevance"], reverse=True)[:4]
        audit["retrieval_sop"] = {
            "mode": sop_mode,
            "chunks": [
                {
                    "id": h.id,
                    "sop": h.payload["sop_code"],
                    "version": h.payload["version"],
                    "section": h.payload["section"],
                    "score": round(h.score, 4),
                    "components": h.components,
                }
                for h in sop_hits
            ],
            "version_decisions": sop_decisions,
        }
        self._stage(s, inv, "sop_retrieval", "done", f"{len(sop_refs)} SOP ({sop_mode})")
        self._event(
            s,
            inv,
            "sop_retrieved",
            f"Retrieved {len(sop_refs)} SOP reference(s): " + ", ".join(f"{r['sop_code']} v{r['version']}" for r in sop_refs),
            t0,
            meta={"mode": sop_mode},
            log_name="sop_retrieved",
        )

        # 4. historical incidents
        t0 = time.perf_counter()
        self._stage(s, inv, "historical_search", "running")
        hist_all = retr.retrieve_historical(rq, top_k=30)
        hist_mode = retr.last_mode
        hist_show = [{**h.payload, "score": round(h.score, 4), "components": h.components} for h in hist_all[: cfg.top_k]]
        hist_match = [{"score": h.score, "root_cause_category": h.payload["root_cause_category"]} for h in hist_all]
        audit["retrieval_historical"] = {
            "mode": hist_mode,
            "top": [{"id": h["incident_key"], "score": h["score"]} for h in hist_show],
            "candidates_considered": len(hist_all),
        }
        self._stage(s, inv, "historical_search", "done", f"{len(hist_show)} incidents ({hist_mode})")
        self._event(
            s,
            inv,
            "historical_incidents_retrieved",
            f"Retrieved {len(hist_show)} similar historical incident(s) as supporting evidence",
            t0,
            meta={"mode": hist_mode},
            log_name="historical_incidents_retrieved",
        )

        # 5. topology & plan
        t0 = time.perf_counter()
        self._stage(s, inv, "topology_inspection", "running")
        plan = refine_plan_with_llm(
            plan_tools(cls, topo, unit_devices, unit=unit, device=cls.device, incident_time_iso=T.isoformat()), cls, self.llm
        )
        audit["tool_plan"] = plan.to_dict()
        self._stage(
            s,
            inv,
            "topology_inspection",
            "done",
            f"{len(plan.selected_tools)} tools planned; affected sample {plan.affected_hosts or 'n/a'}",
        )
        self._event(
            s,
            inv,
            "topology_retrieved",
            f"Topology inspected; planned {len(plan.selected_tools)} read-only tool(s)",
            t0,
            meta={"reason": plan.reason, "affected_sample": plan.affected_hosts, "control": plan.control_hosts},
            log_name="topology_retrieved",
        )

        # 6. MCP diagnostics
        t0 = time.perf_counter()
        self._stage(s, inv, "mcp_diagnostics", "running")
        as_of = (T + timedelta(minutes=cfg.tool_snapshot_offset_minutes)).isoformat()
        calls: list[tuple[str, dict[str, Any]]] = []
        for pt in plan.selected_tools:
            a = dict(pt.arguments)
            if pt.tool in AS_OF_TOOLS and cfg.demo_mode:
                a["as_of"] = as_of
            if pt.tool == "search_logs":
                a.update(
                    start_time=(T - timedelta(minutes=cfg.correlation_window_minutes)).isoformat(),
                    end_time=(T + timedelta(minutes=cfg.correlation_window_minutes)).isoformat(),
                )
            calls.append((pt.tool, a))
        results = self.mcp.call_batch(calls)
        runs: list[ToolRun] = []
        for pt, (tool, args), res in zip(plan.selected_tools, calls, results, strict=True):
            run = ToolRun(tool, args, pt.purpose, res.status, res.result, res.error, res.execution_ms, utcnow())
            runs.append(run)
            s.add(
                ToolExecution(
                    investigation_id=inv.id,
                    tool_name=tool,
                    purpose=pt.purpose,
                    arguments=args,
                    result=res.result,
                    execution_time=res.execution_ms,
                    status=res.status,
                    error_message=res.error,
                )
            )
            isvc.add_event(
                s,
                inc.id,
                inv.id,
                "tool_execution",
                f"Executed {tool}" + ("" if res.ok else f" (failed: {res.error})"),
                status="ok" if res.ok else "error",
                duration_ms=res.execution_ms,
                meta={"tool": tool, "arguments": args},
            )
            log_event(
                logger,
                "mcp_tool_called",
                incident_id=inc.id,
                investigation_id=inv.id,
                status="ok" if res.ok else "error",
                tool=tool,
                execution_ms=res.execution_ms,
            )
        s.commit()
        ok_count = sum(1 for r in runs if r.status == "success")
        self._stage(s, inv, "mcp_diagnostics", "done" if ok_count or not runs else "failed", f"{ok_count}/{len(runs)} tools succeeded")

        # 7. logs + correlation
        t0 = time.perf_counter()
        self._stage(s, inv, "log_correlation", "running")
        w0, w1 = T - timedelta(minutes=cfg.correlation_window_minutes), T + timedelta(minutes=cfg.correlation_window_minutes)
        records = log_service.window_records(s, w0, w1)
        corr = correlate(records, T, affected_unit=unit, hosts=hosts, ip_unit=ip_unit)
        auth_failures = sum(1 for r in records if r.event_type == "AUTH_FAILURE")
        audit["log_queries"] = [
            {"kind": "window", "start": w0.isoformat(), "end": w1.isoformat(), "records": len(records), "anomaly_groups": len(corr.groups)}
        ]
        audit["tool_logs"] = [{"tool": r.name, "arguments": r.arguments} for r in runs if r.name == "search_logs"]
        self._stage(s, inv, "log_correlation", "done", f"{len(records)} log records, {len(corr.patterns)} temporal pattern(s)")
        self._event(
            s,
            inv,
            "logs_retrieved",
            f"Collected {len(records)} log records in +-{cfg.correlation_window_minutes} min window; {len(corr.groups)} anomaly group(s), patterns: {[p.name for p in corr.patterns]}",
            t0,
            meta={"records": len(records)},
            log_name="logs_retrieved",
        )

        # 8-10. evidence, hypotheses, scoring
        t0 = time.perf_counter()
        self._stage(s, inv, "root_cause_analysis", "running", top_status="analyzing")
        store = EvidenceStore(T, cfg.log_half_life_minutes)
        ctx = BuildContext(T, unit, cls.affected_service, plan.affected_hosts, plan.control_hosts, access_switches=plan.access_switches)
        evidence_from_report(store, inc.description, cls.internet_normal, cls.others_normal, T)
        for r in runs:
            evidence_from_tool(store, r, ctx)
            first = store.by_key(r.evidence_keys[0]) if r.evidence_keys else None
            r.summary = first.content if first else (r.error or "")
        derive_aggregates(store, ctx)
        evidence_from_correlation(store, corr, topo, ctx, auth_failures, cfg.correlation_window_minutes)
        confirmed = set(corr.affected_endpoints) | {
            e.meta["host"] for e in store.items if e.meta.get("role_hint") == "affected" and "endpoint_packet_loss" in e.tags
        }
        scope = analyze_scope(topo, sorted(confirmed), corr.impact_units, cls.affected_scope, unhealthy_hosts=confirmed)
        sample = sorted(confirmed)[0] if confirmed else (plan.affected_hosts[0] if plan.affected_hosts else None)
        topo_info = evidence_from_topology(store, topo, scope, "SIMRS-APP-01", sample)
        if unit and unit_devices.get(unit):
            sws = sorted({sw for h in unit_devices[unit] if (sw := hosts[h].switch)})
            store.add(
                "device_inventory",
                f"Inventori: unit {unit} memiliki {len(unit_devices[unit])} endpoint pada switch akses {', '.join(sws)}.",
                source_id="devices",
                tags=["device_inventory"],
                relevance=0.6,
            )
        for hrow in hist_show[:3]:
            ev = store.add(
                "historical_recent" if hrow["age_days"] <= 90 else "historical_old",
                f"Incident historis {hrow['incident_key']} ({hrow['timestamp'][:10]}, {hrow['unit']}): {hrow['description']} Penyebab tercatat: {hrow['root_cause']}; penyelesaian: {hrow['resolution']} ({hrow['resolution_time_minutes']} menit). Kesamaan {hrow['similarity']}.",
                source_id=hrow["incident_key"],
                tags=[f"historical_similar_{hrow['root_cause_category']}"],
                relevance=hrow["score"],
                kind="INFERENCE",
            )
            ev.temporal = hrow["components"]["temporal"]
        for sref in sop_refs[:3]:
            store.add(
                "sop",
                f"SOP {sref['sop_code']} v{sref['version']} (berlaku {sref['effective_date']}) - {sref['title']}; bagian relevan: {', '.join(sorted(set(sref['matched_sections'])))}.",
                source_id=f"{sref['sop_code']}@{sref['version']}",
                tags=["sop_reference"],
                relevance=sref["relevance"],
            )
        direct = [
            e for e in store.items if e.source_type in ("mcp_tool", "network_log", "server_log", "log_correlation") and e.kind != "UNKNOWN"
        ]
        if not direct:
            store.add(
                "mcp_tool",
                "Evidence tidak mencukupi: tidak ada diagnostik langsung maupun log anomali yang dapat dikorelasikan pada jendela waktu insiden.",
                kind="UNKNOWN",
                tags=["insufficient_direct_evidence"],
                relevance=0.4,
            )
        labels = {
            "switch": scope.shared_access_switch
            or (next(iter(scope.access_groups)) if scope.access_groups else (topo_info.get("access_switch") or "switch akses")),
            "device": sample or "endpoint",
            "server": "SIMRS-APP-01",
            "dns": "DNS-01",
            "db": "SIMRS-DB-01",
        }
        patterns = {p.cause_domain: p.score for p in corr.patterns if p.order_ok}
        hyps = evaluate(
            store, scope, hist_match, patterns, cfg.hypothesis_weights, labels, ok_count, len(runs), cfg.min_confidence_for_root_cause
        )
        top = hyps[0] if hyps else None
        conclusive = bool(top and top.status == "most_supported")
        audit["hypotheses"] = [h.to_dict() for h in hyps]
        self._stage(s, inv, "root_cause_analysis", "done", f"top: {top.id if top else 'n/a'} ({top.confidence if top else 0})")
        self._event(
            s,
            inv,
            "hypotheses_generated",
            f"Generated {len(hyps)} hypotheses; leading {top.id if top else 'n/a'} score {top.score if top else 0} confidence {top.confidence if top else 0} ({'conclusive' if conclusive else 'inconclusive'})",
            t0,
            meta={"top": top.id if top else None},
            log_name="hypotheses_generated",
        )

        # 11-15. remediation + report
        t0 = time.perf_counter()
        self._stage(s, inv, "recommendation", "running", top_status="generating_report")
        devs = list(s.scalars(select(Device).where(Device.hostname.in_(sorted(confirmed) or ["-"]))))
        ports = [f"{d.hostname}:{d.switch_port}" for d in sorted(devs, key=lambda d: d.hostname)]
        recs = build_recommendations(
            top, conclusive, store, cls, topo_info, sorted(confirmed), sop_versions, ports, devs[0].vlan if devs else None
        )
        failed = [r.name for r in runs if r.status != "success"]
        no_data = [e.content for e in store.items if "ping_no_data" in e.tags]
        lim = [
            (
                "Diagnostik berbasis data infrastruktur sintetis (DEMO_MODE); tidak ada modifikasi sistem produksi yang dilakukan."
                if cfg.demo_mode
                else "Diagnostik dijalankan dalam mode read-only."
            ),
            "Semua tool MCP bersifat read-only; rekomendasi memerlukan verifikasi dan persetujuan IT Support sebelum tindakan apapun.",
            "Confidence adalah evidence confidence score berbasis bobot evidence, bukan probabilitas statistik.",
            "Incident historis dan SOP dipakai sebagai supporting evidence/referensi, bukan bukti penyebab incident saat ini.",
        ]
        if failed:
            lim.append(f"Diagnostic tool gagal dijalankan: {', '.join(sorted(set(failed)))}; evidence terkait tidak tersedia.")
        lim += [f"Evidence tidak mencukupi: {t}" for t in no_data[:3]]
        if ai_mode == "fallback":
            lim.append(
                "LLM tidak digunakan (DEMO_FALLBACK_MODE): klasifikasi berbasis aturan, scoring hipotesis dan laporan berbasis template terstruktur."
            )
        if "hashing" in self.embedder.name or sop_mode == "keyword" or hist_mode == "keyword":
            lim.append(
                f"Retrieval memakai fallback ({self.embedder.name} / {sop_mode}/{hist_mode}); kualitas pencarian semantik dapat lebih rendah dibanding model embedding penuh."
            )
        if top and top.contradicting and conclusive:
            lim.append(
                "Evidence menunjukkan kondisi yang belum sepenuhnya konsisten: "
                + "; ".join(ev.content[:110] for ev in (store.by_key(k) for k in top.contradicting[:2]) if ev)
            )
        if not conclusive:
            lim.append("Root cause belum dapat ditentukan secara memadai.")
        if scope.scope_level == "unknown":
            lim.append("Cakupan dampak tidak dapat ditentukan dari log pada jendela waktu tersebut.")
        facts = {
            "classification": cls.to_dict(),
            "top_hypothesis": top.description if top else None,
            "confidence": top.confidence if top else None,
            "conclusive": conclusive,
            "evidence": [e.content for e in store.sorted_items() if e.role == "supporting"][:6],
            "limitations": lim[:4],
        }
        narrative = llm_narrative(self.llm, facts)
        if narrative:
            ai_mode = "llm"
        incident_dict = {
            "id": str(inc.id),
            "ticket_number": inc.ticket_number,
            "title": inc.title,
            "description": inc.description,
            "affected_unit": inc.affected_unit,
            "affected_device": inc.affected_device,
            "affected_service": inc.affected_service,
            "occurred_at": T.isoformat(),
        }
        report = build_report(
            incident=incident_dict,
            cls=cls,
            status="completed",
            store=store,
            hyps=hyps,
            conclusive=conclusive,
            recs=recs,
            sop_refs=sop_refs,
            sop_decisions=sop_decisions,
            hist=hist_show,
            tool_runs=runs,
            plan=plan.to_dict(),
            corr=corr,
            topo_info=topo_info,
            scope=scope,
            limitations=lim,
            narrative=narrative,
            ai_mode=ai_mode,
            model=self.llm.model if ai_mode == "llm" else "rule-based-fallback",
            config=inv.config_snapshot or {},
        )
        report["audit"] = {
            "stored_at": utcnow().isoformat(),
            "investigation_id": str(inv.id),
            "parent_investigation_id": (str(inv.parent_investigation_id) if inv.parent_investigation_id else None),
            "request_id": inv.request_id,
            "embedding": self.embedder.name,
            "retrieval": {"sop_mode": sop_mode, "historical_mode": hist_mode},
        }
        audit.update(recommendations=recs["actions"], evidence_keys=[e.key for e in store.items], report_keys=list(report))
        for ev_item in store.sorted_items():
            s.add(
                InvestigationEvidence(
                    investigation_id=inv.id,
                    evidence_key=ev_item.key,
                    source_type=ev_item.source_type,
                    source_id=ev_item.source_id,
                    evidence_text=ev_item.content,
                    kind=ev_item.kind,
                    role=ev_item.role,
                    evidence_timestamp=ev_item.timestamp,
                    temporal_relation=ev_item.relation,
                    relevance_score=round(ev_item.relevance, 4),
                    temporal_score=ev_item.temporal,
                    confidence_contribution=ev_item.contribution,
                    priority_rank=ev_item.priority,
                    tags=ev_item.tags,
                    hypothesis_ids=ev_item.hypothesis_roles,
                    meta=ev_item.meta,
                )
            )
        inv.report, inv.audit = report, audit
        inv.summary = report["incident_summary"]
        inv.root_cause_category = top.category if conclusive and top else None
        inv.confidence_score = top.confidence if top else None
        inv.ai_mode, inv.model_used = ai_mode, report["model_used"]
        inv.status, inv.completed_at = "completed", utcnow()
        inv.duration_ms = round((time.perf_counter() - started) * 1000, 1)
        self._stage(s, inv, "recommendation", "done", f"{len(recs['actions'])} recommendations")
        self._event(
            s,
            inv,
            "investigation_completed",
            f"Investigation completed in {inv.duration_ms} ms",
            started,
            meta={"confidence": inv.confidence_score, "root_cause_category": inv.root_cause_category},
            log_name="investigation_completed",
        )
        s.commit()
