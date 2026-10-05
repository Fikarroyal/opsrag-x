#!/usr/bin/env python
"""(Re)create embeddings for SOP chunks and historical incidents (missing ones, or all with --force / after changing EMBEDDING_MODEL)."""

from __future__ import annotations

import argparse

from _common import session

from app.rag.embeddings import get_embedder
from app.rag.ingestion import create_embeddings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    emb = get_embedder()
    with session() as s:
        print(f"embedder={emb.name} dim={emb.dim}", create_embeddings(s, emb, force=a.force))


if __name__ == "__main__":
    main()
