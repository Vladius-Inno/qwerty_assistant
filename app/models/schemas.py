# app/models/schemas.py
from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import date
import json

class ArticleMeta(BaseModel):
    id: int
    title: str
    date: date
    source_link: Optional[str]
    article_link: Optional[str] = None
    release_number: Optional[int]
    topic_id: Optional[int]

    class Config:
        orm_mode = True


class ArticleFull(ArticleMeta):
    body: str
    extra_links: Optional[Dict[str, Any]]  # <-- важно
    raw_json: Optional[dict]

    @field_validator("raw_json", "extra_links", mode="before")
    def parse_json_fields(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v

class SimpleArticle(BaseModel):
    id: int
    title: str
    date: date

