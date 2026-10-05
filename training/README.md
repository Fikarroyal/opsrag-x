# OpsRAG-X - optional LoRA fine-tuning

Fine-tuning is **optional**. The application never imports `torch`/`transformers`/`peft`; without a fine-tuned model it uses
an LLM classifier (Ollama, if running) or the deterministic rule-based classifier (`backend/app/ai/classifier.py`).

## Data (all synthetic, IT infrastructure only - no patient data)
| file (`training/datasets/`) | task | examples |
|---|---|---|
| `incident_classification.jsonl` | category / severity / scope / service | 260 |
| `severity_classification.jsonl` | severity given category + scope | 230 |
| `root_cause_classification.jsonl` | root-cause category from an evidence summary | 230 |
| `tool_selection.jsonl` | choose read-only MCP tools + reason | 230 |
| `response_format.jsonl` | structured JSON investigation response | 220 |

Format: `{"instruction": "...", "input": "...", "output": {...}}`. `generate_datasets.py` regenerates them deterministically from templates.
`prepare_dataset.py` validates the schema, rejects patient-related terms, de-duplicates and writes chat-format
`prepared/train.jsonl` / `val.jsonl` (90/10 split).

## Commands
```bash
python training/prepare_dataset.py                 # validate + split
pip install -r training/requirements.txt           # on a GPU machine
BASE_MODEL=Qwen/Qwen2.5-1.5B-Instruct EPOCHS=3 BATCH_SIZE=4 LEARNING_RATE=2e-4 MAX_SEQ_LENGTH=768 OUTPUT_DIR=training/output/lora-opsragx \
  python training/train_lora.py
python training/evaluate_model.py --model-dir training/output/lora-opsragx
```
Configuration (env or CLI flags): `BASE_MODEL`, `OUTPUT_DIR`, `BATCH_SIZE`, `EPOCHS`, `LEARNING_RATE`, `MAX_SEQ_LENGTH`.
If no CUDA GPU (or the dependencies) is present, `train_lora.py` explains what is needed and exits with code 0 - it never crashes the
workflow. `--allow-cpu` exists only for a smoke test with a tiny model, `--dry-run` only validates the environment.

## Evaluation
`evaluate_model.py` always reports the **rule-based baseline** on the held-out validation split and on the 50-incident benchmark
(`data/benchmark`), and additionally the LoRA model when `--model-dir` is given. Output: `training/results/evaluation.json`.

## Honest status
* `generate_datasets.py`, `prepare_dataset.py`, `evaluate_model.py` (baseline) and the guard paths of `train_lora.py` were executed and tested.
* **The LoRA training loop itself was NOT executed in the development sandbox** (no GPU, model downloads blocked). It uses stable
  `transformers.Trainer` + `peft` APIs (loss only on the assistant answer), but treat the first run on your GPU machine as the real test.
* The datasets and the benchmark are templated from the same vocabulary, so a fine-tuned model will look better here than on real tickets.
