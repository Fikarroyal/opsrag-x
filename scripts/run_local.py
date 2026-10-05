#!/usr/bin/env python
"""One-command local run (no Docker, no PostgreSQL, no Node needed if frontend/dist exists).

    python scripts/run_local.py              # SQLite + synthetic data + MCP server + backend + web UI on http://localhost:8000
    python scripts/run_local.py --reset      # delete the local database and start from scratch
    python scripts/run_local.py --llm        # also use Ollama (OLLAMA_BASE_URL / OLLAMA_MODEL) when it is running

Everything uses the synthetic demo hospital (no patient data). Stop with Ctrl+C.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(msg: str) -> None:
    print(f"\n[ERROR] {msg}\n", file=sys.stderr)
    raise SystemExit(1)


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def wait_http(url: str, timeout: float = 60.0) -> bool:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.7)
    return False


def ensure_frontend() -> bool:
    dist = ROOT / "frontend" / "dist" / "index.html"
    if dist.is_file():
        return True
    npm = shutil.which("npm")
    if not npm:
        print("[warn] frontend/dist not found and npm is not installed: the web UI is unavailable (API docs still work at /docs).")
        return False
    print("[setup] building the frontend (first run only, needs internet for npm)...", flush=True)
    fe = ROOT / "frontend"
    for cmd in ([npm, "install", "--no-audit", "--no-fund"], [npm, "run", "build"]):
        if subprocess.run(cmd, cwd=fe).returncode != 0:
            print("[warn] frontend build failed: the web UI is unavailable (API docs still work at /docs).")
            return False
    return dist.is_file()


def dataset_fingerprint() -> str:
    h = hashlib.sha256()
    for sub in ("raw", "docs", "sop"):
        for f in sorted((ROOT / "data" / sub).glob("*")):
            if f.is_file():
                h.update(f.name.encode())
                h.update(f.read_bytes())
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to expose on your network")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--mcp-port", type=int, default=8001)
    ap.add_argument("--db-url", default=None, help="override the database URL (default: SQLite file data/opsragx.db)")
    ap.add_argument("--reset", action="store_true", help="delete the local SQLite database first")
    ap.add_argument("--llm", action="store_true", help="enable the Ollama LLM provider (default: rule-based fallback)")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    if sys.version_info < (3, 10):  # noqa: UP036
        fail(f"Python 3.10+ is required (found {sys.version.split()[0]}). Install a newer Python and recreate the venv.")
    missing = []
    for mod in (
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pydantic_settings",
        "pandas",
        "sklearn",
        "pymupdf",
        "reportlab",
        "mcp",
        "pgvector",
        "httpx",
    ):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        fail(f"Missing Python packages: {', '.join(missing)}.\nRun:  pip install -r backend/requirements.txt")
    for port, name in ((a.port, "backend"), (a.mcp_port, "MCP server")):
        if not port_free(port):
            fail(f"Port {port} ({name}) is already in use. Stop the other process or pick another with --port / --mcp-port.")

    db_file = ROOT / "data" / "opsragx.db"
    if a.reset:
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_file) + suffix).unlink(missing_ok=True)
    if not a.db_url and db_file.exists():
        # a new release may ship regenerated data (e.g. renamed hospital): rebuild the local database instead of showing stale rows
        stamp = Path(str(db_file) + ".dataset")
        if not stamp.exists() or stamp.read_text().strip() != dataset_fingerprint():
            print("[setup] bundled data changed since this database was created: rebuilding it", flush=True)
            for suffix in ("", "-wal", "-shm"):
                Path(str(db_file) + suffix).unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": a.db_url or f"sqlite:///{db_file.as_posix()}",
            "MCP_SERVER_URL": f"http://127.0.0.1:{a.mcp_port}",
            "MCP_PORT": str(a.mcp_port),
            "MCP_HOST": "127.0.0.1",
            "DATA_DIR": str(ROOT / "data"),
            "DEMO_MODE": "true",
            "CORS_ORIGINS": "*",
            "PYTHONUNBUFFERED": "1",
        }
    )
    env.setdefault("EMBEDDING_BACKEND", "hashing")
    if not a.llm:
        env["LLM_ENABLED"] = "false"
    ui = ensure_frontend()

    print(f"[1/3] preparing database + synthetic data ({env['DATABASE_URL'].split('@')[-1]})", flush=True)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "bootstrap.py"), "--if-empty"], env=env, cwd=ROOT)
    if r.returncode != 0:
        fail("Database bootstrap failed (see output above).")

    if not a.db_url:
        Path(str(db_file) + ".dataset").write_text(dataset_fingerprint())
    procs: list[subprocess.Popen[bytes]] = []
    try:
        print(f"[2/3] starting MCP server (read-only tools) on :{a.mcp_port}", flush=True)
        procs.append(subprocess.Popen([sys.executable, "server.py"], cwd=ROOT / "mcp-server", env=env))
        if not wait_http(f"http://127.0.0.1:{a.mcp_port}/health", 40):
            fail("MCP server did not start (see output above).")
        print(f"[3/3] starting backend on {a.host}:{a.port}", flush=True)
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", a.host, "--port", str(a.port)], cwd=ROOT / "backend", env=env
            )
        )
        shown = "localhost" if a.host in ("127.0.0.1", "0.0.0.0") else a.host
        base = f"http://{shown}:{a.port}"
        if not wait_http(f"http://127.0.0.1:{a.port}/api/health", 60):
            fail("Backend did not start (see output above).")
        print("\n" + "=" * 62)
        print("  OpsRAG-X is running")
        print(f"  Web UI   : {base}/" + ("" if ui else "   (not built)"))
        print(f"  API docs : {base}/docs")
        print("  Try      : open Incidents -> INC-2026-001 -> Run investigation")
        print("  Stop     : Ctrl+C")
        print("=" * 62 + "\n", flush=True)
        if ui and not a.no_browser:
            webbrowser.open(base + "/")
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("a process exited; shutting down")
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
