from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_settings_dep
from app.config import Settings
from app.database.models import Device, Service
from app.schemas.common import Page
from app.schemas.inventory import DeviceOut, ServerOut
from app.services import monitoring_service as mon

router = APIRouter(prefix="/api", tags=["infrastructure"])


@router.get(
    "/devices",
    response_model=Page[DeviceOut],
    summary="Device inventory",
    description="Paginated endpoints/network devices with search and filters.",
)
def devices(
    q: str | None = None,
    unit: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Any:
    conds: list[Any] = []
    if q:
        conds.append(or_(Device.hostname.ilike(f"%{q}%"), Device.ip_address.ilike(f"%{q}%")))
    for col, v in ((Device.unit, unit), (Device.device_type, device_type), (Device.status, status)):
        if v:
            conds.append(col == v)
    total = db.scalar(select(func.count()).select_from(Device).where(*conds)) or 0
    rows = list(
        db.scalars(select(Device).where(*conds).order_by(Device.unit, Device.hostname).offset((page - 1) * page_size).limit(page_size))
    )
    names = {
        d.id: d.hostname
        for d in db.scalars(
            select(Device).where(Device.device_type.like("%switch"), Device.id.in_([r.switch_id for r in rows if r.switch_id] or [None]))
        )
    }
    items = []
    for r in rows:
        o = DeviceOut.model_validate(r)
        o.switch = names.get(r.switch_id) if r.switch_id else None
        items.append(o)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/devices/filters", summary="Distinct units and device types")
def device_filters(db: Session = Depends(get_db)) -> Any:
    return {
        "units": sorted(db.scalars(select(Device.unit).distinct())),
        "device_types": sorted(db.scalars(select(Device.device_type).distinct())),
    }


@router.get(
    "/servers",
    response_model=list[ServerOut],
    summary="Server monitoring overview",
    description="Latest CPU/memory sample and service states; `as_of` views the state at a historical time (demo data range 2026-09-20..28).",
)
def servers(as_of: datetime | None = None, db: Session = Depends(get_db)) -> Any:
    return mon.servers_overview(db, as_of.replace(tzinfo=None) if as_of else None)


@router.get("/servers/{hostname}/metrics", summary="CPU/memory samples of a server")
def server_metrics(hostname: str, start: datetime, end: datetime, db: Session = Depends(get_db)) -> Any:
    if end < start or end - start > timedelta(days=3):
        raise HTTPException(422, "range must be positive and at most 3 days")
    return mon.server_metrics(db, hostname, start.replace(tzinfo=None), end.replace(tzinfo=None))


@router.get(
    "/services",
    summary="Service monitoring",
    description="Monitored services with status at `as_of` (or latest) and availability over the monitoring history.",
)
def services(as_of: datetime | None = None, db: Session = Depends(get_db)) -> Any:
    from app.config import get_settings
    from app.services.incident_service import _service_availability

    avail = {a["service"]: a for a in _service_availability(str(get_settings().raw_dir / "service_status.csv"))}
    current = mon.service_status_at(as_of.replace(tzinfo=None) if as_of else None)
    cfg = {s.name: s for s in db.scalars(select(Service))}
    return [
        {
            **c,
            "availability": avail.get(c["service"], {}).get("availability"),
            "protocol": cfg[c["service"]].protocol if c["service"] in cfg else None,
        }
        for c in current
    ]


@router.get("/services/{name}/history", summary="Service status history")
def service_history(name: str, start: datetime | None = None, end: datetime | None = None) -> Any:
    return mon.service_history(name, start.replace(tzinfo=None) if start else None, end.replace(tzinfo=None) if end else None)


@router.get(
    "/topology",
    summary="Network topology",
    description="Nodes (hostname, IP, type, VLAN, unit, status) and edges of the documented synthetic hospital network.",
)
def topology(settings: Settings = Depends(get_settings_dep)) -> Any:
    return json.loads((settings.raw_dir / "network_topology.json").read_text(encoding="utf-8"))
