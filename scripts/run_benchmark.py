#!/usr/bin/env python
"""Execute the 50-incident benchmark and experiments A-D; writes data/processed/benchmark_results.json (real measurements)."""

from __future__ import annotations

import argparse
import json

from _common import settings

from app.ai.llm import get_llm
from app.database.session import get_session_factory
from app.evaluation.benchmark import run_benchmark
from app.mcp.client import MCPClient
from app.rag.embeddings import get_embedder


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--allow-degraded", action="store_true", help="run even if the MCP server is unreachable (tool evidence will be missing)"
    )
    a = ap.parse_args()
    mcp = MCPClient(settings=settings)
    if not mcp.health() and not a.allow_degraded:
        raise SystemExit(
            f"MCP server not reachable at {settings.mcp_server_url}; start it (`make dev` or `docker compose up mcp-server`) "
            "or pass --allow-degraded. Refusing to overwrite benchmark_results.json with tool-less numbers."
        )
    res = run_benchmark(get_session_factory(), settings, mcp, get_embedder(), get_llm(settings), limit=a.limit)
    cols = [
        "classification_accuracy",
        "precision_at_k",
        "recall_at_k",
        "sop_hit_rate",
        "tool_selection_f1",
        "root_cause_agreement",
        "evidence_coverage",
        "avg_time_s",
    ]
    print(f"{'exp':<4}" + "".join(f"{c[:14]:>16}" for c in cols))
    for e in res["experiments"]:
        print(f"{e['id']:<4}" + "".join(f"{('-' if e['metrics'].get(c) is None else e['metrics'][c]):>16}" for c in cols))
    print(json.dumps({k: res[k] for k in ("benchmark_size", "k", "embedding", "classifier")}))


if __name__ == "__main__":
    main()
