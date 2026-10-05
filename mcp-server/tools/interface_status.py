from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field, field_validator

from tools import datastore
from tools.common import ToolError, ToolInput, register, safe_host

IF_EVENTS = {"INTERFACE_DOWN": "down", "INTERFACE_ERRORS": "up_with_errors", "INTERFACE_UP": "up"}


class Input(ToolInput):
    hostname: str
    window_minutes: int = Field(default=15, ge=1, le=60)

    _v = field_validator("hostname")(lambda cls, v: safe_host(v))


class Output(BaseModel):
    hostname: str
    as_of: str
    interfaces: list[dict]
    peer_reports: list[dict]
    summary: dict


@register(
    "get_network_interface_status",
    "Read-only interface state (up/down/errors) of a network device from recent interface events and neighbour reports.",
    Input,
    Output,
)
def get_network_interface_status(inp: Input) -> Output:
    node = datastore.resolve_node(inp.hostname)
    if not node:
        raise ToolError("not_found", f"device '{inp.hostname}' is not in the topology")
    host = node["hostname"]
    as_of = inp.as_of_dt()
    rows = datastore.network_logs().between(as_of - timedelta(minutes=inp.window_minutes), as_of)
    own = [r for r in rows if r["source_device"] == host and r["interface"]]
    state: dict[str, dict] = {}
    for e in datastore.adjacency().get(host.upper(), []):
        state[e["local_if"]] = {
            "name": e["local_if"],
            "peer": e["peer"],
            "status": "up",
            "crc_errors": 0,
            "latency_ms": None,
            "packet_loss": None,
            "last_event": None,
            "last_event_time": None,
        }
    for r in own:  # rows are time-ordered, so later events overwrite earlier ones
        s = state.setdefault(
            r["interface"],
            {
                "name": r["interface"],
                "peer": r["destination"],
                "status": "up",
                "crc_errors": 0,
                "latency_ms": None,
                "packet_loss": None,
                "last_event": None,
                "last_event_time": None,
            },
        )
        s["peer"] = r["destination"]
        s["latency_ms"], s["packet_loss"] = r["_lat"], r["_loss"]
        s["crc_errors"] = max(s["crc_errors"], r["_crc"])
        if r["event_type"] in IF_EVENTS:
            s["status"], s["last_event"], s["last_event_time"] = (IF_EVENTS[r["event_type"]], r["event_type"], r["timestamp"])
        elif r["event_type"] == "HIGH_LATENCY":
            s["last_event"], s["last_event_time"] = "HIGH_LATENCY", r["timestamp"]
            s["status"] = "up_with_errors" if s["status"] == "up" and s["crc_errors"] > 0 else s["status"]
    reports = [
        {
            "reporter": r["source_device"],
            "event_type": r["event_type"],
            "message": r["message"],
            "timestamp": r["timestamp"],
            "interface": r["interface"],
        }
        for r in rows
        if r["source_device"] != host and r["event_type"] in IF_EVENTS and host.lower() in r["message"].lower()
    ]
    ifs = sorted(state.values(), key=lambda x: x["name"])
    return Output(
        hostname=host,
        as_of=as_of.isoformat(),
        interfaces=ifs,
        peer_reports=reports[-5:],
        summary={
            "down": sum(1 for i in ifs if i["status"] == "down"),
            "with_errors": sum(1 for i in ifs if i["status"] == "up_with_errors"),
            "max_crc_errors": max([i["crc_errors"] for i in ifs] or [0]),
        },
    )
