"""Inventory helpers: host/unit maps from the devices table (used by correlation and planning)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Device
from app.investigation.correlation import HostInfo


def host_maps(session: Session) -> tuple[dict[str, HostInfo], dict[str, str], dict[str, list[str]]]:
    devices = list(session.scalars(select(Device)))
    by_id = {d.id: d.hostname for d in devices}
    hosts: dict[str, HostInfo] = {}
    ip_unit: dict[str, str] = {}
    unit_devices: dict[str, list[str]] = {}
    for d in devices:
        hosts[d.hostname] = HostInfo(unit=d.unit, device_type=d.device_type, switch=by_id.get(d.switch_id) if d.switch_id else None)
        if d.device_type in ("pc", "printer"):
            ip_unit[d.ip_address] = d.unit
            unit_devices.setdefault(d.unit, []).append(d.hostname)
    return hosts, ip_unit, unit_devices
