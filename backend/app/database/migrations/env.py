"""Alembic environment: DATABASE_URL comes from the environment (never hard-coded)."""

from __future__ import annotations

from typing import Any

from alembic import context
from pgvector.sqlalchemy import Vector
from sqlalchemy import text

from app.config import get_settings
from app.database.models import Base
from app.database.session import make_engine

target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: Any) -> Any:
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.Vector({obj.dim})"
    return False


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True, render_item=render_item)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine()
    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, render_item=render_item, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
