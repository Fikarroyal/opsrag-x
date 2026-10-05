"""Shared bootstrap for CLI scripts: makes the backend package importable from the repo root or from the Docker image."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "backend", ROOT):
    if (candidate / "app" / "__init__.py").exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.config import get_settings  # noqa: E402
from app.database.session import get_session_factory  # noqa: E402

settings = get_settings()


def session():  # type: ignore[no-untyped-def]
    return get_session_factory()()
