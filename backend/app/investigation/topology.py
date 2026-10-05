"""Topology engine: graph loading, path calculation and scope analysis (endpoint / access switch / distribution / core)."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ENDPOINT_TYPES = {"pc", "printer"}


@dataclass
class TopologyGraph:
    nodes: dict[str, dict[str, Any]]
    adj: dict[str, list[dict[str, Any]]]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopologyGraph:
        nodes = {n["hostname"].upper(): n for n in data["nodes"]}
        adj: dict[str, list[dict[str, Any]]] = {}
        for e in data["edges"]:
            adj.setdefault(e["source"].upper(), []).append(
                {"peer": e["target"], "local_if": e["source_interface"], "peer_if": e["target_interface"], "link_type": e["link_type"]}
            )
            adj.setdefault(e["target"].upper(), []).append(
                {"peer": e["source"], "local_if": e["target_interface"], "peer_if": e["source_interface"], "link_type": e["link_type"]}
            )
        return cls(nodes, adj, data)

    @classmethod
    def load(cls, path: Path) -> TopologyGraph:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def node(self, host: str) -> dict[str, Any] | None:
        return self.nodes.get(host.upper())

    def path(self, src: str, dst: str) -> list[str] | None:
        s, d = src.upper(), dst.upper()
        if s not in self.adj or d not in self.adj:
            return None
        prev: dict[str, str | None] = {s: None}
        q: deque[str] = deque([s])
        while q:
            cur = q.popleft()
            if cur == d:
                break
            for e in self.adj.get(cur, []):
                nxt = e["peer"].upper()
                if nxt not in prev:
                    prev[nxt] = cur
                    q.append(nxt)
        if d not in prev:
            return None
        out: list[str] = []
        cur2: str | None = d
        while cur2 is not None:
            out.append(self.nodes[cur2]["hostname"])
            cur2 = prev[cur2]
        return list(reversed(out))

    def _neighbor_of_type(self, host: str, dtype: str) -> str | None:
        for e in self.adj.get(host.upper(), []):
            n = self.node(e["peer"])
            if n and n["device_type"] == dtype:
                return n["hostname"]
        return None

    def access_switch(self, host: str) -> str | None:
        n = self.node(host)
        if n and n["device_type"] == "access_switch":
            return n["hostname"]
        return self._neighbor_of_type(host, "access_switch")

    def dist_switch(self, access: str) -> str | None:
        return self._neighbor_of_type(access, "distribution_switch")

    def uplink(self, access: str) -> dict[str, str] | None:
        for e in self.adj.get(access.upper(), []):
            n = self.node(e["peer"])
            if n and n["device_type"] == "distribution_switch":
                return {"interface": e["local_if"], "peer": n["hostname"], "peer_interface": e["peer_if"]}
        return None

    def endpoints_of(self, access: str) -> list[str]:
        return [
            self.nodes[e["peer"].upper()]["hostname"]
            for e in self.adj.get(access.upper(), [])
            if self.nodes[e["peer"].upper()]["device_type"] in ENDPOINT_TYPES
        ]


@lru_cache
def load_topology(path: str) -> TopologyGraph:
    return TopologyGraph.load(Path(path))


@dataclass
class ScopeAnalysis:
    affected_hosts: list[str]
    access_groups: dict[str, list[str]]
    shared_access_switch: str | None
    dist_groups: dict[str, list[str]]
    units: list[str]
    peers_healthy: list[str]
    scope_level: str  # single_device | single_unit | multi_unit | hospital_wide | unknown


def analyze_scope(
    topo: TopologyGraph,
    affected_hosts: list[str],
    impact_units: list[str],
    classification_scope: str | None,
    unhealthy_hosts: set[str] | None = None,
) -> ScopeAnalysis:
    """Where do the affected endpoints sit in the topology?

    * shared_access_switch: all (>=2) affected endpoints hang off ONE access switch -> local switch/uplink suspect.
    * scope_level: derived from where anomalies were actually observed (impact_units); falls back to the classifier's scope.
    """
    unhealthy = {h.upper() for h in (unhealthy_hosts or set())} | {h.upper() for h in affected_hosts}
    groups: dict[str, list[str]] = {}
    dists: dict[str, list[str]] = {}
    for h in affected_hosts:
        sw = topo.access_switch(h)
        if sw:
            groups.setdefault(sw, []).append(h)
            d = topo.dist_switch(sw)
            if d:
                dists.setdefault(d, []).append(h)
    shared = next(iter(groups)) if len(groups) == 1 and len(affected_hosts) >= 2 else None
    peers_ok: list[str] = []
    if groups:
        for sw in groups:
            peers_ok += [p for p in topo.endpoints_of(sw) if p.upper() not in unhealthy]
    if len(impact_units) >= 3:
        level = "hospital_wide"
    elif len(impact_units) == 2:
        level = "multi_unit"
    elif len(impact_units) == 1:
        level = "single_device" if len(affected_hosts) == 1 else "single_unit"
    elif classification_scope in ("single_device", "single_unit", "multi_unit", "hospital_wide"):
        level = classification_scope
    else:
        level = "unknown"
    return ScopeAnalysis(sorted(set(affected_hosts)), groups, shared, dists, impact_units, peers_ok, level)
