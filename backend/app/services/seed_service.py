"""Seed the synthetic hospital: users, servers, devices, services, incident tickets (idempotent)."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Device, Incident, Server, Service, User


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def seed_core(session: Session, raw: Path) -> dict[str, int]:
    counts = {"users": 0, "servers": 0, "devices": 0, "services": 0, "incidents": 0}
    users = {}
    for email, name, role in [
        ("it.support@rsyogyakarta.local", "IT Support", "it_support"),
        ("helpdesk@rsyogyakarta.local", "Helpdesk", "helpdesk"),
    ]:
        u = session.scalar(select(User).where(User.email == email))
        if not u:
            u = User(email=email, name=name, role=role)
            session.add(u)
            counts["users"] += 1
        users[role] = u
    session.flush()
    servers: dict[str, Server] = {s.hostname: s for s in session.scalars(select(Server))}
    for r in _rows(raw / "servers.csv"):
        if r["hostname"] not in servers:
            s = Server(
                hostname=r["hostname"],
                ip_address=r["ip_address"],
                role=r["role"],
                environment=r["environment"],
                status=r["status"],
                operating_system=r["operating_system"],
                meta={"boot_time": r["boot_time"], "synthetic": True},
            )
            session.add(s)
            servers[r["hostname"]] = s
            counts["servers"] += 1
    session.flush()
    existing = {d.hostname: d for d in session.scalars(select(Device))}
    inv = _rows(raw / "device_inventory.csv")
    for r in inv:
        if r["hostname"] in existing:
            continue
        d = Device(
            hostname=r["hostname"],
            ip_address=r["ip_address"],
            mac_address=r["mac_address"],
            unit=r["unit"],
            vlan=int(r["vlan"]),
            device_type=r["device_type"],
            operating_system=r["os"],
            status=r["status"],
            switch_port=r["port"] or None,
            last_seen=datetime.fromisoformat(r["last_seen"]),
            meta={"synthetic": True},
        )
        session.add(d)
        existing[r["hostname"]] = d
        counts["devices"] += 1
    session.flush()
    for r in inv:  # second pass: switch_id links
        d = existing[r["hostname"]]
        if r["switch"] and r["switch"] in existing and d.switch_id is None:
            d.switch_id = existing[r["switch"]].id
    latest: dict[str, dict[str, str]] = {}
    for r in _rows(raw / "service_status.csv"):
        if r["service"] not in latest or r["last_checked"] >= latest[r["service"]]["last_checked"]:
            latest[r["service"]] = r
    have = {s.name for s in session.scalars(select(Service))}
    for name, r in latest.items():
        if name in have:
            continue
        session.add(
            Service(
                name=name,
                server_id=servers[r["server"]].id,
                port=int(r["port"]),
                protocol="udp" if name == "DNS" else "tcp",
                status=r["status"],
                health_endpoint=r["endpoint"],
                response_time_ms=float(r["response_time"]),
                last_checked=datetime.fromisoformat(r["last_checked"]),
            )
        )
        counts["services"] += 1
    have_t = {t for t in session.scalars(select(Incident.ticket_number))}
    for r in _rows(raw / "incident_ticket.csv"):
        if r["ticket_number"] in have_t:
            continue
        session.add(
            Incident(
                ticket_number=r["ticket_number"],
                title=r["title"],
                description=r["description"],
                reported_by=users["helpdesk"].id,
                reporter_name=r["reported_by"],
                affected_unit=r["affected_unit"] or None,
                affected_device=r["affected_device"] or None,
                affected_service=r["affected_service"] or None,
                severity=r["severity"],
                category=r["category"],
                status=r["status"],
                occurred_at=datetime.fromisoformat(r["occurred_at"]),
                scenario_id=r["scenario_id"] or None,
            )
        )
        counts["incidents"] += 1
    session.commit()
    return counts


def seed_summary(session: Session) -> dict[str, Any]:
    from sqlalchemy import func

    from app.database.models import HistoricalIncident, Log, SopChunk, SopVersion

    def n(m: Any) -> int:
        return session.scalar(select(func.count()).select_from(m)) or 0

    return {
        "devices": n(Device),
        "servers": n(Server),
        "services": n(Service),
        "incidents": n(Incident),
        "logs": n(Log),
        "historical_incidents": n(HistoricalIncident),
        "sop_versions": n(SopVersion),
        "sop_chunks": n(SopChunk),
    }
