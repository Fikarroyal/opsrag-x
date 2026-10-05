#!/usr/bin/env python
"""First-run initialisation: wait for DB -> migrations -> seed -> ingest SOP -> embeddings. Safe to re-run (idempotent)."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from _common import ROOT, session, settings
from sqlalchemy import func, select, text

from app.database.models import Incident
from app.database.session import get_engine, init_db
from app.rag.embeddings import get_embedder
from app.rag.ingestion import create_embeddings, ingest_historical_csv, ingest_infra_doc, ingest_sop_pdf
from app.services import log_service
from app.services.seed_service import seed_core, seed_summary


def wait_for_db(timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            with get_engine().connect() as c:
                c.execute(text("SELECT 1"))
            return
        except Exception as exc:
            if time.time() > deadline:
                raise SystemExit(f"database not reachable: {type(exc).__name__}") from None
            print("waiting for database...", flush=True)
            time.sleep(2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--if-empty", action="store_true", help="skip seeding when incidents already exist")
    a = ap.parse_args()
    wait_for_db()
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        init_db(engine)  # local mode: create tables directly (Alembic migrations target PostgreSQL + pgvector)
        print("schema: created (SQLite local mode)", flush=True)
    else:
        cwd = ROOT / "backend" if (ROOT / "backend" / "alembic.ini").exists() else ROOT
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=cwd, check=True)
        print("migrations: ok", flush=True)
    with session() as s:
        if a.if_empty and (s.scalar(select(func.count()).select_from(Incident)) or 0) > 0:
            print("database already seeded; skipping (use scripts/seed_database.py to force)")
            return
        raw = settings.raw_dir
        print("core      :", seed_core(s, raw))
        for f in ("server_logs.csv", "network_logs.csv"):
            r = log_service.ingest_file(s, raw / f)
            print(f"logs      : {r['file']} inserted={r['inserted']} rejected={r['rejected']}")
        emb = get_embedder()
        print("historical:", ingest_historical_csv(s, raw / "historical_incidents.csv", emb))
        print("sop       :", ingest_sop_pdf(s, settings.data_dir / "sop" / "hospital_it_sop.pdf", emb))
        print("infra doc :", ingest_infra_doc(s, settings.data_dir / "docs" / "infrastructure.md", emb))
        print("embeddings:", create_embeddings(s, emb), f"({emb.name})")
        print("summary   :", seed_summary(s))


if __name__ == "__main__":
    main()
