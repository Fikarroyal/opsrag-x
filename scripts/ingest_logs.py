#!/usr/bin/env python
"""Ingest server/network logs from CSV or JSON with schema validation; malformed records are rejected with a clear report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import session, settings

from app.services import log_service


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", type=Path, help="CSV/JSON log files (default: data/raw server_logs.csv + network_logs.csv)")
    ap.add_argument("--kind", choices=["server", "network"], help="force schema (auto-detected by default)")
    a = ap.parse_args()
    files = a.files or [settings.raw_dir / "server_logs.csv", settings.raw_dir / "network_logs.csv"]
    rc = 0
    with session() as s:
        for f in files:
            try:
                rep = log_service.ingest_file(s, f, a.kind)
            except (ValueError, OSError) as exc:
                print(f"ERROR {f}: {exc}", file=sys.stderr)
                rc = 1
                continue
            print(json.dumps({k: v for k, v in rep.items() if k != "rejects"}))
            for r in rep["rejects"][:10]:
                print(f"  rejected row {r['row']}: {r['reason']}", file=sys.stderr)
            rc = rc or (2 if rep["rejected"] else 0)
    return rc


if __name__ == "__main__":
    sys.exit(main())
