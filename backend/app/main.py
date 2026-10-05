"""OpsRAG-X FastAPI application."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.ai.llm import BaseLLMProvider, get_llm
from app.api import ai_config, auth, dashboard, health, incidents, inventory, investigations, knowledge
from app.api.deps import require_user
from app.config import Settings, get_settings
from app.database.session import get_session_factory
from app.logging_config import configure_logging, request_id_var
from app.mcp.client import MCPClient
from app.rag.embeddings import Embedder, get_embedder

logger = logging.getLogger("app.request")

DESCRIPTION = """
**OpsRAG-X** - Temporal Evidence-Based Incident Investigation Agent for small-hospital IT infrastructure.

An *investigation agent*, not an autonomous operator: it retrieves SOPs (version-aware) and similar historical incidents, inspects topology,
runs **read-only** MCP diagnostics, correlates logs temporally, scores root-cause hypotheses with an *evidence confidence score* and produces an
auditable report. All demo data is synthetic; no patient data is used. Recommendations always require IT Support verification.
"""


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    mcp: MCPClient | None = None,
    llm: BaseLLMProvider | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        logger.info("starting %s v%s (env=%s, demo_mode=%s)", settings.app_name, __version__, settings.app_env, settings.demo_mode)
        yield

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "health"},
            {"name": "auth"},
            {"name": "incidents"},
            {"name": "investigations"},
            {"name": "infrastructure"},
            {"name": "knowledge"},
            {"name": "dashboard"},
            {"name": "ai"},
        ],
    )
    app.state.settings = settings
    app.state.session_factory = session_factory or get_session_factory()
    app.state.llm = llm if llm is not None else get_llm(settings)
    app.state.mcp = mcp or MCPClient(settings=settings)
    app.state.embedder = embedder or get_embedder()
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # safety net: handled below by the generic handler as well
            logger.exception("unhandled error")
            response = JSONResponse({"error": "internal_error", "message": "Internal server error", "request_id": rid}, status_code=500)
        response.headers["X-Request-ID"] = rid
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "event": "http_request",
                "duration": round((time.perf_counter() - started) * 1000, 2),
                "status": str(response.status_code),
            },
        )
        request_id_var.reset(token)
        return response

    def err(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
        return JSONResponse({"error": code, "message": message, "request_id": request_id_var.get(), **extra}, status_code=status)

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404 and request.method == "GET":
            page = _spa_response(app, request.url.path)
            if page is not None:
                return page  # type: ignore[return-value]
        return err(
            exc.status_code,
            {401: "unauthorized", 404: "not_found", 409: "conflict", 422: "validation_error", 429: "too_many_requests"}.get(
                exc.status_code, "http_error"
            ),
            str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()]
        return err(422, "validation_error", "Request validation failed", details=details)

    @app.exception_handler(Exception)
    async def generic_exc(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled %s", type(exc).__name__)  # details stay in logs; the client only sees a sanitized message
        return err(500, "internal_error", "Internal server error")

    app.include_router(health.router)
    app.include_router(auth.router)
    for r in (incidents.router, investigations.router, inventory.router, knowledge.router, dashboard.router, ai_config.router):
        app.include_router(r, dependencies=[Depends(require_user)])
    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    """Serve the built React app (single-process / public hosting). Unknown non-API GET paths fall back to index.html (SPA routing)."""
    dist = settings.frontend_dist or Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        return
    app.state.frontend_dist = dist
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")


def _spa_response(app: FastAPI, path: str) -> FileResponse | None:
    dist: Path | None = getattr(app.state, "frontend_dist", None)
    if dist is None or path.startswith("/api/") or path in ("/api", "/openapi.json"):
        return None
    candidate = (dist / path.lstrip("/")).resolve()
    if path != "/" and candidate.is_file() and dist.resolve() in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(dist / "index.html")


app = create_app()
