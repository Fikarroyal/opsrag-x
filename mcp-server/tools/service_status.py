from __future__ import annotations

from pydantic import BaseModel, Field

from tools import datastore
from tools.common import ToolError, ToolInput, register

ALIASES = {
    "SIMRS": "SIMRS",
    "SIM-APOTEK": "SIM-APOTEK",
    "APOTEK": "SIM-APOTEK",
    "DNS": "DNS",
    "DATABASE": "DATABASE",
    "DB": "DATABASE",
    "FILE SERVER": "FILE SERVER",
    "FILE": "FILE SERVER",
    "MONITORING": "MONITORING",
}


class Input(ToolInput):
    service_name: str = Field(min_length=2, max_length=40)


class Output(BaseModel):
    service: str
    status: str
    server: str
    port: int
    response_time_ms: float
    http_status: int
    last_checked: str
    as_of: str


@register("query_service_status", "Read-only latest monitored status of a hospital IT service.", Input, Output)
def query_service_status(inp: Input) -> Output:
    canon = ALIASES.get(inp.service_name.strip().upper())
    if not canon:
        raise ToolError("not_found", f"service '{inp.service_name}' is not monitored (known: {sorted(set(ALIASES.values()))})")
    as_of = inp.as_of_dt()
    st = datastore.latest_service_state(canon, as_of)
    if not st:
        raise ToolError("no_data", f"no status sample for {canon} at or before {as_of.isoformat()}")
    return Output(
        service=canon,
        status=st["status"],
        server=st["server"],
        port=int(st["port"]),
        response_time_ms=float(st["response_time"]),
        http_status=int(st["http_status"]),
        last_checked=st["last_checked"],
        as_of=as_of.isoformat(),
    )
