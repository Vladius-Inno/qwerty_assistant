from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CallLLMRequest(BaseModel):
    messages: List[Dict[str, str]]
    model: Optional[str] = Field(default=None, description="Override model name if needed")
    temperature: Optional[float] = 1.0
    max_completions_tokens: Optional[int] = Field(default=None, description="Max tokens for completion")


class FetchArticlesRequest(BaseModel):
    ids: List[int]


class RelatedArticlesRequest(BaseModel):
    article_id: int
    method: str = Field(default="semantic")
    top_n: int = Field(default=10, ge=1, le=200)


class CombinedSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=200)
    preselect: int = Field(default=200, ge=10, le=2000)
    alpha: float = Field(default=0.7, ge=0.0, le=1.0)


class AgentLoopRequest(BaseModel):
    user_goal: str
    max_turns: int = Field(default=3, ge=1, le=8)


class StartJobResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # queued | running | done | error
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[dict | str] = None
    error: Optional[str] = None
    message: Optional[str] = None

