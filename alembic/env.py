from __future__ import annotations

from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import BASE_DIR
from app.services.conversation_store import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def conversation_database_url() -> str:
    explicit_url = os.getenv("CONVERSATION_DATABASE_URL")
    if explicit_url:
        return explicit_url
    db_path = os.getenv("CONVERSATION_DB_PATH", str(BASE_DIR / "data" / "conversations.db"))
    if db_path == ":memory:":
        return "sqlite:///:memory:"
    return f"sqlite:///{Path(db_path).as_posix()}"


def run_migrations_offline() -> None:
    url = conversation_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config_section = config.get_section(config.config_ini_section, {})
    config_section["sqlalchemy.url"] = conversation_database_url()
    connectable = engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
