#!/usr/bin/env python
"""Ingest the SOP PDF (version-aware) and infrastructure documentation: parse -> clean -> chunk -> metadata -> embed -> store. Idempotent."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import session, settings

from app.rag.ingestion import ingest_infra_doc, ingest_sop_pdf


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sop", type=Path, default=settings.data_dir / "sop" / "hospital_it_sop.pdf")
    ap.add_argument("--infra", type=Path, default=settings.data_dir / "docs" / "infrastructure.md")
    a = ap.parse_args()
    with session() as s:
        print("sop   :", ingest_sop_pdf(s, a.sop))
        print("infra :", ingest_infra_doc(s, a.infra))


if __name__ == "__main__":
    main()
