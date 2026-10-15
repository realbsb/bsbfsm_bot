"""Инициализация SQLAlchemy async-движка и сессий."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import Settings


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def init(self) -> None:
        self._engine = create_async_engine(
            self._settings.db_dsn,
            pool_size=self._settings.db_pool_size,
            max_overflow=self._settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            echo=False,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    @property
    def engine(self) -> AsyncEngine:
        assert self._engine, "Database.init() not called"
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        assert self._session_factory, "Database.init() not called"
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        if self._engine:
            await self._engine.dispose()
