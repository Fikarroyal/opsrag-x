import math
from datetime import datetime, timedelta

from app.investigation.correlation import HostInfo, LogRecord, correlate
from app.investigation.temporal import AFTER, BEFORE, DURING, UNRELATED, temporal_relation, temporal_score
from app.rag.retriever import combine

T = datetime(2026, 9, 28, 9, 42)


def test_temporal_score_decay_properties():
    hl = 600.0
    assert temporal_score(0, hl) == 1.0
    assert math.isclose(temporal_score(hl, hl), 0.5)
    assert math.isclose(temporal_score(2 * hl, hl), 0.25)
    assert temporal_score(60, hl) > temporal_score(600, hl) > temporal_score(6000, hl) > 0
    assert temporal_score(-300, hl) == temporal_score(300, hl)  # symmetric closeness
    assert 0 <= temporal_score(10**9, hl) <= 1


def test_temporal_relation_buckets():
    assert temporal_relation(T - timedelta(minutes=5), T) == BEFORE
    assert temporal_relation(T, T) == DURING
    assert temporal_relation(T + timedelta(minutes=4), T) == DURING
    assert temporal_relation(T + timedelta(minutes=20), T) == AFTER
    assert temporal_relation(T + timedelta(hours=3), T) == UNRELATED
    assert temporal_relation(T - timedelta(hours=3), T) == UNRELATED


def test_combine_uses_weights():
    w = {"semantic": 0.45, "temporal": 0.25, "category": 0.10, "service": 0.10, "source": 0.10}
    assert math.isclose(combine({"semantic": 1, "temporal": 1, "category": 1, "service": 1, "source": 1}, w), 1.0)
    assert math.isclose(combine({"semantic": 1}, w), 0.45)
    assert combine({}, w) == 0.0


def test_settings_weights_normalised(settings):
    assert math.isclose(sum(settings.retrieval_weights.values()), 1.0)
    assert math.isclose(sum(settings.hypothesis_weights.values()), 1.0)


def _rec(sec, src, host, ev, **kw):
    return LogRecord(T + timedelta(seconds=sec), src, host, ev, **kw)


def test_correlation_detects_network_then_application_pattern():
    hosts = {
        "PC-POLI3-001": HostInfo("Poli 3", "pc", "SW-POLI3"),
        "PC-POLI3-002": HostInfo("Poli 3", "pc", "SW-POLI3"),
        "PC-POLI3-003": HostInfo("Poli 3", "pc", "SW-POLI3"),
        "SW-POLI3": HostInfo("IT", "access_switch", "SW-DIST-01"),
        "SIMRS-APP-01": HostInfo(None, "server"),
    }
    ip_unit = {"10.30.3.11": "Poli 3"}
    recs = [_rec(-240, "network", "SW-POLI3", "HIGH_LATENCY", latency_ms=300, packet_loss=9)]
    recs += [_rec(-120 + i * 10, "network", f"PC-POLI3-00{1 + i % 3}", "PACKET_LOSS", packet_loss=18.0, latency_ms=300) for i in range(9)]
    recs += [_rec(2 + i, "server", "SIMRS-APP-01", "HTTP_TIMEOUT", level="ERROR", ip_address="10.30.3.11") for i in range(6)]
    res = correlate(recs, T, affected_unit="Poli 3", hosts=hosts, ip_unit=ip_unit)
    p = res.dominant_pattern
    assert p and p.name == "network_degradation_then_application_failure" and p.order_ok and p.score > 0.7
    assert res.impact_units == ["Poli 3"] and res.flags["unit_only_impact"]
    assert set(res.affected_endpoints) == {"PC-POLI3-001", "PC-POLI3-002", "PC-POLI3-003"}


def test_correlation_order_violation_is_flagged_not_hidden():
    hosts = {"SIMRS-DB-01": HostInfo(None, "server")}
    recs = [_rec(-100, "server", "SIMRS-APP-01", "HTTP_TIMEOUT", level="ERROR")] + [
        _rec(60 + i, "server", "SIMRS-DB-01", "DB_CONN_POOL_EXHAUSTED", level="ERROR") for i in range(5)
    ]
    res = correlate(recs, T, affected_unit=None, hosts=hosts, ip_unit={})
    p = next(x for x in res.patterns if x.cause_domain == "database")
    assert not p.order_ok  # DB failure AFTER the application symptom must not be reported as the cause


def test_isolated_baseline_events_do_not_create_patterns():
    recs = [
        _rec(-30, "server", "SIMRS-DB-01", "DB_QUERY_SLOW", level="WARN"),
        _rec(-20, "server", "SIMRS-DB-01", "DB_QUERY_SLOW", level="WARN"),
    ]
    assert correlate(recs, T, affected_unit=None, hosts={}, ip_unit={}).patterns == []
