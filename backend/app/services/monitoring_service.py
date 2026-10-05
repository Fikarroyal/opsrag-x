"""Monitoring views: server resource samples (from the logs table) and service status history (monitoring snapshots CSV)."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models import Log, Server


@lru_cache
def _status_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["last_checked"] = pd.to_datetime(df["last_checked"])
    return df.sort_values("last_checked")


def service_status_at(as_of: datetime | None) -> list[dict[str, Any]]:
    df = _status_df(str(get_settings().raw_dir / "service_status.csv"))
    if as_of is not None:
        df = df[df["last_checked"] <= as_of]
    out = []
    for name, g in df.groupby("service"):
        r = g.iloc[-1]
        out.append(
            {
                "service": name,
                "server": r["server"],
                "status": r["status"],
                "response_time_ms": float(r["response_time"]),
                "port": int(r["port"]),
                "http_status": int(r["http_status"]),
                "endpoint": r["endpoint"],
                "last_checked": r["last_checked"].isoformat(),
            }
        )
    return sorted(out, key=lambda x: x["service"])


def service_history(service: str, start: datetime | None, end: datetime | None, limit: int = 240) -> list[dict[str, Any]]:
    df = _status_df(str(get_settings().raw_dir / "service_status.csv"))
    df = df[df["service"] == service]
    if start is not None:
        df = df[df["last_checked"] >= start]
    if end is not None:
        df = df[df["last_checked"] <= end]
    if len(df) > limit:
        df = df.iloc[:: max(1, len(df) // limit)]
    return [
        {"timestamp": r.last_checked.isoformat(), "status": r.status, "response_time_ms": float(r.response_time)} for r in df.itertuples()
    ]


def servers_overview(session: Session, as_of: datetime | None) -> list[dict[str, Any]]:
    states = service_status_at(as_of)
    out = []
    for s in session.scalars(select(Server).order_by(Server.hostname)):
        q = select(Log).where(Log.hostname == s.hostname, Log.event_type == "RESOURCE_SAMPLE")
        if as_of:
            q = q.where(Log.timestamp <= as_of)
        sample = session.scalar(q.order_by(Log.timestamp.desc()).limit(1))
        ref = as_of or (sample.timestamp if sample else None)
        errors = 0
        if ref:
            errors = (
                session.scalar(
                    select(func.count())
                    .select_from(Log)
                    .where(
                        Log.hostname == s.hostname,
                        Log.log_level == "ERROR",
                        Log.timestamp <= ref,
                        Log.timestamp >= ref - timedelta(minutes=15),
                    )
                )
                or 0
            )
        svcs = [x for x in states if x["server"] == s.hostname]
        cpu = sample.meta.get("cpu") if sample else None
        mem = sample.meta.get("memory") if sample else None
        status = "healthy"
        if any(x["status"] == "degraded" for x in svcs) or (cpu or 0) >= 85 or (mem or 0) >= 90:
            status = "degraded"
        if any(x["status"] == "down" for x in svcs):
            status = "down"
        out.append(
            {
                "hostname": s.hostname,
                "ip_address": s.ip_address,
                "role": s.role,
                "status": status,
                "operating_system": s.operating_system,
                "cpu": cpu,
                "memory": mem,
                "sample_timestamp": sample.timestamp if sample else None,
                "services": svcs,
                "recent_errors": errors,
            }
        )
    return out


def server_metrics(session: Session, hostname: str, start: datetime, end: datetime, limit: int = 300) -> list[dict[str, Any]]:
    rows = list(
        session.scalars(
            select(Log)
            .where(Log.hostname == hostname, Log.event_type == "RESOURCE_SAMPLE", Log.timestamp >= start, Log.timestamp <= end)
            .order_by(Log.timestamp)
        )
    )
    if len(rows) > limit:
        rows = rows[:: max(1, len(rows) // limit)]
    return [{"timestamp": r.timestamp.isoformat(), "cpu": r.meta.get("cpu"), "memory": r.meta.get("memory")} for r in rows]
