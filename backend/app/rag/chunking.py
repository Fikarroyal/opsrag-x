"""SOP PDF parsing, cleaning and chunking (pipeline: parse -> clean -> chunk -> metadata)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SECTION_LABELS = [
    "Tujuan",
    "Indikasi",
    "Prasyarat",
    "Langkah Investigasi",
    "Indikator Evidence",
    "Langkah Remediation",
    "Verifikasi",
    "Rollback",
    "Catatan",
]
SECTION_KEYS = {lbl: lbl.lower().replace(" ", "_") for lbl in SECTION_LABELS}
HEADER_RE = re.compile(
    r"(SOP-\d{3})\s*\|\s*v([\d.]+)\s*\|\s*Berlaku:\s*(\d{4}-\d{2}-\d{2})\s*\|\s*Status:\s*(\w+)\s*\|\s*Judul:\s*(.+?)\s*Kode SOP:",
    re.DOTALL,
)
SECTION_RE = re.compile(r"^(" + "|".join(SECTION_LABELS) + r"):\s*$", re.MULTILINE)
CATEGORY_RE = re.compile(r"Kategori:\s*(\w+)\.")
MAX_CHUNK_CHARS = 900


@dataclass
class ParsedSopVersion:
    sop_code: str
    title: str
    version: str
    effective_date: date
    status: str
    category: str | None
    sections: dict[str, str]
    content_hash: str = ""
    chunks: list[dict] = field(default_factory=list)


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(path: Path) -> str:
    import pymupdf  # PyMuPDF

    with pymupdf.open(path) as doc:
        return clean_text("\n".join(page.get_text() for page in doc))


def parse_sop_text(text: str) -> list[ParsedSopVersion]:
    """Identify SOP headers (code/version/effective date/status) and split each block into sections."""
    matches = list(HEADER_RE.finditer(text))
    out: list[ParsedSopVersion] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() - len("Kode SOP:") : end]
        cat = CATEGORY_RE.search(body)
        parts = SECTION_RE.split(body)
        sections: dict[str, str] = {}
        # parts = [preamble, label1, text1, label2, text2, ...]
        for j in range(1, len(parts) - 1, 2):
            sections[SECTION_KEYS[parts[j]]] = clean_text(parts[j + 1])
        title = re.sub(r"\s+", " ", m.group(5)).strip()
        v = ParsedSopVersion(
            sop_code=m.group(1),
            title=title,
            version=m.group(2),
            effective_date=date.fromisoformat(m.group(3)),
            status=m.group(4),
            category=cat.group(1) if cat else None,
            sections=sections,
        )
        payload = json.dumps({"c": v.sop_code, "v": v.version, "d": m.group(3), "s": sections}, sort_keys=True, ensure_ascii=False)
        v.content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        v.chunks = chunk_sections(v)
        out.append(v)
    return out


def _split_long(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    lines, chunks, cur = text.split("\n"), [], ""
    for line in lines:
        if cur and len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def chunk_sections(v: ParsedSopVersion) -> list[dict]:
    """One chunk per section (split further when long). The header prefix makes each chunk self-describing."""
    chunks: list[dict] = []
    for label in SECTION_LABELS:
        key = SECTION_KEYS[label]
        body = v.sections.get(key)
        if not body:
            continue
        for idx, piece in enumerate(_split_long(body)):
            chunks.append(
                {
                    "section": key,
                    "chunk_index": idx,
                    "text": f"[{v.sop_code} v{v.version} | {v.title}] {label}: {piece}",
                    "metadata": {
                        "document_type": "sop",
                        "source": "hospital_it_sop.pdf",
                        "source_id": f"{v.sop_code}@{v.version}",
                        "timestamp": v.effective_date.isoformat(),
                        "category": v.category,
                        "sop_version": v.version,
                        "sop_code": v.sop_code,
                        "service": "SIMRS" if v.sop_code == "SOP-001" else None,
                    },
                }
            )
    return chunks


def chunk_markdown(text: str, source: str) -> list[dict]:
    """Infrastructure documentation: chunk by '## heading' sections."""
    chunks: list[dict] = []
    blocks = re.split(r"^## ", text, flags=re.MULTILINE)
    for i, block in enumerate(blocks[1:] if len(blocks) > 1 else blocks):
        head, _, body = block.partition("\n")
        piece = clean_text(body)
        if not piece:
            continue
        chunks.append(
            {
                "section": re.sub(r"\W+", "_", head.strip().lower()),
                "chunk_index": i,
                "text": f"[{source}] {head.strip()}: {piece}",
                "metadata": {"document_type": "infra_doc", "source": source, "source_id": f"{source}#{head.strip()}"},
            }
        )
    return chunks
