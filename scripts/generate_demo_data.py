#!/usr/bin/env python
"""Deterministic generator for the fully SYNTHETIC "RS Yogyakarta" dataset.

No patient data of any kind is generated: only IT infrastructure telemetry
(devices, topology, logs, service status, incident tickets).

All timestamps are naive local hospital time (WIB) and never depend on the wall clock,
so every run yields byte-identical files (reproducible demo).

Outputs (under data/):
  raw/network_topology.json, raw/device_inventory.csv, raw/servers.csv,
  raw/server_logs.csv, raw/network_logs.csv, raw/service_status.csv,
  raw/historical_incidents.csv, raw/incident_ticket.csv,
  benchmark/benchmark_incidents.json, docs/infrastructure.md
"""

from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
SEED = 20260928

rng = random.Random(SEED)

# ----------------------------------------------------------------------------
# Static hospital layout
# ----------------------------------------------------------------------------
VLANS = {10: "Management", 20: "Server", 30: "Poli", 40: "Farmasi", 50: "Kasir", 60: "Laboratorium", 70: "Penunjang/IGD"}

# unit -> (slug, vlan, subnet, n_pcs, access switch, distribution switch)
UNITS: dict[str, tuple[str, int, str, int, str, str]] = {
    "Poli 1": ("POLI1", 30, "10.30.1", 12, "SW-POLI1", "SW-DIST-01"),
    "Poli 2": ("POLI2", 30, "10.30.2", 12, "SW-POLI2", "SW-DIST-01"),
    "Poli 3": ("POLI3", 30, "10.30.3", 12, "SW-POLI3", "SW-DIST-01"),
    "Farmasi": ("FARMASI", 40, "10.40.0", 10, "SW-FARMASI", "SW-DIST-01"),
    "Kasir": ("KASIR", 50, "10.50.0", 8, "SW-KASIR", "SW-DIST-01"),
    "Laboratorium": ("LAB", 60, "10.60.0", 8, "SW-LAB", "SW-DIST-02"),
    "Radiologi": ("RADIOLOGI", 70, "10.70.1", 8, "SW-RADIOLOGI", "SW-DIST-02"),
    "IGD": ("IGD", 70, "10.70.2", 10, "SW-IGD", "SW-DIST-02"),
    "Rekam Medis": ("REKAMMEDIS", 70, "10.70.3", 8, "SW-REKAMMEDIS", "SW-DIST-02"),
    "IT": ("IT", 10, "10.10.1", 6, "SW-IT", "SW-DIST-02"),
}
PRINTER_UNITS = ["Poli 1", "Poli 2", "Poli 3", "Farmasi", "Kasir", "Laboratorium"]

SERVERS = [
    # hostname, ip, role, os, boot_time
    ("SIMRS-APP-01", "10.20.0.10", "application", "Ubuntu Server 22.04", "2026-09-16 04:12:00"),
    ("SIMRS-DB-01", "10.20.0.11", "database", "Ubuntu Server 22.04", "2026-08-30 02:05:00"),
    ("DNS-01", "10.20.0.2", "dns", "Debian 12", "2026-09-01 03:00:00"),
    ("FILE-01", "10.20.0.20", "file", "Windows Server 2019", "2026-09-10 01:30:00"),
    ("MONITOR-01", "10.20.0.30", "monitoring", "Ubuntu Server 22.04", "2026-09-05 05:45:00"),
]
SERVER_IP = {h: ip for h, ip, *_ in SERVERS}

NET_GEAR = [
    # hostname, ip, type, vlan, unit
    ("RTR-CORE", "10.10.0.1", "router", 10, "IT"),
    ("CORE-SW-01", "10.10.0.2", "core_switch", 10, "IT"),
    ("SW-DIST-01", "10.10.0.3", "distribution_switch", 10, "IT"),
    ("SW-DIST-02", "10.10.0.4", "distribution_switch", 10, "IT"),
]

SERVICES = [
    # name, server, port, endpoint
    ("SIMRS", "SIMRS-APP-01", 8080, "http://simrs.internal:8080/health"),
    ("SIM-APOTEK", "SIMRS-APP-01", 8081, "http://simrs.internal:8081/health"),
    ("DNS", "DNS-01", 53, "dns://dns-01.internal:53"),
    ("DATABASE", "SIMRS-DB-01", 5432, "tcp://simrs-db.internal:5432"),
    ("FILE SERVER", "FILE-01", 445, "smb://file.internal:445"),
    ("MONITORING", "MONITOR-01", 9090, "http://monitor.internal:9090/-/healthy"),
]
DNS_RECORDS = {
    "simrs.internal": "10.20.0.10",
    "simrs-db.internal": "10.20.0.11",
    "dns-01.internal": "10.20.0.2",
    "file.internal": "10.20.0.20",
    "monitor.internal": "10.20.0.30",
}

START = datetime(2026, 9, 20, 0, 0, 0)
END = datetime(2026, 9, 28, 23, 59, 0)


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ----------------------------------------------------------------------------
# Scenarios (deterministic temporal patterns)
# ----------------------------------------------------------------------------
SCENARIOS: dict[str, dict[str, Any]] = {
    "S1": {"ticket": "INC-2026-001", "T": datetime(2026, 9, 28, 9, 42), "name": "SIMRS inaccessible from Poli 3"},
    "S2": {"ticket": "INC-2026-002", "T": datetime(2026, 9, 27, 13, 15), "name": "DNS internal failure"},
    "S3": {"ticket": "INC-2026-003", "T": datetime(2026, 9, 26, 10, 30), "name": "SIMRS database timeout"},
    "S4": {"ticket": "INC-2026-004", "T": datetime(2026, 9, 25, 14, 5), "name": "Server overload"},
    "S5": {"ticket": "INC-2026-005", "T": datetime(2026, 9, 24, 8, 50), "name": "Farmasi network disruption"},
}


def in_scenario_window(t: datetime) -> bool:
    return any(s["T"] - timedelta(minutes=45) <= t <= s["T"] + timedelta(minutes=90) for s in SCENARIOS.values())


# ----------------------------------------------------------------------------
# Topology, inventory
# ----------------------------------------------------------------------------
def mac(n: int) -> str:
    return "00:1A:2B:%02X:%02X:%02X" % ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def build_inventory():
    devices: list[dict] = []
    nodes: list[dict] = []
    edges: list[dict] = []
    counter = 1000

    def add_node(hostname, ip, dtype, vlan, unit, layer, **meta):
        nodes.append(
            {
                "id": hostname,
                "hostname": hostname,
                "ip": ip,
                "device_type": dtype,
                "vlan": vlan,
                "unit": unit,
                "status": "healthy",
                "layer": layer,
                "meta": meta,
            }
        )

    for h, ip, t, v, u in NET_GEAR:
        add_node(h, ip, t, v, u, {"router": 0, "core_switch": 1, "distribution_switch": 2}[t])
        counter += 1
        devices.append(
            dict(
                hostname=h,
                ip_address=ip,
                mac_address=mac(counter),
                unit=u,
                vlan=v,
                device_type=t,
                os="NetOS 4.2",
                switch="",
                port="",
                status="online",
                last_seen="2026-09-28 23:50:00",
            )
        )
    for h, ip, role, os_, boot in SERVERS:
        add_node(h, ip, "server", 20, "IT", 1, role=role, boot_time=boot, os=os_)
    edges.append(dict(source="CORE-SW-01", target="RTR-CORE", source_interface="Te1/0/24", target_interface="Te0/0/0", link_type="uplink"))
    for i, (h, *_rest) in enumerate(SERVERS, start=1):
        edges.append(dict(source=h, target="RTR-CORE", source_interface="eth0", target_interface=f"Gi0/{i}", link_type="server"))
    for i, d in enumerate(["SW-DIST-01", "SW-DIST-02"], start=1):
        edges.append(dict(source=d, target="CORE-SW-01", source_interface="Te1/0/1", target_interface=f"Te1/0/{i}", link_type="uplink"))

    dist_port = {"SW-DIST-01": 0, "SW-DIST-02": 0}
    for unit, (slug, vlan, subnet, n_pc, access, dist) in UNITS.items():
        acc_ip = "10.10.0.%d" % (11 + list(UNITS).index(unit))
        add_node(access, acc_ip, "access_switch", 10, unit, 3, uplink="Gi0/48")
        counter += 1
        devices.append(
            dict(
                hostname=access,
                ip_address=acc_ip,
                mac_address=mac(counter),
                unit=unit,
                vlan=10,
                device_type="access_switch",
                os="NetOS 4.2",
                switch=dist,
                port="Gi0/48",
                status="online",
                last_seen="2026-09-28 23:50:00",
            )
        )
        dist_port[dist] += 1
        edges.append(
            dict(source=access, target=dist, source_interface="Gi0/48", target_interface=f"Gi0/{dist_port[dist]}", link_type="uplink")
        )
        for i in range(1, n_pc + 1):
            host = f"PC-{slug}-{i:03d}"
            ip = f"{subnet}.{10 + i}"
            counter += 1
            os_ = rng.choice(["Windows 10 Pro", "Windows 11 Pro", "Windows 10 Pro"])
            devices.append(
                dict(
                    hostname=host,
                    ip_address=ip,
                    mac_address=mac(counter),
                    unit=unit,
                    vlan=vlan,
                    device_type="pc",
                    os=os_,
                    switch=access,
                    port=f"Gi0/{i}",
                    status="online",
                    last_seen="2026-09-28 23:50:00",
                )
            )
            add_node(host, ip, "pc", vlan, unit, 4)
            edges.append(dict(source=host, target=access, source_interface="eth0", target_interface=f"Gi0/{i}", link_type="access"))
        if unit in PRINTER_UNITS:
            host = f"PRN-{slug}-001"
            ip = f"{subnet}.{10 + n_pc + 1}"
            counter += 1
            devices.append(
                dict(
                    hostname=host,
                    ip_address=ip,
                    mac_address=mac(counter),
                    unit=unit,
                    vlan=vlan,
                    device_type="printer",
                    os="Embedded",
                    switch=access,
                    port=f"Gi0/{n_pc + 1}",
                    status="online",
                    last_seen="2026-09-28 23:50:00",
                )
            )
            add_node(host, ip, "printer", vlan, unit, 4)
            edges.append(dict(source=host, target=access, source_interface="eth0", target_interface=f"Gi0/{n_pc + 1}", link_type="access"))
    topo = {
        "hospital": "RS Yogyakarta",
        "synthetic": True,
        "vlans": {str(k): v for k, v in VLANS.items()},
        "dns_records": DNS_RECORDS,
        "nodes": nodes,
        "edges": edges,
    }
    return devices, topo


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# ----------------------------------------------------------------------------
# Logs
# ----------------------------------------------------------------------------
SLOG: list[dict] = []
NLOG: list[dict] = []
SVC: list[dict] = []
ANOMALY_NET = {
    "PACKET_LOSS",
    "DNS_FAILURE",
    "HIGH_LATENCY",
    "CONNECTION_REFUSED",
    "TIMEOUT",
    "INTERFACE_DOWN",
    "INTERFACE_ERRORS",
    "VLAN_MISCONFIG",
    "GATEWAY_UNREACHABLE",
}


def slog(t, host, service, level, event, msg, ip="", **meta):
    SLOG.append(
        dict(
            timestamp=fmt(t),
            hostname=host,
            service=service,
            level=level,
            event_type=event,
            message=msg,
            source_ip=ip,
            metadata=json.dumps(meta, sort_keys=True) if meta else "{}",
        )
    )


def nlog(t, src, dst, proto, port, lat, loss, status, event, msg, iface="", crc=0):
    NLOG.append(
        dict(
            timestamp=fmt(t),
            source_device=src,
            destination=dst,
            protocol=proto,
            port=port,
            latency_ms=round(lat, 1),
            packet_loss=round(loss, 1),
            status=status,
            event_type=event,
            message=msg,
            interface=iface,
            crc_errors=crc,
        )
    )


def jitter(dt: datetime, seconds: int = 20) -> datetime:
    return dt + timedelta(seconds=rng.randint(0, seconds))


def minutes(t0: datetime, t1: datetime, step: float = 1.0):
    t = t0
    while t <= t1:
        yield t
        t += timedelta(minutes=step)


def hour_of_day_active(t: datetime) -> bool:
    return 7 <= t.hour < 20


PATHS = [
    "/api/queue",
    "/api/billing/invoice",
    "/api/pharmacy/orders",
    "/api/lab/orders",
    "/api/registration/schedule",
    "/api/session/refresh",
]
PC_HOSTS: list[tuple[str, str, str]] = []  # (hostname, ip, unit)


def all_pcs():
    return PC_HOSTS


def resource_sample(t, host, cpu, mem, disk=None, **extra):
    disk = disk if disk is not None else rng.uniform(40, 58)
    slog(
        t,
        host,
        "system",
        "INFO",
        "RESOURCE_SAMPLE",
        f"cpu={cpu:.1f}% mem={mem:.1f}% disk={disk:.1f}%",
        "",
        cpu=round(cpu, 1),
        memory=round(mem, 1),
        disk=round(disk, 1),
        **extra,
    )


def base_cpu(host, t):
    day = hour_of_day_active(t)
    return {
        "SIMRS-APP-01": rng.uniform(38, 58) if day else rng.uniform(12, 24),
        "SIMRS-DB-01": rng.uniform(25, 45) if day else rng.uniform(8, 18),
        "DNS-01": rng.uniform(5, 14),
        "FILE-01": rng.uniform(10, 30),
        "MONITOR-01": rng.uniform(15, 30),
    }[host]


def base_mem(host):
    return {
        "SIMRS-APP-01": rng.uniform(58, 66),
        "SIMRS-DB-01": rng.uniform(64, 74),
        "DNS-01": rng.uniform(22, 30),
        "FILE-01": rng.uniform(40, 55),
        "MONITOR-01": rng.uniform(45, 55),
    }[host]


def gen_baseline():
    t = START
    while t <= END:
        day = hour_of_day_active(t)
        # resource samples hourly for every server
        for host, *_ in SERVERS:
            resource_sample(jitter(t, 300), host, base_cpu(host, t), base_mem(host))
        # SIMRS application requests
        for _ in range(14 if day else 4):
            pc = rng.choice(PC_HOSTS)
            ms = int(rng.gauss(140, 35))
            ms = max(60, ms)
            tt = jitter(t, 3500)
            r = rng.random()
            if r < 0.006 and not in_scenario_window(tt):
                slog(
                    tt,
                    "SIMRS-APP-01",
                    "simrs",
                    "ERROR",
                    "APP_ERROR",
                    "Unhandled exception in report module (retry succeeded)",
                    pc[1],
                    unit=pc[2],
                )
            elif r < 0.02 and not in_scenario_window(tt):
                slog(
                    tt,
                    "SIMRS-APP-01",
                    "simrs",
                    "WARN",
                    "SLOW_RESPONSE",
                    f"GET {rng.choice(PATHS)} 200 {ms + 1200}ms",
                    pc[1],
                    response_ms=ms + 1200,
                    unit=pc[2],
                )
            elif r < 0.03:
                slog(
                    tt,
                    "SIMRS-APP-01",
                    "simrs",
                    "WARN",
                    "AUTH_FAILURE",
                    f"Login failed for user usr-{rng.randint(100, 260)} (bad credentials)",
                    pc[1],
                    unit=pc[2],
                )
            else:
                slog(
                    tt,
                    "SIMRS-APP-01",
                    "simrs",
                    "INFO",
                    "HTTP_REQUEST_OK",
                    f"GET {rng.choice(PATHS)} 200 {ms}ms",
                    pc[1],
                    status_code=200,
                    response_ms=ms,
                    unit=pc[2],
                )
        # database
        for _ in range(8 if day else 4):
            tt = jitter(t, 3500)
            if rng.random() < 0.02 and not in_scenario_window(tt):
                slog(
                    tt,
                    "SIMRS-DB-01",
                    "database",
                    "WARN",
                    "DB_QUERY_SLOW",
                    f"Slow query {rng.randint(1200, 2400)}ms on reporting view",
                    "10.20.0.10",
                )
            else:
                slog(
                    tt,
                    "SIMRS-DB-01",
                    "database",
                    "INFO",
                    "DB_CONN_OK",
                    f"Connection accepted from SIMRS-APP-01 (active={rng.randint(12, 34)})",
                    "10.20.0.10",
                    active=0,
                )
        # dns
        for _ in range(10 if day else 4):
            pc = rng.choice(PC_HOSTS)
            tt = jitter(t, 3500)
            if rng.random() < 0.01 and not in_scenario_window(tt):
                slog(tt, "DNS-01", "dns", "WARN", "DNS_QUERY_FAIL", "NXDOMAIN for simrs-intranet.internal (client typo)", pc[1])
            else:
                slog(
                    tt,
                    "DNS-01",
                    "dns",
                    "INFO",
                    "DNS_QUERY_OK",
                    f"A simrs.internal -> 10.20.0.10 ({rng.randint(2, 9)}ms)",
                    pc[1],
                    response_ms=5,
                )
        for _ in range(4 if day else 2):
            slog(
                jitter(t, 3500),
                "FILE-01",
                "file",
                "INFO",
                "FILE_ACCESS_OK",
                f"SMB session opened share=admin-docs ({rng.randint(1, 9)} files)",
                rng.choice(PC_HOSTS)[1],
            )
        for _ in range(6):
            slog(
                jitter(t, 3500),
                "MONITOR-01",
                "monitoring",
                "INFO",
                "HEALTHCHECK_OK",
                f"probe SIMRS-APP-01 200 {rng.randint(90, 160)}ms",
                "10.20.0.30",
            )
        # network probes
        for _ in range(16):
            pc = rng.choice(PC_HOSTS)
            tt = jitter(t, 3500)
            dst, proto, port = rng.choices(
                [("SIMRS-APP-01", "TCP", 8080), ("DNS-01", "UDP", 53), ("RTR-CORE", "ICMP", 0)], weights=[6, 2, 2]
            )[0]
            lat = rng.uniform(1.2, 8.5)
            if rng.random() < 0.03:
                nlog(
                    tt,
                    pc[0],
                    dst,
                    proto,
                    port,
                    rng.uniform(30, 70),
                    rng.uniform(0, 1.5),
                    "ok",
                    "LATENCY_BLIP",
                    "transient latency blip within tolerance",
                )
            else:
                nlog(tt, pc[0], dst, proto, port, lat, 0, "ok", "PING_OK" if proto == "ICMP" else "NORMAL_TRAFFIC", "probe ok")
        t += timedelta(hours=1)
    gen_monitor_probes(START, END, 30.0)
    # access switch uplink probes (IP SLA) every 30 min
    t = START
    while t <= END:
        for unit, (_, _, _, _, access, dist) in UNITS.items():
            nlog(jitter(t, 120), access, dist, "ICMP", 0, rng.uniform(0.6, 2.4), 0, "ok", "PING_OK", "uplink ip-sla ok", "Gi0/48", 0)
        t += timedelta(minutes=30)
    # scattered anomalies outside scenario windows (noise the correlator must ignore)
    kinds = [
        ("TIMEOUT", "timeout to file share"),
        ("CONNECTION_REFUSED", "connection refused on port 445"),
        ("VLAN_MISCONFIG", "port moved to wrong VLAN after patching"),
        ("HIGH_LATENCY", "high latency on uplink"),
        ("PACKET_LOSS", "isolated packet loss burst"),
        ("GATEWAY_UNREACHABLE", "gateway briefly unreachable"),
    ]
    placed = 0
    while placed < 30:
        tt = START + timedelta(minutes=rng.randint(0, int((END - START).total_seconds() // 60)))
        if in_scenario_window(tt):
            continue
        pc = rng.choice(PC_HOSTS)
        ev, msg = rng.choice(kinds)
        nlog(tt, pc[0], "SIMRS-APP-01", "TCP", 8080, rng.uniform(120, 900), rng.uniform(5, 30), "degraded", ev, msg)
        placed += 1


def svc_snapshot(t, overrides: dict[str, dict] | None = None):
    overrides = overrides or {}
    for name, server, port, endpoint in SERVICES:
        o = overrides.get(name, {})
        status = o.get("status", "running")
        rt = o.get("rt", (rng.randint(90, 150) if name in {"SIMRS", "SIM-APOTEK", "MONITORING"} else rng.randint(3, 14)))
        http = o.get("http", 200 if name in {"SIMRS", "SIM-APOTEK", "MONITORING"} else 0)
        SVC.append(
            dict(
                service=name,
                server=server,
                status=status,
                response_time=rt,
                last_checked=fmt(t),
                endpoint=endpoint,
                port=port,
                http_status=http,
            )
        )


def gen_service_baseline():
    t = START
    while t <= END:
        svc_snapshot(t)
        t += timedelta(hours=1)


def gen_monitor_probes(t0: datetime, t1: datetime, step: float, skip: set[str] | None = None):
    """MONITOR-01 -> servers / access switches ICMP probes (monitoring vantage point)."""
    skip = skip or set()
    targets = [h for h, *_ in SERVERS if h != "MONITOR-01"] + [v[4] for v in UNITS.values()]
    for t in minutes(t0, t1, step):
        for dst in targets:
            if dst in skip:
                continue
            nlog(
                t + timedelta(seconds=rng.randint(0, 25)),
                "MONITOR-01",
                dst,
                "ICMP",
                0,
                rng.uniform(0.4, 2.2),
                0,
                "ok",
                "PING_OK",
                "icmp echo ok",
            )


def gen_scenario_common(T: datetime, unit_hint: str | None = None, skip_switches: set[str] | None = None):
    """Control-group probes + healthy background inside the +-30 min window."""
    gen_monitor_probes(T - timedelta(minutes=20), T + timedelta(minutes=35), 1.0, skip_switches)
    controls = ["PC-POLI2-001", "PC-POLI1-001", "PC-KASIR-001", "PC-FARMASI-001", "PC-LAB-001", "PC-IGD-001"]
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=35), 1):
        for c in controls:
            if unit_hint and c.startswith(f"PC-{UNITS[unit_hint][0]}-"):
                continue
            nlog(
                t + timedelta(seconds=rng.randint(0, 40)),
                c,
                "SIMRS-APP-01",
                "TCP",
                8080,
                rng.uniform(1.4, 7.0),
                0,
                "ok",
                "NORMAL_TRAFFIC",
                "probe ok",
            )


def s1_poli3(T):
    """Switch/uplink degradation on SW-POLI3 -> multiple Poli 3 endpoints lose SIMRS."""
    ips = {f"PC-POLI3-{i:03d}": f"10.30.3.{10 + i}" for i in range(1, 13)}
    targets = {1: 18.0, 2: 15.0, 3: 21.0, 4: 17.0, 5: 19.0, 6: 16.0}
    # uplink degradation begins ~4 min before users complain
    for k, t in enumerate(minutes(T - timedelta(minutes=4), T + timedelta(minutes=25), 0.5)):
        prog = min(1.0, (k + 1) / 14)
        lat = 40 + 340 * prog + rng.uniform(-15, 25)
        loss = 3 + 11 * prog + rng.uniform(-1, 1.5)
        crc = int(120 + 3300 * prog + rng.randint(0, 60))
        ev = "INTERFACE_ERRORS" if k % 2 == 0 else "HIGH_LATENCY"
        nlog(
            t,
            "SW-POLI3",
            "SW-DIST-01",
            "ICMP",
            0,
            lat,
            loss,
            "degraded",
            ev,
            ("Gi0/48 input errors increasing (CRC)" if ev == "INTERFACE_ERRORS" else "uplink latency above threshold"),
            "Gi0/48",
            crc,
        )
    # endpoints (first onset ~ T-2 min; onset PC-POLI3-001 first)
    for i, target in targets.items():
        host = f"PC-POLI3-{i:03d}"
        start = T - timedelta(minutes=2) + timedelta(seconds=(i - 1) * 6)
        for t in minutes(start, T + timedelta(minutes=23), 0.75):
            loss = max(4.0, rng.gauss(target, 2.2))
            if rng.random() < 0.18:
                nlog(
                    t,
                    host,
                    "SIMRS-APP-01",
                    "TCP",
                    8080,
                    rng.uniform(2500, 5000),
                    max(4.0, rng.gauss(target, 2.2)),
                    "failed",
                    "TIMEOUT",
                    "request to SIMRS-APP-01:8080 timed out",
                )
            else:
                nlog(
                    t,
                    host,
                    "SIMRS-APP-01",
                    "TCP",
                    8080,
                    rng.uniform(150, 520),
                    loss,
                    "degraded",
                    "PACKET_LOSS",
                    f"packet loss {loss:.0f}% to SIMRS-APP-01",
                )
    for i in range(7, 13):  # peers on the same switch that are only marginally affected
        host = f"PC-POLI3-{i:03d}"
        for t in minutes(T - timedelta(minutes=1), T + timedelta(minutes=20), 2):
            nlog(t, host, "SIMRS-APP-01", "TCP", 8080, rng.uniform(4, 25), rng.choice([0, 0, 0.5]), "ok", "NORMAL_TRAFFIC", "probe ok")
    # server side: SIMRS-APP-01 sees timeouts only for Poli 3 source IPs
    seq = [(T - timedelta(seconds=-2), "HTTP_TIMEOUT", "ERROR"), (T + timedelta(seconds=5), "APP_ERROR", "ERROR")]
    for t in minutes(T + timedelta(seconds=2), T + timedelta(minutes=22), 0.4):
        i = rng.randint(1, 6)
        ip = ips[f"PC-POLI3-{i:03d}"]
        if rng.random() < 0.6:
            slog(
                t, "SIMRS-APP-01", "simrs", "ERROR", "HTTP_TIMEOUT", f"upstream request timeout after 30000ms from {ip}", ip, unit="Poli 3"
            )
        else:
            slog(t, "SIMRS-APP-01", "simrs", "ERROR", "APP_ERROR", f"session aborted: connection reset by peer {ip}", ip, unit="Poli 3")
    slog(
        T + timedelta(seconds=2),
        "SIMRS-APP-01",
        "simrs",
        "ERROR",
        "HTTP_TIMEOUT",
        f"upstream request timeout after 30000ms from {ips['PC-POLI3-001']}",
        ips["PC-POLI3-001"],
        unit="Poli 3",
    )
    slog(
        T + timedelta(seconds=5),
        "SIMRS-APP-01",
        "simrs",
        "ERROR",
        "APP_ERROR",
        f"session aborted: connection reset by peer {ips['PC-POLI3-001']}",
        ips["PC-POLI3-001"],
        unit="Poli 3",
    )
    _ = seq
    for t in minutes(T - timedelta(minutes=10), T + timedelta(minutes=30), 0.5):  # other units keep working
        pc = rng.choice([p for p in PC_HOSTS if p[2] != "Poli 3"])
        ms = int(rng.gauss(135, 25))
        slog(
            t,
            "SIMRS-APP-01",
            "simrs",
            "INFO",
            "HTTP_REQUEST_OK",
            f"GET {rng.choice(PATHS)} 200 {ms}ms",
            pc[1],
            status_code=200,
            response_ms=ms,
            unit=pc[2],
        )
    for t in minutes(T - timedelta(minutes=10), T + timedelta(minutes=30), 1):
        slog(t, "MONITOR-01", "monitoring", "INFO", "HEALTHCHECK_OK", f"probe SIMRS-APP-01 200 {rng.randint(100, 140)}ms", "10.20.0.30")
        resource_sample(t, "SIMRS-APP-01", rng.uniform(38, 52), rng.uniform(60, 65))
        resource_sample(t, "SIMRS-DB-01", rng.uniform(28, 42), rng.uniform(66, 72))
        if rng.random() < 0.6:
            slog(
                t,
                "DNS-01",
                "dns",
                "INFO",
                "DNS_QUERY_OK",
                f"A simrs.internal -> 10.20.0.10 ({rng.randint(3, 8)}ms)",
                ips[f"PC-POLI3-{rng.randint(1, 6):03d}"],
                response_ms=5,
            )
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=45)):
        svc_snapshot(t)


def s2_dns(T):
    onset = T - timedelta(minutes=1, seconds=20)
    for t in minutes(onset, T + timedelta(minutes=40), 0.25):
        pc = rng.choice(PC_HOSTS)
        slog(
            t,
            "DNS-01",
            "dns",
            "ERROR",
            "DNS_QUERY_FAIL",
            "SERVFAIL for simrs.internal: zone data unavailable (resolver worker unresponsive)",
            pc[1],
            rcode="SERVFAIL",
        )
    slog(
        onset - timedelta(seconds=10),
        "DNS-01",
        "dns",
        "WARN",
        "RESOURCE_HIGH_CPU",
        "resolver worker stalled, request queue growing",
        "",
        queue=480,
    )
    for t in minutes(onset, T + timedelta(minutes=35), 0.5):
        pc = rng.choice(PC_HOSTS)
        nlog(
            t,
            pc[0],
            "DNS-01",
            "UDP",
            53,
            rng.uniform(3000, 5000),
            0,
            "failed",
            "DNS_FAILURE",
            "DNS query for simrs.internal failed (SERVFAIL)",
        )
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=35), 1):
        for c in ["PC-POLI1-002", "PC-KASIR-002", "PC-IGD-002"]:
            nlog(
                t + timedelta(seconds=rng.randint(0, 40)),
                c,
                "SIMRS-APP-01",
                "ICMP",
                0,
                rng.uniform(1.4, 7.0),
                0,
                "ok",
                "PING_OK",
                "ping by IP ok",
            )
        resource_sample(t, "DNS-01", rng.uniform(6, 13), rng.uniform(24, 30))
        resource_sample(t, "SIMRS-APP-01", rng.uniform(38, 52), rng.uniform(60, 65))
        resource_sample(t, "SIMRS-DB-01", rng.uniform(28, 42), rng.uniform(66, 72))
        slog(
            t, "MONITOR-01", "monitoring", "INFO", "HEALTHCHECK_OK", f"probe SIMRS-APP-01 by IP 200 {rng.randint(100, 140)}ms", "10.20.0.30"
        )
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=45)):
        down = onset <= t <= T + timedelta(minutes=41)
        svc_snapshot(t, {"DNS": {"status": "down", "rt": 5000, "http": 0}} if down else None)


def s3_db(T):
    for t in minutes(T - timedelta(minutes=3), T + timedelta(minutes=30), 0.5):
        pc = rng.choice(PC_HOSTS)
        slog(
            t,
            "SIMRS-DB-01",
            "database",
            "WARN",
            "DB_QUERY_SLOW",
            f"Slow query {rng.randint(5200, 9800)}ms (waiting on lock/connection slot)",
            "10.20.0.10",
        )
    slog(
        T - timedelta(seconds=10),
        "SIMRS-DB-01",
        "database",
        "ERROR",
        "DB_CONN_POOL_EXHAUSTED",
        "remaining connection slots are reserved (max_connections=100 reached)",
        "10.20.0.10",
        active=100,
    )
    for t in minutes(T - timedelta(seconds=10), T + timedelta(minutes=30), 0.25):
        slog(
            t,
            "SIMRS-DB-01",
            "database",
            "ERROR",
            "DB_CONN_POOL_EXHAUSTED",
            "remaining connection slots are reserved (max_connections=100 reached)",
            "10.20.0.10",
            active=100,
        )
    slog(
        T + timedelta(seconds=2),
        "SIMRS-APP-01",
        "simrs",
        "ERROR",
        "DB_CONN_TIMEOUT",
        "Database connection timeout after 10000ms (pool exhausted)",
        "10.20.0.11",
    )
    slog(
        T + timedelta(seconds=5),
        "SIMRS-APP-01",
        "simrs",
        "ERROR",
        "APP_ERROR",
        "HTTP 500: unable to obtain database connection",
        "10.20.0.11",
    )
    slog(
        T + timedelta(seconds=10), "SIMRS-APP-01", "simrs", "ERROR", "HTTP_TIMEOUT", "upstream request timeout after 30000ms", "10.20.0.11"
    )
    for t in minutes(T, T + timedelta(minutes=30), 0.3):
        pc = rng.choice(PC_HOSTS)
        ev = rng.choice(["DB_CONN_TIMEOUT", "APP_ERROR", "HTTP_TIMEOUT"])
        msg = {
            "DB_CONN_TIMEOUT": "Database connection timeout after 10000ms (pool exhausted)",
            "APP_ERROR": "HTTP 500: unable to obtain database connection",
            "HTTP_TIMEOUT": f"upstream request timeout after 30000ms from {pc[1]}",
        }[ev]
        slog(t, "SIMRS-APP-01", "simrs", "ERROR", ev, msg, pc[1], unit=pc[2])
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=35), 1):
        resource_sample(t, "SIMRS-DB-01", rng.uniform(78, 92), rng.uniform(88, 94), connections=100)
        resource_sample(t, "SIMRS-APP-01", rng.uniform(40, 55), rng.uniform(60, 66))
        resource_sample(t, "DNS-01", rng.uniform(6, 13), rng.uniform(24, 30))
        slog(
            t,
            "DNS-01",
            "dns",
            "INFO",
            "DNS_QUERY_OK",
            f"A simrs.internal -> 10.20.0.10 ({rng.randint(3, 8)}ms)",
            rng.choice(PC_HOSTS)[1],
            response_ms=5,
        )
        slog(
            t,
            "MONITOR-01",
            "monitoring",
            "ERROR" if t >= T - timedelta(minutes=1) else "INFO",
            "HEALTHCHECK_FAIL" if t >= T - timedelta(minutes=1) else "HEALTHCHECK_OK",
            (
                "probe SIMRS-APP-01 503 (database unreachable)"
                if t >= T - timedelta(minutes=1)
                else f"probe SIMRS-APP-01 200 {rng.randint(100, 140)}ms"
            ),
            "10.20.0.30",
        )
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=45)):
        bad = T - timedelta(minutes=2) <= t <= T + timedelta(minutes=32)
        svc_snapshot(
            t,
            (
                {"DATABASE": {"status": "degraded", "rt": 4500, "http": 0}, "SIMRS": {"status": "degraded", "rt": 8000, "http": 503}}
                if bad
                else None
            ),
        )


def s4_overload(T):
    ramp_start = T - timedelta(minutes=10)
    for t in minutes(ramp_start, T + timedelta(minutes=35), 1):
        prog = min(1.0, ((t - ramp_start).total_seconds() / 60) / 10)
        cpu = 55 + 42 * prog + rng.uniform(-2, 2) if t <= T + timedelta(minutes=30) else rng.uniform(45, 60)
        mem = 68 + 25 * prog + rng.uniform(-1, 1) if t <= T + timedelta(minutes=30) else rng.uniform(62, 68)
        resource_sample(t, "SIMRS-APP-01", cpu, mem)
        if cpu > 88 and t <= T + timedelta(minutes=30):
            slog(
                t,
                "SIMRS-APP-01",
                "system",
                "WARN",
                "RESOURCE_HIGH_CPU",
                f"cpu usage {cpu:.0f}% above threshold 90% (report-export job)",
                "",
                cpu=round(cpu, 1),
            )
    for t in minutes(T - timedelta(minutes=1), T + timedelta(minutes=30), 0.3):
        pc = rng.choice(PC_HOSTS)
        ms = rng.randint(4200, 9500)
        if rng.random() < 0.25:
            slog(
                t,
                "SIMRS-APP-01",
                "simrs",
                "ERROR",
                "HTTP_TIMEOUT",
                f"upstream request timeout after 30000ms from {pc[1]}",
                pc[1],
                unit=pc[2],
            )
        else:
            slog(
                t,
                "SIMRS-APP-01",
                "simrs",
                "WARN",
                "SLOW_RESPONSE",
                f"GET {rng.choice(PATHS)} 200 {ms}ms",
                pc[1],
                response_ms=ms,
                unit=pc[2],
            )
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=35), 1):
        resource_sample(t, "SIMRS-DB-01", rng.uniform(30, 45), rng.uniform(66, 72))
        slog(
            t,
            "DNS-01",
            "dns",
            "INFO",
            "DNS_QUERY_OK",
            f"A simrs.internal -> 10.20.0.10 ({rng.randint(3, 8)}ms)",
            rng.choice(PC_HOSTS)[1],
            response_ms=5,
        )
        slog(t, "MONITOR-01", "monitoring", "WARN", "SLOW_RESPONSE", f"probe SIMRS-APP-01 200 {rng.randint(5000, 8000)}ms", "10.20.0.30")
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=45)):
        bad = T - timedelta(minutes=6) <= t <= T + timedelta(minutes=31)
        svc_snapshot(t, {"SIMRS": {"status": "degraded", "rt": 6500, "http": 200}} if bad else None)


def s5_farmasi(T):
    down = T - timedelta(minutes=2, seconds=10)
    nlog(
        down,
        "SW-FARMASI",
        "SW-DIST-01",
        "ICMP",
        0,
        0,
        100,
        "failed",
        "INTERFACE_DOWN",
        "Gi0/48 changed state to down (uplink)",
        "Gi0/48",
        0,
    )
    nlog(
        down + timedelta(seconds=1),
        "SW-DIST-01",
        "SW-FARMASI",
        "ICMP",
        0,
        0,
        100,
        "failed",
        "INTERFACE_DOWN",
        "Gi0/4 changed state to down (link to SW-FARMASI)",
        "Gi0/4",
        0,
    )
    nlog(
        down + timedelta(seconds=45),
        "SW-FARMASI",
        "SW-DIST-01",
        "ICMP",
        0,
        0,
        100,
        "failed",
        "INTERFACE_DOWN",
        "Gi0/48 flapping, remains down",
        "Gi0/48",
        0,
    )
    for t in minutes(down, T + timedelta(minutes=35), 1):
        nlog(t, "MONITOR-01", "SW-FARMASI", "ICMP", 0, 0, 100, "failed", "GATEWAY_UNREACHABLE", "SW-FARMASI management address unreachable")
    for i in range(1, 11):
        host = f"PC-FARMASI-{i:03d}"
        for t in minutes(down + timedelta(seconds=30 + i * 3), T + timedelta(minutes=35), 0.5):
            nlog(t, host, "SIMRS-APP-01", "TCP", 8081, 0, 100, "failed", "GATEWAY_UNREACHABLE", "default gateway 10.40.0.1 unreachable")
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=35), 1):
        resource_sample(t, "SIMRS-APP-01", rng.uniform(38, 52), rng.uniform(60, 65))
        resource_sample(t, "SIMRS-DB-01", rng.uniform(28, 42), rng.uniform(66, 72))
        slog(t, "MONITOR-01", "monitoring", "INFO", "HEALTHCHECK_OK", f"probe SIMRS-APP-01 200 {rng.randint(100, 140)}ms", "10.20.0.30")
        slog(
            t,
            "DNS-01",
            "dns",
            "INFO",
            "DNS_QUERY_OK",
            f"A simrs.internal -> 10.20.0.10 ({rng.randint(3, 8)}ms)",
            rng.choice([p for p in PC_HOSTS if p[2] != "Farmasi"])[1],
            response_ms=5,
        )
        pc = rng.choice([p for p in PC_HOSTS if p[2] != "Farmasi"])
        slog(
            t,
            "SIMRS-APP-01",
            "simrs",
            "INFO",
            "HTTP_REQUEST_OK",
            f"GET {rng.choice(PATHS)} 200 {rng.randint(110, 160)}ms",
            pc[1],
            status_code=200,
            unit=pc[2],
        )
    for t in minutes(T - timedelta(minutes=20), T + timedelta(minutes=45)):
        svc_snapshot(t)


# ----------------------------------------------------------------------------
# Historical incidents
# ----------------------------------------------------------------------------
PATTERNS = {
    "access_switch_uplink": dict(
        cat="application",
        rcc="network",
        sev="medium",
        svc="SIMRS",
        mins=(35, 25),
        desc=[
            "SIMRS tidak dapat diakses dari {u}, beberapa komputer mengalami packet loss dan koneksi putus-putus.",
            "Beberapa komputer di {u} tidak bisa membuka SIMRS, internet umum masih normal.",
            "SIMRS di {u} sangat lambat lalu timeout, komputer unit lain normal.",
            "Aplikasi SIMRS {u} tidak merespons sejak pagi, ping ke server putus-putus.",
        ],
        rc=[
            "Uplink access switch {sw} mengalami CRC error sehingga packet loss tinggi",
            "Access switch {sw} mengalami degradasi uplink (SFP mulai rusak)",
            "Patch cable uplink {sw} longgar menyebabkan packet loss intermiten",
        ],
        res=[
            "Ganti SFP dan patch cable uplink {sw}, verifikasi tidak ada interface error",
            "Reseat kabel uplink, bersihkan port, restart access switch {sw} sesuai SOP-003",
            "Ganti kabel uplink {sw} dan pantau counter interface selama 30 menit",
        ],
    ),
    "switch_down": dict(
        cat="network",
        rcc="network",
        sev="high",
        svc="SIMRS",
        mins=(55, 30),
        desc=[
            "Seluruh komputer {u} tidak dapat mengakses aplikasi, tidak ada koneksi jaringan.",
            "Beberapa komputer di {u} tidak dapat terhubung ke jaringan sama sekali.",
            "{u} offline: semua PC tidak bisa konek ke SIMRS maupun internet.",
        ],
        rc=[
            "Interface uplink {sw} down (port fisik mati)",
            "Access switch {sw} mati karena power adaptor rusak",
            "Uplink {sw} flapping lalu down akibat kabel putus",
        ],
        res=[
            "Ganti kabel/transceiver uplink {sw} dan aktifkan kembali port sesuai SOP-007",
            "Ganti power adaptor {sw} lalu verifikasi konektivitas semua endpoint",
            "Pasang kabel uplink baru dan restore konfigurasi port {sw}",
        ],
    ),
    "dns_failure": dict(
        cat="dns",
        rcc="dns",
        sev="critical",
        svc="DNS",
        mins=(40, 20),
        desc=[
            "DNS internal tidak bisa resolve simrs.internal dari semua unit.",
            "Aplikasi SIMRS tidak bisa dibuka dengan nama, tetapi bisa lewat alamat IP.",
            "nslookup simrs.internal gagal SERVFAIL di banyak komputer.",
        ],
        rc=[
            "Proses resolver pada DNS-01 hang dan tidak merespons query",
            "Zone file simrs.internal korup setelah perubahan record",
            "DNS-01 kehabisan worker thread akibat lonjakan query",
        ],
        res=[
            "Restart layanan DNS setelah validasi zone file (SOP-002)",
            "Restore zone file dari backup terakhir lalu reload resolver",
            "Restart resolver DNS-01 dan tambah worker thread",
        ],
    ),
    "db_connection": dict(
        cat="database",
        rcc="database",
        sev="critical",
        svc="DATABASE",
        mins=(60, 35),
        desc=[
            "SIMRS error database connection timeout di semua unit.",
            "Semua unit tidak bisa menyimpan transaksi di SIMRS, muncul error 500.",
            "SIMRS lambat lalu gagal, log aplikasi menunjukkan connection timeout ke database.",
        ],
        rc=[
            "Connection pool SIMRS-DB-01 penuh (max_connections tercapai)",
            "Long-running query menahan lock dan menghabiskan koneksi",
            "Idle session menumpuk sehingga slot koneksi habis",
        ],
        res=[
            "Terminate idle session, naikkan max_connections, tuning pool sesuai SOP-005",
            "Batalkan query bermasalah, restart pool aplikasi, tambah indeks",
            "Bersihkan session idle dan set idle timeout",
        ],
    ),
    "server_overload": dict(
        cat="server",
        rcc="server",
        sev="high",
        svc="SIMRS",
        mins=(45, 25),
        desc=[
            "Server SIMRS mengalami response lambat di semua unit.",
            "SIMRS sangat lemot sejak siang, banyak user mengeluh.",
            "Response time SIMRS di atas 5 detik, CPU server terlihat tinggi.",
        ],
        rc=[
            "Job export laporan menghabiskan CPU SIMRS-APP-01",
            "Memory leak pada proses aplikasi menyebabkan swap berlebihan",
            "Lonjakan request bersamaan saat jam kunjungan puncak membebani SIMRS-APP-01",
        ],
        res=[
            "Hentikan job export, jadwalkan ulang di luar jam sibuk, restart service (SOP-006)",
            "Restart proses aplikasi dan naikkan batas memori",
            "Tambah worker aplikasi dan aktifkan rate limit",
        ],
    ),
    "endpoint_issue": dict(
        cat="hardware",
        rcc="hardware",
        sev="low",
        svc="SIMRS",
        mins=(25, 12),
        desc=[
            "Komputer {d} tidak bisa membuka SIMRS, komputer lain di unit normal.",
            "Internet komputer {d} terputus tetapi komputer lain normal.",
            "PC {d} sering disconnect dari jaringan.",
        ],
        rc=["Kabel LAN {d} rusak", "NIC {d} bermasalah", "Port access switch {sw} yang dipakai {d} rusak"],
        res=["Ganti kabel LAN dan uji konektivitas", "Ganti NIC / pindahkan ke port cadangan", "Pindahkan kabel ke port lain pada {sw}"],
    ),
    "auth_failure": dict(
        cat="authentication",
        rcc="authentication",
        sev="medium",
        svc="SIMRS",
        mins=(30, 15),
        desc=[
            "SIMRS tidak bisa login tetapi internet normal.",
            "User {u} tidak dapat login ke SIMRS, muncul pesan autentikasi gagal.",
            "Login SIMRS ditolak untuk beberapa user di {u}.",
        ],
        rc=[
            "Layanan autentikasi SIMRS menolak kredensial akibat time skew server",
            "Akun layanan autentikasi kedaluwarsa",
            "Konfigurasi direktori user tidak sinkron",
        ],
        res=[
            "Sinkronisasi waktu server dan restart layanan autentikasi (SOP-008)",
            "Perpanjang akun layanan dan reset cache token",
            "Sinkronkan direktori user dan verifikasi login",
        ],
    ),
    "service_crash": dict(
        cat="application",
        rcc="application",
        sev="high",
        svc="SIMRS",
        mins=(30, 15),
        desc=[
            "SIMRS tidak bisa dibuka dari semua unit, halaman error 502.",
            "Layanan SIMRS berhenti, tidak ada respons dari server aplikasi.",
            "Aplikasi SIMRS crash berulang, user harus login ulang.",
        ],
        rc=[
            "Proses SIMRS berhenti akibat out-of-memory",
            "Deployment terakhir menyebabkan service crash loop",
            "Service SIMRS-APP-01 berhenti setelah update paket",
        ],
        res=[
            "Restart service SIMRS dan verifikasi health endpoint (SOP-001)",
            "Rollback versi aplikasi ke rilis sebelumnya",
            "Naikkan limit memori service dan aktifkan auto-restart",
        ],
    ),
    "vlan_config": dict(
        cat="configuration",
        rcc="configuration",
        sev="medium",
        svc="SIMRS",
        mins=(40, 20),
        desc=[
            "Komputer baru di {u} tidak bisa akses SIMRS, IP tidak sesuai segmen.",
            "Beberapa PC {u} dapat IP segmen salah setelah pemindahan kabel.",
            "Setelah maintenance, komputer {u} tidak bisa konek ke server.",
        ],
        rc=["Port {sw} berada pada VLAN yang salah setelah patching", "Konfigurasi VLAN trunk {sw} hilang setelah reload"],
        res=["Koreksi VLAN port dan simpan konfigurasi {sw}", "Restore konfigurasi trunk dari backup dan verifikasi VLAN"],
    ),
    "file_service": dict(
        cat="service",
        rcc="service",
        sev="medium",
        svc="FILE SERVER",
        mins=(35, 20),
        desc=["Shared folder di FILE-01 tidak bisa dibuka dari {u}.", "File server tidak merespons, backup harian gagal."],
        rc=["Layanan SMB pada FILE-01 hang", "Disk FILE-01 penuh"],
        res=["Restart layanan SMB dan verifikasi akses share", "Bersihkan disk dan pindahkan arsip lama"],
    ),
    "unknown": dict(
        cat="unknown",
        rcc="unknown",
        sev="low",
        svc="SIMRS",
        mins=(60, 40),
        desc=["Gangguan sesaat pada SIMRS di {u}, sudah normal sendiri.", "Laporan lambat sesaat, tidak bisa direproduksi."],
        rc=["Penyebab tidak dapat ditentukan (gangguan transien)"],
        res=["Dipantau, tidak ada tindakan; ditutup setelah 24 jam normal"],
    ),
}
PATTERN_COUNTS = {
    "access_switch_uplink": 42,
    "switch_down": 14,
    "dns_failure": 20,
    "db_connection": 22,
    "server_overload": 20,
    "endpoint_issue": 20,
    "auth_failure": 15,
    "service_crash": 15,
    "vlan_config": 12,
    "file_service": 8,
    "unknown": 8,
}
SCENARIO_PATTERNS = {
    "S1": ["access_switch_uplink", "switch_down"],
    "S2": ["dns_failure"],
    "S3": ["db_connection"],
    "S4": ["server_overload"],
    "S5": ["switch_down", "access_switch_uplink"],
}


def gen_historical():
    rows = []
    unit_names = list(UNITS)
    for pat, n in PATTERN_COUNTS.items():
        spec = PATTERNS[pat]
        for _ in range(n):
            days = rng.random()
            # ~30% of incidents are recent (last 60 days) so temporal weighting matters
            when = datetime(2026, 9, 18) - timedelta(days=rng.uniform(0, 60) if days < 0.3 else rng.uniform(60, 230))
            when = when.replace(hour=rng.randint(7, 19), minute=rng.randint(0, 59), second=0, microsecond=0)
            unit = rng.choice([u for u in unit_names if u != "IT"])
            slug, _, _, n_pc, access, _ = UNITS[unit]
            dev = f"PC-{slug}-{rng.randint(1, n_pc):03d}"
            sev = spec["sev"]
            if unit == "IGD" and sev in {"low", "medium"}:
                sev = {"low": "medium", "medium": "high"}[sev]
            fmt_args = dict(u=unit, d=dev, sw=access)
            mean, sd = spec["mins"]
            res_min = max(8, int(rng.gauss(mean, sd)))
            rows.append(
                dict(
                    timestamp=fmt(when),
                    unit=(unit if pat not in {"dns_failure", "db_connection", "server_overload", "service_crash"} else "Semua Unit"),
                    device=dev if pat == "endpoint_issue" else "",
                    description=rng.choice(spec["desc"]).format(**fmt_args),
                    category=spec["cat"],
                    severity=sev,
                    status=rng.choice(["resolved", "resolved", "closed"]),
                    affected_service=spec["svc"],
                    root_cause=rng.choice(spec["rc"]).format(**fmt_args),
                    resolution=rng.choice(spec["res"]).format(**fmt_args),
                    resolution_time_minutes=res_min,
                    root_cause_category=spec["rcc"],
                    pattern=pat,
                )
            )
    rows.sort(key=lambda r: r["timestamp"])
    for i, r in enumerate(rows, start=1):
        r["incident_id"] = f"HIST-{i:04d}"
    cols = [
        "incident_id",
        "timestamp",
        "unit",
        "device",
        "description",
        "category",
        "severity",
        "status",
        "affected_service",
        "root_cause",
        "resolution",
        "resolution_time_minutes",
        "root_cause_category",
        "pattern",
    ]
    return [{c: r[c] for c in cols} for r in rows]


# ----------------------------------------------------------------------------
# Tickets + benchmark
# ----------------------------------------------------------------------------
TICKETS = [
    dict(
        ticket_number="INC-2026-001",
        title="SIMRS tidak dapat dibuka dari Poli 3",
        description="Beberapa komputer di Poli 3 tidak dapat membuka SIMRS. Internet umum masih dapat digunakan. Gangguan mulai dirasakan sekitar pukul 09:42.",
        reported_by="Petugas Poli 3",
        affected_unit="Poli 3",
        affected_device="",
        affected_service="SIMRS",
        severity="medium",
        category="application",
        status="open",
        occurred_at="2026-09-28 09:42:00",
        scenario_id="S1",
    ),
    dict(
        ticket_number="INC-2026-002",
        title="DNS internal tidak bisa resolve server SIMRS",
        description="DNS internal tidak bisa resolve simrs.internal dari berbagai unit. Aplikasi SIMRS tidak dapat dibuka dengan nama host. Mulai sekitar pukul 13:15.",
        reported_by="Petugas Kasir",
        affected_unit="Semua Unit",
        affected_device="",
        affected_service="DNS",
        severity="critical",
        category="dns",
        status="open",
        occurred_at="2026-09-27 13:15:00",
        scenario_id="S2",
    ),
    dict(
        ticket_number="INC-2026-003",
        title="SIMRS error database timeout",
        description="SIMRS menampilkan error database connection timeout di semua unit sejak sekitar pukul 10:30. Transaksi tidak dapat disimpan.",
        reported_by="Petugas IGD",
        affected_unit="Semua Unit",
        affected_device="",
        affected_service="DATABASE",
        severity="critical",
        category="database",
        status="open",
        occurred_at="2026-09-26 10:30:00",
        scenario_id="S3",
    ),
    dict(
        ticket_number="INC-2026-004",
        title="Server SIMRS response lambat",
        description="Server SIMRS mengalami response lambat di semua unit sejak sekitar pukul 14:05. Halaman butuh lebih dari 5 detik untuk terbuka.",
        reported_by="Petugas Farmasi",
        affected_unit="Semua Unit",
        affected_device="",
        affected_service="SIMRS",
        severity="high",
        category="server",
        status="open",
        occurred_at="2026-09-25 14:05:00",
        scenario_id="S4",
    ),
    dict(
        ticket_number="INC-2026-005",
        title="Komputer unit Farmasi tidak dapat mengakses aplikasi",
        description="Beberapa komputer di unit farmasi tidak dapat mengakses aplikasi SIM-APOTEK. Mulai sekitar pukul 08:50.",
        reported_by="Apoteker Jaga",
        affected_unit="Farmasi",
        affected_device="",
        affected_service="SIM-APOTEK",
        severity="medium",
        category="application",
        status="open",
        occurred_at="2026-09-24 08:50:00",
        scenario_id="S5",
    ),
    dict(
        ticket_number="INC-2026-006",
        title="SIMRS tidak bisa login",
        description="SIMRS tidak bisa login tetapi internet normal. Muncul pesan autentikasi gagal untuk beberapa user sekitar pukul 15:10.",
        reported_by="Petugas Rekam Medis",
        affected_unit="Rekam Medis",
        affected_device="",
        affected_service="SIMRS",
        severity="medium",
        category="authentication",
        status="open",
        occurred_at="2026-09-27 15:10:00",
        scenario_id="",
    ),
    dict(
        ticket_number="INC-2026-007",
        title="Internet komputer kasir terputus",
        description="Internet komputer kasir terputus tetapi komputer lain normal. Perangkat: PC-KASIR-003. Mulai pukul 11:20.",
        reported_by="Petugas Kasir",
        affected_unit="Kasir",
        affected_device="PC-KASIR-003",
        affected_service="",
        severity="low",
        category="network",
        status="open",
        occurred_at="2026-09-26 11:20:00",
        scenario_id="",
    ),
    dict(
        ticket_number="INC-2026-008",
        title="Printer Laboratorium tidak terdeteksi",
        description="Printer laboratorium tidak terdeteksi dari komputer analis sejak sekitar pukul 08:05.",
        reported_by="Petugas Laboratorium",
        affected_unit="Laboratorium",
        affected_device="PRN-LAB-001",
        affected_service="",
        severity="low",
        category="hardware",
        status="open",
        occurred_at="2026-09-25 08:05:00",
        scenario_id="",
    ),
]

BENCH = {
    "S1": dict(
        texts=[
            ("SIMRS tidak bisa dibuka dari komputer Poli 3.", "application", "medium"),
            (
                "Beberapa komputer di Poli 3 tidak dapat membuka SIMRS. Internet umum masih dapat digunakan. Gangguan mulai sekitar pukul 09:42.",
                "application",
                "medium",
            ),
            ("Aplikasi SIMRS di Poli 3 loading terus lalu timeout.", "application", "medium"),
            ("Poli 3 tidak bisa akses SIMRS, koneksi putus-putus sejak pukul 09:42.", "network", "medium"),
            ("Users in Poli 3 cannot open SIMRS since 09:42, other units are fine.", "application", "medium"),
            ("Dokter di Poli 3 melaporkan SIMRS tidak merespons sejak pukul 09:42.", "application", "medium"),
            ("Komputer Poli 3 mengalami packet loss dan SIMRS tidak bisa diakses.", "network", "medium"),
            ("SIMRS Poli 3 error timeout saat membuka menu pendaftaran.", "application", "medium"),
            ("Beberapa PC di Poli 3 tidak dapat terhubung ke server aplikasi pukul 09:42.", "network", "medium"),
            ("Poli 3 tidak dapat menggunakan SIMRS, unit lain normal.", "application", "medium"),
        ],
        unit="Poli 3",
        service="SIMRS",
        sop=["SOP-003", "SOP-007", "SOP-001"],
        rcc="network",
        tools=["ping_host", "get_network_interface_status", "check_http", "check_dns", "query_service_status", "get_topology_path"],
        tags=[
            "multi_endpoint_loss",
            "switch_interface_errors",
            "switch_latency_high",
            "shared_access_switch",
            "server_healthy",
            "dns_ok",
            "control_group_ok",
        ],
    ),
    "S2": dict(
        texts=[
            ("DNS internal tidak bisa resolve server SIMRS.", "dns", "critical"),
            ("nslookup simrs.internal gagal di banyak komputer sejak pukul 13:15.", "dns", "critical"),
            ("SIMRS tidak bisa dibuka lewat nama host tetapi bisa lewat IP, mulai pukul 13:15. DNS bermasalah.", "dns", "critical"),
            ("Semua unit gagal resolve nama server SIMRS.", "dns", "critical"),
            ("Internal DNS resolution fails for simrs.internal across the hospital since 13:15.", "dns", "critical"),
            ("Komputer di seluruh rumah sakit tidak dapat resolve simrs.internal.", "dns", "critical"),
            ("Nama host server SIMRS tidak bisa di-resolve, DNS error SERVFAIL.", "dns", "critical"),
            ("DNS server tidak menjawab query, semua unit terdampak sejak 13:15.", "dns", "critical"),
            ("Resolve nama simrs.internal timeout di semua komputer.", "dns", "critical"),
            ("Gangguan DNS internal, SIMRS tidak dapat diakses dengan nama.", "dns", "critical"),
        ],
        unit="Semua Unit",
        service="DNS",
        sop=["SOP-002", "SOP-001"],
        rcc="dns",
        tools=["check_dns", "ping_host", "query_service_status", "check_http"],
        tags=["dns_failed", "hospital_wide_impact", "server_healthy"],
    ),
    "S3": dict(
        texts=[
            ("SIMRS error database connection timeout di semua unit.", "database", "critical"),
            ("SIMRS database timeout sejak pukul 10:30, transaksi tidak bisa disimpan.", "database", "critical"),
            ("Semua unit mendapat error 500 di SIMRS, log menunjukkan database timeout.", "database", "critical"),
            ("Koneksi database SIMRS gagal, aplikasi menampilkan connection timeout.", "database", "critical"),
            ("Database SIMRS tidak merespons sejak 10:30 di seluruh rumah sakit.", "database", "critical"),
            ("SIMRS database connection error, semua user terdampak.", "database", "critical"),
            ("Query database SIMRS timeout dan aplikasi gagal menyimpan data.", "database", "critical"),
            ("The SIMRS database connection times out for every unit since 10:30.", "database", "critical"),
            ("SIMRS lambat lalu error database di semua unit pukul 10:30.", "database", "critical"),
            ("Seluruh unit tidak bisa menyimpan transaksi karena database timeout.", "database", "critical"),
        ],
        unit="Semua Unit",
        service="DATABASE",
        sop=["SOP-005", "SOP-001"],
        rcc="database",
        tools=["query_service_status", "get_server_status", "search_logs", "check_http"],
        tags=["db_unhealthy", "db_error_logs", "hospital_wide_impact", "dns_ok"],
    ),
    "S4": dict(
        texts=[
            ("Server SIMRS mengalami response lambat.", "server", "high"),
            ("SIMRS sangat lambat di semua unit sejak pukul 14:05, server terlihat overload.", "server", "high"),
            ("Response server SIMRS lambat, halaman butuh lebih dari 5 detik sejak 14:05.", "server", "high"),
            ("Server aplikasi SIMRS lemot, CPU tinggi, semua unit mengeluh.", "server", "high"),
            ("SIMRS server is very slow for all units since 14:05.", "server", "high"),
            ("Kinerja server SIMRS menurun drastis pukul 14:05, response lambat.", "server", "high"),
            ("Server SIMRS overload, semua komputer merasakan lambat.", "server", "high"),
            ("SIMRS response time tinggi di seluruh rumah sakit sejak 14:05.", "server", "high"),
            ("Semua unit melaporkan SIMRS lambat dan sering timeout.", "server", "high"),
            ("Server SIMRS response lambat, memori dan CPU hampir penuh.", "server", "high"),
        ],
        unit="Semua Unit",
        service="SIMRS",
        sop=["SOP-006", "SOP-004"],
        rcc="server",
        tools=["get_server_status", "check_http", "query_service_status", "search_logs"],
        tags=["server_cpu_high", "http_slow", "hospital_wide_impact", "dns_ok"],
    ),
    "S5": dict(
        texts=[
            ("Beberapa komputer di unit farmasi tidak dapat mengakses aplikasi.", "application", "medium"),
            ("Unit Farmasi tidak bisa membuka SIM-APOTEK sejak pukul 08:50.", "application", "medium"),
            ("Semua komputer Farmasi tidak ada koneksi jaringan sejak 08:50.", "network", "medium"),
            ("Farmasi offline, komputer tidak bisa terhubung ke server.", "network", "medium"),
            ("Pharmacy computers cannot reach the application since 08:50.", "application", "medium"),
            ("Komputer farmasi tidak bisa akses SIMRS maupun SIM-APOTEK, jaringan putus.", "network", "medium"),
            ("SIM-APOTEK tidak bisa dibuka di Farmasi pukul 08:50, unit lain normal.", "application", "medium"),
            ("Apoteker melaporkan seluruh PC Farmasi tidak dapat terhubung ke jaringan.", "network", "medium"),
            ("Aplikasi apotek tidak dapat diakses dari Farmasi.", "application", "medium"),
            ("Unit farmasi tidak dapat mengakses aplikasi, tidak ada koneksi.", "network", "medium"),
        ],
        unit="Farmasi",
        service="SIM-APOTEK",
        sop=["SOP-007", "SOP-003"],
        rcc="network",
        tools=["ping_host", "get_network_interface_status", "get_topology_path", "check_http"],
        tags=["multi_endpoint_loss", "switch_uplink_down", "shared_access_switch", "server_healthy", "control_group_ok"],
    ),
}


def gen_benchmark(hist_rows):
    items = []
    n = 0
    for sid, spec in BENCH.items():
        T = SCENARIOS[sid]["T"]
        rel = [r["incident_id"] for r in hist_rows if r["pattern"] in SCENARIO_PATTERNS[sid]]
        for text, cat, sev in spec["texts"]:
            n += 1
            items.append(
                dict(
                    id=f"BM-{n:03d}",
                    scenario_id=sid,
                    description=text,
                    occurred_at=fmt(T),
                    unit=spec["unit"],
                    affected_service=spec["service"],
                    expected_category=cat,
                    expected_severity=sev,
                    expected_sop=spec["sop"],
                    relevant_patterns=SCENARIO_PATTERNS[sid],
                    relevant_historical_ids=rel,
                    expected_root_cause_category=spec["rcc"],
                    expected_tools=spec["tools"],
                    expected_evidence_tags=spec["tags"],
                )
            )
    return items


INFRA_DOC = """# Dokumentasi Infrastruktur TI - RS Yogyakarta (SINTETIS)

Dokumen ini fiktif dan hanya berisi informasi infrastruktur TI. Tidak ada data pasien.

## Topologi Jaringan
Jalur logis dari endpoint ke server aplikasi: PC unit -> switch akses unit -> SW-DIST-01/SW-DIST-02 -> CORE-SW-01 -> RTR-CORE -> server.
Setiap switch akses terhubung ke distribution switch melalui uplink Gi0/48. Server SIMRS-APP-01, SIMRS-DB-01, DNS-01, FILE-01 dan MONITOR-01 berada di VLAN 20 dan terhubung langsung ke RTR-CORE.

## VLAN
VLAN 10 Management, VLAN 20 Server, VLAN 30 Poli (Poli 1-3), VLAN 40 Farmasi, VLAN 50 Kasir, VLAN 60 Laboratorium, VLAN 70 Penunjang/IGD (Radiologi, IGD, Rekam Medis).

## Layanan
SIMRS berjalan pada SIMRS-APP-01 port 8080, SIM-APOTEK port 8081. Database SIMRS berjalan pada SIMRS-DB-01 port 5432. DNS internal pada DNS-01 port 53 (zona simrs.internal). File server FILE-01 port 445. Monitoring pada MONITOR-01 port 9090.

## Dependensi
SIMRS bergantung pada DNS-01 (resolusi nama simrs.internal) dan SIMRS-DB-01 (database). Gangguan DNS menyebabkan aplikasi tidak dapat dibuka dengan nama host meskipun server sehat. Gangguan switch akses hanya mempengaruhi endpoint di bawah switch tersebut.

## Baseline Normal
Latency endpoint ke SIMRS-APP-01 normal 1-9 ms, packet loss 0%. Response health SIMRS 90-160 ms. CPU SIMRS-APP-01 jam kerja 38-58%, memori 58-66%. Koneksi database aktif normal di bawah 40 dari batas 100.
"""


def main():
    devices, topo = build_inventory()
    PC_HOSTS.extend((d["hostname"], d["ip_address"], d["unit"]) for d in devices if d["device_type"] == "pc")
    RAW.mkdir(parents=True, exist_ok=True)
    gen_baseline()
    gen_service_baseline()
    gen_scenario_common(SCENARIOS["S1"]["T"], "Poli 3", {"SW-POLI3"})
    gen_scenario_common(SCENARIOS["S2"]["T"])
    gen_scenario_common(SCENARIOS["S3"]["T"])
    gen_scenario_common(SCENARIOS["S4"]["T"])
    gen_scenario_common(SCENARIOS["S5"]["T"], "Farmasi", {"SW-FARMASI"})
    s1_poli3(SCENARIOS["S1"]["T"])
    s2_dns(SCENARIOS["S2"]["T"])
    s3_db(SCENARIOS["S3"]["T"])
    s4_overload(SCENARIOS["S4"]["T"])
    s5_farmasi(SCENARIOS["S5"]["T"])
    SLOG.sort(key=lambda r: r["timestamp"])
    NLOG.sort(key=lambda r: r["timestamp"])
    SVC.sort(key=lambda r: (r["last_checked"], r["service"]))
    hist = gen_historical()

    write_csv(
        RAW / "device_inventory.csv",
        devices,
        ["hostname", "ip_address", "mac_address", "unit", "vlan", "device_type", "os", "switch", "port", "status", "last_seen"],
    )
    write_csv(
        RAW / "servers.csv",
        [
            dict(hostname=h, ip_address=ip, role=r, environment="production", status="online", operating_system=os_, boot_time=b)
            for h, ip, r, os_, b in SERVERS
        ],
    )
    write_csv(
        RAW / "server_logs.csv", SLOG, ["timestamp", "hostname", "service", "level", "event_type", "message", "source_ip", "metadata"]
    )
    write_csv(
        RAW / "network_logs.csv",
        NLOG,
        [
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
            "interface",
            "crc_errors",
        ],
    )
    write_csv(
        RAW / "service_status.csv", SVC, ["service", "server", "status", "response_time", "last_checked", "endpoint", "port", "http_status"]
    )
    write_csv(RAW / "historical_incidents.csv", hist)
    write_csv(RAW / "incident_ticket.csv", TICKETS)
    (RAW / "network_topology.json").write_text(json.dumps(topo, indent=1), encoding="utf-8")
    bench = gen_benchmark(hist)
    (DATA / "benchmark").mkdir(exist_ok=True)
    (DATA / "benchmark" / "benchmark_incidents.json").write_text(json.dumps(bench, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA / "docs").mkdir(exist_ok=True)
    (DATA / "docs" / "infrastructure.md").write_text(INFRA_DOC, encoding="utf-8")
    print(
        f"devices={len(devices)} server_logs={len(SLOG)} network_logs={len(NLOG)} service_status={len(SVC)} "
        f"historical={len(hist)} tickets={len(TICKETS)} benchmark={len(bench)} nodes={len(topo['nodes'])} edges={len(topo['edges'])}"
    )
    _ = math


if __name__ == "__main__":
    main()
