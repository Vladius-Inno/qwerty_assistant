# app/models/schemas.py
from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import date
import json


# --- Базовые сокращённые данные об статье ---
# Используется для list-запросов, таймлайнов, выдачи последних статей и похожих
class SimpleArticle(BaseModel):
    id: int
    title: str
    date: date
    score: Optional[float] = None


# --- Метаданные статьи ---
# Используется для комбинированного поиска, поиска по ключевым словам, list с фильтрами
class ArticleMeta(BaseModel):
    id: int
    title: str
    date: date
    release_number: Optional[int]
    topic_name: Optional[str] = None
    keywords: List[str] = []
    tags: List[str] = []
    summary: Optional[str] = None
    score: Optional[float] = None

    class Config:
        orm_mode = True


# --- Полный формат статьи ---
# Используется для get article по id
class ArticleFull(ArticleMeta):
    body: str
    source_link: Optional[str]
    article_link: Optional[str] = None
    extra_links: Optional[Dict[str, Any]]

    @field_validator("extra_links", mode="before")
    def parse_json_fields(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v
