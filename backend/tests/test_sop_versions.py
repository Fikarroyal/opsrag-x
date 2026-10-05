from datetime import datetime

from app.rag.retriever import Retriever


def chosen(db, embedder, when):
    versions, decisions = Retriever(db, embedder).applicable_sop_versions(when)
    return {v.sop_code: v.version for v in versions}, decisions


def test_current_incident_uses_active_version_not_future_one(db, embedder):
    c, dec = chosen(db, embedder, datetime(2026, 9, 28, 9, 42))
    assert c["SOP-003"] == "2.1" and c["SOP-001"] == "1.1"
    future = next(d for d in dec if d["sop_code"] == "SOP-003" and d["version"] == "2.2")
    assert not future["selected"] and "not yet effective" in future["reason"]


def test_older_incident_uses_older_version(db, embedder):
    c, _ = chosen(db, embedder, datetime(2026, 5, 1))
    assert c["SOP-003"] == "2.0" and c["SOP-001"] == "1.0"


def test_version_becomes_effective_on_its_date(db, embedder):
    assert chosen(db, embedder, datetime(2026, 10, 14, 23, 59))[0]["SOP-003"] == "2.1"
    assert chosen(db, embedder, datetime(2026, 10, 15, 0, 0))[0]["SOP-003"] == "2.2"
    assert chosen(db, embedder, datetime(2027, 1, 1))[0]["SOP-003"] == "2.2"


def test_no_sop_before_first_effective_date(db, embedder):
    c, _ = chosen(db, embedder, datetime(2025, 12, 1))
    assert "SOP-003" not in c and c == {}


def test_retrieved_chunks_only_come_from_applicable_versions(db, embedder):
    from app.rag.retriever import RetrievalQuery

    hits, _ = Retriever(db, embedder).retrieve_sops(
        RetrievalQuery(text="network connectivity switch uplink packet loss", incident_time=datetime(2026, 5, 1), category="network"), 12
    )
    assert hits and all(
        h.payload["version"] != "2.2" and not (h.payload["sop_code"] == "SOP-003" and h.payload["version"] == "2.1") for h in hits
    )
