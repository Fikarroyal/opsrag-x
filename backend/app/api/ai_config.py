from __future__ import annotations

import json
import threading
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.ai.llm import BaseLLMProvider, LLMUnavailableError
from app.api.deps import get_llm_dep, get_mcp_dep, get_settings_dep
from app.config import Settings
from app.mcp.client import READ_ONLY_TOOLS, MCPClient

router = APIRouter(prefix="/api", tags=["ai"])
_run_state: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()


@router.get(
    "/ai/config",
    summary="AI / RAG / MCP configuration (read-only view)",
    description="Effective configuration with secrets excluded. Changing values requires editing the environment (.env).",
)
def ai_config(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    llm: BaseLLMProvider = Depends(get_llm_dep),
    mcp: MCPClient = Depends(get_mcp_dep),
) -> Any:
    emb = request.app.state.embedder
    return {
        "mode": "llm" if llm.is_available() else "DEMO_FALLBACK_MODE",
        "llm": llm.describe(),
        "embedding": {
            "name": emb.name,
            "dim": emb.dim,
            "configured_model": settings.embedding_model,
            "backend": settings.embedding_backend,
        },
        "retrieval_weights": settings.retrieval_weights,
        "hypothesis_weights": settings.hypothesis_weights,
        "top_k": settings.top_k,
        "history_half_life_days": settings.history_half_life_days,
        "sop_half_life_days": settings.sop_half_life_days,
        "log_half_life_minutes": settings.log_half_life_minutes,
        "correlation_window_minutes": settings.correlation_window_minutes,
        "min_confidence_for_root_cause": settings.min_confidence_for_root_cause,
        "demo_mode": settings.demo_mode,
        "mcp": {
            "url": settings.mcp_server_url,
            "transport": settings.mcp_transport,
            "healthy": mcp.health(),
            "tools": sorted(READ_ONLY_TOOLS),
            "read_only": True,
        },
    }


@router.post("/ai/test/llm", summary="Test LLM connectivity")
def test_llm(llm: BaseLLMProvider = Depends(get_llm_dep)) -> Any:
    if not llm.is_available():
        return {
            "ok": False,
            "message": "LLM provider unavailable - the system runs in DEMO_FALLBACK_MODE (rule-based classification, template reports).",
        }
    try:
        out = llm.generate("You are a health probe.", "Reply with the single word: ok", temperature=0.0)
        return {"ok": True, "message": out.strip()[:80]}
    except LLMUnavailableError as exc:
        return {"ok": False, "message": str(exc)}


@router.post("/ai/test/mcp", summary="Test MCP server connectivity")
def test_mcp(mcp: MCPClient = Depends(get_mcp_dep)) -> Any:
    if not mcp.health():
        return {
            "ok": False,
            "message": "MCP server unreachable; investigations continue with tool failures recorded as evidence limitations.",
        }
    r = mcp.call("query_service_status", {"service_name": "SIMRS"})
    return {"ok": r.ok, "message": "MCP tool call succeeded" if r.ok else r.error, "execution_ms": r.execution_ms}


@router.get(
    "/analytics/benchmark",
    summary="Latest benchmark / experiment results",
    description="Computed by actually executing the benchmark (POST /api/analytics/benchmark/run or `make benchmark`); never hard-coded.",
)
def benchmark_results(settings: Settings = Depends(get_settings_dep)) -> Any:
    path = settings.data_dir / "processed" / "benchmark_results.json"
    if not path.exists():
        return {
            "available": False,
            "message": "No benchmark has been executed yet. Run `make benchmark` or POST /api/analytics/benchmark/run.",
        }
    return {"available": True, **json.loads(path.read_text(encoding="utf-8")), "run_state": _run_state}


@router.post("/analytics/benchmark/run", status_code=202, summary="Execute the benchmark experiments (A-D) in the background")
def run_benchmark(request: Request, background: BackgroundTasks) -> Any:
    from app.evaluation.benchmark import run_benchmark as runner

    with _lock:
        if _run_state.get("status") == "running":
            raise HTTPException(409, "A benchmark run is already in progress")
        _run_state.update(status="running")
    st = request.app.state

    def job() -> None:
        try:
            res = runner(st.session_factory, st.settings, st.mcp, st.embedder, st.llm)
            _run_state.update(status="completed", finished=res["generated_at"])
        except Exception as exc:  # noqa: BLE001
            _run_state.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:200]}")

    background.add_task(job)
    return {"status": "running"}
