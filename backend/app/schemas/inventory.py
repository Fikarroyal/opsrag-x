from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    hostname: str
    ip_address: str
    mac_address: str | None
    unit: str
    vlan: int | None
    device_type: str
    operating_system: str | None
    status: str
    switch_port: str | None
    switch: str | None = None
    last_seen: datetime | None


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    timestamp: datetime
    source: str
    hostname: str
    ip_address: str | None
    destination: str | None
    service: str | None
    log_level: str
    event_type: str
    message: str
    latency_ms: float | None
    packet_loss: float | None


class HistoricalOut(BaseModel):
    incident_key: str
    timestamp: datetime
    unit: str | None
    device: str | None
    description: str
    category: str
    severity: str
    affected_service: str | None
    root_cause: str
    root_cause_category: str
    resolution: str | None
    resolution_time_minutes: int | None
    pattern: str | None = None
    similarity: float | None = None
    used_in_investigation: bool = False


class ServerOut(BaseModel):
    hostname: str
    ip_address: str
    role: str
    status: str
    operating_system: str | None
    cpu: float | None
    memory: float | None
    sample_timestamp: datetime | None
    services: list[dict[str, Any]]
    recent_errors: int
