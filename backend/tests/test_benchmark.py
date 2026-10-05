from sqlalchemy import select

from app.database.models import Incident
from app.evaluation.benchmark import f1, purge, run_benchmark


def test_f1_helper():
    assert f1({"a", "b"}, {"a", "b"}) == 1.0 and f1({"a"}, {"b"}) == 0.0 and 0 < f1({"a", "c"}, {"a", "b"}) < 1 and f1(set(), {"a"}) == 0.0


def test_benchmark_runs_and_cleans_up(session_factory, settings, mcp_client, embedder):
    res = run_benchmark(session_factory, settings, mcp_client, embedder, None, limit=10, write=False)
    assert [e["id"] for e in res["experiments"]] == ["A", "B", "C", "D"] and res["benchmark_size"] == 10
    m = {e["id"]: e["metrics"] for e in res["experiments"]}
    for e in m.values():
        assert 0 <= e["classification_accuracy"] <= 1 and 0 <= e["root_cause_agreement"] <= 1 and e["avg_time_s"] >= 0
    assert m["A"].get("precision_at_k") is None and m["A"].get("tool_selection_f1") is None  # not applicable -> absent, not fake zero
    assert m["D"]["evidence_coverage"] > m["B"]["evidence_coverage"] and m["D"]["tool_selection_f1"] > 0.5
    assert len(res["items"]) == 10 and "notes" in res
    with session_factory() as s:
        assert s.scalar(select(Incident).where(Incident.ticket_number.like("BENCH-%"))) is None
        purge(s)
