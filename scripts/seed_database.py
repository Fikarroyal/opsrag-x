#!/usr/bin/env python
"""Seed the synthetic hospital: users, servers, devices, services, tickets, logs and historical incidents."""

from __future__ import annotations

import json

from _common import session, settings

from app.rag.ingestion import ingest_historical_csv
from app.services import log_service
from app.services.seed_service import seed_core, seed_summary


def main() -> None:
    raw = settings.raw_dir
    with session() as s:
        print("core       :", seed_core(s, raw))
        for f in ("server_logs.csv", "network_logs.csv"):
            rep = log_service.ingest_file(s, raw / f)
            print(f"logs       : {rep['file']} inserted={rep['inserted']} skipped={rep['skipped_duplicates']} rejected={rep['rejected']}")
        print("historical :", ingest_historical_csv(s, raw / "historical_incidents.csv"))
        print("summary    :", json.dumps(seed_summary(s)))


if __name__ == "__main__":
    main()
