from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
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


# ---------------- Background jobs for long agent loops ----------------

import asyncio
import uuid
from datetime import datetime, timezone

_JOBS: dict[str, dict] = {}


class StartJobResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # queued | running | done | error
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[dict | str] = None
    error: Optional[str] = None


@router.post("/agent-loop/start", response_model=StartJobResponse)
async def api_agent_loop_start(
    payload: AgentLoopRequest,
    current_user: User = Depends(get_current_user),
) -> StartJobResponse:
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = {
        "status": "queued",
        "result": None,
        "error": None,
        "started_at": None,
        "finished_at": None,
        "user_id": str(current_user.id),
    }

    async def _runner():
        j = _JOBS.get(job_id)
        if j is None:
            return
        j["status"] = "running"
        j["started_at"] = datetime.now(timezone.utc)
        try:
            res = await agent_loop(user_goal=payload.user_goal, max_turns=payload.max_turns)
            j["result"] = res
            j["status"] = "done"
        except Exception as e:
            j["error"] = str(e)
            j["status"] = "error"
        finally:
            j["finished_at"] = datetime.now(timezone.utc)

    asyncio.create_task(_runner())
    return StartJobResponse(job_id=job_id)


@router.get("/agent-loop/status/{job_id}", response_model=JobStatusResponse)
async def api_agent_loop_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> JobStatusResponse:
    j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    # Optional: enforce ownership
    # if j.get("user_id") != str(current_user.id):
    #     raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job_id,
        status=j.get("status", "unknown"),
        started_at=j.get("started_at"),
        finished_at=j.get("finished_at"),
        result=j.get("result"),
        error=j.get("error"),
    )
