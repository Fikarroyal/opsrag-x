from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.incident_service import dashboard_stats

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get(
    "/dashboard/stats",
    summary="Dashboard statistics",
    description="KPI cards and chart series (category, severity, trend, root cause distribution, resolution time, service availability).",
)
def stats(db: Session = Depends(get_db)) -> Any:
    return dashboard_stats(db)
