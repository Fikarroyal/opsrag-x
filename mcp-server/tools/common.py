"""Shared validation helpers + tool registry. ALL TOOLS ARE READ-ONLY (no writes, no shell, no config changes)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from tools import datastore

UTC = timezone.utc  # datetime.UTC only exists on Python 3.11+

logger = logging.getLogger("mcp.tools")
if not logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)
    logger.propagate = False

DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() in ("1", "true", "yes")
TOOL_TIMEOUT_S = float(os.environ.get("TOOL_TIMEOUT_SECONDS", "8"))
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-\.]{0,120}[A-Za-z0-9])?$")

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mcp-tool")


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    as_of: str | None = None  # reference time (demo mode); default = end of dataset

    @field_validator("as_of")
    @classmethod
    def _valid_as_of(cls, v: str | None) -> str | None:
        if v:
            try:
                datastore.parse_ts(v)
            except ValueError as exc:
                raise ValueError("as_of must be an ISO timestamp, e.g. 2026-09-28T09:47:00") from exc
        return v

    def as_of_dt(self) -> datetime:
        return datastore.parse_ts(self.as_of) or datastore.default_as_of()


def safe_host(v: str) -> str:
    if not HOST_RE.match(v):
        raise ValueError("invalid host/hostname (letters, digits, '-' and '.' only)")
    return v


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[ToolInput]
    output_model: type[BaseModel]
    fn: Callable[[Any], BaseModel]


REGISTRY: dict[str, ToolSpec] = {}


def register(
    name: str, description: str, input_model: type[ToolInput], output_model: type[BaseModel]
) -> Callable[[Callable[[Any], BaseModel]], Callable[[Any], BaseModel]]:
    def deco(fn: Callable[[Any], BaseModel]) -> Callable[[Any], BaseModel]:
        REGISTRY[name] = ToolSpec(name, description, input_model, output_model, fn)
        return fn

    return deco


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Validate input -> run with timeout -> validate output -> structured JSON (never raises)."""
    started = time.perf_counter()
    args = arguments or {}
    spec = REGISTRY.get(name)

    def finish(ok: bool, **kw: Any) -> dict[str, Any]:
        ms = round((time.perf_counter() - started) * 1000, 2)
        out = {"ok": ok, "tool": name, "execution_ms": ms, "demo_mode": DEMO_MODE, **kw}
        logger.info(
            json.dumps(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "event": "tool_call",
                    "tool": name,
                    "status": "ok" if ok else kw.get("error", {}).get("code"),
                    "duration_ms": ms,
                    "args": {k: (str(v)[:80]) for k, v in args.items()},
                }
            )
        )
        return out

    if spec is None:
        return finish(False, error={"code": "unknown_tool", "message": f"unknown tool '{name}'"})
    try:
        inp = spec.input_model.model_validate(args)
    except ValidationError as exc:
        return finish(
            False,
            error={"code": "invalid_input", "message": "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())},
        )
    future = _pool.submit(spec.fn, inp)
    try:
        raw = future.result(timeout=TOOL_TIMEOUT_S)
        result = spec.output_model.model_validate(raw.model_dump() if isinstance(raw, BaseModel) else raw)
        return finish(True, result=result.model_dump(mode="json"))
    except FutureTimeout:
        future.cancel()
        return finish(False, error={"code": "timeout", "message": f"tool exceeded {TOOL_TIMEOUT_S}s"})
    except ToolError as exc:
        return finish(False, error={"code": exc.code, "message": exc.message})
    except ValidationError as exc:
        return finish(False, error={"code": "invalid_output", "message": str(exc)[:300]})
    except Exception as exc:  # last resort: never leak stack traces
        logger.exception("tool crashed")
        return finish(False, error={"code": "internal_error", "message": type(exc).__name__})
