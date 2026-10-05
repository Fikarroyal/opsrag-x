from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.llm import BaseLLMProvider
from app.api.deps import get_db, get_llm_dep, get_orchestrator
from app.database.models import Incident, IncidentEvent, Investigation
from app.investigation.orchestrator import InvestigationOrchestrator
from app.schemas.common import Page
from app.schemas.incident import IncidentCreate, IncidentOut, ResolveRequest
from app.schemas.investigation import InvestigationBrief, TimelineEvent
from app.schemas.recommendation import ErrorResponse
from app.services import incident_service as svc

router = APIRouter(prefix="/api", tags=["incidents"])
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorResponse, "description": "Incident not found"}}
RUNNING = ("queued", "running", "collecting_evidence", "analyzing", "generating_report")


def _get(db: Session, incident_id: uuid.UUID) -> Incident:
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(404, "Incident not found")
    return inc


@router.get("/incidents", response_model=Page[IncidentOut], summary="List incidents", description="Paginated list with search and filters.")
def list_incidents(
    q: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    unit: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Any:
    rows, total = svc.list_incidents(
        db, q=q, status=status, severity=severity, category=category, unit=unit, page=page, page_size=page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": rows}


@router.get("/incidents/{incident_id}", response_model=IncidentOut, responses=NOT_FOUND, summary="Get incident")
def get_incident(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> Any:
    return _get(db, incident_id)


@router.post(
    "/incidents",
    response_model=IncidentOut,
    status_code=201,
    responses={422: {"model": ErrorResponse}},
    summary="Create incident",
    description="Creates an IT incident (no patient data). Triage classification (category/severity/service) is filled automatically by the LLM classifier or the rule-based fallback.",
)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db), llm: BaseLLMProvider = Depends(get_llm_dep)) -> Any:
    return svc.create_incident(db, payload, llm)


@router.post(
    "/incidents/{incident_id}/investigate",
    response_model=InvestigationBrief,
    status_code=202,
    responses={**NOT_FOUND, 409: {"model": ErrorResponse}},
    summary="Start AI investigation",
    description="Queues an investigation and runs it in the background. Poll `GET /api/investigations/{id}` for progress: queued -> running -> collecting_evidence -> analyzing -> generating_report -> completed.",
)
def investigate(
    incident_id: uuid.UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    orch: InvestigationOrchestrator = Depends(get_orchestrator),
) -> Any:
    inc = _get(db, incident_id)
    if db.scalar(select(Investigation.id).where(Investigation.incident_id == inc.id, Investigation.status.in_(RUNNING))):
        raise HTTPException(409, "An investigation for this incident is already running")
    inv = orch.create(db, inc)
    background.add_task(orch.run, inv.id)
    return inv


@router.post(
    "/incidents/{incident_id}/resolve", response_model=IncidentOut, responses=NOT_FOUND, summary="Mark incident resolved (by IT Support)"
)
def resolve(incident_id: uuid.UUID, req: ResolveRequest, db: Session = Depends(get_db)) -> Any:
    return svc.resolve_incident(db, _get(db, incident_id), req)


@router.get(
    "/incidents/{incident_id}/investigations",
    response_model=list[InvestigationBrief],
    responses=NOT_FOUND,
    summary="Investigations of an incident (newest first)",
)
def incident_investigations(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> Any:
    _get(db, incident_id)
    return list(db.scalars(select(Investigation).where(Investigation.incident_id == incident_id).order_by(Investigation.started_at.desc())))


@router.get(
    "/incidents/{incident_id}/events", response_model=list[TimelineEvent], responses=NOT_FOUND, summary="Audit events of an incident"
)
def incident_events(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> Any:
    _get(db, incident_id)
    return list(
        db.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.timestamp, IncidentEvent.created_at)
        )
    )


@router.get(
    "/scenarios",
    summary="Incident scenarios",
    description="Five synthetic, reproducible scenarios selectable from the UI; each maps to a pre-seeded incident.",
)
def demo_scenarios(db: Session = Depends(get_db)) -> Any:
    meta = {
        "S1": ("SIMRS inaccessible from Poli 3", "Switch/uplink degradation: multiple Poli 3 endpoints lose SIMRS"),
        "S2": ("DNS internal failure", "DNS failure -> application unavailable by name"),
        "S3": ("SIMRS database timeout", "Database failure -> application error"),
        "S4": ("Server overload", "Server overload -> high response time"),
        "S5": ("Farmasi network disruption", "Uplink down -> all Farmasi endpoints offline"),
    }
    rows = {i.scenario_id: i for i in db.scalars(select(Incident).where(Incident.scenario_id.is_not(None)))}
    return [
        {
            "id": sid,
            "name": name,
            "description": desc,
            "incident_id": str(rows[sid].id) if sid in rows else None,
            "ticket_number": rows[sid].ticket_number if sid in rows else None,
            "prefill": (
                {
                    "title": rows[sid].title,
                    "description": rows[sid].description,
                    "affected_unit": rows[sid].affected_unit,
                    "affected_service": rows[sid].affected_service,
                    "occurred_at": rows[sid].occurred_at.isoformat(),
                }
                if sid in rows
                else None
            ),
        }
        for sid, (name, desc) in meta.items()
    ]
