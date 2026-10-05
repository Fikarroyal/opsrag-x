from __future__ import annotations

from pydantic import BaseModel, field_validator

from tools import datastore
from tools.common import ToolError, ToolInput, register, safe_host


class Input(ToolInput):
    hostname: str

    _v = field_validator("hostname")(lambda cls, v: safe_host(v))


class Output(BaseModel):
    hostname: str
    ip_address: str
    mac_address: str
    unit: str
    vlan: int
    vlan_name: str
    device_type: str
    operating_system: str
    switch: str
    switch_port: str
    status: str
    last_seen: str
    peers_on_same_switch: int
    neighbors: list[dict]


@register("get_device_info", "Read-only device inventory record incl. access switch/port, VLAN and topology neighbours.", Input, Output)
def get_device_info(inp: Input) -> Output:
    node = datastore.resolve_node(inp.hostname)
    dev = datastore.inventory().get(node["hostname"].upper()) if node else None
    if not dev:
        raise ToolError("not_found", f"device '{inp.hostname}' is not in the inventory")
    peers = (
        sum(
            1
            for d in datastore.inventory().values()
            if d["switch"] == dev["switch"] and d["hostname"] != dev["hostname"] and d["device_type"] in ("pc", "printer")
        )
        if dev["switch"]
        else 0
    )
    return Output(
        hostname=dev["hostname"],
        ip_address=dev["ip_address"],
        mac_address=dev["mac_address"],
        unit=dev["unit"],
        vlan=int(dev["vlan"]),
        vlan_name=datastore.topology()["vlans"].get(str(dev["vlan"]), "unknown"),
        device_type=dev["device_type"],
        operating_system=dev["os"],
        switch=dev["switch"],
        switch_port=dev["port"],
        status=dev["status"],
        last_seen=dev["last_seen"],
        peers_on_same_switch=peers,
        neighbors=[
            {"peer": e["peer"], "local_interface": e["local_if"], "peer_interface": e["peer_if"], "link_type": e["link_type"]}
            for e in datastore.adjacency().get(dev["hostname"].upper(), [])
            if e["link_type"] != "access" or dev["device_type"] != "access_switch"
        ][:12],
    )
