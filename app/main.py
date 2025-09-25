from contextlib import asynccontextmanager

import logging
import os

from fastapi import FastAPI

from app.api import articles
from app.api import agent as agent_api
from app.api import auth as auth_api
from app.db.pool import close_db, connect_db
from app.db.sa import close_sa_engine, init_sa_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize asyncpg (existing services) and SQLAlchemy (auth)
    await connect_db()
    await init_sa_engine()
    # Create tables for auth models if needed (idempotent)
    try:
        from app.db.base import Base
        from app.models import auth_models  # noqa: F401 ensure model registration
        from app.models import chat_models  # noqa: F401 ensure model registration
        from app.db.sa import _engine as _sa_engine  # type: ignore

        if _sa_engine is not None:
            async with _sa_engine.begin() as conn:  # type: ignore
                await conn.run_sync(Base.metadata.create_all)
    except Exception:
        # If migrations are managed externally, ignore table creation errors
        pass
    try:
        yield
    finally:
        await close_sa_engine()
        await close_db()


app = FastAPI(
    lifespan=lifespan,
    root_path=os.getenv("ROOT_PATH", "")
)
app.include_router(articles.router)
app.include_router(auth_api.router)
app.include_router(agent_api.router)
from app.api import chats as chats_api  # noqa: E402
app.include_router(chats_api.router)

# Basic logging configuration (can be overridden by server config)
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=_LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Suppress noisy bcrypt version warning from passlib when using bcrypt>=4
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)
