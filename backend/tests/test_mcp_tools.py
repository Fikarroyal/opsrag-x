import re

import pytest
import server as mcp_server
from starlette.testclient import TestClient
from tools import REGISTRY, call_tool, common

AS_OF = "2026-09-28T09:47:00"


def test_all_ten_tools_registered_and_read_only():
    assert set(REGISTRY) == {
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
    forbidden = re.compile(r"exec|restart|delete|shutdown|reboot|change|config|write|kill|remove|set_")
    assert not [n for n in REGISTRY if forbidden.search(n)]
    from app.mcp.client import READ_ONLY_TOOLS

    assert set(REGISTRY) == READ_ONLY_TOOLS


def test_input_validation_rejects_bad_arguments():
    assert call_tool("ping_host", {"host": "bad host; rm -rf /"})["error"]["code"] == "invalid_input"
    assert call_tool("ping_host", {"host": "PC-POLI3-001", "evil": 1})["error"]["code"] == "invalid_input"  # unknown field forbidden
    assert call_tool("ping_host", {"host": "PC-POLI3-001", "as_of": "yesterday"})["error"]["code"] == "invalid_input"
    assert (
        call_tool("search_logs", {"start_time": "2026-09-28T00:00:00", "end_time": "2026-09-30T00:00:00"})["error"]["code"]
        == "invalid_input"
    )  # > 24h
    assert (
        call_tool("search_logs", {"start_time": "2026-09-28T09:00:00", "end_time": "2026-09-28T10:00:00", "severity": "fatal"})["error"][
            "code"
        ]
        == "invalid_input"
    )
    assert call_tool("check_http", {"url": "ftp://x/y"})["error"]["code"] == "invalid_input"
    assert call_tool("does_not_exist", {})["error"]["code"] == "unknown_tool"
    assert call_tool("get_device_info", {"hostname": "NOPE-999"})["error"]["code"] == "not_found"


def test_structured_output_and_metadata():
    r = call_tool("query_service_status", {"service_name": "SIMRS", "as_of": AS_OF})
    assert r["ok"] and r["tool"] == "query_service_status" and r["demo_mode"] is True and isinstance(r["execution_ms"], float)
    assert (
        {"service", "status", "server", "port"} <= set(r["result"])
        and r["result"]["server"] == "SIMRS-APP-01"
        and r["result"]["port"] == 8080
    )


def test_synthetic_pings_follow_scenario():
    loss = {
        h: call_tool("ping_host", {"host": h, "as_of": AS_OF})["result"]
        for h in ("PC-POLI3-001", "PC-POLI3-002", "PC-POLI3-003", "PC-POLI2-001")
    }
    assert (
        12 < loss["PC-POLI3-001"]["packet_loss"] < 25
        and 10 < loss["PC-POLI3-002"]["packet_loss"] < 22
        and 15 < loss["PC-POLI3-003"]["packet_loss"] < 28
    )
    assert loss["PC-POLI2-001"]["packet_loss"] == 0 and loss["PC-POLI2-001"]["reachable"] is True
    assert call_tool("ping_host", {"host": "SIMRS-APP-01", "as_of": AS_OF})["result"]["packet_loss"] == 0


def test_server_http_dns_for_poli3_scenario():
    assert call_tool("check_http", {"url": "http://simrs.internal:8080/health", "as_of": AS_OF})["result"]["status_code"] == 200
    d = call_tool("check_dns", {"hostname": "simrs.internal", "as_of": AS_OF})["result"]
    assert d["success"] and d["resolved_ip"] == "10.20.0.10"
    s = call_tool("get_server_status", {"server_name": "SIMRS-APP-01", "as_of": AS_OF})["result"]
    assert s["status"] == "healthy" and s["cpu"] < 70 and re.match(r"\d+d \d{2}h", s["uptime"])


def test_dns_failure_scenario_separates_name_and_ip():
    t = "2026-09-27T13:20:00"
    assert call_tool("check_dns", {"hostname": "simrs.internal", "as_of": t})["result"]["success"] is False
    assert call_tool("check_http", {"url": "http://simrs.internal:8080/health", "as_of": t})["result"]["status_code"] == 0
    assert call_tool("check_http", {"url": "http://10.20.0.10:8080/health", "as_of": t})["result"]["healthy"] is True


def test_db_overload_and_farmasi_scenarios():
    assert call_tool("query_service_status", {"service_name": "database", "as_of": "2026-09-26T10:35:00"})["result"]["status"] == "degraded"
    assert call_tool("get_server_status", {"server_name": "SIMRS-APP-01", "as_of": "2026-09-25T14:10:00"})["result"]["cpu"] > 85
    f = call_tool("get_network_interface_status", {"hostname": "SW-FARMASI", "as_of": "2026-09-24T08:55:00"})["result"]
    assert f["summary"]["down"] >= 1 and any(i["name"] == "Gi0/48" and i["status"] == "down" for i in f["interfaces"])
    assert call_tool("ping_host", {"host": "SW-FARMASI", "as_of": "2026-09-24T08:55:00"})["result"]["reachable"] is False


def test_interface_errors_on_poli3_uplink():
    r = call_tool("get_network_interface_status", {"hostname": "SW-POLI3", "as_of": AS_OF})["result"]
    up = next(i for i in r["interfaces"] if i["name"] == "Gi0/48")
    assert up["status"] == "up_with_errors" and up["crc_errors"] > 500 and up["peer"] == "SW-DIST-01"


def test_topology_device_logs_and_history_tools():
    p = call_tool("get_topology_path", {"source": "PC-POLI3-001", "destination": "SIMRS-APP-01"})["result"]
    assert [n["hostname"] for n in p["path"]] == ["PC-POLI3-001", "SW-POLI3", "SW-DIST-01", "CORE-SW-01", "RTR-CORE", "SIMRS-APP-01"] and p[
        "hops"
    ] == 5
    d = call_tool("get_device_info", {"hostname": "PC-POLI3-001"})["result"]
    assert d["switch"] == "SW-POLI3" and d["vlan"] == 30 and d["peers_on_same_switch"] == 12
    lg = call_tool(
        "search_logs",
        {
            "start_time": "2026-09-28T09:40:00",
            "end_time": "2026-09-28T09:46:00",
            "hostname": "SIMRS-APP-01",
            "query": "timeout",
            "limit": 3,
        },
    )["result"]
    assert lg["returned"] == 3 and lg["truncated"] and all("timeout" in x["message"].lower() for x in lg["logs"])
    h = call_tool("search_previous_incident", {"query": "SIMRS tidak bisa dibuka packet loss", "category": "application", "as_of": AS_OF})[
        "result"
    ]
    assert h["incidents"] and all(i["timestamp"] < "2026-09-28" for i in h["incidents"])


def test_timeout_is_enforced(monkeypatch):
    import time

    spec = REGISTRY["check_dns"]
    monkeypatch.setattr(common, "TOOL_TIMEOUT_S", 0.05)
    monkeypatch.setattr(spec, "fn", lambda inp: time.sleep(0.5))
    r = call_tool("check_dns", {"hostname": "simrs.internal"})
    assert not r["ok"] and r["error"]["code"] == "timeout"


def test_output_validation_catches_bad_tool_results(monkeypatch):
    monkeypatch.setattr(REGISTRY["check_dns"], "fn", lambda inp: {"hostname": 1})
    assert call_tool("check_dns", {"hostname": "simrs.internal"})["error"]["code"] == "invalid_output"


def test_rest_facade_status_codes():
    c = TestClient(mcp_server.build_app())
    assert c.get("/health").json()["read_only"] is True
    assert len(c.get("/api/tools").json()["tools"]) == 10
    assert c.post("/api/tools/nope", json={}).status_code == 404
    assert c.post("/api/tools/ping_host", json={"host": "x y"}).status_code == 422
    assert c.post("/api/tools/ping_host", content="not-json").status_code == 400
    assert c.post("/api/tools/ping_host", json={"host": "SW-POLI3", "as_of": AS_OF}).status_code == 200


def test_live_mode_requires_allowlist(monkeypatch):
    monkeypatch.setattr(common, "DEMO_MODE", False)
    import tools.http_check as hc

    monkeypatch.setattr(hc, "DEMO_MODE", False)
    monkeypatch.delenv("LIVE_ALLOWED_HOSTS", raising=False)
    assert call_tool("check_http", {"url": "http://example.com/"})["error"]["code"] == "host_not_allowed"
    _ = pytest
