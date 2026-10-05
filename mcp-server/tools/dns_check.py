from __future__ import annotations

import os
import socket
import time

from pydantic import BaseModel, field_validator

from tools import datastore
from tools.common import DEMO_MODE, ToolError, ToolInput, register, safe_host


class Input(ToolInput):
    hostname: str

    _v = field_validator("hostname")(lambda cls, v: safe_host(v))


class Output(BaseModel):
    hostname: str
    resolved_ip: str | None
    success: bool
    response_time_ms: float
    error: str | None = None
    as_of: str | None = None


@register("check_dns", "Read-only DNS resolution check (demo: driven by DNS service state and internal zone records).", Input, Output)
def check_dns(inp: Input) -> Output:
    name = inp.hostname.lower()
    if not DEMO_MODE:
        allow = [h.strip().lower() for h in os.environ.get("LIVE_ALLOWED_HOSTS", "").split(",") if h.strip()]
        if not any(name == a or name.endswith(a if a.startswith(".") else "." + a) for a in allow):
            raise ToolError("host_not_allowed", "hostname is not in LIVE_ALLOWED_HOSTS")
        t0 = time.perf_counter()
        try:
            ip = str(socket.getaddrinfo(name, None)[0][4][0])
            return Output(hostname=inp.hostname, resolved_ip=ip, success=True, response_time_ms=round((time.perf_counter() - t0) * 1000, 1))
        except OSError as exc:
            return Output(
                hostname=inp.hostname,
                resolved_ip=None,
                success=False,
                response_time_ms=round((time.perf_counter() - t0) * 1000, 1),
                error=type(exc).__name__,
            )
    as_of = inp.as_of_dt()
    records: dict[str, str] = datastore.topology()["dns_records"]
    node = datastore.nodes().get(inp.hostname.upper())
    rec_ip: str | None = records.get(name) or (node or {}).get("ip")
    dns = datastore.latest_service_state("DNS", as_of)
    if dns and dns["status"] != "running":
        err = "SERVFAIL" if dns["status"] == "degraded" else "SERVFAIL (resolver not answering)"
        return Output(
            hostname=inp.hostname,
            resolved_ip=None,
            success=False,
            response_time_ms=float(dns["response_time"]),
            error=err,
            as_of=as_of.isoformat(),
        )
    if not rec_ip:
        return Output(
            hostname=inp.hostname,
            resolved_ip=None,
            success=False,
            response_time_ms=float(dns["response_time"]) if dns else 8.0,
            error="NXDOMAIN",
            as_of=as_of.isoformat(),
        )
    return Output(
        hostname=inp.hostname,
        resolved_ip=rec_ip,
        success=True,
        response_time_ms=float(dns["response_time"]) if dns else 8.0,
        as_of=as_of.isoformat(),
    )
