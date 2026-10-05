"""Read-only synthetic "CMDB + monitoring + log store" used by MCP tools in DEMO_MODE.

Everything is loaded from data/raw (CSV/JSON) and never written. Timestamps are naive local hospital time.
"""

from __future__ import annotations

import bisect
import csv
import json
import os
from collections import deque
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    env = os.environ.get("DATA_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "raw").is_dir():
            return parent / "data"
    return here.parents[2] / "data"


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip().replace("Z", "").replace("T", " ")
    if "+" in v[10:]:
        v = v[: v.index("+", 10)]
    return datetime.fromisoformat(v)


def _read_csv(name: str) -> list[dict[str, Any]]:
    with (data_dir() / "raw" / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


class TimeIndex:
    """Sorted rows with a parallel timestamp list for O(log n) window queries."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = sorted(rows, key=lambda r: r["_ts"])
        self.ts = [r["_ts"] for r in self.rows]

    def between(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return self.rows[bisect.bisect_left(self.ts, start) : bisect.bisect_right(self.ts, end)]

    def latest_before(self, end: datetime, pred: Any = None, max_scan: int = 5000) -> dict[str, Any] | None:
        i = bisect.bisect_right(self.ts, end) - 1
        scanned = 0
        while i >= 0 and scanned < max_scan:
            if pred is None or pred(self.rows[i]):
                return self.rows[i]
            i -= 1
            scanned += 1
        return None


@lru_cache
def topology() -> dict[str, Any]:
    return json.loads((data_dir() / "raw" / "network_topology.json").read_text(encoding="utf-8"))


@lru_cache
def nodes() -> dict[str, dict[str, Any]]:
    return {n["hostname"].upper(): n for n in topology()["nodes"]}


@lru_cache
def adjacency() -> dict[str, list[dict[str, Any]]]:
    adj: dict[str, list[dict[str, Any]]] = {}
    for e in topology()["edges"]:
        adj.setdefault(e["source"].upper(), []).append(
            {"peer": e["target"], "local_if": e["source_interface"], "peer_if": e["target_interface"], "link_type": e["link_type"]}
        )
        adj.setdefault(e["target"].upper(), []).append(
            {"peer": e["source"], "local_if": e["target_interface"], "peer_if": e["source_interface"], "link_type": e["link_type"]}
        )
    return adj


@lru_cache
def ip_index() -> dict[str, str]:
    return {n["ip"]: n["hostname"] for n in topology()["nodes"]}


@lru_cache
def inventory() -> dict[str, dict[str, Any]]:
    return {r["hostname"].upper(): r for r in _read_csv("device_inventory.csv")}


@lru_cache
def servers() -> dict[str, dict[str, Any]]:
    return {r["hostname"].upper(): r for r in _read_csv("servers.csv")}


@lru_cache
def server_logs() -> TimeIndex:
    rows = _read_csv("server_logs.csv")
    for r in rows:
        r["_ts"] = parse_ts(r["timestamp"])
        r["_meta"] = json.loads(r["metadata"] or "{}")
    return TimeIndex(rows)


@lru_cache
def network_logs() -> TimeIndex:
    rows = _read_csv("network_logs.csv")
    for r in rows:
        r["_ts"] = parse_ts(r["timestamp"])
        r["_lat"] = float(r["latency_ms"] or 0)
        r["_loss"] = float(r["packet_loss"] or 0)
        r["_crc"] = int(float(r.get("crc_errors") or 0))
    return TimeIndex(rows)


@lru_cache
def service_rows() -> dict[str, TimeIndex]:
    by: dict[str, list[dict[str, Any]]] = {}
    for r in _read_csv("service_status.csv"):
        r["_ts"] = parse_ts(r["last_checked"])
        by.setdefault(r["service"].upper(), []).append(r)
    return {k: TimeIndex(v) for k, v in by.items()}


@lru_cache
def historical() -> list[dict[str, Any]]:
    rows = _read_csv("historical_incidents.csv")
    for r in rows:
        r["_ts"] = parse_ts(r["timestamp"])
    return rows


def default_as_of() -> datetime:
    return max(server_logs().ts[-1], network_logs().ts[-1])


def resolve_node(name: str) -> dict[str, Any] | None:
    key = name.strip()
    n = nodes().get(key.upper())
    if n:
        return n
    host = ip_index().get(key)
    return nodes().get(host.upper()) if host else None


def latest_service_state(service: str, as_of: datetime) -> dict[str, Any] | None:
    idx = service_rows().get(service.upper())
    return idx.latest_before(as_of) if idx else None


def shortest_path(src: str, dst: str) -> list[str] | None:
    s, d = src.upper(), dst.upper()
    adj = adjacency()
    if s not in adj or d not in adj:
        return None
    prev: dict[str, str | None] = {s: None}
    q: deque[str] = deque([s])
    while q:
        cur = q.popleft()
        if cur == d:
            break
        for e in adj.get(cur, []):
            nxt = e["peer"].upper()
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
    if d not in prev:
        return None
    path, cur2 = [], d
    while cur2 is not None:
        path.append(nodes()[cur2]["hostname"])
        cur2 = prev[cur2]  # type: ignore[assignment]
    return list(reversed(path))
