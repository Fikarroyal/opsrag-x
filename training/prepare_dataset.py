#!/usr/bin/env python
"""Validate, de-duplicate and convert the JSONL datasets into chat-format train/val splits (training/prepared/)."""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, DST = HERE / "datasets", HERE / "prepared"
SYSTEM = "You are OpsRAG-X, an evidence-based IT incident investigation assistant for hospital IT infrastructure. Answer with valid JSON only. Never use patient information."
PATIENT_RE = re.compile(
    r"\b(pasien|patient|diagnosa|diagnosis|no\.?\s*rm|nomor\s+rekam|nik\b|bpjs)\b", re.IGNORECASE
)  # rekam MEDIS as a UNIT name is allowed, patient identifiers are not
TASKS = ["incident_classification", "severity_classification", "root_cause_classification", "tool_selection", "response_format"]


def load(task: str) -> list[dict]:
    rows, seen = [], set()
    for n, line in enumerate((SRC / f"{task}.jsonl").read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        r = json.loads(line)
        if not {"instruction", "input", "output"} <= set(r) or not isinstance(r["output"], (dict, list)):
            raise SystemExit(f"{task}.jsonl line {n}: needs instruction/input/output(object)")
        blob = json.dumps(r, ensure_ascii=False)
        if PATIENT_RE.search(blob):
            raise SystemExit(f"{task}.jsonl line {n}: contains patient-related terms; datasets must be IT-infrastructure only")
        key = (r["instruction"], r["input"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    return rows


def to_chat(r: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"{r['instruction']}\n\n{r['input']}"},
            {"role": "assistant", "content": json.dumps(r["output"], ensure_ascii=False)},
        ]
    }


def main() -> int:
    rng = random.Random(42)
    DST.mkdir(exist_ok=True)
    train, val = [], []
    for t in TASKS:
        rows = load(t)
        rng.shuffle(rows)
        cut = max(1, int(len(rows) * 0.9))
        train += [{**to_chat(r), "task": t} for r in rows[:cut]]
        val += [{**to_chat(r), "task": t, "raw": r} for r in rows[cut:]]
        print(f"{t:<28} {len(rows):>4} examples -> train {cut}, val {len(rows) - cut}")
    rng.shuffle(train)
    for name, rows in (("train", train), ("val", val)):
        with (DST / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {DST}/train.jsonl ({len(train)}) and val.jsonl ({len(val)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
