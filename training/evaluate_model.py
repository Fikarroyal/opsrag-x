#!/usr/bin/env python
"""Evaluate classifiers on (a) the held-out validation split and (b) the 50-incident benchmark.

* The rule-based fallback classifier is always evaluated (no GPU/model needed) - this is the baseline.
* With --model-dir (LoRA adapter) and the training dependencies + a GPU, the fine-tuned model is evaluated as well.
Results are written to training/results/ (real measurements only).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.ai.classifier import classify_rules  # noqa: E402


def acc(pairs: list[tuple[object, object]]) -> float:
    return round(sum(a == b for a, b in pairs) / len(pairs), 4) if pairs else 0.0


def eval_rules() -> dict:
    out: dict = {}
    val = (
        [json.loads(line) for line in (HERE / "prepared" / "val.jsonl").open(encoding="utf-8")]
        if (HERE / "prepared" / "val.jsonl").exists()
        else []
    )
    cls = [v["raw"] for v in val if v["task"] == "incident_classification"]
    preds = [(classify_rules(r["input"]), r["output"]) for r in cls]
    out["validation_split"] = {
        "n": len(cls),
        "category_accuracy": acc([(p.category, o["category"]) for p, o in preds]),
        "severity_accuracy": acc([(p.severity, o["severity"]) for p, o in preds]),
        "scope_accuracy": acc([(p.affected_scope, o["affected_scope"]) for p, o in preds]),
    }
    bench = json.loads((ROOT / "data" / "benchmark" / "benchmark_incidents.json").read_text(encoding="utf-8"))
    bp = [(classify_rules(b["description"]), b) for b in bench]
    out["benchmark"] = {
        "n": len(bench),
        "category_accuracy": acc([(p.category, b["expected_category"]) for p, b in bp]),
        "severity_accuracy": acc([(p.severity, b["expected_severity"]) for p, b in bp]),
    }
    return out


def eval_model(model_dir: str) -> dict | str:
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        return f"skipped: missing dependency {exc.name} (pip install -r training/requirements.txt)"
    if not torch.cuda.is_available():
        return "skipped: no CUDA GPU available for model inference"
    cfg = json.loads((Path(model_dir) / "opsragx_training_config.json").read_text())
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = PeftModel.from_pretrained(
        AutoModelForCausalLM.from_pretrained(cfg["base_model"], torch_dtype=torch.bfloat16).to("cuda"), model_dir
    ).eval()
    from prepare_dataset import SYSTEM  # type: ignore[import-not-found]

    def ask(text: str) -> dict | None:
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Classify this IT incident.\n\n{text}"}]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda")
        with torch.no_grad():
            gen = model.generate(ids, max_new_tokens=96, do_sample=False)
        try:
            return json.loads(tok.decode(gen[0][ids.shape[1] :], skip_special_tokens=True))
        except json.JSONDecodeError:
            return None

    bench = json.loads((ROOT / "data" / "benchmark" / "benchmark_incidents.json").read_text(encoding="utf-8"))
    t0 = time.time()
    outs = [ask(b["description"]) for b in bench]
    return {
        "n": len(bench),
        "json_valid_rate": round(sum(o is not None for o in outs) / len(outs), 4),
        "category_accuracy": acc([((o or {}).get("category"), b["expected_category"]) for o, b in zip(outs, bench, strict=True)]),
        "severity_accuracy": acc([((o or {}).get("severity"), b["expected_severity"]) for o, b in zip(outs, bench, strict=True)]),
        "seconds": round(time.time() - t0, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-dir", help="LoRA adapter directory produced by train_lora.py")
    a = ap.parse_args()
    res: dict = {"rule_based_baseline": eval_rules()}
    res["fine_tuned_model"] = eval_model(a.model_dir) if a.model_dir else "not evaluated (no --model-dir; training is optional)"
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "evaluation.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
