"""Shared fixtures. Tests run on in-memory SQLite + the hashing embedder + the in-process MCP REST facade:
no PostgreSQL, Ollama, model download or network is needed (`pytest` just works)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

os.environ["EMBEDDING_BACKEND"] = "hashing"
os.environ["LLM_ENABLED"] = "false"
os.environ["AUTH_REQUIRED"] = "false"  # auth is covered by tests/test_auth.py with an explicit settings override
os.environ["DATABASE_URL"] = "sqlite://"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mcp-server"))

import pytest  # noqa: E402
import server as mcp_server  # noqa: E402  (mcp-server/server.py)
from starlette.testclient import TestClient  # noqa: E402

from app.ai.llm import NullProvider  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402
from app.mcp.client import MCPClient  # noqa: E402
from app.rag.embeddings import HashingEmbedder  # noqa: E402
from app.rag.ingestion import ingest_historical_csv, ingest_infra_doc, ingest_sop_pdf  # noqa: E402
from app.services import log_service  # noqa: E402
from app.services.seed_service import seed_core  # noqa: E402

logging.disable(logging.CRITICAL)


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def embedder():
    return HashingEmbedder(get_settings().embedding_dim)


@pytest.fixture(scope="session")
def session_factory(settings, embedder):
    engine = make_engine("sqlite://")
    init_db(engine)
    sf = make_session_factory(engine)
    with sf() as s:
        seed_core(s, settings.raw_dir)
        for f in ("server_logs.csv", "network_logs.csv"):
            log_service.ingest_file(s, settings.raw_dir / f)
        ingest_historical_csv(s, settings.raw_dir / "historical_incidents.csv", embedder)
        ingest_sop_pdf(s, settings.data_dir / "sop" / "hospital_it_sop.pdf", embedder)
        ingest_infra_doc(s, settings.data_dir / "docs" / "infrastructure.md", embedder)
    return sf


@pytest.fixture(scope="session")
def mcp_client():
    return MCPClient(transport="rest", http_client=TestClient(mcp_server.build_app()))


@pytest.fixture()
def db(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture(scope="session")
def client(settings, session_factory, mcp_client, embedder):
    app = create_app(settings, session_factory=session_factory, mcp=mcp_client, llm=NullProvider(), embedder=embedder)
    return TestClient(app)


@pytest.fixture(scope="session")
def orchestrator(session_factory, settings, mcp_client, embedder):
    from app.investigation.orchestrator import InvestigationOrchestrator

    return InvestigationOrchestrator(session_factory, settings, mcp_client, NullProvider(), embedder)


def run_investigation(session_factory, orchestrator, ticket: str):
    """Create + run an investigation for a seeded ticket and return the stored Investigation."""
    from sqlalchemy import select

    from app.database.models import Incident, Investigation

    with session_factory() as s:
        inc = s.scalar(select(Incident).where(Incident.ticket_number == ticket))
        inv = orchestrator.create(s, inc)
        iid = inv.id
    orchestrator.run(iid)
    with session_factory() as s:
        return s.get(Investigation, iid)
