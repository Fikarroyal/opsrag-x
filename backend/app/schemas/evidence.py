from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    evidence_key: str
    source_type: str
    source_id: str | None
    evidence_text: str
    kind: str
    role: str
    evidence_timestamp: datetime | None
    temporal_relation: str | None
    relevance_score: float
    temporal_score: float | None
    confidence_contribution: float | None
    priority_rank: int
    tags: list[str]
    hypothesis_ids: dict[str, Any]


class ToolExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tool_name: str
    purpose: str | None
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    execution_time: float | None
    status: str
    error_message: str | None
    created_at: datetime
