from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pretrend.config import get_settings


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        database_url = settings.database_url_async
        if not database_url.startswith("postgresql+asyncpg://"):
            raise RuntimeError("database_url_async must use postgresql+asyncpg")
        _engine = create_async_engine(
            database_url,
            future=True,
            pool_pre_ping=True,
            connect_args={"timeout": 2},
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async_session = get_sessionmaker()
    async with async_session() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
