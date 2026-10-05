"""RAG ingestion: SOP PDF, infrastructure docs, historical incidents (+ embeddings). Idempotent (no duplicates)."""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import HistoricalIncident, Resolution, SopChunk, SopDocument, SopVersion
from app.rag.chunking import chunk_markdown, extract_pdf_text, parse_sop_text
from app.rag.embeddings import Embedder, get_embedder
from app.rag.retriever import Retriever

logger = logging.getLogger(__name__)


def _embed_safely(embedder: Embedder, texts: list[str]) -> list[Any]:
    try:
        return [v.tolist() for v in embedder.embed(texts)]
    except Exception as exc:
        logger.warning("embedding failed (%s); rows stored without vectors (keyword fallback will be used)", exc)
        return [None] * len(texts)


def ingest_sop_pdf(session: Session, path: Path, embedder: Embedder | None = None) -> dict[str, int]:
    embedder = embedder or get_embedder()
    text = extract_pdf_text(path)
    parsed = parse_sop_text(text)
    report = {"versions_found": len(parsed), "versions_added": 0, "versions_skipped_duplicate": 0, "chunks_added": 0}
    for pv in parsed:
        if session.scalar(select(SopVersion).where(SopVersion.content_hash == pv.content_hash)):
            report["versions_skipped_duplicate"] += 1
            continue
        doc = session.scalar(select(SopDocument).where(SopDocument.doc_code == pv.sop_code))
        if doc is None:
            doc = SopDocument(doc_code=pv.sop_code, title=pv.title, doc_type="sop", category=pv.category, source_path=path.name)
            session.add(doc)
            session.flush()
        ver = SopVersion(
            document_id=doc.id,
            sop_code=pv.sop_code,
            version=pv.version,
            effective_date=pv.effective_date,
            status=pv.status,
            content_hash=pv.content_hash,
            sections=pv.sections,
        )
        session.add(ver)
        session.flush()
        vecs = _embed_safely(embedder, [c["text"] for c in pv.chunks])
        for c, vec in zip(pv.chunks, vecs, strict=True):
            session.add(
                SopChunk(
                    version_id=ver.id,
                    document_id=doc.id,
                    sop_code=pv.sop_code,
                    section=c["section"],
                    chunk_index=c["chunk_index"],
                    text=c["text"],
                    embedding=vec,
                    embedding_model=embedder.name if vec is not None else None,
                    meta=c["metadata"],
                )
            )
            report["chunks_added"] += 1
        report["versions_added"] += 1
    session.commit()
    return report


def ingest_infra_doc(session: Session, path: Path, embedder: Embedder | None = None) -> dict[str, int]:
    import hashlib

    embedder = embedder or get_embedder()
    raw = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if session.scalar(select(SopVersion).where(SopVersion.content_hash == digest)):
        return {"versions_added": 0, "versions_skipped_duplicate": 1, "chunks_added": 0}
    doc = session.scalar(select(SopDocument).where(SopDocument.doc_code == "INFRA-DOC")) or SopDocument(
        doc_code="INFRA-DOC", title="Dokumentasi Infrastruktur TI", doc_type="infra_doc", category=None, source_path=path.name
    )
    session.add(doc)
    session.flush()
    ver = SopVersion(
        document_id=doc.id,
        sop_code="INFRA-DOC",
        version="1.0",
        effective_date=datetime(2026, 1, 1).date(),
        status="active",
        content_hash=digest,
        sections={"raw": raw},
    )
    session.add(ver)
    session.flush()
    chunks = chunk_markdown(raw, path.name)
    vecs = _embed_safely(embedder, [c["text"] for c in chunks])
    for c, vec in zip(chunks, vecs, strict=True):
        session.add(
            SopChunk(
                version_id=ver.id,
                document_id=doc.id,
                sop_code="INFRA-DOC",
                section=c["section"],
                chunk_index=c["chunk_index"],
                text=c["text"],
                embedding=vec,
                embedding_model=embedder.name if vec is not None else None,
                meta=c["metadata"],
            )
        )
    session.commit()
    return {"versions_added": 1, "versions_skipped_duplicate": 0, "chunks_added": len(chunks)}


def ingest_historical_csv(session: Session, path: Path, embedder: Embedder | None = None) -> dict[str, int]:
    embedder = embedder or get_embedder()
    existing = set(session.scalars(select(HistoricalIncident.incident_key)))
    rows = [r for r in csv.DictReader(path.open(encoding="utf-8")) if r["incident_id"] not in existing]
    added = 0
    objs: list[HistoricalIncident] = []
    for r in rows:
        obj = HistoricalIncident(
            incident_key=r["incident_id"],
            timestamp=datetime.fromisoformat(r["timestamp"]),
            unit=r["unit"] or None,
            device=r["device"] or None,
            description=r["description"],
            category=r["category"],
            severity=r["severity"],
            status=r["status"],
            affected_service=r["affected_service"] or None,
            root_cause=r["root_cause"],
            root_cause_category=r["root_cause_category"],
            pattern=r.get("pattern") or None,
        )
        obj.resolution = Resolution(
            root_cause=r["root_cause"],
            root_cause_category=r["root_cause_category"],
            resolution=r["resolution"],
            resolution_time_minutes=int(r["resolution_time_minutes"]),
        )
        objs.append(obj)
    vecs = _embed_safely(embedder, [Retriever.hist_text(o) for o in objs])
    for o, vec in zip(objs, vecs, strict=True):
        o.embedding, o.embedding_model = vec, (embedder.name if vec is not None else None)
        session.add(o)
        added += 1
    session.commit()
    return {"historical_added": added, "historical_skipped_duplicate": len(existing)}


def create_embeddings(session: Session, embedder: Embedder | None = None, *, force: bool = False) -> dict[str, int]:
    """(Re)compute embeddings for rows that lack them or that were produced by another embedder."""
    embedder = embedder or get_embedder()
    counts = {"sop_chunks": 0, "historical_incidents": 0}
    targets: list[tuple[Any, str, Any]] = [
        (SopChunk, "sop_chunks", lambda o: o.text),
        (HistoricalIncident, "historical_incidents", Retriever.hist_text),
    ]
    for model, key, textfn in targets:
        all_rows: list[Any] = list(session.scalars(select(model)))
        rows: list[Any] = [r for r in all_rows if force or r.embedding is None or r.embedding_model != embedder.name]
        for start in range(0, len(rows), 64):
            batch = rows[start : start + 64]
            vecs = _embed_safely(embedder, [textfn(r) for r in batch])
            for r, v in zip(batch, vecs, strict=True):
                if v is not None:
                    r.embedding, r.embedding_model = v, embedder.name
                    counts[key] += 1
        session.commit()
    return counts
