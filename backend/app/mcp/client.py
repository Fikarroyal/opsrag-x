"""MCP client for the read-only diagnostics server.

transport="mcp"  : real Model Context Protocol over streamable HTTP (one session per batch of tool calls).
transport="rest" : the server's REST facade (used by tests and as an operational fallback).
Every failure is converted into a structured ToolCallResult - an unreachable MCP server never crashes an investigation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

READ_ONLY_TOOLS = {
    "get_server_status",
    "check_http",
    "check_dns",
    "ping_host",
    "query_service_status",
    "search_logs",
    "get_device_info",
    "search_previous_incident",
    "get_topology_path",
    "get_network_interface_status",
}


@dataclass
class ToolCallResult:
    tool: str
    ok: bool
    result: dict[str, Any] | None
    error: str | None
    execution_ms: float
    status: str  # success | error | timeout


class MCPClient:
    def __init__(
        self,
        url: str | None = None,
        transport: str | None = None,
        timeout: float | None = None,
        http_client: Any = None,
        settings: Settings | None = None,
    ) -> None:
        s = settings or get_settings()
        self.url = (url or s.mcp_server_url).rstrip("/")
        self.transport = transport or s.mcp_transport
        self.timeout = timeout or s.mcp_timeout_seconds
        self._http = http_client  # e.g. starlette TestClient (tests)

    # --------------------------------------------------------------- health
    def health(self) -> bool:
        try:
            r = self._http.get("/health") if self._http is not None else httpx.get(f"{self.url}/health", timeout=2.0)
            return bool(r.status_code == 200 and r.json().get("status") == "healthy")
        except Exception:
            return False

    # --------------------------------------------------------------- calls
    def call(self, tool: str, arguments: dict[str, Any]) -> ToolCallResult:
        return self.call_batch([(tool, arguments)])[0]

    def call_batch(self, calls: list[tuple[str, dict[str, Any]]]) -> list[ToolCallResult]:
        for tool, _ in calls:  # client-side allow-list: the agent can never call anything but read-only tools
            if tool not in READ_ONLY_TOOLS:
                return [ToolCallResult(t, False, None, f"tool '{t}' is not in the read-only allow-list", 0.0, "error") for t, _ in calls]
        if self.transport == "rest" or self._http is not None:
            return [self._rest(t, a) for t, a in calls]
        try:
            return asyncio.run(self._mcp_batch(calls))
        except Exception as exc:
            logger.warning("MCP session failed: %s", type(exc).__name__)
            return [ToolCallResult(t, False, None, f"MCP server unreachable ({type(exc).__name__})", 0.0, "error") for t, _ in calls]

    def _rest(self, tool: str, args: dict[str, Any]) -> ToolCallResult:
        t0 = time.perf_counter()
        body = {k: v for k, v in args.items() if v is not None}
        try:
            r = (
                self._http.post(f"/api/tools/{tool}", json=body)
                if self._http is not None
                else httpx.post(f"{self.url}/api/tools/{tool}", json=body, timeout=self.timeout)
            )
            data = r.json()
        except Exception as exc:
            return ToolCallResult(
                tool, False, None, f"MCP REST call failed ({type(exc).__name__})", round((time.perf_counter() - t0) * 1000, 2), "error"
            )
        return self._parse(tool, data, t0)

    @staticmethod
    def _parse(tool: str, data: Any, t0: float) -> ToolCallResult:
        ms = round((time.perf_counter() - t0) * 1000, 2)
        if isinstance(data, dict) and data.get("ok") and isinstance(data.get("result"), dict):
            return ToolCallResult(tool, True, data["result"], None, float(data.get("execution_ms", ms)), "success")
        err = (data or {}).get("error", {}) if isinstance(data, dict) else {}
        code = err.get("code", "error")
        return ToolCallResult(
            tool, False, None, f"{code}: {err.get('message', 'unknown error')}", ms, "timeout" if code == "timeout" else "error"
        )

    async def _mcp_batch(self, calls: list[tuple[str, dict[str, Any]]]) -> list[ToolCallResult]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        out: list[ToolCallResult] = []
        async with (
            streamablehttp_client(f"{self.url}/mcp", timeout=self.timeout) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            for tool, args in calls:
                t0 = time.perf_counter()
                body = {k: v for k, v in args.items() if v is not None}
                try:
                    res = await asyncio.wait_for(session.call_tool(tool, body), timeout=self.timeout)
                    payload: Any = getattr(res, "structuredContent", None)
                    if not (isinstance(payload, dict) and "ok" in payload):
                        payload = json.loads(getattr(res.content[0], "text", "{}")) if res.content else {}
                    if isinstance(payload, dict) and "ok" not in payload and isinstance(payload.get("result"), dict):
                        payload = payload["result"]
                    out.append(self._parse(tool, payload, t0))
                except TimeoutError:
                    out.append(
                        ToolCallResult(
                            tool, False, None, "timeout: client-side timeout", round((time.perf_counter() - t0) * 1000, 2), "timeout"
                        )
                    )
                except Exception as exc:
                    out.append(
                        ToolCallResult(
                            tool, False, None, f"error: {type(exc).__name__}", round((time.perf_counter() - t0) * 1000, 2), "error"
                        )
                    )
        return out
