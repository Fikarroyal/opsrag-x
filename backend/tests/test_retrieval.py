from datetime import datetime, timedelta

import numpy as np
import pytest

from app.database.models import HistoricalIncident
from app.rag.chunking import parse_sop_text
from app.rag.embeddings import HashingEmbedder, cosine
from app.rag.ingestion import ingest_historical_csv, ingest_sop_pdf
from app.rag.retriever import RetrievalQuery, Retriever

T = datetime(2026, 9, 28, 9, 42)


def q(text, **kw):
    return RetrievalQuery(text=text, incident_time=kw.pop("t", T), **kw)


def test_hashing_embedder_is_deterministic_and_semantic(embedder):
    a, b, c = embedder.embed(
        ["SIMRS tidak bisa dibuka dari Poli 3", "SIMRS tidak dapat diakses dari Poli 2", "printer kasir kehabisan kertas"]
    )
    assert np.allclose(embedder.embed(["x y z"]), embedder.embed(["x y z"]))
    assert abs(np.linalg.norm(a) - 1) < 1e-9 and cosine(a, b) > cosine(a, c)


def test_semantic_sop_retrieval_finds_relevant_sop(db, embedder):
    r = Retriever(db, embedder)
    hits, _ = r.retrieve_sops(q("DNS SERVFAIL resolve simrs.internal gagal di semua unit", category="dns", service="DNS"), 6)
    assert hits and hits[0].payload["sop_code"] == "SOP-002"
    hits, _ = r.retrieve_sops(q("switch akses uplink packet loss beberapa endpoint", category="network"), 6)
    assert any(h.payload["sop_code"] in ("SOP-003", "SOP-007") for h in hits[:3])


def test_historical_retrieval_returns_similar_network_incidents_without_future_leakage(db, embedder):
    r = Retriever(db, embedder)
    hits = r.retrieve_historical(
        q(
            "SIMRS tidak bisa dibuka dari komputer Poli 3. Beberapa komputer packet loss.",
            category="application",
            service="SIMRS",
            unit="Poli 3",
        ),
        8,
    )
    assert len(hits) == 8
    assert sum(h.payload["root_cause_category"] == "network" for h in hits) >= 5
    assert all(datetime.fromisoformat(h.payload["timestamp"]) < T for h in hits)
    assert hits == sorted(hits, key=lambda h: h.score, reverse=True)
    for h in hits[:1]:
        assert {"incident_key", "timestamp", "unit", "root_cause", "resolution", "resolution_time_minutes", "similarity"} <= set(h.payload)


def test_historical_incidents_before_incident_time_only(db, embedder):
    r = Retriever(db, embedder)
    early = datetime(2026, 2, 10)
    hits = r.retrieve_historical(q("SIMRS tidak bisa dibuka", t=early), 10)
    assert all(datetime.fromisoformat(h.payload["timestamp"]) < early for h in hits)


def test_temporal_weighting_prefers_recent_equally_similar_items(db, embedder):
    base = db.query(HistoricalIncident).first()
    assert base is not None
    text = "zzqx unik frase pengujian temporal gangguan switch"
    for i, age in enumerate((2, 400)):
        h = HistoricalIncident(
            incident_key=f"TMP-{i}",
            timestamp=T - timedelta(days=age),
            unit="Poli 1",
            description=text,
            category="network",
            severity="low",
            status="resolved",
            root_cause="x",
            root_cause_category="network",
        )
        h.embedding, h.embedding_model = (embedder.embed([Retriever.hist_text(h)])[0].tolist(), embedder.name)
        db.add(h)
    db.commit()
    try:
        r = Retriever(db, embedder)
        with_t = {h.payload["incident_key"]: h.score for h in r.retrieve_historical(q(text), 6, use_temporal=True)}
        without = {h.payload["incident_key"]: h.score for h in r.retrieve_historical(q(text), 6, use_temporal=False)}
        gap_with, gap_without = (with_t["TMP-0"] - with_t["TMP-1"], without["TMP-0"] - without["TMP-1"])
        assert gap_with > 0.15  # recent incident clearly preferred when temporal weighting is on
        assert 0 <= gap_without < gap_with / 4  # without it only the small source-reliability prior remains (identical semantic score)
    finally:
        db.query(HistoricalIncident).filter(HistoricalIncident.incident_key.like("TMP-%")).delete(synchronize_session=False)
        db.commit()


class BrokenEmbedder:
    name, dim = "broken", 384

    def embed(self, texts):
        raise RuntimeError("model unavailable")


def test_keyword_fallback_when_embedding_fails(db):
    r = Retriever(db, BrokenEmbedder())
    hits = r.retrieve_historical(q("SIMRS tidak bisa dibuka packet loss", category="application"), 5)
    assert hits and r.last_mode == "keyword"
    sops, _ = r.retrieve_sops(q("DNS SERVFAIL resolve", category="dns"), 4)
    assert sops and r.last_mode == "keyword"


def test_sop_parsing_extracts_versions_and_sections(settings):
    from app.rag.chunking import extract_pdf_text

    parsed = parse_sop_text(extract_pdf_text(settings.data_dir / "sop" / "hospital_it_sop.pdf"))
    codes = {(p.sop_code, p.version) for p in parsed}
    assert {("SOP-003", "2.0"), ("SOP-003", "2.1"), ("SOP-003", "2.2"), ("SOP-001", "1.1")} <= codes
    v = next(p for p in parsed if (p.sop_code, p.version) == ("SOP-003", "2.1"))
    assert {
        "tujuan",
        "indikasi",
        "prasyarat",
        "langkah_investigasi",
        "indikator_evidence",
        "langkah_remediation",
        "verifikasi",
        "rollback",
        "catatan",
    } <= set(v.sections)
    assert v.title == "Penanganan Network Connectivity" and str(v.effective_date) == "2026-07-01"


def test_ingestion_is_idempotent(db, settings, embedder):
    rep = ingest_sop_pdf(db, settings.data_dir / "sop" / "hospital_it_sop.pdf", embedder)
    assert rep["versions_added"] == 0 and rep["versions_skipped_duplicate"] == 11
    assert ingest_historical_csv(db, settings.raw_dir / "historical_incidents.csv", embedder)["historical_added"] == 0
