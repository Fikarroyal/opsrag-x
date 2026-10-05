"""Log access (indexed, paginated, windowed) and validated ingestion of CSV/JSON logs."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.database.models import Log, utcnow
from app.investigation.correlation import LogRecord

logger = logging.getLogger(__name__)
LEVELS = {"DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL"}
SERVER_COLS = ["timestamp", "hostname", "service", "level", "event_type", "message"]
NETWORK_COLS = [
    "timestamp",
    "source_device",
    "destination",
    "protocol",
    "port",
    "latency_ms",
    "packet_loss",
    "status",
    "event_type",
    "message",
]
CHUNK = 2000


def to_record(row: Log) -> LogRecord:
    return LogRecord(
        timestamp=row.timestamp,
        source=row.source,
        hostname=row.hostname,
        event_type=row.event_type,
        level=row.log_level,
        message=row.message,
        ip_address=row.ip_address,
        destination=row.destination,
        service=row.service,
        latency_ms=row.latency_ms,
        packet_loss=row.packet_loss,
        meta=row.meta or {},
    )


def window_records(session: Session, start: datetime, end: datetime, limit: int = 30000) -> list[LogRecord]:
    """Rows inside [start, end] using the timestamp index; bounded by `limit` (never loads the whole table)."""
    stmt = select(Log).where(Log.timestamp >= start, Log.timestamp <= end).order_by(Log.timestamp).limit(limit)
    return [to_record(r) for r in session.scalars(stmt)]


def search(
    session: Session,
    *,
    q: str | None = None,
    hostname: str | None = None,
    service: str | None = None,
    level: str | None = None,
    event_type: str | None = None,
    source: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Log], int]:
    conds: list[Any] = []
    if q:
        conds.append(Log.message.ilike(f"%{q}%"))
    if hostname:
        conds.append(Log.hostname == hostname)
    if service:
        conds.append(Log.service == service)
    if level:
        conds.append(Log.log_level == level.upper())
    if event_type:
        conds.append(Log.event_type == event_type)
    if source:
        conds.append(Log.source == source)
    if start:
        conds.append(Log.timestamp >= start)
    if end:
        conds.append(Log.timestamp <= end)
    total = session.scalar(select(func.count()).select_from(Log).where(*conds)) or 0
    rows = list(session.scalars(select(Log).where(*conds).order_by(Log.timestamp.desc()).offset((page - 1) * page_size).limit(page_size)))
    return rows, total


def distinct_values(session: Session) -> dict[str, list[str]]:
    return {
        "hostnames": sorted(session.scalars(select(Log.hostname).distinct())),
        "services": sorted(x for x in session.scalars(select(Log.service).distinct()) if x),
        "event_types": sorted(session.scalars(select(Log.event_type).distinct())),
        "levels": sorted(session.scalars(select(Log.log_level).distinct())),
    }


# ------------------------------------------------------------------ ingestion
def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    raise ValueError(f"unsupported file type '{path.suffix}' (use .csv or .json)")


def detect_kind(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    if set(NETWORK_COLS) <= cols:
        return "network"
    if set(SERVER_COLS) <= cols:
        return "server"
    raise ValueError(f"unrecognised log schema; server logs need {SERVER_COLS}, network logs need {NETWORK_COLS}")


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def validate_rows(df: pd.DataFrame, kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (valid rows as Log kwargs, rejects with row number + reason)."""
    ok: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for i, r in enumerate(df.to_dict("records"), start=2):
        ts = pd.to_datetime(r.get("timestamp"), errors="coerce")
        if pd.isna(ts):
            rejects.append({"row": i, "reason": f"invalid timestamp '{r.get('timestamp')}'"})
            continue
        ts = ts.to_pydatetime().replace(tzinfo=None)
        msg, ev = (str(r.get("message") or "").strip(), str(r.get("event_type") or "").strip())
        if not msg or not ev:
            rejects.append({"row": i, "reason": "message and event_type are required"})
            continue
        if kind == "server":
            host, level = (str(r.get("hostname") or "").strip(), str(r.get("level") or "").upper())
            if not host or level not in LEVELS:
                rejects.append({"row": i, "reason": f"hostname required and level must be one of {sorted(LEVELS)}"})
                continue
            meta: dict[str, Any] = {}
            raw = r.get("metadata")
            if isinstance(raw, dict):
                meta = raw
            elif raw:
                try:
                    meta = json.loads(raw)
                except (TypeError, ValueError):
                    rejects.append({"row": i, "reason": "metadata is not valid JSON"})
                    continue
            ok.append(
                dict(
                    timestamp=ts,
                    source="server",
                    hostname=host,
                    ip_address=(r.get("source_ip") or None),
                    service=(str(r.get("service") or "") or None),
                    log_level="WARN" if level == "WARNING" else level,
                    event_type=ev,
                    message=msg,
                    meta=meta,
                )
            )
        else:
            host = str(r.get("source_device") or "").strip()
            lat, loss = _num(r.get("latency_ms")), _num(r.get("packet_loss"))
            if not host or lat is None or loss is None or not (0 <= loss <= 100) or lat < 0:
                rejects.append({"row": i, "reason": "source_device required; latency_ms >= 0 and packet_loss in 0..100 must be numeric"})
                continue
            status = str(r.get("status") or "").lower()
            ok.append(
                dict(
                    timestamp=ts,
                    source="network",
                    hostname=host,
                    destination=str(r.get("destination") or "") or None,
                    service="network",
                    log_level=("ERROR" if status == "failed" else ("WARN" if status == "degraded" else "INFO")),
                    event_type=ev,
                    message=msg,
                    latency_ms=lat,
                    packet_loss=loss,
                    meta={
                        "status": status,
                        "protocol": r.get("protocol"),
                        "port": r.get("port"),
                        "interface": r.get("interface") or None,
                        "crc_errors": int(_num(r.get("crc_errors")) or 0),
                    },
                )
            )
    return ok, rejects


def ingest_file(session: Session, path: Path, kind: str | None = None) -> dict[str, Any]:
    """Validate + insert logs; identical rows already stored are skipped (multiset comparison => idempotent)."""
    df = _read(path)
    kind = kind or detect_kind(df)
    rows, rejects = validate_rows(df, kind)
    inserted = skipped = 0
    if rows:
        lo, hi = min(r["timestamp"] for r in rows), max(r["timestamp"] for r in rows)
        existing: Counter[tuple[Any, ...]] = Counter(
            (x.timestamp, x.hostname, x.event_type, x.message)
            for x in session.scalars(select(Log).where(Log.source == kind, Log.timestamp >= lo, Log.timestamp <= hi))
        )
        fresh: list[dict[str, Any]] = []
        now = utcnow()
        for r in rows:
            key = (r["timestamp"], r["hostname"], r["event_type"], r["message"])
            if existing[key] > 0:
                existing[key] -= 1
                skipped += 1
                continue
            r.setdefault("ip_address", None)
            r.update(id=__import__("uuid").uuid4(), created_at=now, updated_at=now)
            fresh.append(r)
        for i in range(0, len(fresh), CHUNK):
            chunk = fresh[i : i + CHUNK]
            for c in chunk:
                c["meta"] = c.pop("meta")
            session.execute(insert(Log), [{**c, "meta": c["meta"]} for c in chunk])
        session.commit()
        inserted = len(fresh)
    return {
        "file": path.name,
        "kind": kind,
        "rows_read": len(df),
        "inserted": inserted,
        "skipped_duplicates": skipped,
        "rejected": len(rejects),
        "rejects": rejects[:50],
    }
