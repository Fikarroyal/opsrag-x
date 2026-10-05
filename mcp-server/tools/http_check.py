from __future__ import annotations

import os
import time
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, field_validator

from tools import datastore
from tools.common import DEMO_MODE, ToolError, ToolInput, register

PORT_SERVICE = {8080: "SIMRS", 8081: "SIM-APOTEK", 9090: "MONITORING"}


class Input(ToolInput):
    url: str

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        p = urlparse(v)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise ValueError("url must be http(s)://host[:port][/path]")
        if len(v) > 300:
            raise ValueError("url too long")
        return v


class Output(BaseModel):
    url: str
    status_code: int
    response_time_ms: float
    healthy: bool
    service: str | None = None
    error: str | None = None
    as_of: str | None = None


def _live_allowed(host: str) -> bool:
    allow = [h.strip().lower() for h in os.environ.get("LIVE_ALLOWED_HOSTS", "").split(",") if h.strip()]
    return any(host.lower() == a or host.lower().endswith(a if a.startswith(".") else "." + a) for a in allow)


@register(
    "check_http", "Read-only HTTP GET health check of a service endpoint (demo: derived from service monitoring data).", Input, Output
)
def check_http(inp: Input) -> Output:
    p = urlparse(inp.url)
    host, port = p.hostname or "", p.port or (443 if p.scheme == "https" else 80)
    if not DEMO_MODE:
        if not _live_allowed(host):
            raise ToolError("host_not_allowed", "host is not in LIVE_ALLOWED_HOSTS")
        t0 = time.perf_counter()
        try:
            r = httpx.get(inp.url, timeout=5.0, follow_redirects=False)
            ms = (time.perf_counter() - t0) * 1000
            return Output(url=inp.url, status_code=r.status_code, response_time_ms=round(ms, 1), healthy=r.status_code < 400 and ms < 2000)
        except httpx.HTTPError as exc:
            return Output(
                url=inp.url,
                status_code=0,
                response_time_ms=round((time.perf_counter() - t0) * 1000, 1),
                healthy=False,
                error=type(exc).__name__,
            )
    as_of = inp.as_of_dt()
    node = datastore.resolve_node(host)
    is_name = host.lower() in datastore.topology()["dns_records"]
    if node is None and not is_name:
        raise ToolError("host_not_found", f"host '{host}' is not part of the synthetic inventory")
    if is_name:
        dns = datastore.latest_service_state("DNS", as_of)
        if dns and dns["status"] != "running":
            return Output(
                url=inp.url,
                status_code=0,
                response_time_ms=5000.0,
                healthy=False,
                error="name resolution failed (DNS)",
                as_of=as_of.isoformat(),
            )
    server_host = (
        datastore.topology()["dns_records"].get(host.lower())
        and datastore.ip_index().get(datastore.topology()["dns_records"][host.lower()])
    ) or (node or {}).get("hostname")
    service = PORT_SERVICE.get(port)
    if not service or not server_host:
        raise ToolError("no_service", f"no monitored HTTP service on {host}:{port}")
    st = datastore.latest_service_state(service, as_of)
    if not st or st["server"].upper() != str(server_host).upper():
        raise ToolError("no_service", f"{service} is not hosted on {server_host}")
    rt = float(st["response_time"])
    if st["status"] == "down":
        return Output(
            url=inp.url,
            status_code=0,
            response_time_ms=rt,
            healthy=False,
            service=service,
            error="connection refused",
            as_of=as_of.isoformat(),
        )
    code = int(st["http_status"]) or 200
    return Output(
        url=inp.url,
        status_code=code,
        response_time_ms=rt,
        healthy=code < 400 and rt < 2000 and st["status"] == "running",
        service=service,
        as_of=as_of.isoformat(),
    )
