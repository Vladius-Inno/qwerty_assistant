from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.models.auth_models import User
from app.llm.call_llm import call_llm
from app.llm.agent_2 import agent_loop, set_progress_callback
from app.services.articles import fetch_articles as svc_fetch_articles
from app.services.relations import get_related_articles_agent as svc_get_related
from app.services.search import combined_search_agent as svc_combined_search
from app.core.jobs import job_store
from app.schemas.agent import (
    AgentLoopRequest,
    CallLLMRequest,
    CombinedSearchRequest,
    FetchArticlesRequest,
    JobStatusResponse,
    RelatedArticlesRequest,
    StartJobResponse,
)


router = APIRouter(prefix="/api/agent", tags=["agent"])

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
from datetime import datetime, timezone


@router.post("/agent-loop/start", response_model=StartJobResponse)
async def api_agent_loop_start(
    payload: AgentLoopRequest,
    current_user: User = Depends(get_current_user),
) -> StartJobResponse:
    job_id = job_store.start(
        lambda: agent_loop(user_goal=payload.user_goal, max_turns=payload.max_turns),
        user_id=str(current_user.id),
        on_progress=None,
        bind_progress=set_progress_callback,
        on_finalize=lambda: set_progress_callback(None),
    )
    return StartJobResponse(job_id=job_id)


@router.get("/agent-loop/status/{job_id}", response_model=JobStatusResponse)
async def api_agent_loop_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> JobStatusResponse:
    rec = job_store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    # Optional: enforce ownership
    # if j.get("user_id") != str(current_user.id):
    #     raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job_id,
        status=rec.status or "unknown",
        started_at=rec.started_at,
        finished_at=rec.finished_at,
        result=rec.result,
        error=rec.error,
        message=rec.message,
    )
