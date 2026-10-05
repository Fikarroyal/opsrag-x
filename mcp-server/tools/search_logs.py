from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field, field_validator, model_validator

from tools import datastore
from tools.common import ToolInput, register

LEVELS = {"critical": {"CRITICAL", "ERROR"}, "error": {"ERROR", "CRITICAL"}, "warn": {"WARN"}, "warning": {"WARN"}, "info": {"INFO"}}


class Input(ToolInput):
    query: str | None = Field(default=None, max_length=120)
    start_time: str
    end_time: str
    hostname: str | None = Field(default=None, max_length=80)
    service: str | None = Field(default=None, max_length=60)
    severity: str | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("start_time", "end_time")
    @classmethod
    def _ts(cls, v: str) -> str:
        datastore.parse_ts(v)
        return v

    @field_validator("severity")
    @classmethod
    def _sev(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in LEVELS:
            raise ValueError(f"severity must be one of {sorted(LEVELS)}")
        return v

    @model_validator(mode="after")
    def _range(self) -> Input:
        s, e = datastore.parse_ts(self.start_time), datastore.parse_ts(self.end_time)
        assert s and e
        if e < s:
            raise ValueError("end_time must be >= start_time")
        if e - s > timedelta(hours=24):
            raise ValueError("time range must be <= 24 hours")
        return self


class Output(BaseModel):
    total_matches: int
    returned: int
    truncated: bool
    logs: list[dict]


def _net_level(r: dict) -> str:
    return "ERROR" if r["status"] == "failed" else ("WARN" if r["status"] == "degraded" else "INFO")


@register("search_logs", "Read-only search across server and network logs (time range <= 24h, max 200 rows).", Input, Output)
def search_logs(inp: Input) -> Output:
    s, e = datastore.parse_ts(inp.start_time), datastore.parse_ts(inp.end_time)
    assert s and e
    tokens = [t.lower() for t in (inp.query or "").split() if t]
    levels = LEVELS[inp.severity.lower()] if inp.severity else None
    out: list[dict] = []
    for r in datastore.server_logs().between(s, e):
        out.append(
            {
                "timestamp": r["timestamp"],
                "source": "server",
                "hostname": r["hostname"],
                "service": r["service"],
                "level": r["level"],
                "event_type": r["event_type"],
                "message": r["message"],
                "ip_address": r["source_ip"],
            }
        )
    for r in datastore.network_logs().between(s, e):
        out.append(
            {
                "timestamp": r["timestamp"],
                "source": "network",
                "hostname": r["source_device"],
                "service": "network",
                "level": _net_level(r),
                "event_type": r["event_type"],
                "message": f"{r['message']} (dst={r['destination']} latency={r['_lat']}ms loss={r['_loss']}%)",
                "ip_address": None,
            }
        )

    def keep(x: dict) -> bool:
        if inp.hostname and x["hostname"].lower() != inp.hostname.lower():
            return False
        if inp.service and (x["service"] or "").lower() != inp.service.lower():
            return False
        if levels and x["level"] not in levels:
            return False
        hay = f"{x['message']} {x['event_type']} {x['hostname']}".lower()
        return all(t in hay for t in tokens)

    matches = sorted((x for x in out if keep(x)), key=lambda x: x["timestamp"])
    return Output(
        total_matches=len(matches), returned=min(len(matches), inp.limit), truncated=len(matches) > inp.limit, logs=matches[: inp.limit]
    )
