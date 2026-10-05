#!/usr/bin/env python
"""Generate the SYNTHETIC fine-tuning datasets (JSONL) from templates. No patient data, deterministic (seeded).

Writes training/datasets/{incident_classification,severity_classification,root_cause_classification,tool_selection,response_format}.jsonl
Each line: {"instruction": str, "input": str, "output": object}
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent / "datasets"
rng = random.Random(7)
UNITS = ["Poli 1", "Poli 2", "Poli 3", "Farmasi", "Kasir", "Laboratorium", "Radiologi", "IGD", "Rekam Medis"]
TIMES = ["07:55", "08:30", "09:42", "10:15", "11:05", "13:15", "14:05", "15:20"]
DEVICES = {
    "Poli 1": "PC-POLI1-004",
    "Poli 2": "PC-POLI2-007",
    "Poli 3": "PC-POLI3-002",
    "Farmasi": "PC-FARMASI-003",
    "Kasir": "PC-KASIR-003",
    "Laboratorium": "PC-LAB-005",
    "Radiologi": "PC-RADIOLOGI-002",
    "IGD": "PC-IGD-006",
    "Rekam Medis": "PC-REKAMMEDIS-001",
}

# (category, scope, service, base severity, templates)
PATTERNS: list[tuple[str, str, str | None, str, list[str]]] = [
    (
        "application",
        "single_unit",
        "SIMRS",
        "medium",
        [
            "SIMRS tidak dapat dibuka dari {unit}.",
            "Beberapa komputer di {unit} tidak bisa membuka SIMRS. Internet umum masih normal. Mulai pukul {time}.",
            "Aplikasi SIMRS di {unit} loading terus lalu timeout sejak {time}.",
            "Users in {unit} cannot open SIMRS since {time}, other units are fine.",
            "Dokter di {unit} melaporkan SIMRS tidak merespons.",
        ],
    ),
    (
        "application",
        "hospital_wide",
        "SIMRS",
        "critical",
        [
            "SIMRS tidak bisa dibuka dari semua unit, halaman error 502.",
            "Seluruh rumah sakit tidak dapat membuka SIMRS sejak {time}.",
            "SIMRS down di semua unit, aplikasi tidak merespons.",
        ],
    ),
    (
        "application",
        "single_unit",
        "SIM-APOTEK",
        "medium",
        ["SIM-APOTEK tidak bisa dibuka di {unit} sejak {time}.", "Aplikasi apotek tidak dapat diakses dari {unit}."],
    ),
    (
        "network",
        "single_unit",
        "SIMRS",
        "medium",
        [
            "Komputer {unit} mengalami packet loss dan SIMRS tidak bisa diakses.",
            "Semua komputer {unit} tidak ada koneksi jaringan sejak {time}.",
            "{unit} offline, komputer tidak bisa terhubung ke server.",
            "Poli tidak bisa akses SIMRS, koneksi putus-putus di {unit}.",
        ],
    ),
    (
        "network",
        "single_device",
        None,
        "low",
        [
            "Internet {device} terputus tetapi komputer lain normal.",
            "{device} sering disconnect dari jaringan, komputer lain di {unit} normal.",
            "Koneksi {device} putus sejak {time}.",
        ],
    ),
    (
        "dns",
        "hospital_wide",
        "DNS",
        "critical",
        [
            "DNS internal tidak bisa resolve server SIMRS.",
            "nslookup simrs.internal gagal di banyak komputer sejak {time}.",
            "SIMRS tidak bisa dibuka lewat nama host tetapi bisa lewat IP. DNS bermasalah.",
            "Internal DNS resolution fails across the hospital since {time}.",
        ],
    ),
    (
        "database",
        "hospital_wide",
        "DATABASE",
        "critical",
        [
            "SIMRS error database connection timeout di semua unit.",
            "Database SIMRS tidak merespons sejak {time}, transaksi tidak bisa disimpan.",
            "Koneksi database SIMRS gagal, semua user terdampak.",
            "The SIMRS database connection times out for every unit since {time}.",
        ],
    ),
    (
        "server",
        "hospital_wide",
        "SIMRS",
        "high",
        [
            "Server SIMRS mengalami response lambat.",
            "SIMRS sangat lambat di semua unit sejak {time}, server terlihat overload.",
            "Server aplikasi SIMRS lemot, CPU tinggi, semua unit mengeluh.",
            "SIMRS server is very slow for all units since {time}.",
        ],
    ),
    (
        "authentication",
        "single_unit",
        "SIMRS",
        "medium",
        [
            "SIMRS tidak bisa login tetapi internet normal di {unit}.",
            "User {unit} tidak dapat login ke SIMRS, muncul pesan autentikasi gagal.",
            "Login SIMRS ditolak untuk beberapa user di {unit}.",
        ],
    ),
    (
        "hardware",
        "single_device",
        None,
        "low",
        [
            "Printer {unit} tidak terdeteksi dari {device}.",
            "Komputer {device} mati total, kabel daya sudah dicek.",
            "Keyboard dan mouse {device} tidak berfungsi.",
        ],
    ),
    (
        "configuration",
        "single_unit",
        "SIMRS",
        "medium",
        [
            "Komputer baru di {unit} tidak bisa akses SIMRS, VLAN tidak sesuai.",
            "Setelah maintenance, PC {unit} dapat IP segmen salah, konfigurasi VLAN diduga bermasalah.",
        ],
    ),
    (
        "service",
        "single_unit",
        "FILE SERVER",
        "medium",
        ["Shared folder di file server tidak bisa dibuka dari {unit}.", "File server tidak merespons dari {unit}, backup harian gagal."],
    ),
]
ORDER = ["low", "medium", "high", "critical"]
ROOT = {  # category -> (root cause category, evidence sentences supporting it)
    "network": (
        "network",
        [
            "Beberapa endpoint pada switch akses yang sama mengalami packet loss bersamaan.",
            "Interface uplink switch akses menunjukkan error CRC dan latency meningkat.",
            "Server aplikasi sehat dan DNS berfungsi.",
            "Unit lain tidak terdampak.",
        ],
    ),
    "dns": (
        "dns",
        [
            "DNS lookup simrs.internal gagal SERVFAIL dari banyak unit.",
            "Akses lewat alamat IP tetap berhasil.",
            "Log DNS-01 menunjukkan DNS_QUERY_FAIL sebelum gejala aplikasi.",
            "Layanan DNS berstatus down.",
        ],
    ),
    "database": (
        "database",
        [
            "Layanan DATABASE berstatus degraded.",
            "Log database menunjukkan connection pool exhausted sebelum error aplikasi.",
            "Seluruh unit terdampak.",
            "Jaringan dan DNS normal.",
        ],
    ),
    "server": (
        "server",
        [
            "CPU server aplikasi di atas 90% dan memori tinggi.",
            "Response time tinggi dari semua unit tanpa error koneksi.",
            "Lonjakan resource mendahului respons lambat.",
            "Database dan DNS normal.",
        ],
    ),
    "authentication": (
        "authentication",
        ["Log AUTH_FAILURE meningkat untuk banyak akun.", "Health endpoint SIMRS normal.", "Jaringan dan DNS normal."],
    ),
    "hardware": (
        "hardware",
        ["Hanya satu endpoint yang mengalami packet loss.", "Endpoint lain pada switch yang sama normal.", "Server dan DNS sehat."],
    ),
    "configuration": (
        "configuration",
        ["Log VLAN_MISCONFIG pada port switch akses.", "Endpoint baru mendapat segmen IP yang salah.", "Server dan DNS sehat."],
    ),
    "service": ("service", ["Layanan file server berstatus degraded.", "Hanya akses ke shared folder yang gagal.", "Jaringan normal."]),
    "application": (
        "application",
        ["Health endpoint SIMRS mengembalikan 503.", "Log aplikasi menunjukkan error dari semua unit.", "Database dan DNS normal."],
    ),
}
TOOLS = {  # (category, scope) -> tools
    ("application", "single_unit"): [
        "ping_host",
        "get_network_interface_status",
        "get_topology_path",
        "check_http",
        "query_service_status",
        "get_server_status",
        "check_dns",
    ],
    ("application", "hospital_wide"): ["check_http", "query_service_status", "get_server_status", "check_dns", "ping_host"],
    ("network", "single_unit"): ["ping_host", "get_network_interface_status", "get_topology_path", "check_http"],
    ("network", "single_device"): ["ping_host", "get_device_info", "get_network_interface_status", "get_topology_path"],
    ("dns", "hospital_wide"): ["check_dns", "check_http", "query_service_status", "ping_host", "search_logs"],
    ("database", "hospital_wide"): ["query_service_status", "get_server_status", "search_logs", "check_http"],
    ("server", "hospital_wide"): ["get_server_status", "check_http", "query_service_status", "search_logs", "check_dns"],
    ("authentication", "single_unit"): ["check_http", "query_service_status", "get_server_status", "search_logs"],
    ("hardware", "single_device"): ["get_device_info", "ping_host", "get_network_interface_status", "get_topology_path"],
    ("configuration", "single_unit"): ["ping_host", "get_network_interface_status", "get_topology_path", "get_device_info"],
    ("service", "single_unit"): ["query_service_status", "ping_host", "search_logs"],
}


def severity(cat: str, scope: str, base: str, unit: str | None) -> str:
    idx = ORDER.index(base)
    if unit == "IGD" and scope != "hospital_wide":
        idx = min(3, idx + 1)
    return ORDER[idx]


def sample_incidents(n: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    guard = 0
    while len(out) < n and guard < n * 50:
        guard += 1
        cat, scope, svc, sev0, temps = rng.choice(PATTERNS)
        unit = rng.choice(UNITS) if scope != "hospital_wide" else None
        text = (
            rng.choice(temps)
            .format(unit=unit or "", device=DEVICES.get(unit or "Poli 3", "PC-POLI3-002"), time=rng.choice(TIMES))
            .replace("  ", " ")
            .strip()
        )
        if text in seen:
            continue
        seen.add(text)
        out.append(
            {"text": text, "category": cat, "scope": scope, "service": svc, "severity": severity(cat, scope, sev0, unit), "unit": unit}
        )
    return out


def write(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{name}.jsonl: {len(rows)} examples")


def main() -> None:
    inc = sample_incidents(260)
    write(
        "incident_classification",
        [
            {
                "instruction": "Classify this IT incident.",
                "input": i["text"],
                "output": {
                    "category": i["category"],
                    "severity": i["severity"],
                    "affected_scope": i["scope"],
                    "affected_service": i["service"],
                },
            }
            for i in inc
        ],
    )
    write(
        "severity_classification",
        [
            {
                "instruction": "Assign the severity (low, medium, high or critical) of this IT incident given its category and scope.",
                "input": f"{i['text']} | category={i['category']} | scope={i['scope']}",
                "output": {"severity": i["severity"]},
            }
            for i in inc[:230]
        ],
    )
    rc = []
    for i in inc[:230]:
        root, sents = ROOT[i["category"]]
        k = rng.randint(2, len(sents))
        chosen = rng.sample(sents, k)
        distract = []
        if i["category"] not in ("dns",) and rng.random() < 0.5:
            distract.append("Evidence lama dari incident historis menyebut penyebab berbeda (hanya supporting evidence).")
        rc.append(
            {
                "instruction": "Given the incident and the evidence summary, choose the most supported root-cause category. Historical incidents are supporting evidence only.",
                "input": f"Incident: {i['text']}\nEvidence:\n" + "\n".join(f"- {s}" for s in chosen + distract),
                "output": {
                    "root_cause_category": root,
                    "confidence_band": "high" if k >= 3 else "medium",
                    "note": "evidence confidence score, not a probability",
                },
            }
        )
    write("root_cause_classification", rc)
    ts = []
    for i in inc[:230]:
        tools = TOOLS.get((i["category"], i["scope"])) or TOOLS[("application", "single_unit")]
        ts.append(
            {
                "instruction": "Select the minimal set of READ-ONLY MCP diagnostic tools for this incident classification and explain why.",
                "input": json.dumps(
                    {
                        "incident": i["text"],
                        "category": i["category"],
                        "affected_scope": i["scope"],
                        "affected_service": i["service"],
                        "unit": i["unit"],
                    },
                    ensure_ascii=False,
                ),
                "output": {
                    "reason": f"{i['category']} incident with scope {i['scope']}: test the competing domains and localise the fault with a control device.",
                    "selected_tools": tools,
                },
            }
        )
    write("tool_selection", ts)
    rf = []
    for i in inc[:220]:
        root, sents = ROOT[i["category"]]
        sup = rng.sample(sents, min(3, len(sents)))
        rf.append(
            {
                "instruction": "Format these findings as the structured investigation JSON. Do not invent evidence; keep uncertainty explicit.",
                "input": f"Incident: {i['text']}\nSupporting: {' | '.join(sup)}\nContradicting: Unit lain normal.\nHypothesis: {root}",
                "output": {
                    "incident_summary": f"{i['text']} Hipotesis paling didukung: {root}.",
                    "root_cause_hypotheses": [
                        {
                            "description": root,
                            "confidence": 0.0,
                            "supporting_evidence": sup,
                            "contradicting_evidence": ["Unit lain normal."],
                        }
                    ],
                    "limitations": [
                        "Confidence dihitung dari evidence scoring, bukan probabilitas statistik.",
                        "Rekomendasi memerlukan verifikasi IT Support.",
                    ],
                },
            }
        )
    write("response_format", rf)


if __name__ == "__main__":
    main()
