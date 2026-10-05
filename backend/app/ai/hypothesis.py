"""Root-cause hypothesis engine: catalog of hypotheses with weighted evidence indicators.

Each hypothesis declares
  * supports    : indicators (any-of tag sets) that support it, weights summing to 1.0
  * contradicts : indicators that argue against it (subtract from evidence_support)
  * state       : current-service-state tags that are consistent / inconsistent with it
  * topology    : alignment table by observed scope (single_device / single_unit / multi_unit / hospital_wide)
Scores are computed from the evidence store only - nothing is hard-coded per incident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.investigation.confidence import ConfidenceResult, evidence_confidence, hypothesis_score
from app.investigation.evidence import Evidence, EvidenceStore
from app.investigation.topology import ScopeAnalysis

Indicator = tuple[str, frozenset[str], float]


def ind(name: str, tags: set[str], w: float) -> Indicator:
    return (name, frozenset(tags), w)


SERVER_SIDE = {"single_device": 0.10, "single_unit": 0.25, "multi_unit": 0.8, "hospital_wide": 1.0, "unknown": 0.0}
SWITCH_TAGS = {"switch_interface_errors", "switch_uplink_down", "switch_latency_high", "switch_unreachable"}
MIN_EVIDENCE_SUPPORT = 0.30  # below this, a hypothesis has no real direct evidence


@dataclass
class HypothesisDef:
    id: str
    category: str
    template: str
    supports: list[Indicator]
    contradicts: list[Indicator]
    state_supports: set[str]
    state_contradicts: set[str]
    topology: dict[str, float]
    pattern_domain: str | None
    next_diagnostic: str
    sop_codes: list[str]
    direct: frozenset[str] = frozenset()  # indicators that are DIRECT evidence of this cause (not elimination)


CATALOG: list[HypothesisDef] = [
    HypothesisDef(
        "H_NET_ACCESS",
        "network",
        "Network path interruption around {switch} access switch/uplink",
        [
            ind("multi_endpoint_impact", {"multi_endpoint_loss"}, 0.20),
            ind("shared_access_switch", {"shared_access_switch"}, 0.18),
            ind("switch_degradation", SWITCH_TAGS, 0.22),
            ind("unit_isolation", {"unit_only_impact", "control_group_ok"}, 0.15),
            ind("network_precedes_symptom", {"pattern_network_first"}, 0.10),
            ind("server_side_healthy", {"server_healthy"}, 0.08),
            ind("dns_ok", {"dns_ok"}, 0.07),
        ],
        [
            ind("single_endpoint_only", {"single_endpoint_loss"}, 0.30),
            ind("affected_endpoints_ok", {"affected_endpoints_ok"}, 0.30),
            ind("wide_impact", {"hospital_wide_impact", "control_group_loss"}, 0.35),
            ind("internet_reported_ok", {"reported_internet_ok"}, 0.10),
            ind("partial_switch_impact", {"partial_switch_impact"}, 0.08),
            ind("dns_failure", {"dns_failed"}, 0.10),
        ],
        {"server_healthy", "dns_ok"},
        {"app_unhealthy", "db_unhealthy", "dns_failed", "server_cpu_high"},
        {"single_device": 0.2, "single_unit": 1.0, "multi_unit": 0.3, "hospital_wide": 0.05, "unknown": 0.0},
        "network",
        "Inspect the access switch uplink (interface counters, CRC errors, transceiver/cable) and compare with a healthy access switch.",
        ["SOP-003", "SOP-007"],
        direct=frozenset({"multi_endpoint_impact", "shared_access_switch", "switch_degradation"}),
    ),
    HypothesisDef(
        "H_ENDPOINT",
        "hardware",
        "Local endpoint issue on {device} (NIC, cable or switch port)",
        [
            ind("single_endpoint", {"single_endpoint_loss"}, 0.35),
            ind("peers_healthy", {"peers_healthy"}, 0.25),
            ind("control_ok", {"control_group_ok", "unit_only_impact"}, 0.15),
            ind("server_healthy", {"server_healthy"}, 0.10),
            ind("dns_ok", {"dns_ok"}, 0.05),
            ind("no_switch_degradation", {"switch_interfaces_ok", "switch_ok"}, 0.10),
        ],
        [
            ind("multi_endpoint", {"multi_endpoint_loss"}, 0.45),
            ind("switch_degradation", SWITCH_TAGS, 0.30),
            ind("wide_impact", {"hospital_wide_impact"}, 0.30),
        ],
        {"server_healthy", "dns_ok"},
        {"app_unhealthy", "db_unhealthy"},
        {"single_device": 1.0, "single_unit": 0.1, "multi_unit": 0.0, "hospital_wide": 0.0, "unknown": 0.0},
        "network",
        "Swap the cable and switch port for the affected endpoint and re-test connectivity.",
        ["SOP-003"],
        direct=frozenset({"single_endpoint", "peers_healthy"}),
    ),
    HypothesisDef(
        "H_APP",
        "application",
        "SIMRS application service unavailable or unhealthy on {server}",
        [
            ind("app_health_failing", {"app_unhealthy", "service_down", "service_degraded"}, 0.35),
            ind("multi_unit_errors", {"hospital_wide_impact", "multi_unit_impact"}, 0.20),
            ind("app_error_logs", {"app_errors_wide"}, 0.20),
            ind("db_ok", {"db_ok"}, 0.10),
            ind("dns_ok", {"dns_ok"}, 0.05),
            ind("network_ok", {"control_group_ok"}, 0.10),
        ],
        [
            ind("app_healthy", {"server_healthy"}, 0.35),
            ind("db_unhealthy", {"db_unhealthy"}, 0.25),
            ind("db_precedes", {"pattern_db_first"}, 0.20),
            ind("dns_failed", {"dns_failed"}, 0.20),
            ind("unit_only", {"unit_only_impact"}, 0.20),
            ind("overload", {"server_cpu_high"}, 0.35),
            ind("overload_precedes", {"pattern_server_first"}, 0.15),
        ],
        {"app_unhealthy", "service_degraded", "service_down"},
        {"server_healthy"},
        SERVER_SIDE,
        None,
        "Check the SIMRS application process, application logs and recent deployments on the application server.",
        ["SOP-001"],
        direct=frozenset({"app_health_failing", "app_error_logs"}),
    ),
    HypothesisDef(
        "H_DNS",
        "dns",
        "DNS resolution failure on {dns}",
        [
            ind("dns_lookup_failing", {"dns_failed", "dns_service_down"}, 0.40),
            ind("dns_failure_logs", {"dns_failure_logs"}, 0.25),
            ind("wide_impact", {"hospital_wide_impact", "multi_unit_impact"}, 0.10),
            ind("ip_path_ok", {"ip_http_healthy", "server_reachable", "control_group_ok"}, 0.15),
            ind("dns_precedes", {"pattern_dns_first"}, 0.10),
        ],
        [ind("dns_ok", {"dns_ok"}, 0.50), ind("unit_only", {"unit_only_impact"}, 0.15)],
        {"dns_failed", "dns_service_down"},
        {"dns_ok"},
        SERVER_SIDE,
        "dns",
        "Query DNS-01 directly for simrs.internal, review resolver logs and zone data validity.",
        ["SOP-002"],
        direct=frozenset({"dns_lookup_failing", "dns_failure_logs"}),
    ),
    HypothesisDef(
        "H_DB",
        "database",
        "Database connection failure on {db} (connection pool exhausted or database unavailable)",
        [
            ind("db_service_unhealthy", {"db_unhealthy"}, 0.30),
            ind("db_error_logs", {"db_error_logs"}, 0.25),
            ind("db_precedes_app", {"pattern_db_first"}, 0.15),
            ind("wide_impact", {"hospital_wide_impact", "multi_unit_impact"}, 0.10),
            ind("db_resource_pressure", {"db_resource_high"}, 0.10),
            ind("network_dns_ok", {"dns_ok", "control_group_ok"}, 0.10),
        ],
        [ind("db_ok", {"db_ok"}, 0.45), ind("dns_failed", {"dns_failed"}, 0.10), ind("unit_only", {"unit_only_impact"}, 0.15)],
        {"db_unhealthy"},
        {"db_ok"},
        SERVER_SIDE,
        "database",
        "Inspect active connections, idle sessions and long-running queries on the database server.",
        ["SOP-005"],
        direct=frozenset({"db_service_unhealthy", "db_error_logs"}),
    ),
    HypothesisDef(
        "H_OVERLOAD",
        "server",
        "Application server resource overload on {server}",
        [
            ind("cpu_mem_high", {"server_cpu_high"}, 0.35),
            ind("slow_not_failing", {"http_slow", "app_slow_logs"}, 0.25),
            ind("overload_precedes", {"pattern_server_first"}, 0.15),
            ind("wide_impact", {"hospital_wide_impact", "multi_unit_impact"}, 0.10),
            ind("db_dns_ok", {"db_ok", "dns_ok"}, 0.15),
        ],
        [
            ind("server_normal", {"server_normal"}, 0.40),
            ind("db_precedes", {"pattern_db_first"}, 0.20),
            ind("unit_only", {"unit_only_impact"}, 0.15),
        ],
        {"server_cpu_high", "http_slow"},
        {"server_normal"},
        SERVER_SIDE,
        "server",
        "Identify the process or scheduled job consuming CPU/memory on the application server.",
        ["SOP-006", "SOP-004"],
        direct=frozenset({"cpu_mem_high", "slow_not_failing"}),
    ),
    HypothesisDef(
        "H_CORE",
        "network",
        "Core network or routing failure (RTR-CORE / CORE-SW-01 / distribution layer)",
        [
            ind("multi_unit_loss", {"control_group_loss", "server_unreachable"}, 0.45),
            ind("wide_impact", {"hospital_wide_impact"}, 0.15),
            ind("network_precedes", {"pattern_network_first"}, 0.15),
            ind("multi_endpoint", {"multi_endpoint_loss"}, 0.25),
        ],
        [
            ind("control_ok", {"control_group_ok"}, 0.50),
            ind("unit_only", {"unit_only_impact"}, 0.40),
            ind("server_reachable", {"server_reachable"}, 0.10),
        ],
        {"server_unreachable", "control_group_loss"},
        {"control_group_ok", "server_reachable"},
        {"single_device": 0.0, "single_unit": 0.1, "multi_unit": 0.8, "hospital_wide": 1.0, "unknown": 0.0},
        "network",
        "Check RTR-CORE and CORE-SW-01 interface/route state and reachability from several units.",
        ["SOP-003"],
        direct=frozenset({"multi_unit_loss", "multi_endpoint"}),
    ),
    HypothesisDef(
        "H_AUTH",
        "authentication",
        "Authentication service failure (login rejected while network and application are healthy)",
        [
            ind("auth_failure_logs", {"auth_failure_logs"}, 0.50),
            ind("app_healthy", {"server_healthy", "http_healthy"}, 0.25),
            ind("network_ok", {"control_group_ok", "endpoint_ok"}, 0.10),
            ind("dns_ok", {"dns_ok"}, 0.15),
        ],
        [ind("app_unhealthy", {"app_unhealthy", "service_down"}, 0.30), ind("dns_failed", {"dns_failed"}, 0.20)],
        {"auth_failure_logs"},
        {"app_unhealthy"},
        SERVER_SIDE,
        None,
        "Review authentication logs for the failing accounts and verify server time synchronisation.",
        ["SOP-008"],
        direct=frozenset({"auth_failure_logs"}),
    ),
    HypothesisDef(
        "H_CONFIG",
        "configuration",
        "Configuration error (VLAN/port) on {switch}",
        [
            ind("vlan_misconfig_logs", {"vlan_misconfig_logs"}, 0.60),
            ind("shared_switch", {"shared_access_switch"}, 0.20),
            ind("server_healthy", {"server_healthy"}, 0.10),
            ind("dns_ok", {"dns_ok"}, 0.10),
        ],
        [
            ind("switch_degradation", {"switch_interface_errors", "switch_uplink_down"}, 0.20),
            ind("wide_impact", {"hospital_wide_impact"}, 0.30),
        ],
        {"vlan_misconfig_logs"},
        {"switch_interface_errors"},
        {"single_device": 0.5, "single_unit": 0.6, "multi_unit": 0.2, "hospital_wide": 0.0, "unknown": 0.0},
        "network",
        "Compare the running VLAN/trunk configuration of the switch against the last known-good backup.",
        ["SOP-003"],
        direct=frozenset({"vlan_misconfig_logs"}),
    ),
]


@dataclass
class Hypothesis:
    id: str
    category: str
    description: str
    components: dict[str, float]
    score: float
    confidence: float = 0.0
    status: str = "unlikely"
    supporting: list[str] = field(default_factory=list)
    contradicting: list[str] = field(default_factory=list)
    hit_indicators: list[str] = field(default_factory=list)
    contradicted_by: list[str] = field(default_factory=list)
    missing_indicators: list[str] = field(default_factory=list)
    confidence_detail: ConfidenceResult | None = None
    definition: HypothesisDef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "description": self.description,
            "score": self.score,
            "confidence": self.confidence,
            "status": self.status,
            "components": {k: round(v, 3) for k, v in self.components.items()},
            "supporting_evidence": self.supporting,
            "contradicting_evidence": self.contradicting,
            "indicators_supported": self.hit_indicators,
            "indicators_contradicted": self.contradicted_by,
            "indicators_missing": self.missing_indicators,
        }


def _hit(store_tags: set[str], indicator: Indicator) -> bool:
    return bool(indicator[1] & store_tags)


def evaluate(
    store: EvidenceStore,
    scope: ScopeAnalysis,
    hist_matches: list[dict[str, Any]],
    patterns: dict[str, float],
    weights: dict[str, float],
    labels: dict[str, str],
    tools_ok: int,
    tools_planned: int,
    min_confidence: float,
) -> list[Hypothesis]:
    tags = store.tags()
    out: list[Hypothesis] = []
    for d in CATALOG:
        sup_hits = [i for i in d.supports if _hit(tags, i)]
        con_hits = [i for i in d.contradicts if _hit(tags, i)]
        evidence_support = max(0.0, min(1.0, sum(i[2] for i in sup_hits) - sum(i[2] for i in con_hits)))
        if not any(i[0] in d.direct for i in sup_hits):  # only elimination evidence (healthy server/DNS...) is not evidence FOR this cause
            evidence_support = min(evidence_support, 0.1)
        sup_items: list[Evidence] = [e for e in store.items if any(e.tags and set(e.tags) & i[1] for i in sup_hits)]
        con_items: list[Evidence] = [e for e in store.items if any(e.tags and set(e.tags) & i[1] for i in con_hits)]
        ts_vals = [e.temporal for e in sup_items if e.temporal is not None]
        order = patterns.get(d.pattern_domain, 0.0) if d.pattern_domain else 0.0
        if d.id == "H_APP":
            order = 0.8 if not patterns else 0.2
        temporal = 0.7 * (sum(ts_vals) / len(ts_vals) if ts_vals else 0.0) + 0.3 * order
        topology = d.topology.get(scope.scope_level, 0.0)
        if d.id == "H_NET_ACCESS" and scope.scope_level == "single_unit" and not scope.shared_access_switch:
            topology = 0.5
        hist = max([m["score"] for m in hist_matches if m.get("root_cause_category") == d.category] or [0.0])
        st_present = tags & (d.state_supports | d.state_contradicts)
        if not st_present:
            state = 0.0
        else:
            frac = len(tags & d.state_supports) / len(d.state_supports) if d.state_supports else 0.0
            state = max(0.0, min(1.0, frac - (0.5 if tags & d.state_contradicts else 0.0)))
        uniq = {e.key: e for e in sup_items}
        source = sum(e.reliability for e in uniq.values()) / len(uniq) if uniq else 0.0
        # Context alone (topology fit, history, source reliability) must not create a conclusion: gate by direct-evidence strength.
        gate = min(1.0, evidence_support / MIN_EVIDENCE_SUPPORT)
        comps = {
            "evidence": evidence_support,
            "temporal": temporal * gate,
            "topology": topology * gate,
            "history": hist * gate,
            "state": state * gate,
            "source": source * gate,
        }
        h = Hypothesis(
            d.id,
            d.category,
            d.template.format(**labels),
            comps,
            hypothesis_score(comps, weights),
            supporting=[e.key for e in sup_items],
            contradicting=[e.key for e in con_items],
            hit_indicators=[i[0] for i in sup_hits],
            contradicted_by=[i[0] for i in con_hits],
            missing_indicators=[i[0] for i in d.supports if not _hit(tags, i)],
            definition=d,
        )
        out.append(h)
    out.sort(key=lambda h: h.score, reverse=True)
    top = out[0].score if out else 0.0
    runner = out[1].score if len(out) > 1 else None
    for idx, h in enumerate(out):
        h.confidence_detail = evidence_confidence(h.score, tools_ok, tools_planned, top, runner, is_top=idx == 0)
        h.confidence = h.confidence_detail.confidence
    if out and out[0].confidence >= min_confidence and out[0].components["evidence"] >= MIN_EVIDENCE_SUPPORT:
        out[0].status = "most_supported"
        for h in out[1:]:
            h.status = (
                "plausible"
                if h.confidence >= 0.35 and h.components["evidence"] >= MIN_EVIDENCE_SUPPORT
                else ("contradicted" if h.contradicted_by and h.components["evidence"] == 0 else "unlikely")
            )
    else:
        for h in out:
            h.status = "insufficient_evidence" if h.components["evidence"] > 0 else "unlikely"
    _assign_roles(store, out)
    return out


def _assign_roles(store: EvidenceStore, hyps: list[Hypothesis]) -> None:
    """Per-evidence role w.r.t. every hypothesis + overall role/contribution w.r.t. the leading hypothesis."""
    for h in hyps:
        for k in h.supporting:
            e = store.by_key(k)
            if e:
                e.hypothesis_roles[h.id] = "supporting"
        for k in h.contradicting:
            e = store.by_key(k)
            if e:
                e.hypothesis_roles[h.id] = "contradicting"
    if not hyps:
        return
    lead = hyps[0]
    d = lead.definition
    assert d is not None
    for e in store.items:
        role = e.hypothesis_roles.get(lead.id, "context")
        e.role = role
        if role == "context":
            continue
        indicators = d.supports if role == "supporting" else d.contradicts
        n_hit = sum(1 for i in indicators if set(e.tags) & i[1])
        share = 0.0
        for i in indicators:
            if set(e.tags) & i[1]:
                holders = [x for x in store.items if set(x.tags) & i[1]]
                share += i[2] / max(1, len(holders))
        e.contribution = (share if role == "supporting" else -share) * (lead.components["evidence"] and 1.0) if n_hit else 0.0
