from __future__ import annotations

import itertools

from pydantic import BaseModel, field_validator

from tools import datastore
from tools.common import ToolError, ToolInput, register, safe_host


class Input(ToolInput):
    source: str
    destination: str

    _v = field_validator("source", "destination")(lambda cls, v: safe_host(v))


class Output(BaseModel):
    source: str
    destination: str
    reachable_in_topology: bool
    hops: int
    path: list[dict]
    links: list[dict]


@register("get_topology_path", "Read-only shortest network path between two nodes in the documented topology.", Input, Output)
def get_topology_path(inp: Input) -> Output:
    a, b = datastore.resolve_node(inp.source), datastore.resolve_node(inp.destination)
    if not a or not b:
        raise ToolError("not_found", "source or destination is not in the topology")
    names = datastore.shortest_path(a["hostname"], b["hostname"])
    if not names:
        return Output(source=a["hostname"], destination=b["hostname"], reachable_in_topology=False, hops=0, path=[], links=[])
    path = [{k: datastore.nodes()[n.upper()][k] for k in ("hostname", "ip", "device_type", "vlan", "unit", "status")} for n in names]
    links = []
    for x, y in itertools.pairwise(names):
        e = next(e for e in datastore.adjacency()[x.upper()] if e["peer"].upper() == y.upper())
        links.append({"from": x, "to": y, "from_interface": e["local_if"], "to_interface": e["peer_if"], "link_type": e["link_type"]})
    return Output(source=a["hostname"], destination=b["hostname"], reachable_in_topology=True, hops=len(names) - 1, path=path, links=links)
