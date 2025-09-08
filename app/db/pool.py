# app/db/pool.py
import asyncpg
from typing import Optional
from app.config import DB_DSN

_pool: Optional[asyncpg.pool.Pool] = None

async def connect_db():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=DB_DSN, min_size=1, max_size=10)
        # Если у тебя установлен пакет pgvector с адаптером asyncpg, можно зарегистрировать:
        try:
            from pgvector.asyncpg import register_vector  # возможно такой импорт доступен
            await register_vector(_pool)  # если API позволяет
            # pass
        except Exception:
            # не критично — оставим, если pgvector не подключён
            pass

async def close_db():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

def pool():
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call connect_db() first.")
    return _pool
