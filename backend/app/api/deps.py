from __future__ import annotations

import uuid
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.ai.llm import BaseLLMProvider
from app.auth import SESSION_COOKIE, read_token
from app.config import Settings
from app.database.models import User
from app.investigation.orchestrator import InvestigationOrchestrator
from app.mcp.client import MCPClient


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_llm_dep(request: Request) -> BaseLLMProvider:
    return request.app.state.llm  # type: ignore[no-any-return]


def get_mcp_dep(request: Request) -> MCPClient:
    return request.app.state.mcp  # type: ignore[no-any-return]


def get_orchestrator(request: Request) -> InvestigationOrchestrator:
    st = request.app.state
    return InvestigationOrchestrator(st.session_factory, st.settings, st.mcp, st.llm, st.embedder)


def authenticate(request: Request, db: Session, settings: Settings) -> User:
    """Resolve the signed-in user from the session cookie or an `Authorization: Bearer` token, or raise 401."""
    token = request.cookies.get(SESSION_COOKIE)
    header = request.headers.get("authorization", "")
    if not token and header.lower().startswith("bearer "):
        token = header[7:].strip()
    uid = read_token(token, settings)
    try:
        user = db.get(User, uuid.UUID(uid)) if uid else None
    except ValueError:
        user = None
    if user is None:
        raise HTTPException(401, "Autentikasi diperlukan. Silakan masuk.")
    return user


def require_user(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep)) -> User | None:
    """Router-level guard. With AUTH_REQUIRED=false (isolated tests only) it is a no-op."""
    if not settings.auth_required:
        return None
    return authenticate(request, db, settings)
