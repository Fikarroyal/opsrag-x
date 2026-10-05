from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_orchestrator
from app.database.models import Incident, IncidentEvent, Investigation, InvestigationEvidence, ToolExecution
from app.investigation.orchestrator import InvestigationOrchestrator
from app.schemas.common import Page
from app.schemas.evidence import EvidenceOut, ToolExecutionOut
from app.schemas.investigation import InvestigationBrief, InvestigationOut, TimelineEvent
from app.schemas.recommendation import ErrorResponse
from app.services.report_pdf import build_pdf

router = APIRouter(prefix="/api", tags=["investigations"])
NF: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse, "description": "Investigation not found"}}
RUNNING = ("queued", "running", "collecting_evidence", "analyzing", "generating_report")


def _inv(db: Session, inv_id: uuid.UUID) -> Investigation:
    inv = db.get(Investigation, inv_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    return inv


def _events(db: Session, inv_id: uuid.UUID) -> list[IncidentEvent]:
    return list(
        db.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.investigation_id == inv_id)
            .order_by(IncidentEvent.timestamp, IncidentEvent.created_at)
        )
    )


@router.get("/investigations", response_model=Page[InvestigationBrief], summary="List investigations")
def list_investigations(
    incident_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Any:
    conds = [
        c
        for c in (Investigation.incident_id == incident_id if incident_id else None, Investigation.status == status if status else None)
        if c is not None
    ]
    total = db.scalar(select(func.count()).select_from(Investigation).where(*conds)) or 0
    rows = list(
        db.scalars(
            select(Investigation).where(*conds).order_by(Investigation.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    return {"total": total, "page": page, "page_size": page_size, "items": rows}


@router.get(
    "/investigations/{inv_id}",
    response_model=InvestigationOut,
    responses=NF,
    summary="Investigation status and report",
    description="Poll this endpoint. `status` progresses queued -> running -> collecting_evidence -> analyzing -> generating_report -> completed|failed; `stages` has per-step state; `report` is filled when completed.",
)
def get_investigation(inv_id: uuid.UUID, db: Session = Depends(get_db)) -> Any:
    return _inv(db, inv_id)


@router.get(
    "/investigations/{inv_id}/timeline",
    responses=NF,
    summary="Investigation timeline",
    description="`events`: audit trail of pipeline stages/tool executions; `evidence_timeline`: temporally ordered infrastructure events.",
)
def timeline(inv_id: uuid.UUID, db: Session = Depends(get_db)) -> Any:
    inv = _inv(db, inv_id)
    return {
        "events": [TimelineEvent.model_validate(e) for e in _events(db, inv_id)],
        "evidence_timeline": (inv.report or {}).get("timeline", []),
    }


@router.get(
    "/investigations/{inv_id}/evidence", response_model=list[EvidenceOut], responses=NF, summary="Evidence used by the investigation"
)
def evidence(inv_id: uuid.UUID, role: str | None = None, source_type: str | None = None, db: Session = Depends(get_db)) -> Any:
    _inv(db, inv_id)
    q = select(InvestigationEvidence).where(InvestigationEvidence.investigation_id == inv_id)
    if role:
        q = q.where(InvestigationEvidence.role == role)
    if source_type:
        q = q.where(InvestigationEvidence.source_type == source_type)
    return list(db.scalars(q.order_by(InvestigationEvidence.priority_rank, InvestigationEvidence.evidence_key)))


@router.get("/investigations/{inv_id}/tools", response_model=list[ToolExecutionOut], responses=NF, summary="Read-only MCP tool executions")
def tools(inv_id: uuid.UUID, db: Session = Depends(get_db)) -> Any:
    _inv(db, inv_id)
    return list(db.scalars(select(ToolExecution).where(ToolExecution.investigation_id == inv_id).order_by(ToolExecution.created_at)))


@router.post(
    "/investigations/{inv_id}/replay",
    response_model=InvestigationBrief,
    status_code=202,
    responses={**NF, 409: {"model": ErrorResponse}},
    summary="Replay investigation",
    description="Re-runs the investigation for the same incident with the current configuration and stores it as a child of the original for comparison.",
)
def replay(
    inv_id: uuid.UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    orch: InvestigationOrchestrator = Depends(get_orchestrator),
) -> Any:
    orig = _inv(db, inv_id)
    inc = db.get(Incident, orig.incident_id)
    assert inc is not None
    if db.scalar(select(Investigation.id).where(Investigation.incident_id == inc.id, Investigation.status.in_(RUNNING))):
        raise HTTPException(409, "An investigation for this incident is already running")
    new = orch.create(db, inc, parent_id=orig.id)
    background.add_task(orch.run, new.id)
    return new


def compare_investigations(a: Investigation, b: Investigation) -> dict[str, Any]:
    ra, rb = a.report or {}, b.report or {}
    ta = ra.get("root_cause_hypotheses", [{}])[0] if ra.get("root_cause_hypotheses") else {}
    tb = rb.get("root_cause_hypotheses", [{}])[0] if rb.get("root_cause_hypotheses") else {}
    ev = lambda r: sorted(e["content"] for e in r.get("evidence", []) if e["source_type"] != "mcp_tool" or True)  # noqa: E731
    tools = lambda r: sorted((t["tool"], json.dumps(t["arguments"], sort_keys=True)) for t in r.get("tools_executed", []))  # noqa: E731
    same_conf = abs((a.confidence_score or 0) - (b.confidence_score or 0)) < 1e-9
    return {
        "a": str(a.id),
        "b": str(b.id),
        "same_top_hypothesis": ta.get("id") == tb.get("id"),
        "top_a": ta.get("id"),
        "top_b": tb.get("id"),
        "confidence_a": a.confidence_score,
        "confidence_b": b.confidence_score,
        "confidence_delta": round((b.confidence_score or 0) - (a.confidence_score or 0), 6),
        "same_tools": tools(ra) == tools(rb),
        "tools_a": len(tools(ra)),
        "tools_b": len(tools(rb)),
        "evidence_a": len(ev(ra)),
        "evidence_b": len(ev(rb)),
        "same_evidence_content": ev(ra) == ev(rb),
        "same_config": (a.config_snapshot == b.config_snapshot),
        "model_a": a.model_used,
        "model_b": b.model_used,
        "duration_ms_a": a.duration_ms,
        "duration_ms_b": b.duration_ms,
        "reproducible": ta.get("id") == tb.get("id") and same_conf and ev(ra) == ev(rb),
    }


@router.get("/investigations/{inv_id}/compare/{other_id}", responses=NF, summary="Compare two investigations (replay reproducibility)")
def compare(inv_id: uuid.UUID, other_id: uuid.UUID, db: Session = Depends(get_db)) -> Any:
    return compare_investigations(_inv(db, inv_id), _inv(db, other_id))


def _export_payload(db: Session, inv: Investigation) -> dict[str, Any]:
    inc = db.get(Incident, inv.incident_id)
    return {
        "export_version": 1,
        "investigation": {
            "id": str(inv.id),
            "incident_id": str(inv.incident_id),
            "status": inv.status,
            "started_at": inv.started_at.isoformat(),
            "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
            "confidence_score": inv.confidence_score,
            "root_cause_category": inv.root_cause_category,
            "model_used": inv.model_used,
            "ai_mode": inv.ai_mode,
            "parent_investigation_id": (str(inv.parent_investigation_id) if inv.parent_investigation_id else None),
        },
        "incident": {"ticket_number": inc.ticket_number if inc else None},
        "report": inv.report,
        "audit": inv.audit,
        "config_snapshot": inv.config_snapshot,
        "input_snapshot": inv.input_snapshot,
        "events": [
            {
                "timestamp": e.timestamp.isoformat(),
                "type": e.event_type,
                "message": e.message,
                "status": e.status,
                "duration_ms": e.duration_ms,
            }
            for e in _events(db, inv.id)
        ],
    }


@router.get(
    "/investigations/{inv_id}/export/json",
    responses=NF,
    summary="Export report as JSON",
    description="Full structured report + audit trail + events as a downloadable JSON file.",
)
def export_json(inv_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    inv = _inv(db, inv_id)
    if inv.status != "completed" or not inv.report:
        raise HTTPException(409, "Investigation is not completed yet")
    body = json.dumps(_export_payload(db, inv), indent=2, ensure_ascii=False, default=str)
    return Response(
        body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="investigation-{inv.report["incident"]["ticket_number"]}-{str(inv.id)[:8]}.json"'
        },
    )


@router.get("/investigations/{inv_id}/export/pdf", responses=NF, summary="Export report as PDF")
def export_pdf(inv_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    inv = _inv(db, inv_id)
    if inv.status != "completed" or not inv.report:
        raise HTTPException(409, "Investigation is not completed yet")
    payload = _export_payload(db, inv)
    pdf = build_pdf(inv.report, {"ticket_number": inv.report["incident"]["ticket_number"]}, payload["events"])
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="investigation-{inv.report["incident"]["ticket_number"]}-{str(inv.id)[:8]}.pdf"'
        },
    )


@router.get("/analytics/investigations", summary="Aggregate statistics over stored investigations")
def investigation_analytics(db: Session = Depends(get_db)) -> Any:
    rows = list(db.scalars(select(Investigation).where(Investigation.status == "completed")))
    by_rc: dict[str, int] = {}
    for r in rows:
        by_rc[r.root_cause_category or "inconclusive"] = by_rc.get(r.root_cause_category or "inconclusive", 0) + 1
    durs = [r.duration_ms for r in rows if r.duration_ms]
    confs = [r.confidence_score for r in rows if r.confidence_score is not None]
    cov = []
    for r in rows:
        ev = (r.report or {}).get("evidence", [])
        cov.append(
            len(
                [
                    e
                    for e in ev
                    if e["source_type"] in ("mcp_tool", "network_log", "server_log", "log_correlation") and e["kind"] != "UNKNOWN"
                ]
            )
            / max(1, len(ev))
        )
    return {
        "total": db.scalar(select(func.count()).select_from(Investigation)) or 0,
        "completed": len(rows),
        "failed": db.scalar(select(func.count()).select_from(Investigation).where(Investigation.status == "failed")) or 0,
        "avg_duration_ms": round(sum(durs) / len(durs), 1) if durs else None,
        "avg_confidence": round(sum(confs) / len(confs), 3) if confs else None,
        "direct_evidence_share": round(sum(cov) / len(cov), 3) if cov else None,
        "root_cause_distribution": [{"name": k, "value": v} for k, v in sorted(by_rc.items(), key=lambda kv: -kv[1])],
        "recent": [
            {
                "id": str(r.id),
                "incident_id": str(r.incident_id),
                "confidence": r.confidence_score,
                "root_cause_category": r.root_cause_category,
                "duration_ms": r.duration_ms,
                "ai_mode": r.ai_mode,
                "started_at": r.started_at.isoformat(),
            }
            for r in sorted(rows, key=lambda r: r.started_at, reverse=True)[:15]
        ],
    }
