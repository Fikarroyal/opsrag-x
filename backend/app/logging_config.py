"""Structured JSON logging with request/incident/investigation correlation ids."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc  # datetime.UTC only exists on Python 3.11+

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
FIELDS = ("event", "incident_id", "investigation_id", "duration", "status")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or request_id_var.get(),
            "message": record.getMessage(),
        }
        for f in FIELDS:
            if hasattr(record, f):
                payload[f] = getattr(record, f)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True  # replaced by request middleware logging
    logging.getLogger("httpx").setLevel(logging.WARNING)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    incident_id: Any = None,
    investigation_id: Any = None,
    started: float | None = None,
    status: str = "ok",
    level: int = logging.INFO,
    **extra: Any,
) -> None:
    """Emit an observability event: timestamp, request_id, incident_id, investigation_id, event, duration, status."""
    duration = round((time.perf_counter() - started) * 1000, 2) if started is not None else None
    logger.log(
        level,
        event,
        extra={
            "event": event,
            "incident_id": str(incident_id) if incident_id else None,
            "investigation_id": str(investigation_id) if investigation_id else None,
            "duration": duration,
            "status": status,
            **extra,
        },
    )
