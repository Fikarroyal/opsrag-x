"""Evidence model + store.

Every evidence item carries: source_type, source_id, timestamp, content, relevance_score, temporal_score,
temporal relation (before/during/after/unrelated), a kind label (FACT / INFERENCE / UNKNOWN) and semantic
`tags` that the hypothesis engine uses to decide support/contradiction. The store also holds source priority.

Source priority (lower rank = stronger):
  1 MCP tool result, 2 infrastructure logs, 3 service status, 4 topology, 5 device inventory,
  6 recent historical incidents, 7 SOP, 8 older historical incidents / unverified user report, 9 generic LLM knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.investigation.temporal import UNRELATED, temporal_relation, temporal_score

PRIORITY = {
    "mcp_tool": 1,
    "network_log": 2,
    "server_log": 2,
    "log_correlation": 2,
    "service_status": 3,
    "topology": 4,
    "device_inventory": 5,
    "historical_recent": 6,
    "sop": 7,
    "historical_old": 8,
    "incident_report": 8,
    "llm_knowledge": 9,
}
RELIABILITY = {
    "mcp_tool": 1.0,
    "network_log": 0.90,
    "server_log": 0.90,
    "log_correlation": 0.85,
    "service_status": 0.90,
    "topology": 0.85,
    "device_inventory": 0.80,
    "historical_recent": 0.70,
    "sop": 0.65,
    "historical_old": 0.50,
    "incident_report": 0.50,
    "llm_knowledge": 0.20,
}


@dataclass
class Evidence:
    source_type: str
    content: str
    source_id: str | None = None
    kind: str = "FACT"
    timestamp: datetime | None = None
    tags: list[str] = field(default_factory=list)
    relevance: float = 0.5
    meta: dict[str, Any] = field(default_factory=dict)
    key: str = ""
    temporal: float | None = None
    relation: str | None = None
    role: str = "context"
    contribution: float | None = None
    hypothesis_roles: dict[str, str] = field(default_factory=dict)

    @property
    def reliability(self) -> float:
        return RELIABILITY.get(self.source_type, 0.5)

    @property
    def priority(self) -> int:
        return PRIORITY.get(self.source_type, 9)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "content": self.content,
            "kind": self.kind,
            "relevance_score": round(self.relevance, 3),
            "temporal_score": (None if self.temporal is None else round(self.temporal, 3)),
            "temporal_relation": self.relation,
            "role": self.role,
            "confidence_contribution": (None if self.contribution is None else round(self.contribution, 3)),
            "priority_rank": self.priority,
            "reliability": self.reliability,
            "tags": self.tags,
            "hypothesis_roles": self.hypothesis_roles,
        }


class EvidenceStore:
    def __init__(self, incident_time: datetime, half_life_minutes: float = 10.0) -> None:
        self.incident_time = incident_time
        self.half_life_s = half_life_minutes * 60.0
        self.items: list[Evidence] = []

    def add(
        self,
        source_type: str,
        content: str,
        *,
        source_id: str | None = None,
        kind: str = "FACT",
        timestamp: datetime | None = None,
        tags: list[str] | None = None,
        relevance: float = 0.5,
        **meta: Any,
    ) -> Evidence:
        ev = Evidence(
            source_type=source_type,
            content=content,
            source_id=(source_id[:250] if source_id else None),
            kind=kind,
            timestamp=timestamp,
            tags=tags or [],
            relevance=relevance,
            meta=meta,
        )
        ev.key = f"E{len(self.items) + 1:02d}"
        if timestamp is not None:
            ev.temporal = temporal_score((timestamp - self.incident_time).total_seconds(), self.half_life_s)
            ev.relation = temporal_relation(timestamp, self.incident_time)
            if ev.relation == UNRELATED:
                ev.relevance *= 0.3
        self.items.append(ev)
        return ev

    def tags(self) -> set[str]:
        return {t for e in self.items for t in e.tags}

    def with_tag(self, *tags: str) -> list[Evidence]:
        want = set(tags)
        return [e for e in self.items if want & set(e.tags)]

    def by_key(self, key: str) -> Evidence | None:
        return next((e for e in self.items if e.key == key), None)

    def sorted_items(self) -> list[Evidence]:
        return sorted(self.items, key=lambda e: (e.priority, -e.relevance, e.key))
