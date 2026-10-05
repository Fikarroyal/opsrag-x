"""Temporal log correlation.

Input : incident time T, affected unit/hosts, log records in [T-15min, T+15min].
Steps : 1) classify every record into a domain (network, application, server, database, dns, device)
        2) mark anomalies and compute the first-anomaly time (onset) per domain
        3) detect causal patterns  cause-domain onset -> symptom onset
              network degradation -> application failure     (network|device)
              DNS failure         -> application failure     (dns)
              database failure    -> application timeout     (database)
              server overload     -> high response time      (server)
        4) score each pattern:
              score = 0.5 * order_ok + 0.25 * lag_score + 0.25 * volume_score
              order_ok     = 1 if cause onset <= symptom onset else 0
              lag_score    = exp(-lag / 600 s)        (closer cause->symptom = stronger)
              volume_score = min(1, cause_event_count / 10)
The symptom onset is the first application anomaly, or the reported incident time when the application logged nothing.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

NET_ANOMALY = {
    "PACKET_LOSS",
    "HIGH_LATENCY",
    "CONNECTION_REFUSED",
    "TIMEOUT",
    "INTERFACE_DOWN",
    "INTERFACE_ERRORS",
    "VLAN_MISCONFIG",
    "GATEWAY_UNREACHABLE",
}
LOSS_EVENTS = {"PACKET_LOSS", "TIMEOUT", "GATEWAY_UNREACHABLE"}
APP_ANOMALY = {"HTTP_TIMEOUT", "APP_ERROR", "DB_CONN_TIMEOUT", "SLOW_RESPONSE", "HEALTHCHECK_FAIL"}
DB_ANOMALY = {"DB_CONN_POOL_EXHAUSTED", "DB_QUERY_SLOW"}
DOMAINS = ["network", "application", "server", "database", "dns", "device"]
ENDPOINT_TYPES = {"pc", "printer"}


@dataclass
class LogRecord:
    timestamp: datetime
    source: str  # server | network
    hostname: str
    event_type: str
    level: str = "INFO"
    message: str = ""
    ip_address: str | None = None
    destination: str | None = None
    service: str | None = None
    latency_ms: float | None = None
    packet_loss: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class HostInfo:
    unit: str | None
    device_type: str
    switch: str | None = None


@dataclass
class LogGroup:
    domain: str
    hostname: str
    event_type: str
    count: int
    first: datetime
    last: datetime
    avg_loss: float | None = None
    max_loss: float | None = None
    avg_latency: float | None = None
    max_crc: int | None = None
    peak_cpu: float | None = None
    sample: str = ""
    units: list[str] = field(default_factory=list)


@dataclass
class Pattern:
    name: str
    cause_domain: str
    cause_onset: datetime
    symptom_onset: datetime
    lag_seconds: float
    order_ok: bool
    event_count: int
    score: float


@dataclass
class CorrelationResult:
    groups: list[LogGroup]
    onsets: dict[str, datetime]
    patterns: list[Pattern]
    impact_units: list[str]
    affected_endpoints: dict[str, dict[str, float]]
    healthy_peers: list[str]
    control_ok_hosts: list[str]
    flags: dict[str, bool]
    counts: dict[str, int]
    timeline: list[dict[str, Any]]

    @property
    def dominant_pattern(self) -> Pattern | None:
        return max(self.patterns, key=lambda p: p.score, default=None)


def is_anomaly(r: LogRecord) -> bool:
    if r.source == "network":
        if r.event_type == "DNS_FAILURE":
            return True
        return r.event_type in NET_ANOMALY
    if r.event_type in APP_ANOMALY or r.event_type in DB_ANOMALY or r.event_type in ("DNS_QUERY_FAIL", "RESOURCE_HIGH_CPU"):
        return True
    if r.event_type == "RESOURCE_SAMPLE":
        return float(r.meta.get("cpu", 0) or 0) >= 85 or float(r.meta.get("memory", 0) or 0) >= 90
    return False


def domain_of(r: LogRecord, hosts: dict[str, HostInfo]) -> str:
    if r.source == "network":
        if r.event_type == "DNS_FAILURE":
            return "dns"
        info = hosts.get(r.hostname)
        return "device" if info and info.device_type in ENDPOINT_TYPES else "network"
    if r.event_type in ("DNS_QUERY_FAIL",) or r.hostname.upper().startswith("DNS"):
        return "dns"
    if r.event_type in DB_ANOMALY or r.hostname.upper().startswith("SIMRS-DB"):
        return "database"
    if r.event_type in ("RESOURCE_HIGH_CPU", "RESOURCE_SAMPLE"):
        return "server"
    return "application"


def correlate(
    records: list[LogRecord], incident_time: datetime, *, affected_unit: str | None, hosts: dict[str, HostInfo], ip_unit: dict[str, str]
) -> CorrelationResult:
    anomalies = [r for r in records if is_anomaly(r)]
    onsets: dict[str, datetime] = {}
    counts: dict[str, int] = defaultdict(int)
    buckets: dict[tuple[str, str, str], list[LogRecord]] = defaultdict(list)
    for r in anomalies:
        d = domain_of(r, hosts)
        buckets[(d, r.hostname, r.event_type)].append(r)
        counts[d] += 1
        if d not in onsets or r.timestamp < onsets[d]:
            onsets[d] = r.timestamp

    groups: list[LogGroup] = []
    for (d, host, ev), rs in buckets.items():
        rs.sort(key=lambda x: x.timestamp)
        losses = [x.packet_loss for x in rs if x.packet_loss is not None]
        lats = [x.latency_ms for x in rs if x.latency_ms]
        cpu = [float(x.meta["cpu"]) for x in rs if "cpu" in x.meta]
        unit_set: set[str] = {ip_unit[x.ip_address] for x in rs if x.ip_address and x.ip_address in ip_unit}
        if host in hosts and d in ("device", "network") and (host_unit := hosts[host].unit):
            unit_set.add(host_unit)
        units = sorted(unit_set)
        groups.append(
            LogGroup(
                d,
                host,
                ev,
                len(rs),
                rs[0].timestamp,
                rs[-1].timestamp,
                sum(losses) / len(losses) if losses else None,
                max(losses) if losses else None,
                sum(lats) / len(lats) if lats else None,
                max((int(x.meta.get("crc_errors", 0) or 0) for x in rs), default=None),
                max(cpu) if cpu else None,
                rs[0].message,
                units,
            )
        )
    groups.sort(key=lambda g: (g.first, g.hostname))

    # endpoints with real loss / latency (not DNS_FAILURE, which has 0 loss by construction)
    affected: dict[str, dict[str, float]] = {}
    for r in anomalies:
        info = hosts.get(r.hostname)
        if (
            r.source == "network"
            and info
            and info.device_type in ENDPOINT_TYPES
            and (r.event_type in LOSS_EVENTS or r.event_type == "HIGH_LATENCY")
        ):
            a = affected.setdefault(r.hostname, {"n": 0, "loss_sum": 0.0, "lat_sum": 0.0})
            a["n"] += 1
            a["loss_sum"] += r.packet_loss or 0
            a["lat_sum"] += r.latency_ms or 0
    affected_stats = {
        h: {"events": v["n"], "avg_loss": round(v["loss_sum"] / v["n"], 1), "avg_latency": round(v["lat_sum"] / v["n"], 1)}
        for h, v in affected.items()
    }

    # units showing symptoms
    impact: set[str] = set()
    for r in anomalies:
        info = hosts.get(r.hostname)
        if (r.source == "network" and info and info.unit and info.device_type in ENDPOINT_TYPES) or (
            r.source == "network" and r.event_type == "DNS_FAILURE" and info and info.unit
        ):
            impact.add(info.unit)
        elif r.source == "server" and r.event_type in (APP_ANOMALY | {"DNS_QUERY_FAIL"}) and r.ip_address in ip_unit:
            impact.add(ip_unit[r.ip_address])
    impact_units = sorted(impact)

    # healthy peers = endpoints on the same access switch(es) as affected hosts that produced only normal probes
    switches = {hosts[h].switch for h in affected_stats if h in hosts and hosts[h].switch}
    normal_hosts = {r.hostname for r in records if r.source == "network" and r.event_type in ("NORMAL_TRAFFIC", "PING_OK")}
    healthy_peers = sorted(
        h
        for h in normal_hosts
        if h in hosts and hosts[h].switch in switches and h not in affected_stats and hosts[h].device_type in ENDPOINT_TYPES
    )
    control_ok = sorted(
        h
        for h in normal_hosts
        if h in hosts and hosts[h].device_type in ENDPOINT_TYPES and hosts[h].unit not in impact and h not in affected_stats
    )

    # symptom onset
    app_onset = onsets.get("application")
    symptom_onset = min(app_onset, incident_time) if app_onset else incident_time
    patterns: list[Pattern] = []
    net_candidates = [onsets[d] for d in ("network", "device") if d in onsets]
    cause_specs = [
        (
            "network_degradation_then_application_failure",
            "network",
            min(net_candidates) if net_candidates else None,
            counts["network"] + counts["device"],
        ),
        ("dns_failure_then_application_failure", "dns", onsets.get("dns"), counts["dns"]),
        ("database_failure_then_application_timeout", "database", onsets.get("database"), counts["database"]),
        ("server_overload_then_high_response_time", "server", onsets.get("server"), counts["server"]),
    ]
    for name, dom, onset, n in cause_specs:
        if onset is None or n < 3:  # a pattern needs a minimum volume of cause events
            continue
        lag = (symptom_onset - onset).total_seconds()
        order_ok = lag >= 0
        score = 0.5 * (1.0 if order_ok else 0.0) + 0.25 * math.exp(-max(lag, 0) / 600.0) + 0.25 * min(1.0, n / 10.0)
        patterns.append(Pattern(name, dom, onset, symptom_onset, lag, order_ok, n, round(score, 3)))

    flags = {
        "unit_only_impact": len(impact_units) == 1 and (affected_unit in (None, "", "Semua Unit") or impact_units[0] == affected_unit),
        "hospital_wide_impact": len(impact_units) >= 3,
        "multi_unit_impact": len(impact_units) == 2,
    }
    timeline = [
        {
            "timestamp": g.first.isoformat(),
            "source": g.hostname,
            "domain": g.domain,
            "event": f"{g.event_type} x{g.count}"
            + (f" (avg loss {g.avg_loss:.0f}%)" if g.avg_loss and g.event_type in LOSS_EVENTS else ""),
            "relevance": (0.9 if g.domain in ("network", "device", "dns", "database", "server") else 0.8),
        }
        for g in groups
    ]
    return CorrelationResult(
        groups, onsets, patterns, impact_units, affected_stats, healthy_peers, control_ok, flags, dict(counts), timeline
    )
