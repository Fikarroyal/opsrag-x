from __future__ import annotations

from pydantic import BaseModel, field_validator

from tools import datastore
from tools.common import ToolError, ToolInput, register, safe_host


class Input(ToolInput):
    server_name: str

    _v = field_validator("server_name")(lambda cls, v: safe_host(v))


class Output(BaseModel):
    server: str
    status: str
    cpu: float | None
    memory: float | None
    uptime: str
    timestamp: str
    as_of: str
    sample_timestamp: str | None
    services: list[dict]
    recent_error_count: int
    basis: str


@register(
    "get_server_status", "Read-only server health: CPU, memory, uptime and service states (derived from monitoring samples).", Input, Output
)
def get_server_status(inp: Input) -> Output:
    srv = datastore.servers().get(inp.server_name.upper())
    if not srv:
        raise ToolError("not_found", f"server '{inp.server_name}' is not in the inventory")
    as_of = inp.as_of_dt()
    host = srv["hostname"]
    sample = datastore.server_logs().latest_before(as_of, lambda r: r["hostname"] == host and r["event_type"] == "RESOURCE_SAMPLE")
    cpu = mem = None
    sample_ts = None
    if sample and (as_of - sample["_ts"]).total_seconds() <= 3 * 3600:
        cpu, mem, sample_ts = (float(sample["_meta"].get("cpu", 0)), float(sample["_meta"].get("memory", 0)), sample["_ts"].isoformat())
    services = []
    for name in ("SIMRS", "SIM-APOTEK", "DNS", "DATABASE", "FILE SERVER", "MONITORING"):
        st = datastore.latest_service_state(name, as_of)
        if st and st["server"].upper() == host.upper():
            services.append(
                {
                    "service": name,
                    "status": st["status"],
                    "response_time_ms": float(st["response_time"]),
                    "last_checked": st["last_checked"],
                }
            )
    window = datastore.server_logs().between(as_of.replace(microsecond=0) - __import__("datetime").timedelta(minutes=5), as_of)
    errors = sum(1 for r in window if r["hostname"] == host and r["level"] == "ERROR")
    status = "healthy"
    if any(s["status"] == "degraded" for s in services) or (cpu is not None and cpu >= 85) or (mem is not None and mem >= 90):
        status = "degraded"
    if any(s["status"] == "down" for s in services):
        status = "down"
    boot = datastore.parse_ts(srv["boot_time"])
    secs = max(0, int((as_of - boot).total_seconds())) if boot else 0
    return Output(
        server=host,
        status=status,
        cpu=cpu,
        memory=mem,
        uptime=f"{secs // 86400}d {secs % 86400 // 3600:02d}h",
        timestamp=as_of.isoformat(),
        as_of=as_of.isoformat(),
        sample_timestamp=sample_ts,
        services=services,
        recent_error_count=errors,
        basis=(
            "cpu/memory from latest RESOURCE_SAMPLE; degraded if cpu>=85 or mem>=90 or a hosted service is degraded; down if a hosted service is down"
            if sample_ts
            else "no recent resource sample; status derived from hosted services only"
        ),
    )
