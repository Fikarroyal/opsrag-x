from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field, field_validator

from tools import datastore
from tools.common import ToolError, ToolInput, register, safe_host

MONITOR = "MONITOR-01"


class Input(ToolInput):
    host: str
    window_minutes: int = Field(default=10, ge=1, le=60)

    _v = field_validator("host")(lambda cls, v: safe_host(v))


class Output(BaseModel):
    host: str
    reachable: bool | None
    latency_ms: float | None
    packet_loss: float | None
    samples: int
    window_minutes: int
    as_of: str
    basis: str


@register(
    "ping_host",
    "Read-only reachability/latency/packet-loss for a host over a trailing window (demo: aggregated from network probe logs; never pings real hosts).",
    Input,
    Output,
)
def ping_host(inp: Input) -> Output:
    node = datastore.resolve_node(inp.host)
    if node is None:
        raise ToolError("host_not_found", f"host '{inp.host}' is not part of the synthetic inventory")
    host = node["hostname"]
    as_of = inp.as_of_dt()
    rows = datastore.network_logs().between(as_of - timedelta(minutes=inp.window_minutes), as_of)
    samples = [r for r in rows if r["source_device"] == host or (r["source_device"] == MONITOR and r["destination"] == host)]
    if not samples:
        return Output(
            host=host,
            reachable=None,
            latency_ms=None,
            packet_loss=None,
            samples=0,
            window_minutes=inp.window_minutes,
            as_of=as_of.isoformat(),
            basis="no probe samples in window (insufficient data)",
        )
    loss = sum(r["_loss"] for r in samples) / len(samples)
    ok = [r["_lat"] for r in samples if r["status"] != "failed" and r["_lat"] > 0]
    lat = sum(ok) / len(ok) if ok else None
    reachable = not all(r["_loss"] >= 100 for r in samples)
    return Output(
        host=host,
        reachable=reachable,
        latency_ms=round(lat, 1) if lat is not None else None,
        packet_loss=round(loss, 1),
        samples=len(samples),
        window_minutes=inp.window_minutes,
        as_of=as_of.isoformat(),
        basis="mean over probes originating at the host or from MONITOR-01 towards the host",
    )
