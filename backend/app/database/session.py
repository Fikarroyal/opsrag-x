"""Engine / session factory helpers. Sync SQLAlchemy 2 (FastAPI runs sync endpoints in a threadpool)."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database.models import Base


def make_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if url.startswith("sqlite"):
        kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
        in_memory = url in ("sqlite://", "sqlite:///:memory:")
        if in_memory:
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)
        if not in_memory:
            # file-based SQLite (local mode): allow concurrent reader + background investigation writer
            @event.listens_for(engine, "connect")
            def _sqlite_pragmas(dbapi_conn: Any, _: Any) -> None:
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@lru_cache
def get_engine() -> Engine:
    return make_engine()


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return make_session_factory(get_engine())


def ensure_vector_indexes(engine: Engine) -> None:
    """HNSW cosine indexes (PostgreSQL + pgvector only)."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for table in ("sop_chunks", "historical_incidents"):
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding_hnsw ON {table} USING hnsw (embedding vector_cosine_ops)"))


def init_db(engine: Engine) -> None:
    """Create all tables directly (tests / SQLite). Production uses Alembic migrations."""
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    _add_missing_user_columns(engine)
    ensure_vector_indexes(engine)


def _add_missing_user_columns(engine: Engine) -> None:
    """Existing local SQLite files created before authentication existed: add users.password_hash in place."""
    if engine.dialect.name != "sqlite":
        return
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    if "password_hash" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))


def get_db(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()
