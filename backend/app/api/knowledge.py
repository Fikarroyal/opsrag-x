from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.database.models import HistoricalIncident, Investigation, Log
from app.schemas.common import Page
from app.schemas.inventory import HistoricalOut, LogOut
from app.services import log_service, sop_service

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get(
    "/logs",
    response_model=Page[LogOut],
    summary="Search logs",
    description="Indexed, paginated server/network log search. Never loads the whole table.",
)
def logs(
    q: str | None = None,
    hostname: str | None = None,
    service: str | None = None,
    level: str | None = None,
    event_type: str | None = None,
    source: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Any:
    rows, total = log_service.search(
        db,
        q=q,
        hostname=hostname,
        service=service,
        level=level,
        event_type=event_type,
        source=source,
        start=start.replace(tzinfo=None) if start else None,
        end=end.replace(tzinfo=None) if end else None,
        page=page,
        page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": rows}


@router.get("/logs/filters", summary="Distinct values for log filters")
def log_filters(db: Session = Depends(get_db)) -> Any:
    return log_service.distinct_values(db)


@router.get(
    "/logs/correlated",
    summary="AI-correlated events of an investigation",
    description="Temporally correlated anomaly events and detected patterns produced by the investigation.",
)
def correlated(investigation_id: uuid.UUID, db: Session = Depends(get_db)) -> Any:
    inv = db.get(Investigation, investigation_id)
    if inv is None or not inv.report:
        raise HTTPException(404, "Investigation report not found")
    r = inv.report
    return {
        "incident_time": r["incident"]["occurred_at"],
        "patterns": r["correlation"]["patterns"],
        "events": [t for t in r["timeline"] if t.get("domain") not in (None, "diagnostic")],
    }


@router.get(
    "/sops",
    summary="SOP library",
    description="SOPs with all versions, effective dates and status; filter by text, category or version status.",
)
def sops(q: str | None = None, category: str | None = None, status: str | None = None, db: Session = Depends(get_db)) -> Any:
    return sop_service.list_sops(db, q, category, status)


@router.get("/sops/{code}", summary="SOP detail")
def sop_detail(code: str, db: Session = Depends(get_db)) -> Any:
    found = [s for s in sop_service.list_sops(db) if s["sop_code"].lower() == code.lower()]
    if not found:
        raise HTTPException(404, "SOP not found")
    return found[0]


@router.get(
    "/historical-incidents",
    response_model=Page[HistoricalOut],
    summary="Historical incidents",
    description="Resolved synthetic incidents. With `investigation_id`, similarity and usage flags of that investigation are attached.",
)
def historical(
    q: str | None = None,
    category: str | None = None,
    unit: str | None = None,
    root_cause_category: str | None = None,
    investigation_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Any:
    used: dict[str, float] = {}
    if investigation_id:
        inv = db.get(Investigation, investigation_id)
        if inv and inv.report:
            used = {h["incident_key"]: h.get("similarity") for h in inv.report.get("historical_incidents", [])}
    conds: list[Any] = []
    if q:
        conds.append(or_(HistoricalIncident.description.ilike(f"%{q}%"), HistoricalIncident.root_cause.ilike(f"%{q}%")))
    for col, v in (
        (HistoricalIncident.category, category),
        (HistoricalIncident.unit, unit),
        (HistoricalIncident.root_cause_category, root_cause_category),
    ):
        if v:
            conds.append(col == v)
    if investigation_id and used:
        conds.append(HistoricalIncident.incident_key.in_(list(used)))
    total = db.scalar(select(func.count()).select_from(HistoricalIncident).where(*conds)) or 0
    rows = list(
        db.scalars(
            select(HistoricalIncident)
            .where(*conds)
            .order_by(HistoricalIncident.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    items = [
        HistoricalOut(
            incident_key=r.incident_key,
            timestamp=r.timestamp,
            unit=r.unit,
            device=r.device,
            description=r.description,
            category=r.category,
            severity=r.severity,
            affected_service=r.affected_service,
            root_cause=r.root_cause,
            root_cause_category=r.root_cause_category,
            resolution=r.resolution.resolution if r.resolution else None,
            resolution_time_minutes=(r.resolution.resolution_time_minutes if r.resolution else None),
            pattern=r.pattern,
            similarity=used.get(r.incident_key),
            used_in_investigation=r.incident_key in used,
        )
        for r in rows
    ]
    if used:
        items.sort(key=lambda x: -(x.similarity or 0))
    return {"total": total, "page": page, "page_size": page_size, "items": items}


_ = Log
