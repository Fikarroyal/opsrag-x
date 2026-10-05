"""OpsRAG-X MCP diagnostics server (READ-ONLY).

Exposes the tools over the MCP streamable-HTTP transport at /mcp and, for health checks and tests,
a tiny REST facade: GET /health, GET /api/tools, POST /api/tools/{name}.
There are intentionally NO tools that execute commands, restart services or change configuration.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools import REGISTRY, call_tool
from tools.common import DEMO_MODE

mcp = FastMCP(
    "opsragx-diagnostics",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8001")),
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    instructions="Read-only diagnostics for hospital IT infrastructure. All results are synthetic in DEMO_MODE.",
)


@mcp.tool(name="get_server_status", description=REGISTRY["get_server_status"].description)
def get_server_status(server_name: str, as_of: str | None = None) -> dict[str, Any]:
    return call_tool("get_server_status", {"server_name": server_name, "as_of": as_of})


@mcp.tool(name="check_http", description=REGISTRY["check_http"].description)
def check_http(url: str, as_of: str | None = None) -> dict[str, Any]:
    return call_tool("check_http", {"url": url, "as_of": as_of})


@mcp.tool(name="check_dns", description=REGISTRY["check_dns"].description)
def check_dns(hostname: str, as_of: str | None = None) -> dict[str, Any]:
    return call_tool("check_dns", {"hostname": hostname, "as_of": as_of})


@mcp.tool(name="ping_host", description=REGISTRY["ping_host"].description)
def ping_host(host: str, window_minutes: int = 10, as_of: str | None = None) -> dict[str, Any]:
    return call_tool("ping_host", {"host": host, "window_minutes": window_minutes, "as_of": as_of})


@mcp.tool(name="query_service_status", description=REGISTRY["query_service_status"].description)
def query_service_status(service_name: str, as_of: str | None = None) -> dict[str, Any]:
    return call_tool("query_service_status", {"service_name": service_name, "as_of": as_of})


@mcp.tool(name="search_logs", description=REGISTRY["search_logs"].description)
def search_logs(
    start_time: str,
    end_time: str,
    query: str | None = None,
    hostname: str | None = None,
    service: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    return call_tool(
        "search_logs",
        {
            "start_time": start_time,
            "end_time": end_time,
            "query": query,
            "hostname": hostname,
            "service": service,
            "severity": severity,
            "limit": limit,
        },
    )


@mcp.tool(name="get_device_info", description=REGISTRY["get_device_info"].description)
def get_device_info(hostname: str) -> dict[str, Any]:
    return call_tool("get_device_info", {"hostname": hostname})


@mcp.tool(name="search_previous_incident", description=REGISTRY["search_previous_incident"].description)
def search_previous_incident(
    query: str, category: str | None = None, unit: str | None = None, limit: int = 5, as_of: str | None = None
) -> dict[str, Any]:
    return call_tool("search_previous_incident", {"query": query, "category": category, "unit": unit, "limit": limit, "as_of": as_of})


@mcp.tool(name="get_topology_path", description=REGISTRY["get_topology_path"].description)
def get_topology_path(source: str, destination: str) -> dict[str, Any]:
    return call_tool("get_topology_path", {"source": source, "destination": destination})


@mcp.tool(name="get_network_interface_status", description=REGISTRY["get_network_interface_status"].description)
def get_network_interface_status(hostname: str, window_minutes: int = 15, as_of: str | None = None) -> dict[str, Any]:
    return call_tool("get_network_interface_status", {"hostname": hostname, "window_minutes": window_minutes, "as_of": as_of})


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "tools": len(REGISTRY), "demo_mode": DEMO_MODE, "read_only": True})


@mcp.custom_route("/api/tools", methods=["GET"])
async def list_tools(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "tools": [
                {"name": s.name, "description": s.description, "input_schema": s.input_model.model_json_schema()} for s in REGISTRY.values()
            ]
        }
    )


@mcp.custom_route("/api/tools/{name}", methods=["POST"])
async def rest_call(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": {"code": "invalid_json", "message": "body must be a JSON object"}}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": {"code": "invalid_json", "message": "body must be a JSON object"}}, status_code=400)
    out = call_tool(request.path_params["name"], body)
    code = 200 if out["ok"] else (404 if out["error"]["code"] == "unknown_tool" else 422)
    return JSONResponse(out, status_code=code)


def build_app() -> Any:
    """ASGI app (used by tests via starlette TestClient)."""
    return mcp.streamable_http_app()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
