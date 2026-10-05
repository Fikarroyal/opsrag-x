"""Incident management: creation (with triage classification), listing, resolution, events, dashboard statistics."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.classifier import classify
from app.ai.llm import BaseLLMProvider
from app.config import get_settings
from app.database.models import HistoricalIncident, Incident, IncidentEvent, Investigation, Resolution, User, utcnow
from app.schemas.incident import IncidentCreate, ResolveRequest


def next_ticket_number(session: Session, when: datetime) -> str:
    prefix = f"INC-{when.year}-"
    last = session.scalar(
        select(Incident.ticket_number).where(Incident.ticket_number.like(f"{prefix}%")).order_by(Incident.ticket_number.desc()).limit(1)
    )
    n = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{n:03d}"


def create_incident(session: Session, data: IncidentCreate, llm: BaseLLMProvider | None = None) -> Incident:
    text = f"{data.title}. {data.description}"
    cls = classify(text, llm, unit_hint=data.affected_unit, device_hint=data.affected_device, service_hint=data.affected_service)
    occurred = data.occurred_at
    if occurred is None:
        now = utcnow()
        occurred = now
        if cls.hinted_time:  # "sekitar pukul 09:42" -> same day as creation
            h, m = cls.hinted_time.split(":")
            occurred = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    reporter = session.scalar(select(User).where(User.role == "helpdesk"))
    inc = Incident(
        ticket_number=next_ticket_number(session, occurred),
        title=data.title.strip(),
        description=data.description.strip(),
        reported_by=reporter.id if reporter else None,
        reporter_name=data.reported_by,
        affected_unit=data.affected_unit or cls.unit,
        affected_device=data.affected_device or cls.device,
        affected_service=data.affected_service or cls.affected_service,
        severity=cls.severity,
        category=cls.category,
        status="open",
        occurred_at=occurred,
    )
    session.add(inc)
    session.flush()
    add_event(
        session,
        inc.id,
        None,
        "incident_created",
        f"Incident {inc.ticket_number} created; triage: {cls.category}/{cls.severity}/{cls.affected_scope} ({cls.method})",
        meta={"classification": cls.to_dict()},
    )
    session.commit()
    return inc


def add_event(
    session: Session,
    incident_id: Any,
    investigation_id: Any,
    event_type: str,
    message: str,
    *,
    status: str = "ok",
    duration_ms: float | None = None,
    meta: dict[str, Any] | None = None,
) -> IncidentEvent:
    ev = IncidentEvent(
        incident_id=incident_id,
        investigation_id=investigation_id,
        event_type=event_type,
        message=message,
        timestamp=utcnow(),
        status=status,
        duration_ms=duration_ms,
        meta=meta or {},
    )
    session.add(ev)
    return ev


def list_incidents(
    session: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    unit: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Incident], int]:
    conds = [Incident.status != "benchmark"]
    if q:
        like = f"%{q}%"
        conds.append(or_(Incident.ticket_number.ilike(like), Incident.title.ilike(like), Incident.description.ilike(like)))
    for col, val in (
        (Incident.status, status),
        (Incident.severity, severity),
        (Incident.category, category),
        (Incident.affected_unit, unit),
    ):
        if val:
            conds.append(col == val)
    total = session.scalar(select(func.count()).select_from(Incident).where(*conds)) or 0
    rows = list(
        session.scalars(
            select(Incident).where(*conds).order_by(Incident.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    return rows, total


def resolve_incident(session: Session, inc: Incident, req: ResolveRequest) -> Incident:
    now = utcnow()
    inc.status, inc.resolved_at = "resolved", now
    minutes = max(1, int((now - inc.occurred_at).total_seconds() // 60)) if now > inc.occurred_at else 1
    session.add(
        Resolution(
            incident_id=inc.id,
            root_cause=req.root_cause,
            root_cause_category=req.root_cause_category,
            resolution=req.resolution,
            resolution_time_minutes=minutes,
            resolved_by="it_support",
        )
    )
    add_event(
        session,
        inc.id,
        None,
        "incident_resolved",
        f"Incident {inc.ticket_number} marked resolved by IT Support",
        meta={"resolution": req.resolution},
    )
    session.commit()
    return inc


@lru_cache
def _service_availability(path: str) -> list[dict[str, Any]]:
    tot: Counter[str] = Counter()
    up: Counter[str] = Counter()
    with Path(path).open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            tot[r["service"]] += 1
            up[r["service"]] += 1 if r["status"] == "running" else 0
    return [{"service": s, "availability": round(100 * up[s] / tot[s], 2), "checks": tot[s]} for s in sorted(tot)]


def dashboard_stats(session: Session) -> dict[str, Any]:
    def count(*conds: Any) -> int:
        return session.scalar(select(func.count()).select_from(Incident).where(Incident.status != "benchmark", *conds)) or 0

    hist = list(session.scalars(select(HistoricalIncident)))
    cur = list(session.scalars(select(Incident).where(Incident.status != "benchmark")))
    res_minutes = [m for m in session.scalars(select(Resolution.resolution_time_minutes)) if m]
    by_cat: Counter[str] = Counter([h.category for h in hist] + [i.category or "unknown" for i in cur])
    by_sev: Counter[str] = Counter([h.severity for h in hist] + [i.severity or "unknown" for i in cur])
    rc: Counter[str] = Counter(h.root_cause_category for h in hist)
    for inv_rc in session.scalars(select(Investigation.root_cause_category).where(Investigation.root_cause_category.is_not(None))):
        if inv_rc:
            rc[inv_rc] += 1
    trend: dict[str, int] = defaultdict(int)
    for d in [h.timestamp for h in hist] + [i.occurred_at for i in cur]:
        trend[d.strftime("%Y-%m")] += 1
    rtt: dict[str, list[int]] = defaultdict(list)
    for h in hist:
        if h.resolution and h.resolution.resolution_time_minutes:
            rtt[h.timestamp.strftime("%Y-%m")].append(h.resolution.resolution_time_minutes)
    recent = list(session.scalars(select(Incident).where(Incident.status != "benchmark").order_by(Incident.occurred_at.desc()).limit(6)))
    return {
        "total_incidents": len(cur),
        "open_incidents": count(Incident.status.in_(["open", "investigating"])),
        "critical_incidents": count(Incident.severity == "critical"),
        "investigations_running": session.scalar(
            select(func.count())
            .select_from(Investigation)
            .where(Investigation.status.in_(["queued", "running", "collecting_evidence", "analyzing", "generating_report"]))
        )
        or 0,
        "resolved_incidents": count(Incident.status.in_(["resolved", "closed"])),
        "historical_incidents": len(hist),
        "average_resolution_minutes": (round(sum(res_minutes) / len(res_minutes), 1) if res_minutes else None),
        "incident_by_category": [{"name": k, "value": v} for k, v in by_cat.most_common()],
        "incident_by_severity": [{"name": k, "value": by_sev.get(k, 0)} for k in ("low", "medium", "high", "critical")],
        "incident_trend": [{"period": k, "incidents": v} for k, v in sorted(trend.items())],
        "root_cause_distribution": [{"name": k, "value": v} for k, v in rc.most_common()],
        "resolution_time_trend": [{"period": k, "avg_minutes": round(sum(v) / len(v), 1)} for k, v in sorted(rtt.items())],
        "service_availability": _service_availability(str(get_settings().raw_dir / "service_status.csv")),
        "recent_incidents": [
            {
                "id": str(i.id),
                "ticket_number": i.ticket_number,
                "title": i.title,
                "severity": i.severity,
                "status": i.status,
                "occurred_at": i.occurred_at.isoformat(),
            }
            for i in recent
        ],
    }
