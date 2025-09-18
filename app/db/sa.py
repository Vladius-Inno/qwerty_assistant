from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import DB_DSN


_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def _to_sqlalchemy_async_dsn(dsn: str | None) -> str:
    if not dsn:
        raise RuntimeError("DATABASE_URL is not configured")
    # Ensure SQLAlchemy asyncpg dialect
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    if dsn.startswith("postgres://"):
        return dsn.replace("postgres://", "postgresql+asyncpg://", 1)
    # Fallback: assume already usable
    return dsn


async def init_sa_engine() -> None:
    global _engine, _sessionmaker
    if _engine is None:
        async_dsn = _to_sqlalchemy_async_dsn(DB_DSN)
        _engine = create_async_engine(async_dsn, pool_pre_ping=True, future=True)
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )


async def close_sa_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    if _sessionmaker is None:
        raise RuntimeError("SQLAlchemy engine is not initialized. Call init_sa_engine() first.")
    session = _sessionmaker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _sessionmaker is None:
        raise RuntimeError("SQLAlchemy engine is not initialized. Call init_sa_engine() first.")
    session = _sessionmaker()
    try:
        yield session
    finally:
        await session.close()
