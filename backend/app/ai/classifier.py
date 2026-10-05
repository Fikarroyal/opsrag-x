"""Incident classifier: LLM classifier (optional) with a deterministic rule-based fallback.

The fallback keeps the whole system runnable without any model. A fine-tuned LoRA model can be plugged in
behind the same interface later (see training/README.md); the application does not require it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from app.ai.llm import BaseLLMProvider, LLMUnavailableError, extract_json
from app.ai.prompts import CATEGORIES, INVESTIGATOR_SYSTEM, SCOPES, SEVERITIES, classification_prompt

logger = logging.getLogger(__name__)

UNIT_PATTERNS: dict[str, str] = {
    "Poli 1": r"poli\s*-?\s*(?:1|i|satu)\b",
    "Poli 2": r"poli\s*-?\s*(?:2|ii|dua)\b",
    "Poli 3": r"poli\s*-?\s*(?:3|iii|tiga)\b",
    "Farmasi": r"farmasi|pharmacy",
    "Kasir": r"kasir|cashier",
    "Laboratorium": r"laborat\w*|\blab\b",
    "Radiologi": r"radiolog\w*",
    "IGD": r"\bigd\b|gawat\s+darurat",
    "Rekam Medis": r"rekam\s*medis|\brm\b",
    "IT": r"\bunit\s+it\b|ruang\s+it",
}
SLUG_UNIT = {
    "POLI1": "Poli 1",
    "POLI2": "Poli 2",
    "POLI3": "Poli 3",
    "FARMASI": "Farmasi",
    "KASIR": "Kasir",
    "LAB": "Laboratorium",
    "RADIOLOGI": "Radiologi",
    "IGD": "IGD",
    "REKAMMEDIS": "Rekam Medis",
    "IT": "IT",
}
DEVICE_RE = re.compile(r"\b((?:PC|PRN)-([A-Z0-9]+)-\d{3})\b", re.IGNORECASE)
TIME_RE = re.compile(r"(?:pukul|jam|sekitar|since|at|sejak)?\s*\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", re.IGNORECASE)

SERVICE_PATTERNS = [
    ("SIM-APOTEK", r"sim-?apotek|aplikasi\s+apotek"),
    ("DATABASE", r"database|\bdb\b|sim-?db"),
    ("DNS", r"\bdns\b|nslookup"),
    ("FILE SERVER", r"file\s*server|shared\s*folder"),
    ("MONITORING", r"monitoring|zabbix|grafana"),
    ("SIMRS", r"simrs|sim\s*rs|aplikasi|application"),
]

NEGATIONS = [
    r"internet\s+(?:umum\s+)?(?:masih\s+)?(?:normal|bisa|dapat|lancar|aman)[^.,;]*",
    r"(?:komputer|pc|unit)\s+lain(?:nya)?\s+(?:di\s+\w+\s+)?(?:juga\s+)?(?:masih\s+)?(?:normal|aman|bisa)[^.,;]*",
    r"other\s+(?:units?|pcs?|computers?)\s+(?:are\s+|is\s+)?(?:fine|normal|ok|working)",
    r"(?:jaringan|koneksi)\s+(?:masih\s+)?normal",
    r"unit\s+lain\s+(?:masih\s+)?normal",
    r"tetapi\s+internet\s+normal",
]
INTERNET_OK_RE = re.compile(
    r"internet\s+(?:umum\s+)?(?:masih\s+)?(?:normal|bisa|dapat|lancar|aman)|tetapi\s+internet\s+normal", re.IGNORECASE
)
OTHERS_OK_RE = re.compile(
    r"(?:komputer|pc|unit)\s+lain(?:nya)?[^.,;]*?(?:normal|aman|bisa)|other\s+(?:units?|pcs?|computers?)\s+(?:are\s+|is\s+)?(?:fine|normal|ok)",
    re.IGNORECASE,
)

# (regex, weight) per category
KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "dns": [
        (r"\bdns\b", 3),
        (r"nslookup", 3),
        (r"resol(?:ve|usi|ution)", 2),
        (r"nama\s+host", 2),
        (r"simrs\.internal", 2),
        (r"servfail", 3),
    ],
    "database": [
        (r"database", 4),
        (r"\bdb\b", 2),
        (r"\bquery\b", 1.5),
        (r"connection\s+pool", 3),
        (r"koneksi\s+database|database\s+connection", 3),
        (r"sim-?db", 3),
    ],
    "authentication": [
        (r"\blogin\b|log\s+in|sign\s+in", 2.5),
        (r"password|kata\s+sandi", 2),
        (r"autentikasi|authentication", 3),
        (r"akun\s+terkunci", 3),
        (r"tidak\s+bisa\s+masuk", 1.5),
    ],
    "server": [
        (r"server\b.{0,40}\b(?:lambat|lemot|down|mati|overload|slow)", 3),
        (r"response\s+(?:time\s+)?(?:lambat|tinggi)", 3),
        (r"overload", 3),
        (r"\bcpu\b", 2),
        (r"memori|memory", 1.5),
        (r"server\s+is\s+(?:very\s+)?slow", 3),
        (r"kinerja\s+server", 3),
        (r"response\s+time", 2),
        (r"\blambat\b|\blemot\b|\bslow\b", 2.5),
        (r"server\s+(?:down|mati)", 3),
    ],
    "network": [
        (r"packet\s*loss", 3),
        (r"koneksi\s+(?:putus|terputus)|putus-putus", 3),
        (r"tidak\s+ada\s+koneksi|no\s+connection", 3),
        (r"jaringan", 2),
        (r"jaringan\s+(?:putus|terputus|down)", 3),
        (r"internet.{0,30}(?:terputus|putus)", 3),
        (r"\bswitch\b", 2),
        (r"\bkabel\b", 1.5),
        (r"\bping\b", 1.5),
        (r"tidak\s+(?:dapat|bisa)\s+(?:terhubung|konek)", 2.5),
        (r"cannot\s+(?:reach|connect)", 3),
        (r"\boffline\b", 2),
        (r"\bwifi\b|\bnetwork\b|\bdisconnect", 2),
    ],
    "hardware": [
        (r"printer", 3),
        (r"monitor\s+mati", 3),
        (r"keyboard|mouse", 2),
        (r"hard\s*disk|hardisk|\bssd\b", 3),
        (r"komputer\s+mati", 3),
        (r"\bnic\b", 2),
        (r"kabel\s+rusak", 3),
        (r"tidak\s+terdeteksi", 2),
        (r"scanner|\bups\b", 2),
    ],
    "configuration": [(r"konfigurasi|configuration", 2.5), (r"\bvlan\b", 3), (r"ip\s+(?:conflict|bentrok)", 3), (r"salah\s+setting", 3)],
    "service": [(r"file\s*server", 3), (r"shared\s*folder", 3), (r"backup", 2), (r"monitoring", 2), (r"layanan", 1)],
    "application": [
        (r"simrs|sim-?apotek", 2),
        (r"aplikasi|application", 2),
        (r"tidak\s+(?:dapat|bisa)\s+(?:dibuka|membuka)|cannot\s+open", 2),
        (r"\berror\b", 0.5),
        (r"timeout", 0.5),
        (r"loading", 1),
        (r"tidak\s+merespons|not\s+responding", 2),
        (r"halaman", 0.5),
    ],
}
TIE_ORDER = ["dns", "database", "authentication", "server", "network", "hardware", "configuration", "service", "application", "unknown"]
SCOPE_BASE = {"single_device": 0, "single_unit": 1, "multi_unit": 2, "hospital_wide": 3, "unknown": 1}
SEV_ORDER = SEVERITIES


@dataclass
class Classification:
    category: str
    secondary_category: str | None
    severity: str
    affected_scope: str
    affected_service: str | None
    confidence: float
    method: str = "rules"
    unit: str | None = None
    device: str | None = None
    hinted_time: str | None = None
    internet_normal: bool = False
    others_normal: bool = False
    reasoning: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_entities(text: str, unit_hint: str | None = None, device_hint: str | None = None) -> dict[str, Any]:
    units = [u for u, p in UNIT_PATTERNS.items() if re.search(p, text, re.IGNORECASE)]
    dm = DEVICE_RE.search(text)
    device = (dm.group(1).upper() if dm else None) or (device_hint or None)
    unit = None
    if device:
        m = DEVICE_RE.match(device)
        unit = SLUG_UNIT.get(m.group(2).upper()) if m else None
    if not unit:
        unit = unit_hint if unit_hint and unit_hint != "Semua Unit" else (units[0] if units else None)
    tm = TIME_RE.search(text)
    return {"units": units, "unit": unit, "device": device, "time": f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None}


def _strip_negations(text: str) -> str:
    for pat in NEGATIONS:
        text = re.sub(pat, " ", text, flags=re.IGNORECASE)
    return text


def classify_rules(
    text: str, unit_hint: str | None = None, device_hint: str | None = None, service_hint: str | None = None
) -> Classification:
    ent = extract_entities(text, unit_hint, device_hint)
    cleaned = _strip_negations(text)
    scores = {c: sum(w for p, w in kws if re.search(p, cleaned, re.IGNORECASE)) for c, kws in KEYWORDS.items()}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], TIE_ORDER.index(kv[0])))
    best, best_s = ranked[0]
    second, second_s = ranked[1]
    reasoning = [f"keyword scores: {', '.join(f'{c}={s:g}' for c, s in ranked[:3] if s > 0) or 'none'}"]
    category = best if best_s >= 1.5 else "unknown"
    # --- scope
    low = text.lower()
    wide = re.search(
        r"semua\s+unit|seluruh\s+(?:rumah\s+sakit|unit|rs)\b|all\s+units|whole\s+hospital|across\s+the\s+hospital|banyak\s+komputer|banyak\s+unit|berbagai\s+unit|semua\s+user|semua\s+komputer\s+di\s+(?:rs|rumah)",
        low,
    )
    single_hint = re.search(
        r"komputer\s+lain\s+(?:masih\s+)?normal|other\s+(?:pcs|computers)\s+(?:are\s+)?(?:fine|normal)", low
    ) and not re.search(r"beberapa|semua|several|multiple|users|all\b", low)
    if ent["device"] or (single_hint and ent["unit"]):
        scope = "single_device"
    elif wide:
        scope = "hospital_wide"
    elif len(ent["units"]) >= 2 or "beberapa unit" in low:
        scope = "multi_unit"
    elif ent["unit"]:
        scope = "single_unit"
    elif category in ("dns", "database", "server") or re.search(r"semua\s+komputer|all\s+computers", low):
        scope = "hospital_wide"
    else:
        scope = "unknown"
    # --- severity
    idx = SCOPE_BASE[scope]
    if ent["unit"] == "IGD":
        idx += 1
    if category == "server" and re.search(r"lambat|lemot|slow|response", low) and not re.search(r"down|mati", low):
        idx -= 1
    if category == "hardware":
        idx = min(idx, 1)
    severity = SEV_ORDER[max(0, min(3, idx))]
    # --- service
    service = service_hint or next((n for n, p in SERVICE_PATTERNS if re.search(p, text, re.IGNORECASE)), None)
    if category == "dns":
        service = "DNS"
    elif category == "database":
        service = "DATABASE"
    elif (
        category in ("application", "server", "authentication", "network")
        and service in (None, "DNS", "DATABASE")
        and re.search(r"simrs|aplikasi", low)
    ):
        service = "SIMRS"
    secondary = second if second_s >= 2.0 and second != best else None
    if category == "application" and not secondary:
        secondary = "server" if scope == "hospital_wide" else "network"
    conf = 0.35 if category == "unknown" else min(0.95, 0.55 + 0.08 * (best_s - second_s) + 0.02 * best_s)
    return Classification(
        category,
        secondary,
        severity,
        scope,
        service,
        round(conf, 2),
        "rules",
        ent["unit"],
        ent["device"],
        ent["time"],
        bool(INTERNET_OK_RE.search(text)),
        bool(OTHERS_OK_RE.search(text)),
        reasoning,
    )


def classify(
    text: str,
    llm: BaseLLMProvider | None = None,
    *,
    unit_hint: str | None = None,
    device_hint: str | None = None,
    service_hint: str | None = None,
) -> Classification:
    """LLM classification when available and valid, otherwise rules. Output is always schema-validated."""
    base = classify_rules(text, unit_hint, device_hint, service_hint)
    if llm is None or not llm.is_available():
        return base
    try:
        raw = llm.generate(INVESTIGATOR_SYSTEM, classification_prompt(text, base.unit, base.device), json_mode=True)
        data = extract_json(raw) or {}
        cat, sev, scope = (data.get("category"), data.get("severity"), data.get("affected_scope"))
        if cat in CATEGORIES and sev in SEVERITIES and scope in SCOPES:
            svc = (
                data.get("affected_service")
                if data.get("affected_service") in ("SIMRS", "SIM-APOTEK", "DNS", "DATABASE", "FILE SERVER", "MONITORING")
                else base.affected_service
            )
            conf = data.get("confidence")
            base.category, base.severity, base.affected_scope, base.affected_service = (cat, sev, scope, svc)
            base.confidence = round(float(conf), 2) if isinstance(conf, (int, float)) and 0 <= conf <= 1 else base.confidence
            base.method = "llm"
            base.reasoning.append(f"LLM classification validated against schema (model {llm.model})")
        else:
            base.reasoning.append("LLM output failed schema validation; rule-based classification kept")
    except (LLMUnavailableError, ValueError, TypeError) as exc:
        logger.info("LLM classification unavailable (%s); using rules", exc)
    return base


def parse_time_hint(hint: str | None, base: datetime) -> datetime | None:
    if not hint:
        return None
    h, m = hint.split(":")
    return base.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
