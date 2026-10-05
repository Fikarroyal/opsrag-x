from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database.models import HistoricalIncident, SopDocument


def list_sops(session: Session, q: str | None = None, category: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    docs = list(
        session.scalars(
            select(SopDocument)
            .options(selectinload(SopDocument.versions))
            .where(SopDocument.doc_type == "sop")
            .order_by(SopDocument.doc_code)
        )
    )
    rel = dict(
        session.execute(select(HistoricalIncident.root_cause_category, func.count()).group_by(HistoricalIncident.root_cause_category)).all()
    )
    out: list[dict[str, Any]] = []
    for d in docs:
        if category and d.category != category:
            continue
        if q and q.lower() not in f"{d.doc_code} {d.title}".lower() and not any(q.lower() in str(v.sections).lower() for v in d.versions):
            continue
        versions = [
            {"version": v.version, "effective_date": v.effective_date.isoformat(), "status": v.status, "sections": v.sections}
            for v in sorted(d.versions, key=lambda x: x.effective_date, reverse=True)
        ]
        if status and not any(v["status"] == status for v in versions):
            continue
        active = next((v for v in versions if v["status"] == "active"), versions[0] if versions else None)
        out.append(
            {
                "sop_code": d.doc_code,
                "title": d.title,
                "category": d.category,
                "active_version": active["version"] if active else None,
                "effective_date": active["effective_date"] if active else None,
                "status": active["status"] if active else None,
                "relevant_incidents": int(rel.get(d.category or "", 0)),
                "versions": versions,
            }
        )
    return out
