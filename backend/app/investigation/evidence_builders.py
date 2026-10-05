"""Turn raw sources (MCP results, correlated logs, topology, retrieval, incident report) into tagged Evidence items.

Nothing here invents state: every item is derived from a tool result / log group / retrieved record that exists,
and failed or empty tools produce UNKNOWN evidence instead of guesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.investigation.correlation import LOSS_EVENTS, CorrelationResult
from app.investigation.evidence import EvidenceStore
from app.investigation.topology import ScopeAnalysis, TopologyGraph

LOSS_THRESHOLD = 5.0  # % packet loss regarded as abnormal
LATENCY_THRESHOLD = 100.0  # ms uplink latency regarded as abnormal
MIN_SIGNAL_EVENTS = 3  # isolated single events are baseline noise, not a failure signal


@dataclass
class ToolRun:
    name: str
    arguments: dict[str, Any]
    purpose: str
    status: str = "success"  # success | error | timeout
    result: dict[str, Any] | None = None
    error: str | None = None
    execution_ms: float = 0.0
    executed_at: datetime | None = None
    evidence_keys: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class BuildContext:
    incident_time: datetime
    unit: str | None
    service: str | None
    affected_hosts: list[str]  # hosts sampled as "affected" by the planner
    control_hosts: list[str]
    app_server: str = "SIMRS-APP-01"
    db_server: str = "SIMRS-DB-01"
    dns_server: str = "DNS-01"
    access_switches: list[str] = field(default_factory=list)


def _ts(result: dict[str, Any] | None, fallback: datetime) -> datetime:
    try:
        return datetime.fromisoformat(str((result or {}).get("as_of")))
    except (TypeError, ValueError):
        return fallback


def _add(
    store: EvidenceStore, run: ToolRun, content: str, tags: list[str], relevance: float, ts: datetime, kind: str = "FACT", **meta: Any
) -> None:
    ev = store.add(
        "mcp_tool",
        content,
        source_id=f"{run.name}({', '.join(f'{k}={v}' for k, v in run.arguments.items() if k != 'as_of')})",
        kind=kind,
        timestamp=ts,
        tags=tags,
        relevance=relevance,
        tool=run.name,
        **meta,
    )
    run.evidence_keys.append(ev.key)


def evidence_from_tool(store: EvidenceStore, run: ToolRun, ctx: BuildContext) -> None:
    if run.status != "success" or not run.result:
        ev = store.add(
            "mcp_tool",
            f"Diagnostic tool {run.name} gagal dijalankan ({run.error or run.status}); hasil tidak tersedia sebagai evidence.",
            source_id=run.name,
            kind="UNKNOWN",
            timestamp=run.executed_at,
            tags=["tool_failed"],
            relevance=0.4,
            tool=run.name,
        )
        run.evidence_keys.append(ev.key)
        return
    r, ts = run.result, _ts(run.result, ctx.incident_time)
    n = run.name
    if n == "ping_host":
        host = r["host"]
        if r["samples"] == 0:
            _add(
                store,
                run,
                f"{host}: tidak ada sampel probe pada jendela pemeriksaan (evidence tidak mencukupi).",
                ["ping_no_data"],
                0.4,
                ts,
                kind="UNKNOWN",
            )
            return
        loss, lat = r["packet_loss"] or 0.0, r["latency_ms"]
        desc = f"{host}: packet loss {loss:.1f}%, latency rata-rata {lat if lat is not None else 'n/a'} ms ({r['samples']} sampel, {r['window_minutes']} menit terakhir)"
        upper = host.upper()
        node = None
        if upper in {h.upper() for h in ctx.affected_hosts}:
            tags = ["endpoint_packet_loss", "ping_affected_loss"] if loss >= LOSS_THRESHOLD else ["endpoint_ok", "ping_affected_ok"]
            if r["reachable"] is False:
                tags.append("endpoint_unreachable")
            _add(store, run, desc, tags, 0.95 if loss >= LOSS_THRESHOLD else 0.7, ts, role_hint="affected", host=host, loss=loss)
        elif upper in {h.upper() for h in ctx.control_hosts}:
            _add(
                store,
                run,
                desc + " [perangkat pembanding di luar unit terdampak]",
                ["ping_control_ok" if loss < 1 else "ping_control_loss"],
                0.85,
                ts,
                role_hint="control",
                host=host,
                loss=loss,
            )
        elif upper == ctx.app_server.upper() or upper in (ctx.dns_server.upper(), ctx.db_server.upper()):
            ok = r["reachable"] and loss < LOSS_THRESHOLD
            _add(
                store,
                run,
                desc + " [vantage: MONITOR-01]",
                ["server_reachable" if ok else "server_unreachable"],
                0.8,
                ts,
                role_hint="server",
                host=host,
            )
        else:  # switches / other network nodes
            tags = []
            if r["reachable"] is False or loss >= 99:
                tags.append("switch_unreachable")
            elif loss >= LOSS_THRESHOLD or (lat or 0) >= LATENCY_THRESHOLD:
                tags += ["switch_latency_high"] if (lat or 0) >= LATENCY_THRESHOLD else []
                tags += ["switch_loss"] if loss >= LOSS_THRESHOLD else []
            else:
                tags.append("switch_ok")
            _add(store, run, desc, tags, 0.9 if tags != ["switch_ok"] else 0.6, ts, role_hint="switch", host=host, loss=loss, latency=lat)
        _ = node
    elif n == "get_network_interface_status":
        host, s = r["hostname"], r["summary"]
        parts, tags = [], []
        for i in r["interfaces"]:
            if i["status"] == "down":
                parts.append(f"{i['name']} DOWN (peer {i['peer']})")
                tags.append("switch_uplink_down")
            elif i["status"] == "up_with_errors":
                parts.append(f"{i['name']} up dengan error (CRC {i['crc_errors']}, latency {i['latency_ms']} ms, loss {i['packet_loss']}%)")
                tags.append("switch_interface_errors")
        if r["peer_reports"]:
            parts.append("laporan tetangga: " + "; ".join(f"{p['reporter']} {p['event_type']}" for p in r["peer_reports"][-2:]))
        if not parts:
            _add(store, run, f"{host}: seluruh interface up tanpa error pada jendela pemeriksaan.", ["switch_interfaces_ok"], 0.7, ts)
        else:
            _add(
                store,
                run,
                f"{host}: " + "; ".join(parts) + f" (ringkasan: down={s['down']}, error={s['with_errors']})",
                sorted(set(tags)),
                0.95,
                ts,
                host=host,
            )
    elif n == "check_http":
        code, rt = r["status_code"], r["response_time_ms"]
        by_ip = r["url"].split("//")[1].split(":")[0].replace(".", "").isdigit()
        base = f"HTTP {r['url']}: status {code}, {rt:.0f} ms" + (f", error: {r['error']}" if r.get("error") else "")
        if r.get("error") and "name resolution" in r["error"]:
            _add(store, run, base, ["dns_failed_http", "dns_failed"], 0.9, ts)
        elif r["healthy"]:
            _add(store, run, base + " (sehat)", ["http_healthy"] + (["ip_http_healthy"] if by_ip else []), 0.9, ts)
        elif code == 0 or code >= 500:
            _add(store, run, base + " (tidak sehat)", ["app_unhealthy"], 0.9, ts)
        elif rt >= 2000:
            _add(store, run, base + " (lambat)", ["http_slow"], 0.9, ts)
        else:
            _add(store, run, base, ["http_degraded"], 0.7, ts)
    elif n == "check_dns":
        if r["success"]:
            _add(store, run, f"DNS {r['hostname']} -> {r['resolved_ip']} ({r['response_time_ms']:.0f} ms)", ["dns_ok"], 0.9, ts)
        else:
            _add(store, run, f"DNS {r['hostname']} gagal resolve: {r['error']} ({r['response_time_ms']:.0f} ms)", ["dns_failed"], 0.95, ts)
    elif n == "query_service_status":
        svc, st = r["service"], r["status"]
        svc_tags: list[str] = []
        if svc == "DATABASE":
            svc_tags = ["db_ok"] if st == "running" else ["db_unhealthy"]
        elif svc == "DNS":
            svc_tags = ["dns_service_ok"] if st == "running" else ["dns_service_down", "dns_failed"]
        else:
            svc_tags = ["service_running"] if st == "running" else (["service_degraded"] if st == "degraded" else ["service_down"])
        _add(
            store,
            run,
            f"Service {svc} pada {r['server']}:{r['port']} berstatus {st} (response {r['response_time_ms']:.0f} ms, HTTP {r['http_status']})",
            svc_tags,
            0.9,
            ts,
            service=svc,
        )
    elif n == "get_server_status":
        cpu, mem, st = r["cpu"], r["memory"], r["status"]
        host = r["server"]
        is_db = host.upper() == ctx.db_server.upper()
        tags = []
        if cpu is not None and mem is not None:
            hot = cpu >= 85 or mem >= 90
            if hot:
                tags.append("db_resource_high" if is_db else "server_cpu_high")
            elif not is_db:
                tags.append("server_normal")
        if st == "healthy" and not is_db:
            tags.append("app_server_healthy")
        content = (
            f"{host}: status {st}, CPU {cpu}%, memori {mem}%, uptime {r['uptime']}"
            if cpu is not None
            else f"{host}: status {st} (tanpa sampel resource)"
        )
        _add(store, run, content, tags, 0.9, ts, host=host)
    elif n == "get_topology_path":
        names = " -> ".join(p["hostname"] for p in r["path"])
        _add(
            store,
            run,
            f"Jalur topologi {r['source']} ke {r['destination']} ({r['hops']} hop): {names}",
            ["topology_path"],
            0.8,
            ts,
            path=[p["hostname"] for p in r["path"]],
        )
    elif n == "get_device_info":
        _add(
            store,
            run,
            f"{r['hostname']} ({r['ip_address']}) unit {r['unit']}, VLAN {r['vlan']} ({r['vlan_name']}), terhubung ke {r['switch']} port {r['switch_port']}; {r['peers_on_same_switch']} endpoint lain pada switch yang sama",
            ["device_inventory"],
            0.7,
            ts,
            switch=r["switch"],
        )
    elif n == "search_logs":
        _add(
            store,
            run,
            f"search_logs: {r['total_matches']} log cocok ({r['returned']} ditampilkan){' [terpotong]' if r['truncated'] else ''} untuk filter {run.arguments.get('hostname') or ''} {run.arguments.get('query') or ''}".strip(),
            ["logs_search"],
            0.6,
            ts,
        )
    elif n == "search_previous_incident":
        top = r["incidents"][0] if r["incidents"] else None
        _add(
            store,
            run,
            f"search_previous_incident: {r['total_candidates']} kandidat"
            + (f"; teratas {top['incident_id']} (kesamaan {top['similarity']}, penyebab: {top['root_cause']})" if top else ""),
            ["historical_tool"],
            0.5,
            ts,
            kind="INFERENCE",
        )


def derive_aggregates(store: EvidenceStore, ctx: BuildContext) -> None:
    """Aggregate per-host tool evidence into scope-level signals (recorded as INFERENCE with links to their sources)."""
    aff = [e for e in store.items if e.meta.get("role_hint") == "affected" and e.source_type == "mcp_tool"]
    lossy = [e for e in aff if "endpoint_packet_loss" in e.tags]
    if len(lossy) >= 2:
        store.add(
            "mcp_tool",
            f"{len(lossy)} dari {len(aff)} endpoint terdampak yang diperiksa menunjukkan packet loss >= {LOSS_THRESHOLD:.0f}% ({', '.join(e.meta['host'] for e in lossy)}).",
            kind="INFERENCE",
            tags=["multi_endpoint_loss"],
            relevance=0.9,
            derived_from=[e.key for e in lossy],
            timestamp=max((e.timestamp for e in lossy if e.timestamp), default=None),
        )
    elif len(lossy) == 1 and len(aff) == 1:
        store.add(
            "mcp_tool",
            f"Hanya satu endpoint ({lossy[0].meta['host']}) yang diperiksa dan menunjukkan packet loss.",
            kind="INFERENCE",
            tags=["single_endpoint_loss"],
            relevance=0.8,
            derived_from=[lossy[0].key],
        )
    elif len(aff) >= 2 and not lossy:
        store.add(
            "mcp_tool",
            f"Endpoint terdampak yang diperiksa ({len(aff)}) tidak menunjukkan packet loss saat pemeriksaan.",
            kind="INFERENCE",
            tags=["affected_endpoints_ok"],
            relevance=0.8,
            derived_from=[e.key for e in aff],
        )
    ctrl = [e for e in store.items if e.meta.get("role_hint") == "control" and e.source_type == "mcp_tool"]
    if ctrl:
        bad = [e for e in ctrl if "ping_control_loss" in e.tags]
        if bad:
            store.add(
                "mcp_tool",
                f"Perangkat pembanding di luar unit terdampak juga mengalami packet loss ({', '.join(e.meta['host'] for e in bad)}).",
                kind="INFERENCE",
                tags=["control_group_loss"],
                relevance=0.9,
                derived_from=[e.key for e in bad],
            )
        else:
            store.add(
                "mcp_tool",
                f"Perangkat pembanding di unit lain ({', '.join(e.meta['host'] for e in ctrl)}) normal (packet loss 0%).",
                kind="INFERENCE",
                tags=["control_group_ok"],
                relevance=0.85,
                derived_from=[e.key for e in ctrl],
            )
    tags = store.tags()
    if (
        "app_server_healthy" in tags
        and "app_unhealthy" not in tags
        and "http_slow" not in tags
        and "service_degraded" not in tags
        and "service_down" not in tags
    ):
        srcs = [e.key for e in store.with_tag("app_server_healthy", "http_healthy", "service_running")]
        store.add(
            "mcp_tool",
            "Server aplikasi SIMRS sehat: status server healthy dan health endpoint/layanan normal.",
            kind="INFERENCE",
            tags=["server_healthy"],
            relevance=0.9,
            derived_from=srcs,
        )
    elif {"app_unhealthy", "http_slow", "service_degraded", "service_down", "server_cpu_high"} & tags:
        store.add(
            "mcp_tool",
            "Server/layanan aplikasi menunjukkan degradasi (status tidak sehat, lambat, atau resource tinggi).",
            kind="INFERENCE",
            tags=["server_degraded"],
            relevance=0.85,
            derived_from=[
                e.key for e in store.with_tag("app_unhealthy", "http_slow", "service_degraded", "service_down", "server_cpu_high")
            ],
        )


def evidence_from_report(
    store: EvidenceStore, description: str, internet_normal: bool, others_normal: bool, incident_time: datetime
) -> None:
    tags = ["incident_report"] + (["reported_internet_ok"] if internet_normal else []) + (["reported_others_ok"] if others_normal else [])
    store.add(
        "incident_report",
        f'Laporan pengguna (belum diverifikasi): "{description[:220]}"',
        kind="FACT",
        timestamp=incident_time,
        tags=tags,
        relevance=0.5,
    )


def evidence_from_correlation(
    store: EvidenceStore, corr: CorrelationResult, topo: TopologyGraph, ctx: BuildContext, auth_failures: int, window_min: int
) -> None:
    fm = lambda d: d.strftime("%H:%M:%S")  # noqa: E731
    endpoint_groups = [g for g in corr.groups if g.domain == "device" and g.event_type in LOSS_EVENTS | {"HIGH_LATENCY"}]
    hosts = corr.affected_endpoints
    if hosts:
        first = min(g.first for g in endpoint_groups)
        last = max(g.last for g in endpoint_groups)
        desc = ", ".join(f"{h} ({v['avg_loss']}%)" for h, v in sorted(hosts.items())[:6]) + (
            f", +{len(hosts) - 6} lainnya" if len(hosts) > 6 else ""
        )
        store.add(
            "network_log",
            f"{len(hosts)} endpoint menunjukkan packet loss/timeout ke server pada {fm(first)}-{fm(last)}: {desc}.",
            source_id="network_logs",
            timestamp=first,
            tags=["multi_endpoint_loss" if len(hosts) >= 2 else "single_endpoint_loss", "endpoint_loss_logs"],
            relevance=0.95,
            hosts=sorted(hosts),
        )
    by_host: dict[str, list] = {}
    for g in corr.groups:
        by_host.setdefault(g.hostname, []).append(g)
    for host, gs in by_host.items():
        node = topo.node(host)
        dtype = node["device_type"] if node else ""
        if dtype in ("access_switch", "distribution_switch", "core_switch", "router") or (
            host == "MONITOR-01" and any(g.event_type == "GATEWAY_UNREACHABLE" for g in gs)
        ):
            evs = {g.event_type: g for g in gs}
            parts, tags = [], []
            if "INTERFACE_ERRORS" in evs:
                g = evs["INTERFACE_ERRORS"]
                parts.append(f"INTERFACE_ERRORS x{g.count} (CRC hingga {g.max_crc})")
                tags.append("switch_interface_errors")
            if "HIGH_LATENCY" in evs and (evs["HIGH_LATENCY"].avg_latency or 0) >= LATENCY_THRESHOLD:
                g = evs["HIGH_LATENCY"]
                parts.append(f"HIGH_LATENCY x{g.count} (rata-rata {g.avg_latency:.0f} ms)")
                tags.append("switch_latency_high")
            if "INTERFACE_DOWN" in evs:
                parts.append(f"INTERFACE_DOWN x{evs['INTERFACE_DOWN'].count} ({evs['INTERFACE_DOWN'].sample})")
                tags.append("switch_uplink_down")
            if "GATEWAY_UNREACHABLE" in evs and host == "MONITOR-01":
                parts.append(
                    f"MONITOR-01 tidak dapat menjangkau {', '.join(sorted({g.sample.split()[0] for g in gs if g.event_type == 'GATEWAY_UNREACHABLE'}))}"
                )
                tags.append("switch_unreachable")
            if "VLAN_MISCONFIG" in evs:
                parts.append(f"VLAN_MISCONFIG x{evs['VLAN_MISCONFIG'].count}")
                tags.append("vlan_misconfig_logs")
            if parts:
                first = min(g.first for g in gs)
                store.add(
                    "network_log",
                    f"{host}: " + "; ".join(parts) + f" mulai {fm(first)}.",
                    source_id="network_logs",
                    timestamp=first,
                    tags=sorted(set(tags)),
                    relevance=0.95,
                    host=host,
                )
    for host, gs in by_host.items():
        node = topo.node(host)
        if node and node["device_type"] in ("pc", "printer"):
            for g in gs:
                if g.event_type == "VLAN_MISCONFIG":
                    store.add(
                        "network_log",
                        f"{host}: VLAN_MISCONFIG x{g.count} ({g.sample})",
                        source_id="network_logs",
                        timestamp=g.first,
                        tags=["vlan_misconfig_logs"],
                        relevance=0.8,
                    )
    app = [g for g in corr.groups if g.domain == "application" and g.event_type in ("HTTP_TIMEOUT", "APP_ERROR", "DB_CONN_TIMEOUT")]
    if app and sum(g.count for g in app) >= MIN_SIGNAL_EVENTS:
        n = sum(g.count for g in app)
        units = sorted({u for g in app for u in g.units})
        first = min(g.first for g in app)
        wide = n >= 5 and (len(units) >= 3 or len(units) == 0)
        tag = ["app_errors_wide"] if wide else (["app_errors_single_unit"] if len(units) == 1 else ["app_errors_multi_unit"])
        store.add(
            "server_log",
            f"{app[0].hostname}: {n} error aplikasi ({', '.join(sorted({g.event_type for g in app}))}) sejak {fm(first)}; sumber unit: {', '.join(units) if units else 'tidak teridentifikasi (internal)'}.",
            source_id="server_logs",
            timestamp=first,
            tags=tag,
            relevance=0.9,
            units=units,
        )
    slow = [g for g in corr.groups if g.event_type == "SLOW_RESPONSE" and g.domain == "application"]
    if slow and sum(g.count for g in slow) >= MIN_SIGNAL_EVENTS:
        n = sum(g.count for g in slow)
        store.add(
            "server_log",
            f"{slow[0].hostname}: {n} respons lambat (SLOW_RESPONSE) sejak {fm(min(g.first for g in slow))}.",
            source_id="server_logs",
            timestamp=min(g.first for g in slow),
            tags=["app_slow_logs"],
            relevance=0.85,
        )
    dns = [g for g in corr.groups if g.domain == "dns"]
    if dns and sum(g.count for g in dns) >= MIN_SIGNAL_EVENTS:
        n = sum(g.count for g in dns)
        units = sorted({u for g in dns for u in g.units})
        store.add(
            "server_log",
            f"DNS: {n} kegagalan resolusi (DNS_QUERY_FAIL/DNS_FAILURE) dari {len(units)} unit sejak {fm(min(g.first for g in dns))}.",
            source_id="server_logs+network_logs",
            timestamp=min(g.first for g in dns),
            tags=["dns_failure_logs"],
            relevance=0.95,
            units=units,
        )
    db = [g for g in corr.groups if g.domain == "database"]
    if db and sum(g.count for g in db) >= MIN_SIGNAL_EVENTS:
        n = sum(g.count for g in db)
        store.add(
            "server_log",
            f"{db[0].hostname}: {n} event database abnormal ({', '.join(sorted({g.event_type for g in db}))}) sejak {fm(min(g.first for g in db))}: {db[0].sample}.",
            source_id="server_logs",
            timestamp=min(g.first for g in db),
            tags=["db_error_logs"],
            relevance=0.95,
        )
    for g in corr.groups:
        if g.domain == "server" and g.event_type in ("RESOURCE_HIGH_CPU", "RESOURCE_SAMPLE") and g.count >= 2:
            is_db = g.hostname.upper().startswith("SIMRS-DB")
            store.add(
                "server_log",
                f"{g.hostname}: resource tinggi ({g.event_type} x{g.count}, CPU puncak {g.peak_cpu}%) sejak {fm(g.first)}.",
                source_id="server_logs",
                timestamp=g.first,
                tags=["db_resource_high" if is_db else "server_cpu_high"],
                relevance=0.9,
                host=g.hostname,
            )
    if auth_failures >= 5:
        store.add(
            "server_log",
            f"{auth_failures} AUTH_FAILURE pada jendela +-{window_min} menit (di atas baseline).",
            source_id="server_logs",
            tags=["auth_failure_logs"],
            relevance=0.85,
        )
    for p in corr.patterns:
        if p.order_ok and p.score >= 0.6:
            ptag = {
                "network": "pattern_network_first",
                "dns": "pattern_dns_first",
                "database": "pattern_db_first",
                "server": "pattern_server_first",
            }[p.cause_domain]
            store.add(
                "log_correlation",
                f"Pola temporal '{p.name}': onset penyebab {fm(p.cause_onset)} mendahului onset gejala {fm(p.symptom_onset)} (jeda {p.lag_seconds:.0f} detik, {p.event_count} event); skor korelasi {p.score:.2f}.",
                kind="INFERENCE",
                timestamp=p.cause_onset,
                tags=[ptag],
                relevance=min(0.95, 0.5 + p.score / 2),
                pattern=p.name,
                score=p.score,
            )
        elif not p.order_ok:
            store.add(
                "log_correlation",
                f"Pola '{p.name}' tidak konsisten secara urutan waktu: event penyebab ({fm(p.cause_onset)}) terjadi setelah gejala ({fm(p.symptom_onset)}).",
                kind="INFERENCE",
                timestamp=p.cause_onset,
                tags=["pattern_order_violation"],
                relevance=0.6,
            )
    if corr.impact_units:
        others = len(corr.control_ok_hosts)
        if corr.flags["unit_only_impact"]:
            store.add(
                "log_correlation",
                f"Anomali hanya teramati pada unit {corr.impact_units[0]}; {others} endpoint lain di unit berbeda menunjukkan probe normal pada jendela yang sama.",
                kind="INFERENCE",
                tags=["unit_only_impact"] + (["control_group_ok"] if others >= 2 else []),
                relevance=0.9,
            )
        elif corr.flags["hospital_wide_impact"]:
            store.add(
                "log_correlation",
                f"Gejala teramati pada {len(corr.impact_units)} unit ({', '.join(corr.impact_units)}): dampak luas lintas unit.",
                kind="INFERENCE",
                tags=["hospital_wide_impact"],
                relevance=0.9,
            )
        elif corr.flags["multi_unit_impact"]:
            store.add(
                "log_correlation",
                f"Gejala teramati pada 2 unit ({', '.join(corr.impact_units)}).",
                kind="INFERENCE",
                tags=["multi_unit_impact"],
                relevance=0.85,
            )
    if corr.healthy_peers and len(hosts) >= 2:
        store.add(
            "network_log",
            f"{len(corr.healthy_peers)} endpoint lain pada switch yang sama menunjukkan probe normal ({', '.join(corr.healthy_peers[:4])}...): dampak parsial pada switch.",
            source_id="network_logs",
            tags=["partial_switch_impact"],
            relevance=0.7,
            kind="FACT",
        )
    elif len(hosts) == 1 and corr.healthy_peers:
        store.add(
            "network_log",
            f"{len(corr.healthy_peers)} endpoint lain pada switch yang sama normal, hanya {next(iter(hosts))} terdampak.",
            source_id="network_logs",
            tags=["peers_healthy"],
            relevance=0.85,
        )


def evidence_from_topology(
    store: EvidenceStore, topo: TopologyGraph, scope: ScopeAnalysis, server: str, sample_host: str | None
) -> dict[str, Any]:
    info: dict[str, Any] = {"path": [], "access_switch": None, "uplink": None}
    if sample_host:
        path = topo.path(sample_host, server)
        info["path"] = path or []
        sw = topo.access_switch(sample_host)
        info["access_switch"] = sw
        up = topo.uplink(sw) if sw else None
        info["uplink"] = up
        if path:
            store.add(
                "topology",
                f"Jalur logis {sample_host} ke {server}: {' -> '.join(path)}.",
                source_id="network_topology.json",
                tags=["topology_path"],
                relevance=0.8,
            )
    if scope.shared_access_switch:
        sw = scope.shared_access_switch
        up = topo.uplink(sw)
        store.add(
            "topology",
            f"{len(scope.affected_hosts)} endpoint terdampak seluruhnya terhubung ke access switch yang sama ({sw}); uplink {up['interface'] + ' -> ' + up['peer'] if up else 'n/a'}.",
            source_id="network_topology.json",
            kind="INFERENCE",
            tags=["shared_access_switch"],
            relevance=0.9,
            switch=sw,
        )
        info["access_switch"], info["uplink"] = sw, up
    elif len(scope.access_groups) > 1:
        store.add(
            "topology",
            f"Endpoint terdampak tersebar pada {len(scope.access_groups)} access switch ({', '.join(scope.access_groups)}): tidak ada satu switch akses bersama.",
            source_id="network_topology.json",
            kind="INFERENCE",
            tags=["no_shared_switch"],
            relevance=0.8,
        )
    return info
