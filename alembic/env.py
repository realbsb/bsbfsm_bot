"""Alembic environment. Async-режим, читает DSN из настроек."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from workflow import models  # noqa: F401 — регистрирует все модели в Base.metadata
from workflow.config import get_settings
from workflow.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    settings = get_settings()
    return settings.db_dsn


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = _get_url()
    engine = create_async_engine(url, pool_pre_ping=True)
    # ВАЖНО: engine.begin() — открывает транзакцию и коммитит на выходе.
    # engine.connect() — autocommit, DDL в MariaDB откатывается, таблиц не появляется.
    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
