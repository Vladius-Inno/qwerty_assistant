# app/api/articles.py
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import asyncio
from app.services import articles as svc
from app.services import search as srch
from app.models.schemas import ArticleFull, ArticleMeta, SimpleArticle
from datetime import date

router = APIRouter(prefix="/api/articles", tags=["articles"])

# -----------------------
#  Поисковые и утилитарные
# -----------------------

@router.get("/search", response_model=List[SimpleArticle],
            summary="Комбинированный семантико-текстовый поиск (stub)")
async def search_articles(
    q: str = Query(..., description="Поисковый запрос"),
    limit: int = Query(20, ge=1, le=200)
) -> List[dict]:
    """
    Быстрый поиск — возвращает сокращённый формат (id, title, date).
    Для получения расширённых метаданных используйте /search/meta.
    """
    results = await srch.combined_search(q, limit=limit)
    # combined_search должен возвращать список dict с ключами id,title,date (и опционально score)
    return results

@router.get("/search/meta", response_model=List[ArticleMeta],
            summary="Комбинированный поиск — вернуть расширенные метаданные (ArticleMeta)")
async def search_articles_meta(q: str = Query(..., description="Поисковый запрос"),
                               limit: int = 20) -> list[ArticleMeta]:
    """
    Поиск + для каждого найденного id подтягиваем расширенные метаданные.
    ВНИМАНИЕ: сейчас реализовано через параллельные вызовы svc.get_article (N запросов).
    Позже заменим на один батч-SQL (рекомендуется).
    """
    ids = await srch.combined_search(q, limit=limit)

    # параллельно подтягиваем полные записи (svc.get_article возвращает dict/row)
    async def _get_meta(article_id: int) -> ArticleMeta | None:
        row: ArticleFull | None = await svc.get_article(article_id)
        if not row:
            return None
        # ArticleMeta поля: id, title, date, release_number, topic_name, keywords, tags, summary
        # svc.get_article может не возвращать topic_name/keywords/tags/summary — тогда Pydantic подставит defaults.
        return ArticleMeta(
            id=row.id,
            title=row.title,
            date=row.date,
            release_number=row.release_number,
            topic_name=row.topic_name,
            keywords=row.keywords,
            tags=row.tags,
            summary=row.summary,
        )

    metas = await asyncio.gather(*[_get_meta(i["id"]) for i in ids])
    # фильтруем None на всякий случай
    metas = [m for m in metas if m is not None]
    return [m for m in metas if m]

@router.get("/search/keywords", summary="Поиск по ключевым словам (keywords table)")
async def api_search_keywords(
    keyword: Optional[List[str]] = Query(None,
                                         description="Повторяющийся параметр, например "
                                                     "?keyword=космос&keyword=галактика"),
    q: Optional[str] = Query(None,
                             description="Альтернатива: список через запятую 'космос,галактика'"),
    mode: str = Query("any", regex="^(any|all)$"),
    partial: bool = Query(False),
    limit: int = Query(20, ge=1, le=200),
):
    """
    Поиск по таблице keywords. Возвращает обёртку с мета-инфой и массивом найденных статей (stub).
    """
    if keyword:
        kws = keyword
    elif q:
        kws = [s.strip() for s in q.split(",") if s.strip()]
    else:
        return {"error": "no keywords provided", "result": []}

    results = await srch.search_by_keywords(kws, mode=mode, partial=partial, limit=limit)
    return {"query": kws, "mode": mode, "partial": partial, "count": len(results), "result": results}


# -----------------------
#  Топики / таймлайны / агрегации
# -----------------------

@router.get("/topic/{topic_name}/timeline", summary="Таймлайн: количество статей по теме")
async def api_timeline(topic_name: str, granularity: str = "month"):
    data = await svc.get_topic_timeline(topic_name, granularity=granularity)
    return {"topic": topic_name, "timeline": data}

@router.get("/topic/{topic_name}/top", summary="Топ статей по теме (stub)", response_model=List[SimpleArticle])
async def api_top_by_topic(topic_name: str, limit: int = 10):
    rows = await svc.get_top_articles_by_topic(topic_name, limit=limit)
    return rows

# -----------------------
#  Списки (meta)
# -----------------------

@router.get("/", response_model=List[ArticleMeta], response_model_exclude_none=True,
            summary="Список статей (расширённый формат — ArticleMeta)")
async def api_list_articles(limit: int = 20, offset: int = 0,
                            topic_id: Optional[int] = None,
                            tag: Optional[str] = None,
                            date_from: Optional[date] = None,
                            date_to: Optional[date] = None,
                            q: Optional[str] = None):
    """
    Возвращает ArticleMeta (без body). Подходит для аналитики и для LLM, когда нужен контекст.
    """
    rows = await svc.list_articles(limit=limit, offset=offset, topic_id=topic_id,
                                   tag=tag, date_from=date_from, date_to=date_to, q=q)
    return rows

# -----------------------
#  Связанные и одиночные статьи — эти маршруты должны идти ПОСЛЕ статических путей
# -----------------------

@router.get("/{article_id}/related", response_model=List[SimpleArticle],
            summary="Похожие/связанные статьи (stub)")
async def api_related(article_id: int, method: str = "semantic", top_n: int = 10):
    rows = await svc.get_related_articles(article_id, method=method, top_n=top_n)
    return rows

@router.get("/{article_id}", response_model=ArticleFull,
            summary="Полная статья по id (ArticleFull)")
async def api_get_article(article_id: int):
    art = await svc.get_article(article_id)
    if not art:
        raise HTTPException(status_code=404, detail="Article not found")
    return art

