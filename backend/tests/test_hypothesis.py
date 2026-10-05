import math
from datetime import datetime

from app.ai.hypothesis import CATALOG, evaluate
from app.investigation.confidence import ambiguity_factor, coverage_factor, evidence_confidence, hypothesis_score
from app.investigation.evidence import PRIORITY, EvidenceStore
from app.investigation.topology import ScopeAnalysis

T = datetime(2026, 9, 28, 9, 42)
W = {"evidence": 0.35, "temporal": 0.20, "topology": 0.15, "history": 0.10, "state": 0.10, "source": 0.10}
LABELS = {"switch": "SW-POLI3", "device": "PC-POLI3-001", "server": "SIMRS-APP-01", "dns": "DNS-01", "db": "SIMRS-DB-01"}


def scope(level="single_unit", shared="SW-POLI3"):
    return ScopeAnalysis(["PC-POLI3-001", "PC-POLI3-002"], {"SW-POLI3": ["a", "b"]}, shared, {}, ["Poli 3"], [], level)


def store_with(*items):
    st = EvidenceStore(T)
    for tags, src, ts in items:
        st.add(src, f"evidence {tags}", tags=list(tags), timestamp=ts, relevance=0.9)
    return st


def test_score_formula_and_bounds():
    comps = {"evidence": 1, "temporal": 1, "topology": 1, "history": 1, "state": 1, "source": 1}
    assert hypothesis_score(comps, W) == 1.0
    assert hypothesis_score({}, W) == 0.0
    assert math.isclose(hypothesis_score({"evidence": 1.0}, W), 0.35)
    assert hypothesis_score({k: 5 for k in W}, W) == 1.0  # clamped


def test_confidence_factors_never_reach_certainty():
    assert coverage_factor(0, 10) == 0.75 and coverage_factor(10, 10) == 1.0 and coverage_factor(0, 0) == 1.0
    assert ambiguity_factor(0.8, 0.75) == 0.9 and ambiguity_factor(0.8, 0.5) == 1.0 and ambiguity_factor(0.8, None) == 1.0
    assert evidence_confidence(1.0, 5, 5, 1.0, 0.1, is_top=True).confidence <= 0.99
    assert (
        evidence_confidence(0.8, 3, 6, 0.8, 0.79, is_top=True).confidence < evidence_confidence(0.8, 6, 6, 0.8, 0.5, is_top=True).confidence
    )


def test_catalog_weights_sum_to_one():
    for d in CATALOG:
        assert math.isclose(sum(i[2] for i in d.supports), 1.0, abs_tol=1e-9), d.id
        assert d.direct <= {i[0] for i in d.supports}, d.id


def test_network_evidence_ranks_network_hypothesis_first():
    st = store_with(
        (("multi_endpoint_loss",), "network_log", T),
        (("shared_access_switch",), "topology", None),
        (("switch_interface_errors", "switch_latency_high"), "network_log", T),
        (("unit_only_impact", "control_group_ok"), "log_correlation", T),
        (("pattern_network_first",), "log_correlation", T),
        (("server_healthy",), "mcp_tool", T),
        (("dns_ok",), "mcp_tool", T),
    )
    h = evaluate(st, scope(), [{"score": 0.6, "root_cause_category": "network"}], {"network": 0.9}, W, LABELS, 6, 6, 0.4)
    assert h[0].id == "H_NET_ACCESS" and h[0].status == "most_supported" and 0.7 < h[0].confidence < 1
    assert "SW-POLI3" in h[0].description
    assert all(x.id != "H_NET_ACCESS" or x.score >= y.score for x in h for y in h if y is not x and x.id == "H_NET_ACCESS")
    assert st.by_key("E01").role == "supporting"


def test_contradicting_evidence_lowers_confidence_and_is_reported():
    base = [
        (("multi_endpoint_loss",), "network_log", T),
        (("shared_access_switch",), "topology", None),
        (("switch_interface_errors",), "network_log", T),
        (("server_healthy",), "mcp_tool", T),
    ]
    clean = evaluate(store_with(*base), scope(), [], {"network": 0.9}, W, LABELS, 4, 4, 0.4)[0]
    contra = evaluate(
        store_with(*base, (("reported_internet_ok",), "incident_report", T), (("partial_switch_impact",), "network_log", T)),
        scope(),
        [],
        {"network": 0.9},
        W,
        LABELS,
        4,
        4,
        0.4,
    )
    top = next(x for x in contra if x.id == "H_NET_ACCESS")
    assert (
        top.confidence < clean.confidence
        and set(top.contradicted_by) == {"internet_reported_ok", "partial_switch_impact"}
        and top.contradicting
    )


def test_context_alone_cannot_create_a_conclusion():
    st = store_with((("server_healthy",), "mcp_tool", T), (("dns_ok",), "mcp_tool", T), (("control_group_ok",), "mcp_tool", T))
    hyps = evaluate(st, scope("single_device", None), [{"score": 0.9, "root_cause_category": "hardware"}], {}, W, LABELS, 3, 3, 0.4)
    assert all(h.status != "most_supported" for h in hyps)  # only elimination evidence (healthy server/DNS) is not evidence for any cause


def test_empty_evidence_is_inconclusive():
    hyps = evaluate(EvidenceStore(T), scope("unknown", None), [], {}, W, LABELS, 0, 0, 0.4)
    assert all(h.status in ("unlikely", "insufficient_evidence") for h in hyps) and hyps[0].confidence < 0.2


def test_failed_tools_reduce_confidence():
    st1 = store_with(
        (("dns_failed", "dns_failure_logs"), "mcp_tool", T),
        (("hospital_wide_impact",), "log_correlation", T),
        (("ip_http_healthy",), "mcp_tool", T),
        (("pattern_dns_first",), "log_correlation", T),
    )
    a = evaluate(st1, scope("hospital_wide", None), [], {"dns": 0.9}, W, LABELS, 5, 5, 0.4)[0]
    b = evaluate(
        store_with(
            (("dns_failed", "dns_failure_logs"), "mcp_tool", T),
            (("hospital_wide_impact",), "log_correlation", T),
            (("ip_http_healthy",), "mcp_tool", T),
            (("pattern_dns_first",), "log_correlation", T),
        ),
        scope("hospital_wide", None),
        [],
        {"dns": 0.9},
        W,
        LABELS,
        1,
        5,
        0.4,
    )[0]
    assert a.id == b.id == "H_DNS" and b.confidence < a.confidence


def test_source_priority_order_matches_spec():
    order = [
        "mcp_tool",
        "network_log",
        "service_status",
        "topology",
        "device_inventory",
        "historical_recent",
        "sop",
        "historical_old",
        "llm_knowledge",
    ]
    ranks = [PRIORITY[k] for k in order]
    assert ranks == sorted(ranks) and ranks[0] == 1 and PRIORITY["llm_knowledge"] == 9
