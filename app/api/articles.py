# app/api/articles.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from app.services import articles as svc
from app.db.queries import combined_search
from app.models.schemas import ArticleFull, ArticleMeta, SimpleArticle
from datetime import date

router = APIRouter(prefix="/api/articles", tags=["articles"])

@router.get("/search", response_model=List[SimpleArticle],
            summary="Комбинированный поиск по статьям")
async def search_articles(
    q: str = Query(..., description="Поисковый запрос"),
    limit: int = 20
) -> List[dict]:
    results = await combined_search(q, limit=limit)
    return results

@router.get("/{article_id}", response_model=ArticleFull)
async def api_get_article(article_id: int):
    art = await svc.get_article(article_id)
    if not art:
        raise HTTPException(status_code=404, detail="Article not found")
    return art

@router.get("/", response_model=List[ArticleMeta], response_model_exclude_none=True)
async def api_list_articles(limit: int = 20, offset: int = 0,
                            topic_id: Optional[int] = None,
                            tag: Optional[str] = None,
                            date_from: Optional[date] = None,
                            date_to: Optional[date] = None,
                            q: Optional[str] = None):
    rows = await svc.list_articles(limit=limit, offset=offset, topic_id=topic_id,
                                   tag=tag, date_from=date_from, date_to=date_to, q=q)
    return rows

@router.get("/search/keywords")
async def api_search_keywords(
    keyword: Optional[List[str]] = Query(None, description="Повторяющийся параметр, например ?keyword=космос&keyword=галактика"),
    q: Optional[str] = Query(None, description="Альтернатива: список через запятую 'космос,галактика'"),
    mode: str = Query("any", regex="^(any|all)$"),
    partial: bool = Query(False),
    limit: int = Query(20, ge=1, le=200),
):
    # Нормализуем вход: либо keyword=... multiple, либо q csv
    if keyword:
        kws = keyword
    elif q:
        kws = [s.strip() for s in q.split(",") if s.strip()]
    else:
        return {"error": "no keywords provided", "result": []}

    results = await svc.search_by_keywords(kws, mode=mode, partial=partial, limit=limit)
    return {"query": kws, "mode": mode, "partial": partial, "count": len(results), "result": results}

# @router.post("/search/semantic", response_model=List[SimpleArticle])
# async def api_search_semantic(embedding: List[float], limit: int = 10):
#     """
#     Вход: embedding как список float (который обычно вычисляет OpenAI).
#     Возвращает ближайшие статьи.
#     """
#     rows = await svc.search_articles_semantic(embedding, limit=limit)
#     return rows


@router.get("/{article_id}/related", response_model=List[SimpleArticle])
async def api_related(article_id: int, method: str = "semantic", top_n: int = 10):
    rows = await svc.get_related_articles(article_id, method=method, top_n=top_n)
    return rows

@router.get("/topic/{topic_name}/timeline")
async def api_timeline(topic_name: str, granularity: str = "month"):
    data = await svc.get_topic_timeline(topic_name, granularity=granularity)
    return {"topic": topic_name, "timeline": data}

@router.get("/topic/{topic_name}/top")
async def api_top_by_topic(topic_name: str, limit: int = 10):
    rows = await svc.get_top_articles_by_topic(topic_name, limit=limit)
    return rows
