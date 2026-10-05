#!/usr/bin/env python
"""Live health check against a running stack (backend + MCP server + DB).

    python scripts/health_check.py                        # health only
    python scripts/health_check.py --investigate INC-2026-001   # also run + verify an investigation

Exit code 0 only when every executed check passed.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
from typing import Any

import httpx

OK, FAIL = "PASS", "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--mcp", default="http://localhost:8001")
    ap.add_argument("--frontend", default=None, help="frontend base URL; checks that /api is proxied to the backend")
    ap.add_argument("--investigate", metavar="TICKET", help="run an investigation for this ticket number and verify the result")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument(
        "--email", default=os.environ.get("OPSRAGX_EMAIL"), help="existing account to sign in with (default: register a throwaway account)"
    )
    ap.add_argument("--password", default=os.environ.get("OPSRAGX_PASSWORD"))
    a = ap.parse_args()

    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"[{OK if ok else FAIL}] {name}" + (f" - {detail}" if detail else ""), flush=True)

    c = httpx.Client(base_url=a.api, timeout=30)
    try:
        r = c.get("/api/health")
        body: dict[str, Any] = r.json()
        check("backend /api/health reachable", r.status_code in (200, 503), f"HTTP {r.status_code}")
        check("database healthy", body.get("database") == "healthy", str(body.get("database")))
        check("RAG data present", body.get("rag") == "healthy", str(body.get("rag_detail")))
        check("MCP server reachable from backend", body.get("mcp") == "healthy", str(body.get("mcp")))
        print(f"       llm={body.get('llm')} mode={body.get('mode')} overall={body.get('status')}")
    except Exception as exc:
        check("backend /api/health reachable", False, f"{type(exc).__name__}: {exc}")
        return 1

    try:
        m = httpx.post(f"{a.mcp}/api/tools/ping_host", json={"host": "SIMRS-APP-01"}, timeout=15)
        check("MCP REST facade answers read-only tool call", m.status_code == 200 and m.json().get("ok") is True, f"HTTP {m.status_code}")
    except Exception as exc:
        check("MCP REST facade answers read-only tool call", False, type(exc).__name__)

    anon = c.get("/api/incidents")
    check("protected API rejects anonymous requests", anon.status_code == 401, f"HTTP {anon.status_code}")
    if a.email and a.password:
        auth = c.post("/api/auth/login", json={"email": a.email, "password": a.password})
        what = f"sign in as {a.email}"
    else:
        tmp = f"healthcheck.{secrets.token_hex(4)}@rsyogyakarta.local"
        a.password = secrets.token_urlsafe(12)
        auth = c.post("/api/auth/register", json={"name": "Health Check", "email": tmp, "password": a.password})
        what = "register a throwaway account"
    check(what, auth.status_code in (200, 201), f"HTTP {auth.status_code}")
    if auth.status_code not in (200, 201):
        return 1
    me = c.get("/api/auth/me")
    check("session cookie accepted", me.status_code == 200, me.json().get("email", ""))

    r = c.get("/openapi.json")
    check(
        "Swagger/OpenAPI available",
        r.status_code == 200 and "paths" in r.json(),
        f"{len(r.json().get('paths', {}))} paths" if r.status_code == 200 else "",
    )

    if a.frontend:
        try:
            f = httpx.get(f"{a.frontend}/api/health", timeout=15)
            check("frontend proxies /api to backend", f.status_code in (200, 503) and "database" in f.json(), f"HTTP {f.status_code}")
        except Exception as exc:
            check("frontend proxies /api to backend", False, type(exc).__name__)

    if a.investigate:
        r = c.get("/api/incidents", params={"q": a.investigate, "page_size": 5})
        items = [i for i in r.json().get("items", []) if i["ticket_number"] == a.investigate]
        check(f"incident {a.investigate} exists", bool(items))
        if items:
            inc = items[0]
            r = c.post(f"/api/incidents/{inc['id']}/investigate")
            check("investigation accepted (202)", r.status_code == 202, f"HTTP {r.status_code}")
            inv_id = r.json().get("id")
            deadline = time.time() + a.timeout
            inv: dict[str, Any] = {}
            while time.time() < deadline:
                inv = c.get(f"/api/investigations/{inv_id}").json()
                if inv.get("status") in ("completed", "failed"):
                    break
                time.sleep(1.0)
            check(
                "investigation completed",
                inv.get("status") == "completed",
                f"status={inv.get('status')} duration_ms={inv.get('duration_ms')}",
            )
            print(
                f"       category={inv.get('root_cause_category')} evidence_confidence_score={inv.get('confidence_score')} mode={inv.get('ai_mode')}"
            )
            ev = c.get(f"/api/investigations/{inv_id}/evidence").json()
            tools = c.get(f"/api/investigations/{inv_id}/tools").json()
            check("evidence persisted", len(ev) > 0, f"{len(ev)} items")
            check("MCP tool executions audited", len(tools) > 0, f"{len(tools)} calls")
            check("report generated", bool(inv.get("report")) and bool(inv.get("summary")))
            check("export JSON", c.get(f"/api/investigations/{inv_id}/export/json").status_code == 200)
            pdf = c.get(f"/api/investigations/{inv_id}/export/pdf")
            check("export PDF", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", f"{len(pdf.content)} bytes")

    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
