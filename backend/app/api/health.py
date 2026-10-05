from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.ai.llm import BaseLLMProvider
from app.api.deps import get_llm_dep, get_mcp_dep
from app.database.models import HistoricalIncident, SopChunk
from app.mcp.client import MCPClient

router = APIRouter(prefix="/api", tags=["health"])
logger = logging.getLogger(__name__)


@router.get(
    "/health",
    summary="Service health",
    description="Status of database, RAG, MCP server and LLM. `degraded` means an optional dependency is unavailable; the app remains usable (fallback mode). Returns 503 only when the database is down.",
)
def health(request: Request, llm: BaseLLMProvider = Depends(get_llm_dep), mcp: MCPClient = Depends(get_mcp_dep)) -> JSONResponse:
    out: dict[str, Any] = {"database": "healthy", "rag": "healthy", "mcp": "healthy", "llm": "available"}
    db_ok = True
    try:
        with request.app.state.session_factory() as s:
            s.execute(text("SELECT 1"))
            chunks = s.scalar(select(func.count()).select_from(SopChunk)) or 0
            hist = s.scalar(select(func.count()).select_from(HistoricalIncident)) or 0
        out["rag"] = "healthy" if chunks and hist else "degraded"
        out["rag_detail"] = {"sop_chunks": chunks, "historical_incidents": hist, "embedding": request.app.state.embedder.name}
    except Exception as exc:
        db_ok = False
        out.update(database="unhealthy", rag="unavailable")
        logger.error("health: database check failed: %s", type(exc).__name__)
    out["mcp"] = "healthy" if mcp.health() else "unavailable"
    out["llm"] = "available" if llm.is_available() else "unavailable"
    out["mode"] = "llm" if out["llm"] == "available" else "DEMO_FALLBACK_MODE"
    out["demo_mode"] = request.app.state.settings.demo_mode
    if not db_ok:
        out["status"] = "unhealthy"
        return JSONResponse(out, status_code=503)
    out["status"] = "healthy" if out["rag"] == "healthy" and out["mcp"] == "healthy" and out["llm"] == "available" else "degraded"
    return JSONResponse(out)
