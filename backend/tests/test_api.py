import time

import pytest
from starlette.testclient import TestClient
from sqlalchemy import select

from app.database.models import Incident


def test_health_reports_degraded_without_llm(client):
    r = client.get("/api/health")
    j = r.json()
    assert (
        r.status_code == 200
        and j["database"] == "healthy"
        and j["rag"] == "healthy"
        and j["llm"] == "unavailable"
        and j["status"] == "degraded"
        and j["mode"] == "DEMO_FALLBACK_MODE"
    )
    assert r.headers["x-request-id"]


def test_health_database_down_returns_503(settings, mcp_client, embedder):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.ai.llm import NullProvider
    from app.database.session import make_engine
    from app.main import create_app

    bad = sessionmaker(bind=make_engine("sqlite:////nonexistent_dir/x/y.db"))
    r = TestClient(create_app(settings, session_factory=bad, mcp=mcp_client, llm=NullProvider(), embedder=embedder)).get("/api/health")
    assert r.status_code == 503 and r.json()["status"] == "unhealthy" and r.json()["database"] == "unhealthy"


def test_incident_crud_validation_and_filters(client):
    bad = client.post("/api/incidents", json={"title": "x", "description": "short"})
    assert bad.status_code == 422 and bad.json()["error"] == "validation_error" and bad.json()["details"] and bad.json()["request_id"]
    bad2 = client.post(
        "/api/incidents", json={"title": "Judul valid", "description": "Deskripsi yang cukup panjang", "affected_device": "x; drop table"}
    )
    assert bad2.status_code == 422
    r = client.post(
        "/api/incidents",
        json={
            "title": "Server SIMRS lambat",
            "description": "Server SIMRS mengalami response lambat di semua unit sejak pukul 14:05.",
            "reported_by": "Tester",
            "occurred_at": "2026-09-25T14:05:00",
        },
    )
    assert r.status_code == 201
    inc = r.json()
    assert (
        inc["ticket_number"].startswith("INC-2026-")
        and inc["category"] == "server"
        and inc["severity"] == "high"
        and inc["affected_service"] == "SIMRS"
        and inc["status"] == "open"
    )
    assert client.get(f"/api/incidents/{inc['id']}").json()["title"] == "Server SIMRS lambat"
    lst = client.get("/api/incidents", params={"q": "SIMRS lambat", "severity": "high", "page_size": 5}).json()
    assert lst["total"] >= 1 and all(i["severity"] == "high" for i in lst["items"])
    assert client.get("/api/incidents", params={"page_size": 3}).json()["page_size"] == 3
    nf = client.get("/api/incidents/00000000-0000-0000-0000-000000000000")
    assert nf.status_code == 404 and nf.json() == {
        "error": "not_found",
        "message": "Incident not found",
        "request_id": nf.json()["request_id"],
    }
    assert client.get("/api/incidents/not-a-uuid").status_code == 422


def _wait(client, inv_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/investigations/{inv_id}").json()
        if j["status"] in ("completed", "failed"):
            return j
        time.sleep(0.2)
    raise AssertionError("investigation did not finish")


def test_investigation_flow_and_exports(client, db):
    inc = db.scalar(select(Incident).where(Incident.ticket_number == "INC-2026-001"))
    r = client.post(f"/api/incidents/{inc.id}/investigate")
    assert r.status_code == 202 and r.json()["status"] in (
        "queued",
        "completed",
        "running",
        "collecting_evidence",
        "analyzing",
        "generating_report",
    )
    iid = r.json()["id"]
    j = _wait(client, iid)
    assert j["status"] == "completed" and j["report"]["root_cause_hypotheses"][0]["id"] == "H_NET_ACCESS" and j["ai_mode"] == "fallback"
    tl = client.get(f"/api/investigations/{iid}/timeline").json()
    assert len(tl["events"]) >= 10 and tl["evidence_timeline"] and tl["events"][0]["event_type"] == "investigation_queued"
    ev = client.get(f"/api/investigations/{iid}/evidence").json()
    assert ev and {"supporting", "contradicting"} <= {e["role"] for e in ev}
    assert all(e["role"] == "supporting" for e in client.get(f"/api/investigations/{iid}/evidence", params={"role": "supporting"}).json())
    tools = client.get(f"/api/investigations/{iid}/tools").json()
    assert tools and all(t["status"] == "success" for t in tools) and any(t["tool_name"] == "ping_host" for t in tools)
    ej = client.get(f"/api/investigations/{iid}/export/json")
    assert (
        ej.status_code == 200
        and "attachment" in ej.headers["content-disposition"]
        and ej.json()["report"]["incident"]["ticket_number"] == "INC-2026-001"
        and ej.json()["events"]
    )
    ep = client.get(f"/api/investigations/{iid}/export/pdf")
    assert ep.status_code == 200 and ep.content[:5] == b"%PDF-" and len(ep.content) > 5000
    rp = client.post(f"/api/investigations/{iid}/replay")
    assert rp.status_code == 202
    j2 = _wait(client, rp.json()["id"])
    assert j2["parent_investigation_id"] == iid
    cmp = client.get(f"/api/investigations/{iid}/compare/{rp.json()['id']}").json()
    assert cmp["reproducible"] is True
    assert client.get(f"/api/incidents/{inc.id}/investigations").json()
    assert client.get(f"/api/incidents/{inc.id}/events").json()
    assert client.get("/api/investigations", params={"incident_id": str(inc.id)}).json()["total"] >= 2


def test_exports_require_completed_investigation(client, db, session_factory, orchestrator):
    inc = db.scalar(select(Incident).where(Incident.ticket_number == "INC-2026-008"))
    with session_factory() as s:
        inv = orchestrator.create(s, s.get(Incident, inc.id))
        iid = str(inv.id)
    assert client.get(f"/api/investigations/{iid}/export/pdf").status_code == 409
    assert client.get(f"/api/investigations/{iid}/export/json").status_code == 409
    assert client.post(f"/api/incidents/{inc.id}/investigate").status_code == 409  # one running investigation per incident


def test_resolve_incident(client):
    inc = client.post(
        "/api/incidents",
        json={"title": "Printer farmasi error", "description": "Printer farmasi tidak terdeteksi dari komputer apoteker sejak pagi."},
    ).json()
    r = client.post(
        f"/api/incidents/{inc['id']}/resolve",
        json={"resolution": "Ganti kabel USB printer", "root_cause": "kabel rusak", "root_cause_category": "hardware"},
    )
    assert r.status_code == 200 and r.json()["status"] == "resolved" and r.json()["resolved_at"]


def test_infrastructure_endpoints(client):
    d = client.get("/api/devices", params={"unit": "Poli 3", "page_size": 5}).json()
    assert (
        d["total"] == 14 and len(d["items"]) == 5 and d["items"][0]["switch"] == "SW-POLI3"
    )  # 12 PCs + 1 printer + the access switch itself
    assert client.get("/api/devices", params={"q": "PC-KASIR-001"}).json()["total"] == 1
    s = client.get("/api/servers").json()
    assert {x["hostname"] for x in s} == {"SIMRS-APP-01", "SIMRS-DB-01", "DNS-01", "FILE-01", "MONITOR-01"}
    hot = {x["hostname"]: x for x in client.get("/api/servers", params={"as_of": "2026-09-25T14:10:00"}).json()}
    assert hot["SIMRS-APP-01"]["status"] == "degraded" and hot["SIMRS-APP-01"]["cpu"] > 85
    sv = client.get("/api/services", params={"as_of": "2026-09-27T13:20:00"}).json()
    assert next(x for x in sv if x["service"] == "DNS")["status"] == "down" and all("availability" in x for x in sv)
    assert client.get("/api/services/DNS/history").json()
    m = client.get("/api/servers/SIMRS-APP-01/metrics", params={"start": "2026-09-25T13:50:00", "end": "2026-09-25T14:30:00"}).json()
    assert m and max(x["cpu"] for x in m) > 90
    assert (
        client.get("/api/servers/SIMRS-APP-01/metrics", params={"start": "2026-09-01T00:00:00", "end": "2026-09-28T00:00:00"}).status_code
        == 422
    )
    t = client.get("/api/topology").json()
    assert len(t["nodes"]) >= 100 and t["edges"] and {"hostname", "ip", "device_type", "vlan", "unit", "status"} <= set(t["nodes"][0])


def test_logs_pagination_and_filters(client):
    p1 = client.get("/api/logs", params={"hostname": "SIMRS-APP-01", "page_size": 20}).json()
    p2 = client.get("/api/logs", params={"hostname": "SIMRS-APP-01", "page_size": 20, "page": 2}).json()
    assert p1["total"] > 1000 and len(p1["items"]) == 20 and p1["items"][0]["id"] != p2["items"][0]["id"]
    err = client.get(
        "/api/logs", params={"level": "error", "event_type": "HTTP_TIMEOUT", "start": "2026-09-28T09:40:00", "end": "2026-09-28T09:50:00"}
    ).json()
    assert err["total"] > 0 and all(i["log_level"] == "ERROR" for i in err["items"])
    assert client.get("/api/logs", params={"page_size": 1000}).status_code == 422
    assert "SIMRS-APP-01" in client.get("/api/logs/filters").json()["hostnames"]


def test_sops_history_dashboard_and_ai_config(client):
    sops = client.get("/api/sops").json()
    s3 = next(s for s in sops if s["sop_code"] == "SOP-003")
    assert (
        len(sops) == 8
        and s3["active_version"] == "2.1"
        and s3["effective_date"] == "2026-07-01"
        and {v["version"] for v in s3["versions"]} == {"2.0", "2.1", "2.2"}
        and s3["relevant_incidents"] > 0
    )
    assert (
        "SOP-002" in [x["sop_code"] for x in client.get("/api/sops", params={"q": "DNS"}).json()]
        and client.get("/api/sops/sop-003").json()["sop_code"] == "SOP-003"
        and client.get("/api/sops/SOP-999").status_code == 404
    )
    h = client.get("/api/historical-incidents", params={"root_cause_category": "dns", "page_size": 5}).json()
    assert h["total"] >= 15 and all(i["root_cause_category"] == "dns" and i["resolution"] for i in h["items"])
    st = client.get("/api/dashboard/stats").json()
    assert (
        st["total_incidents"] >= 8
        and st["incident_by_category"]
        and len(st["incident_by_severity"]) == 4
        and st["service_availability"]
        and st["average_resolution_minutes"] > 0
    )
    cfg = client.get("/api/ai/config").json()
    assert (
        cfg["mode"] == "DEMO_FALLBACK_MODE"
        and cfg["mcp"]["read_only"] is True
        and len(cfg["mcp"]["tools"]) == 10
        and abs(sum(cfg["retrieval_weights"].values()) - 1) < 1e-9
    )
    assert client.post("/api/ai/test/llm").json()["ok"] is False and client.post("/api/ai/test/mcp").json()["ok"] is True


def test_demo_scenarios_endpoint(client):
    sc = client.get("/api/scenarios").json()
    assert [s["id"] for s in sc] == ["S1", "S2", "S3", "S4", "S5"] and all(s["incident_id"] and s["prefill"]["description"] for s in sc)


def test_openapi_documents_every_operation(client):
    spec = client.get("/openapi.json").json()
    ops = [(p, m, o) for p, item in spec["paths"].items() for m, o in item.items()]
    assert len(ops) >= 35 and all(o.get("summary") for _, _, o in ops)
    needed = {
        "/api/health",
        "/api/incidents",
        "/api/incidents/{incident_id}",
        "/api/incidents/{incident_id}/investigate",
        "/api/investigations/{inv_id}",
        "/api/investigations/{inv_id}/timeline",
        "/api/investigations/{inv_id}/evidence",
        "/api/investigations/{inv_id}/tools",
        "/api/devices",
        "/api/servers",
        "/api/services",
        "/api/logs",
        "/api/sops",
        "/api/historical-incidents",
        "/api/topology",
        "/api/dashboard/stats",
        "/api/investigations/{inv_id}/export/json",
        "/api/investigations/{inv_id}/export/pdf",
    }
    assert needed <= set(spec["paths"])


def test_unhandled_errors_are_sanitized(settings, session_factory, mcp_client, embedder):
    from fastapi.testclient import TestClient

    from app.ai.llm import NullProvider
    from app.main import create_app

    app = create_app(settings, session_factory=session_factory, mcp=mcp_client, llm=NullProvider(), embedder=embedder)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internals: password=hunter2")

    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500 and "hunter2" not in r.text and r.json()["error"] == "internal_error"
    _ = pytest


def test_spa_fallback_serves_frontend_but_keeps_api_errors(session_factory, settings, tmp_path):
    from app.main import create_app

    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<html>spa</html>")
    app = create_app(settings.model_copy(update={"frontend_dist": tmp_path}), session_factory=session_factory)
    with TestClient(app) as c:
        assert "spa" in c.get("/incidents/some-id").text  # deep link -> index.html
        assert c.get("/assets/app.js").text == "console.log(1)"
        r = c.get("/api/does-not-exist")
        assert r.status_code == 404 and r.json()["error"] == "not_found"  # API stays JSON
        assert c.get("/api/health").status_code in (200, 503)


def test_module_exposes_asgi_app_for_uvicorn():
    import app.main as m

    assert hasattr(m, "app") and m.app.title.startswith("OpsRAG-X")
