from fastapi import FastAPI
from app.db.pool import connect_db, close_db
from app.api import articles
from contextlib import asynccontextmanager

import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Подключаемся к базе
    await connect_db()
    yield
    # Закрываем соединение
    await close_db()


app = FastAPI(lifespan=lifespan)
app.include_router(articles.router)



