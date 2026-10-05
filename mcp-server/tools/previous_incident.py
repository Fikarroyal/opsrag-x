from __future__ import annotations

import re

from pydantic import BaseModel, Field

from tools import datastore
from tools.common import ToolInput, register

TOKEN = re.compile(r"[a-z0-9\-\.]+")


class Input(ToolInput):
    query: str = Field(min_length=3, max_length=300)
    category: str | None = Field(default=None, max_length=30)
    unit: str | None = Field(default=None, max_length=60)
    limit: int = Field(default=5, ge=1, le=20)


class Output(BaseModel):
    total_candidates: int
    incidents: list[dict]


def _tok(s: str) -> set[str]:
    return set(TOKEN.findall(s.lower()))


@register(
    "search_previous_incident", "Read-only keyword-overlap search over historical incidents (only those before as_of).", Input, Output
)
def search_previous_incident(inp: Input) -> Output:
    before = inp.as_of_dt() if inp.as_of else None
    q = _tok(inp.query)
    scored = []
    for r in datastore.historical():
        if before and r["_ts"] >= before:
            continue
        if inp.category and r["category"] != inp.category and r["root_cause_category"] != inp.category:
            continue
        if inp.unit and r["unit"].lower() not in (inp.unit.lower(), "semua unit"):
            continue
        t = _tok(f"{r['description']} {r['unit']} {r['affected_service']}")
        sim = len(q & t) / len(q | t) if q and t else 0.0
        if sim > 0:
            scored.append((sim, r))
    scored.sort(key=lambda x: (x[0], x[1]["timestamp"]), reverse=True)
    return Output(
        total_candidates=len(scored),
        incidents=[
            {
                "incident_id": r["incident_id"],
                "timestamp": r["timestamp"],
                "unit": r["unit"],
                "description": r["description"],
                "category": r["category"],
                "root_cause": r["root_cause"],
                "root_cause_category": r["root_cause_category"],
                "resolution": r["resolution"],
                "resolution_time_minutes": int(r["resolution_time_minutes"]),
                "similarity": round(sim, 3),
            }
            for sim, r in scored[: inp.limit]
        ],
    )
