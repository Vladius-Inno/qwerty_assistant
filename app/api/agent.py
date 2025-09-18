from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.models.auth_models import User
from app.llm.call_llm import call_llm
from app.llm.agent_2 import agent_loop
from app.services.articles import fetch_articles as svc_fetch_articles
from app.services.relations import get_related_articles_agent as svc_get_related
from app.services.search import combined_search_agent as svc_combined_search


router = APIRouter(prefix="/api/agent", tags=["agent"])


# -------- Schemas --------

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


# -------- Endpoints (protected) --------


@router.post("/call-llm")
async def api_call_llm(
    payload: CallLLMRequest,
    current_user: User = Depends(get_current_user),
):
    result = await call_llm(
        messages=payload.messages,
        model=payload.model or "gpt-4o-mini",
        temperature=payload.temperature,
        max_completions_tokens=payload.max_completions_tokens,
    )
    return {"result": result}


@router.post("/fetch-articles")
async def api_fetch_articles(
    payload: FetchArticlesRequest,
    current_user: User = Depends(get_current_user),
):
    result = await svc_fetch_articles(payload.ids)
    return {"result": result}


@router.post("/get-related-articles")
async def api_get_related_articles(
    payload: RelatedArticlesRequest,
    current_user: User = Depends(get_current_user),
):
    result = await svc_get_related(
        article_id=payload.article_id, method=payload.method, top_n=payload.top_n
    )
    return {"result": result}


@router.post("/combined-search")
async def api_combined_search(
    payload: CombinedSearchRequest,
    current_user: User = Depends(get_current_user),
):
    result = await svc_combined_search(
        query=payload.query,
        limit=payload.limit,
        preselect=payload.preselect,
        alpha=payload.alpha,
    )
    return {"result": result}


@router.post("/agent-loop")
async def api_agent_loop(
    payload: AgentLoopRequest,
    current_user: User = Depends(get_current_user),
):
    result = await agent_loop(user_goal=payload.user_goal, max_turns=payload.max_turns)
    return {"result": result}

