from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class InvestigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    incident_id: uuid.UUID
    parent_investigation_id: uuid.UUID | None
    status: str
    summary: str | None
    root_cause_category: str | None
    confidence_score: float | None
    stages: dict[str, Any]
    report: dict[str, Any] | None
    model_used: str | None
    ai_mode: str | None
    error_message: str | None
    duration_ms: float | None
    started_at: datetime
    completed_at: datetime | None


class InvestigationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    incident_id: uuid.UUID
    status: str
    root_cause_category: str | None
    confidence_score: float | None
    ai_mode: str | None
    duration_ms: float | None
    started_at: datetime
    completed_at: datetime | None


class TimelineEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    message: str
    timestamp: datetime
    status: str
    duration_ms: float | None
    meta: dict[str, Any]
