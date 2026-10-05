"""SQLAlchemy 2 models. UUID primary keys, created_at/updated_at, pgvector embeddings.

Portable types: JSONB and pgvector on PostgreSQL, JSON on SQLite (SQLite is only used by the unit tests).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings

UTC = timezone.utc  # datetime.UTC only exists on Python 3.11+

JSONType = JSON().with_variant(JSONB(), "postgresql")
EmbeddingType = Vector(get_settings().embedding_dim).with_variant(JSON(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), default="it_support")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # null = record only, cannot sign in


class Server(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "servers"
    hostname: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    ip_address: Mapped[str] = mapped_column(String(45))
    role: Mapped[str] = mapped_column(String(40))
    environment: Mapped[str] = mapped_column(String(40), default="production")
    status: Mapped[str] = mapped_column(String(20), default="online")
    operating_system: Mapped[str | None] = mapped_column(String(80))
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class Device(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "devices"
    hostname: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    ip_address: Mapped[str] = mapped_column(String(45))
    mac_address: Mapped[str | None] = mapped_column(String(17))
    unit: Mapped[str] = mapped_column(String(60), index=True)
    vlan: Mapped[int | None] = mapped_column(Integer)
    device_type: Mapped[str] = mapped_column(String(30), index=True)
    operating_system: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="online")
    server_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("servers.id"))
    switch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"))
    switch_port: Mapped[str | None] = mapped_column(String(20))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class Service(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "services"
    name: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    server_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("servers.id"))
    port: Mapped[int | None] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(10), default="tcp")
    status: Mapped[str] = mapped_column(String(20), default="running")
    health_endpoint: Mapped[str | None] = mapped_column(String(255))
    response_time_ms: Mapped[float | None] = mapped_column(Float)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime)


class Incident(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incidents"
    ticket_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    reported_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reporter_name: Mapped[str | None] = mapped_column(String(120))
    affected_unit: Mapped[str | None] = mapped_column(String(60), index=True)
    affected_device: Mapped[str | None] = mapped_column(String(80))
    affected_service: Mapped[str | None] = mapped_column(String(60))
    severity: Mapped[str | None] = mapped_column(String(20), index=True)
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    scenario_id: Mapped[str | None] = mapped_column(String(10))
    investigations: Mapped[list[Investigation]] = relationship(back_populates="incident", order_by="Investigation.started_at.desc()")


class IncidentEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "incident_events"
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("investigations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    duration_ms: Mapped[float | None] = mapped_column(Float)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class Log(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "logs"
    __table_args__ = (Index("ix_logs_hostname_ts", "hostname", "timestamp"), Index("ix_logs_source_ts", "source", "timestamp"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(20))  # server | network
    hostname: Mapped[str] = mapped_column(String(80), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    destination: Mapped[str | None] = mapped_column(String(80))
    service: Mapped[str | None] = mapped_column(String(60), index=True)
    log_level: Mapped[str] = mapped_column(String(10), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    packet_loss: Mapped[float | None] = mapped_column(Float)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class SopDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sop_documents"
    doc_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str] = mapped_column(String(20), default="sop")  # sop | infra_doc
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    source_path: Mapped[str | None] = mapped_column(String(255))
    versions: Mapped[list[SopVersion]] = relationship(back_populates="document", order_by="SopVersion.effective_date")


class SopVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sop_versions"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sop_documents.id"), index=True)
    sop_code: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[str] = mapped_column(String(20))
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20))  # active | superseded | scheduled
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    sections: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    document: Mapped[SopDocument] = relationship(back_populates="versions")
    chunks: Mapped[list[SopChunk]] = relationship(back_populates="version")


class SopChunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sop_chunks"
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sop_versions.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sop_documents.id"), index=True)
    sop_code: Mapped[str] = mapped_column(String(40), index=True)
    section: Mapped[str] = mapped_column(String(40))
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(EmbeddingType, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    version: Mapped[SopVersion] = relationship(back_populates="chunks")


class HistoricalIncident(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "historical_incidents"
    incident_key: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    unit: Mapped[str | None] = mapped_column(String(60), index=True)
    device: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    affected_service: Mapped[str | None] = mapped_column(String(60))
    root_cause: Mapped[str] = mapped_column(Text)
    root_cause_category: Mapped[str] = mapped_column(String(30), index=True)
    pattern: Mapped[str | None] = mapped_column(String(40))
    embedding: Mapped[Any] = mapped_column(EmbeddingType, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    resolution: Mapped[Resolution | None] = relationship(back_populates="historical_incident", uselist=False)


class Resolution(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "resolutions"
    incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    historical_incident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("historical_incidents.id"), index=True)
    root_cause: Mapped[str | None] = mapped_column(Text)
    root_cause_category: Mapped[str | None] = mapped_column(String(30))
    resolution: Mapped[str] = mapped_column(Text)
    resolution_time_minutes: Mapped[int | None] = mapped_column(Integer)
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    historical_incident: Mapped[HistoricalIncident | None] = relationship(back_populates="resolution")


class Investigation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "investigations"
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    parent_investigation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("investigations.id"))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    root_cause_category: Mapped[str | None] = mapped_column(String(30), index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    stages: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    audit: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    model_used: Mapped[str | None] = mapped_column(String(120))
    ai_mode: Mapped[str | None] = mapped_column(String(30))  # llm | fallback
    error_message: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    incident: Mapped[Incident] = relationship(back_populates="investigations")
    evidence_items: Mapped[list[InvestigationEvidence]] = relationship(
        back_populates="investigation", order_by="InvestigationEvidence.priority_rank"
    )
    tool_executions: Mapped[list[ToolExecution]] = relationship(back_populates="investigation", order_by="ToolExecution.created_at")


class InvestigationEvidence(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "investigation_evidence"
    investigation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investigations.id"), index=True)
    evidence_key: Mapped[str] = mapped_column(String(12))
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[str | None] = mapped_column(String(255))
    evidence_text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="FACT")  # FACT | INFERENCE | UNKNOWN
    role: Mapped[str] = mapped_column(String(20), default="context")  # supporting | contradicting | context
    evidence_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    temporal_relation: Mapped[str | None] = mapped_column(String(20))
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    temporal_score: Mapped[float | None] = mapped_column(Float)
    confidence_contribution: Mapped[float | None] = mapped_column(Float)
    priority_rank: Mapped[int] = mapped_column(Integer, default=9)
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    hypothesis_ids: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    investigation: Mapped[Investigation] = relationship(back_populates="evidence_items")


class ToolExecution(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tool_executions"
    investigation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investigations.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(60), index=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    execution_time: Mapped[float | None] = mapped_column(Float)  # milliseconds
    status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str | None] = mapped_column(Text)
    investigation: Mapped[Investigation] = relationship(back_populates="tool_executions")
