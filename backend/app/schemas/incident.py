from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncidentCreate(BaseModel):
    title: str = Field(min_length=5, max_length=255, description="Short incident title")
    description: str = Field(min_length=10, max_length=4000, description="Incident description (IT infrastructure only, no patient data)")
    reported_by: str | None = Field(default=None, max_length=120)
    affected_unit: str | None = Field(default=None, max_length=60)
    affected_device: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9\-\.]+$")
    affected_service: str | None = Field(default=None, max_length=60)
    occurred_at: datetime | None = Field(default=None, description="When the disruption started (naive local hospital time)")

    @field_validator("occurred_at")
    @classmethod
    def _naive(cls, v: datetime | None) -> datetime | None:
        return v.replace(tzinfo=None) if v else v


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_number: str
    title: str
    description: str
    reporter_name: str | None
    affected_unit: str | None
    affected_device: str | None
    affected_service: str | None
    severity: str | None
    category: str | None
    status: str
    occurred_at: datetime
    created_at: datetime
    resolved_at: datetime | None
    scenario_id: str | None


class ResolveRequest(BaseModel):
    resolution: str = Field(min_length=5, max_length=2000)
    root_cause: str | None = Field(default=None, max_length=1000)
    root_cause_category: str | None = Field(default=None, max_length=30)
