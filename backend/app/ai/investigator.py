"""Structured tool planner (+ optional LLM refinement) and optional LLM narrative.

Tool selection is driven by the incident classification (category x scope), never "run everything":
  {"reason": "...", "selected_tools": [{"tool": "check_http", "arguments": {...}, "purpose": "..."}]}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.ai.classifier import Classification
from app.ai.llm import BaseLLMProvider, LLMUnavailableError, extract_json
from app.ai.prompts import INVESTIGATOR_SYSTEM, narrative_prompt, planner_prompt
from app.investigation.topology import TopologyGraph

logger = logging.getLogger(__name__)

SERVICE_URL = {"SIMRS": "http://simrs.internal:8080/health", "SIM-APOTEK": "http://simrs.internal:8081/health"}
SERVICE_NAME = {
    "SIMRS": "SIMRS",
    "SIM-APOTEK": "SIM-APOTEK",
    "DNS": "DNS",
    "DATABASE": "DATABASE",
    "FILE SERVER": "FILE SERVER",
    "MONITORING": "MONITORING",
}
DOMAINS = {
    "application": ["application", "network", "dns"],
    "network": ["network", "application"],
    "dns": ["dns", "application"],
    "database": ["database", "application"],
    "server": ["server", "application"],
    "authentication": ["authentication", "application"],
    "hardware": ["endpoint"],
    "configuration": ["network"],
    "service": ["service"],
    "unknown": ["application", "network", "dns", "server"],
}
CONTROL_PREFERENCE = ["PC-POLI2-001", "PC-POLI1-001", "PC-KASIR-001", "PC-IGD-001", "PC-LAB-001"]
MAX_TOOLS = 14


@dataclass
class PlannedTool:
    tool: str
    arguments: dict[str, Any]
    purpose: str


@dataclass
class ToolPlan:
    reason: str
    domains: list[str]
    selected_tools: list[PlannedTool]
    affected_hosts: list[str] = field(default_factory=list)
    control_hosts: list[str] = field(default_factory=list)
    access_switches: list[str] = field(default_factory=list)
    llm_refined: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "domains": self.domains,
            "llm_refined": self.llm_refined,
            "selected_tools": [{"tool": t.tool, "arguments": t.arguments, "purpose": t.purpose} for t in self.selected_tools],
        }


def plan_tools(
    cls: Classification,
    topo: TopologyGraph,
    unit_devices: dict[str, list[str]],
    *,
    unit: str | None,
    device: str | None,
    incident_time_iso: str,
) -> ToolPlan:
    domains = DOMAINS.get(cls.category, DOMAINS["unknown"])
    service = cls.affected_service or "SIMRS"
    server = "SIMRS-DB-01" if service == "DATABASE" else ("DNS-01" if service == "DNS" else "SIMRS-APP-01")
    tools: list[PlannedTool] = []
    seen: set[tuple[str, str]] = set()

    def add(tool: str, purpose: str, **args: Any) -> None:
        key = (tool, repr(sorted(args.items())))
        if key not in seen and len(tools) < MAX_TOOLS:
            seen.add(key)
            tools.append(PlannedTool(tool, args, purpose))

    affected: list[str] = []
    if device and topo.node(device):
        affected = [device]
    elif unit and cls.affected_scope in ("single_unit", "multi_unit", "single_device", "unknown") and unit_devices.get(unit):
        affected = [h for h in sorted(unit_devices[unit]) if h.startswith("PC-")][:3]
    control: list[str] = []
    unit_key = (unit or "").upper().replace(" ", "")
    for c in CONTROL_PREFERENCE:
        if topo.node(c) and (topo.node(c) or {}).get("unit", "").upper().replace(" ", "") != unit_key:
            control.append(c)
            if len(control) == (2 if cls.affected_scope == "hospital_wide" or not affected else 1):
                break
    switches = sorted({sw for h in affected if (sw := topo.access_switch(h))})
    sample = affected[0] if affected else (control[0] if control else None)

    if "endpoint" in domains or "network" in domains:
        for h in affected:
            add("ping_host", f"Measure packet loss/latency of affected endpoint {h}", host=h)
        for c in control:
            add("ping_host", f"Control: compare with {c} in a different unit to localise the fault", host=c)
        for sw in switches:
            add("get_network_interface_status", f"Inspect uplink/interface errors of access switch {sw}", hostname=sw)
            add("ping_host", f"Check reachability/latency of access switch {sw}", host=sw)
        if sample:
            add("get_topology_path", f"Map the network path from {sample} to {server}", source=sample, destination=server)
        if device or (affected and cls.category in ("hardware", "network") and cls.affected_scope == "single_device"):
            add(
                "get_device_info",
                f"Inventory record and switch port of {affected[0] if affected else device}",
                hostname=(affected[0] if affected else device),
            )
    if "application" in domains:
        svc = service if service in SERVICE_URL else "SIMRS"
        add("check_http", f"Verify {svc} endpoint availability", url=SERVICE_URL[svc])
        add("query_service_status", f"Current monitored state of {svc}", service_name=svc)
        add("get_server_status", "Resource and health state of the application server", server_name="SIMRS-APP-01")
        if "network" in domains and cls.category == "application":
            add("ping_host", "Reachability of the application server from the monitoring vantage point", host="SIMRS-APP-01")
    if "dns" in domains:
        add("check_dns", "Verify internal name resolution of the SIMRS host", hostname="simrs.internal")
        if cls.category == "dns":
            add(
                "check_http",
                "Verify the application by IP to separate DNS failure from application failure",
                url="http://10.20.0.10:8080/health",
            )
            add("query_service_status", "Current monitored state of the DNS service", service_name="DNS")
            add("ping_host", "Reachability of DNS-01 from the monitoring vantage point", host="DNS-01")
            add("search_logs", "Look for DNS resolver errors around the incident", query="SERVFAIL", hostname="DNS-01", severity="error")
    if "database" in domains:
        add("query_service_status", "Current monitored state of the database service", service_name="DATABASE")
        add("get_server_status", "Resource state of the database server", server_name="SIMRS-DB-01")
        add(
            "search_logs",
            "Look for database connection errors around the incident",
            query="connection",
            hostname="SIMRS-DB-01",
            severity="error",
        )
    if "server" in domains:
        add("search_logs", "Look for resource warnings on the application server", query="cpu", hostname="SIMRS-APP-01", severity="warn")
        add("check_dns", "Rule out DNS as the cause of slowness", hostname="simrs.internal")
    if "authentication" in domains:
        add(
            "search_logs",
            "Look for authentication failures around the incident",
            query="Login failed",
            hostname="SIMRS-APP-01",
            severity="warn",
        )
    if "service" in domains:
        svc = SERVICE_NAME.get(service, "FILE SERVER")
        add("query_service_status", f"Current monitored state of {svc}", service_name=svc)
        add("ping_host", "Reachability of FILE-01", host="FILE-01")
    if cls.category == "unknown":
        add(
            "search_previous_incident",
            "Category unclear: look for keyword-similar historical incidents",
            query=cls.reasoning[0] if False else "SIMRS tidak dapat diakses",
            category=None,
        )
    reason = (
        f"Category '{cls.category}' (secondary '{cls.secondary_category}'), scope '{cls.affected_scope}', service '{service}': tests cover domains {domains} to separate "
        f"endpoint, network path, DNS, application and database causes; control device(s) {control or 'n/a'} localise the fault domain."
    )
    return ToolPlan(reason, domains, tools, affected, control, switches)


def refine_plan_with_llm(plan: ToolPlan, cls: Classification, llm: BaseLLMProvider | None) -> ToolPlan:
    """Optional: let the LLM prune the plan. Result is validated: it may only *remove* planned tools, never add new ones."""
    if llm is None or not llm.is_available() or len(plan.selected_tools) <= 4:
        return plan
    try:
        cands = [{"tool": t.tool, "purpose": t.purpose} for t in plan.selected_tools]
        data = extract_json(llm.generate(INVESTIGATOR_SYSTEM, planner_prompt(cls.to_dict(), cands), json_mode=True)) or {}
        keep = data.get("keep")
        if isinstance(keep, list) and keep:
            names = {str(k) for k in keep}
            pruned = [t for t in plan.selected_tools if t.tool in names]
            if len(pruned) >= max(3, len(plan.selected_tools) // 2):
                plan.selected_tools, plan.llm_refined = pruned, True
                plan.reason += f" LLM refinement kept {len(pruned)} of {len(cands)} candidate tools: {data.get('reason', '')}"[:400]
    except (LLMUnavailableError, ValueError, TypeError) as exc:
        logger.info("LLM plan refinement skipped (%s)", exc)
    return plan


def llm_narrative(llm: BaseLLMProvider | None, facts: dict[str, Any]) -> str | None:
    if llm is None or not llm.is_available():
        return None
    try:
        text = llm.generate(INVESTIGATOR_SYSTEM, narrative_prompt(facts), temperature=0.0).strip()
        return text[:1200] if text else None
    except LLMUnavailableError:
        return None
