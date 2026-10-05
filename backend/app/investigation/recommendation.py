"""Recommendation generator. Every action references evidence keys; nothing is executed automatically."""

from __future__ import annotations

from typing import Any

from app.ai.classifier import Classification
from app.ai.hypothesis import Hypothesis
from app.investigation.evidence import EvidenceStore

SOP_FOR = {
    "H_NET_ACCESS": ["SOP-003", "SOP-007"],
    "H_ENDPOINT": ["SOP-003"],
    "H_APP": ["SOP-001"],
    "H_DNS": ["SOP-002"],
    "H_DB": ["SOP-005"],
    "H_OVERLOAD": ["SOP-006", "SOP-004"],
    "H_CORE": ["SOP-003"],
    "H_AUTH": ["SOP-008"],
    "H_CONFIG": ["SOP-003"],
}
SWITCH_TAGS = {"switch_interface_errors", "switch_uplink_down", "switch_latency_high", "switch_unreachable"}

TEMPLATES: dict[str, list[tuple[str, set[str]]]] = {
    "H_NET_ACCESS": [
        (
            "Verifikasi uplink {switch} ({uplink_if} ke {dist}): periksa kondisi kabel, transceiver/SFP dan status port fisik.",
            SWITCH_TAGS | {"shared_access_switch"},
        ),
        (
            "Periksa interface error (CRC, drop, flapping) pada {switch} {uplink_if} dan port peer di {dist}; bandingkan dengan switch akses unit lain yang sehat.",
            SWITCH_TAGS | {"multi_endpoint_loss"},
        ),
        (
            "Verifikasi konfigurasi VLAN dan trunk (VLAN {vlan}) pada port uplink dan port endpoint terdampak.",
            {"shared_access_switch", "multi_endpoint_loss"},
        ),
        ("Verifikasi status port switch untuk endpoint terdampak ({ports}).", {"multi_endpoint_loss", "endpoint_loss_logs"}),
        (
            "Pulihkan konektivitas mengikuti {sop_ref} (ganti kabel/transceiver yang bermasalah; restart switch hanya dengan izin perubahan). Sistem ini tidak melakukan perubahan otomatis.",
            SWITCH_TAGS | {"multi_endpoint_loss"},
        ),
    ],
    "H_ENDPOINT": [
        ("Periksa kabel LAN dan NIC pada {device}; uji dengan kabel pengganti.", {"single_endpoint_loss", "peers_healthy"}),
        ("Pindahkan {device} ke port switch lain ({switch}) dan uji ulang konektivitas.", {"single_endpoint_loss", "peers_healthy"}),
        ("Jika masih gagal, ikuti {sop_ref} untuk penggantian perangkat keras endpoint.", {"single_endpoint_loss"}),
    ],
    "H_APP": [
        (
            "Periksa proses layanan SIMRS dan log aplikasi pada {server} (status service, error terakhir, deployment terbaru).",
            {"app_unhealthy", "service_down", "service_degraded", "app_errors_wide"},
        ),
        (
            "Verifikasi health endpoint SIMRS dan dependensinya (database, DNS) secara manual sebelum tindakan apapun.",
            {"app_unhealthy", "service_degraded", "db_ok", "dns_ok"},
        ),
        (
            "Jika layanan terbukti berhenti, restart service SIMRS setelah persetujuan penanggung jawab sesuai {sop_ref}.",
            {"app_unhealthy", "service_down"},
        ),
    ],
    "H_DNS": [
        (
            "Uji query langsung ke {dns} untuk simrs.internal dan tinjau log resolver.",
            {"dns_failed", "dns_service_down", "dns_failure_logs"},
        ),
        ("Validasi zone file simrs.internal sebelum tindakan perubahan apapun.", {"dns_failure_logs", "dns_failed"}),
        (
            "Jika resolver hang, restart layanan DNS pada {dns} setelah persetujuan, mengikuti {sop_ref}.",
            {"dns_failed", "dns_service_down", "dns_failure_logs"},
        ),
        ("Sebagai workaround sementara, konfirmasi akses SIMRS lewat alamat IP tetap berfungsi.", {"ip_http_healthy", "server_reachable"}),
    ],
    "H_DB": [
        (
            "Periksa jumlah koneksi aktif, session idle dan query yang berjalan lama pada {db}.",
            {"db_unhealthy", "db_error_logs", "db_resource_high"},
        ),
        ("Tinjau connection pool aplikasi dan batas max_connections; koordinasi dengan DBA.", {"db_error_logs", "db_unhealthy"}),
        ("Akhiri session/query bermasalah hanya oleh DBA dan sesuai {sop_ref}.", {"db_unhealthy", "db_error_logs", "pattern_db_first"}),
    ],
    "H_OVERLOAD": [
        (
            "Identifikasi proses atau job terjadwal yang menghabiskan CPU/memori pada {server}.",
            {"server_cpu_high", "app_slow_logs", "http_slow"},
        ),
        (
            "Tinjau job laporan/ekspor yang berjalan pada jam sibuk dan pertimbangkan penjadwalan ulang.",
            {"server_cpu_high", "pattern_server_first"},
        ),
        ("Jika perlu, restart proses aplikasi atau tambah kapasitas dengan izin sesuai {sop_ref}.", {"server_cpu_high", "http_slow"}),
    ],
    "H_CORE": [
        (
            "Periksa status interface dan routing pada RTR-CORE dan CORE-SW-01 serta reachability dari beberapa unit.",
            {"control_group_loss", "server_unreachable", "hospital_wide_impact"},
        ),
        ("Eskalasi ke penanggung jawab jaringan; ikuti {sop_ref}.", {"control_group_loss", "hospital_wide_impact"}),
    ],
    "H_AUTH": [
        ("Tinjau log autentikasi untuk akun yang gagal login dan pola waktunya.", {"auth_failure_logs"}),
        ("Verifikasi sinkronisasi waktu server dan layanan direktori sesuai {sop_ref}.", {"auth_failure_logs", "server_healthy"}),
    ],
    "H_CONFIG": [
        ("Bandingkan konfigurasi VLAN/trunk {switch} dengan backup terakhir yang valid.", {"vlan_misconfig_logs"}),
        ("Koreksi konfigurasi hanya dengan izin perubahan dan ikuti {sop_ref}.", {"vlan_misconfig_logs"}),
    ],
}
VERIFY_BASE = [
    "ping gateway dari endpoint terdampak (packet loss 0%)",
    "resolusi DNS simrs.internal berhasil",
    "HTTP health check SIMRS mengembalikan 200 dengan response normal",
    "pengguna di unit terdampak dapat membuka SIMRS",
]


def _refs(store: EvidenceStore, hyp: Hypothesis | None, tags: set[str]) -> list[str]:
    keys = [e.key for e in store.items if set(e.tags) & tags and (hyp is None or e.hypothesis_roles.get(hyp.id) == "supporting")]
    if not keys and hyp is not None:
        keys = hyp.supporting[:3]
    if not keys:
        keys = [e.key for e in store.items if e.kind == "UNKNOWN"][:2] or [e.key for e in store.items if "incident_report" in e.tags][:1]
    return keys[:6]


def build_recommendations(
    top: Hypothesis | None,
    conclusive: bool,
    store: EvidenceStore,
    cls: Classification,
    topo_info: dict[str, Any],
    scope_hosts: list[str],
    sop_versions: dict[str, Any],
    ports: list[str],
    vlan: Any,
) -> dict[str, Any]:
    up = topo_info.get("uplink") or {}
    labels = {
        "switch": topo_info.get("access_switch") or "switch akses",
        "uplink_if": up.get("interface", "uplink"),
        "dist": up.get("peer", "distribution switch"),
        "vlan": vlan or "unit",
        "ports": ", ".join(ports[:6]) or "port endpoint",
        "device": (scope_hosts[0] if scope_hosts else "endpoint"),
        "server": "SIMRS-APP-01",
        "dns": "DNS-01",
        "db": "SIMRS-DB-01",
    }
    actions: list[dict[str, Any]] = []
    sop_used: list[dict[str, Any]] = []
    verification = list(VERIFY_BASE)
    if conclusive and top is not None:
        codes = [c for c in SOP_FOR.get(top.id, []) if c in sop_versions]
        sop_ref = " / ".join(f"{c} v{sop_versions[c].version}" for c in codes[:2]) or "SOP terkait"
        for c in codes[:2]:
            v = sop_versions[c]
            steps = [s.strip() for s in (v.sections.get("langkah_remediation") or "").split("\n") if s.strip()]
            sop_used.append(
                {
                    "sop_code": c,
                    "version": v.version,
                    "effective_date": v.effective_date.isoformat(),
                    "remediation_steps": steps,
                    "verification": v.sections.get("verifikasi"),
                    "rollback": v.sections.get("rollback"),
                }
            )
            if v.sections.get("verifikasi"):
                verification.append(f"[{c} v{v.version}] {v.sections['verifikasi']}")
        for text, tags in TEMPLATES.get(top.id, []):
            txt = text.format(sop_ref=sop_ref, **labels)
            if (
                top.id == "H_NET_ACCESS"
                and "switch_uplink_down" in store.tags()
                and "uplink" in txt
                and txt.startswith("Verifikasi uplink")
            ):
                txt = txt.replace("Verifikasi uplink", "Uplink terdeteksi DOWN - verifikasi uplink", 1)
            actions.append(
                {
                    "type": "RECOMMENDATION",
                    "text": txt,
                    "evidence_refs": _refs(store, top, tags),
                    "sop_reference": sop_ref if "{sop_ref}" in text else None,
                    "requires_human_approval": True,
                }
            )
    else:
        unknown = [e.key for e in store.items if e.kind == "UNKNOWN"][:3] or [e.key for e in store.items][:2]
        for text in [
            "Root cause belum dapat ditentukan secara memadai. Kumpulkan evidence tambahan: periksa manual konektivitas endpoint terdampak dan status layanan terkait.",
            "Pastikan sumber log dan probe monitoring mencakup perangkat/unit terdampak pada waktu kejadian, lalu jalankan ulang investigasi (Replay).",
            "Eskalasi ke IT Support senior bila gangguan berlanjut; ikuti SOP-001 untuk penanganan awal SIMRS tidak dapat diakses.",
        ]:
            actions.append(
                {"type": "RECOMMENDATION", "text": text, "evidence_refs": unknown, "sop_reference": None, "requires_human_approval": True}
            )
    for i, a in enumerate(actions, start=1):
        a["order"] = i
    next_diag = (
        top.definition.next_diagnostic
        if (top is not None and top.definition is not None)
        else "Collect direct diagnostics (interface counters, service health, application logs) for the affected unit."
    )
    return {"actions": actions, "verification": verification, "next_diagnostic": next_diag, "sop_procedures": sop_used, "labels": labels}
