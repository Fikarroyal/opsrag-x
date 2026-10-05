#!/usr/bin/env python
"""Optional LoRA fine-tuning (Hugging Face Transformers + PEFT). NOT required to run the application.

Environment / CLI configuration: BASE_MODEL, OUTPUT_DIR, BATCH_SIZE, EPOCHS, LEARNING_RATE, MAX_SEQ_LENGTH.
Without a CUDA GPU the script explains what is needed and exits cleanly (exit code 0) instead of crashing;
use --allow-cpu only for a smoke test with a tiny model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def parse() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-model", default=env("BASE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"))
    ap.add_argument("--output-dir", default=env("OUTPUT_DIR", str(HERE / "output" / "lora-opsragx")))
    ap.add_argument("--batch-size", type=int, default=int(env("BATCH_SIZE", "4")))
    ap.add_argument("--epochs", type=float, default=float(env("EPOCHS", "3")))
    ap.add_argument("--learning-rate", type=float, default=float(env("LEARNING_RATE", "2e-4")))
    ap.add_argument("--max-seq-length", type=int, default=int(env("MAX_SEQ_LENGTH", "768")))
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--allow-cpu", action="store_true", help="run without a GPU (very slow; smoke test only)")
    ap.add_argument("--dry-run", action="store_true", help="validate data/config/environment and exit")
    return ap.parse_args()


def check_environment(allow_cpu: bool) -> str | None:
    """Return None when training can proceed, otherwise a human-readable reason."""
    try:
        import peft  # noqa: F401
        import torch
        import transformers  # noqa: F401
    except ImportError as exc:
        return f"missing training dependency ({exc.name}). Install with: pip install -r training/requirements.txt"
    if not torch.cuda.is_available() and not allow_cpu:
        return (
            "no CUDA GPU detected. LoRA training should run on a machine with a suitable GPU (>= 8 GB VRAM for a 0.5B-1.5B model). "
            "The application itself does not need this model: it falls back to the rule-based classifier. Use --allow-cpu for a smoke test."
        )
    return None


def main() -> int:
    a = parse()
    train_file = HERE / "prepared" / "train.jsonl"
    if not train_file.exists():
        print("prepared data not found - run: python training/prepare_dataset.py", file=sys.stderr)
        return 1
    n = sum(1 for _ in train_file.open(encoding="utf-8"))
    cfg = {k: getattr(a, k) for k in ("base_model", "output_dir", "batch_size", "epochs", "learning_rate", "max_seq_length", "lora_r")}
    print("config:", json.dumps(cfg), f"| train examples: {n}")
    reason = check_environment(a.allow_cpu)
    if reason:
        print(f"[train_lora] cannot train in this environment: {reason}")
        return 0
    if a.dry_run:
        print("[train_lora] dry run OK: dependencies and device available.")
        return 0

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq, Trainer, TrainingArguments

    tok = AutoTokenizer.from_pretrained(a.base_model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    dtype = (
        torch.bfloat16
        if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        else (torch.float16 if torch.cuda.is_available() else torch.float32)
    )
    model = AutoModelForCausalLM.from_pretrained(a.base_model, torch_dtype=dtype)
    model = get_peft_model(
        model, LoraConfig(r=a.lora_r, lora_alpha=2 * a.lora_r, lora_dropout=0.05, task_type="CAUSAL_LM", target_modules="all-linear")
    )
    model.print_trainable_parameters()

    def encode(row: dict) -> dict:
        msgs = row["messages"]
        prompt = tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True)
        answer = msgs[-1]["content"] + (tok.eos_token or "")
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        a_ids = tok(answer, add_special_tokens=False)["input_ids"]
        ids = (p_ids + a_ids)[: a.max_seq_length]
        labels = ([-100] * len(p_ids) + a_ids)[: a.max_seq_length]  # loss only on the assistant answer
        return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": labels}

    rows = [encode(json.loads(line)) for line in train_file.open(encoding="utf-8")]

    class DS(torch.utils.data.Dataset):  # type: ignore[type-arg]
        def __len__(self) -> int:
            return len(rows)

        def __getitem__(self, i: int) -> dict:
            return rows[i]

    args = TrainingArguments(
        output_dir=a.output_dir,
        per_device_train_batch_size=a.batch_size,
        num_train_epochs=a.epochs,
        learning_rate=a.learning_rate,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        report_to=[],
        bf16=dtype == torch.bfloat16,
        fp16=dtype == torch.float16,
        remove_unused_columns=False,
        gradient_accumulation_steps=max(1, 16 // a.batch_size),
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        seed=42,
    )
    Trainer(
        model=model, args=args, train_dataset=DS(), data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100)
    ).train()
    model.save_pretrained(a.output_dir)
    tok.save_pretrained(a.output_dir)
    (Path(a.output_dir) / "opsragx_training_config.json").write_text(json.dumps(cfg, indent=2))
    print(f"[train_lora] LoRA adapter saved to {a.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
