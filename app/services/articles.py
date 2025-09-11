# app/services/articles.py
from typing import Optional, List, Any, Tuple
from app.db.pool import pool
from datetime import date
from app.models.schemas import ArticleFull
import json

# -----------------------
# НИЖЕ — функции чтения
# -----------------------

async def get_article(article_id: int) -> Optional[ArticleFull]:
    """
    Вернуть полную статью по id (ArticleFull) вместе с topic_name, keywords, tags, summary.
    Используем подзапросы, чтобы не делать GROUP BY и не потерять поля.
    """
    sql = """
    SELECT
      a.id,
      a.title,
      a.body,
      a.date,
      a.source_link,
      a.article_link,
      a.release_number,
      -- topic name через article_topics -> topic_dictionary
      (
        SELECT td.name
        FROM article_topics at
        JOIN topic_dictionary td ON td.id = at.topic_id
        WHERE at.article_id = a.id
        LIMIT 1
      ) AS topic_name,
      -- keywords as text[]
      COALESCE(
        (SELECT array_agg(k.keyword) FROM keywords k WHERE k.article_id = a.id),
        ARRAY[]::text[]
      ) AS keywords,
      -- tags as text[]
      COALESCE(
        (SELECT array_agg(t.name)
         FROM tags t
         JOIN article_tags at ON at.tag_id = t.id
         WHERE at.article_id = a.id),
        ARRAY[]::text[]
      ) AS tags,
      -- latest summary (if any)
      (SELECT s.summary FROM summaries s WHERE s.article_id = a.id ORDER BY s.id DESC LIMIT 1) AS summary,
      a.extra_links
    FROM articles a
    WHERE a.id = $1
    """
    p = pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(sql, article_id)
        if not row:
            return None

        # asyncpg Row -> dict
        article = dict(row)

        # keywords/tags: гарантируем список строк (asyncpg возвращает list или None)
        kws = article.get("keywords")
        if kws is None:
            article["keywords"] = []
        else:
            # если это already a list of bytes/str, convert to str
            article["keywords"] = [str(x) for x in kws]

        tgs = article.get("tags")
        if tgs is None:
            article["tags"] = []
        else:
            article["tags"] = [str(x) for x in tgs]

        # extra_links может быть dict (jsonb) или строка -> приводим к dict
        extra = article.get("extra_links")
        if isinstance(extra, str):
            try:
                article["extra_links"] = json.loads(extra)
            except Exception:
                article["extra_links"] = {}
        elif extra is None:
            article["extra_links"] = {}
        # если extra уже dict — оставляем как есть

        # summary может быть None; ArticleFull.summary (в наследуемой модели) — Optional
        # Вернём Pydantic-модель
        return ArticleFull(**article)

# async def get_article(article_id: int) -> Optional[dict]:
#     """
#     Вернуть полную статью по id (включая body и метаданные).
#     """
#     sql = """
#     SELECT id, title, body, date, source_link, article_link, raw_json, release_number, extra_links, created_at, topic_id
#     FROM articles
#     WHERE id = $1
#     """
#     p = pool()
#     async with p.acquire() as conn:
#         row = await conn.fetchrow(sql, article_id)
#         article = dict(row)
#         if isinstance(article.get("extra_links"), str):
#             try:
#                 article["extra_links"] = json.loads(article["extra_links"])
#             except json.JSONDecodeError:
#                 article["extra_links"] = {}
#         return article if article else None

# async def get_article_metadata(article_id: int) -> Optional[dict]:
#     """
#     Быстрая мета-информация (без тела).
#     """
#     sql = """
#     SELECT id, title, date, source_link, article_link, release_number, topic_id, extra_links
#     FROM articles
#     WHERE id = $1
#     """
#     p = pool()
#     async with p.acquire() as conn:
#         row = await conn.fetchrow(sql, article_id)
#         return dict(row) if row else None


async def list_articles(limit: int = 20, offset: int = 0,
                        topic_id: Optional[int] = None,
                        tag: Optional[str] = None,
                        date_from: Optional[date] = None,
                        date_to: Optional[date] = None,
                        q: Optional[str] = None,
                        order_by: str = "date") -> List[dict]:
    """
    Удобная выборка со фильтрами.
    - tag: название тега (string)
    - q: текстовый поиск по заголовку или body (ILIKE)
    """
    where = []
    args: List[Any] = []
    idx = 1

    if topic_id is not None:
        where.append(f"a.topic_id = ${idx}"); args.append(topic_id); idx += 1

    if tag:
        where.append(f"t.name = ${idx}"); args.append(tag); idx += 1

    if date_from:
        where.append(f"a.date >= ${idx}"); args.append(date_from); idx += 1

    if date_to:
        where.append(f"a.date <= ${idx}"); args.append(date_to); idx += 1

    if q:
        where.append(f"(a.title ILIKE ${idx} OR a.body ILIKE ${idx})"); args.append(f"%{q}%"); idx += 1

    where_sql = " AND ".join(where)
    if where_sql:
        where_sql = "WHERE " + where_sql

    # join только если нужен тег
    join_sql = ""
    if tag:
        join_sql = "JOIN article_tags at ON at.article_id = a.id JOIN tags t ON t.id = at.tag_id"

    sql = f"""
    SELECT a.id, a.title, a.date, a.source_link, a.article_link, a.release_number, a.topic_id
    FROM articles a
    {join_sql}
    {where_sql}
    ORDER BY a.{order_by} DESC
    LIMIT ${idx} OFFSET ${idx+1}
    """
    args.extend([limit, offset])

    p = pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]


# async def get_articles_by_period(start_date: str, end_date: str) -> List[dict]:
#     sql = """
#     SELECT id, title, date
#     FROM articles
#     WHERE date BETWEEN $1 AND $2
#     ORDER BY date
#     """
#     p = pool()
#     async with p.acquire() as conn:
#         rows = await conn.fetch(sql, start_date, end_date)
#         return [dict(r) for r in rows]


# ---------- Семантический поиск (требует эмбеддинг запроса) ----------
def _vec_to_pg_literal(vec: List[float]) -> str:
    # Преобразует Python list в Postgres vector literal: '[0.1,0.2,...]'
    return "[" + ",".join(map(str, vec)) + "]"

# ---------- Связанные статьи ----------
async def get_related_articles(article_id: int, method: str = "semantic", top_n:int = 10) -> List[dict]:
    """
    Если method == semantic: берём embedding этой статьи и ищем ближайшие (кроме самой).
    Если method == keywords: ищем по общим keywords/tags.
    """
    p = pool()
    async with p.acquire() as conn:
        if method == "semantic":
            emb_row = await conn.fetchrow("SELECT embedding FROM article_embeddings WHERE article_id = $1", article_id)
            if not emb_row:
                return []
            emb = emb_row["embedding"]
            # emb может приходить как список или как строка; приводим к строковому literal
            if isinstance(emb, list):
                v_lit = _vec_to_pg_literal(emb)
            else:
                v_lit = str(emb)
            sql = """
            SELECT a.id, a.title, a.date
            FROM article_embeddings e
            JOIN articles a ON a.id = e.article_id
            WHERE e.article_id <> $2
            ORDER BY e.embedding <-> $1::vector
            LIMIT $3
            """
            rows = await conn.fetch(sql, v_lit, article_id, top_n)
            return [dict(r) for r in rows]

        else:
            # keywords/tags based:
            sql = """
            SELECT a.id, a.title, a.date, COUNT(*) as score
            FROM keywords k
            JOIN articles a ON a.id = k.article_id
            WHERE k.keyword IN (
                SELECT keyword FROM keywords WHERE article_id = $1
            ) AND a.id <> $1
            GROUP BY a.id, a.title
            ORDER BY score DESC
            LIMIT $2
            """
            rows = await conn.fetch(sql, article_id, top_n)
            return [dict(r) for r in rows]


# ---------- ТАЙМЛАЙН по теме ----------
async def get_topic_timeline(topic_name: str, granularity: str = "month") -> List[Tuple[str,int]]:
    """
    Возвращает список (period, count). granularity = 'month' or 'year'
    """
    if granularity not in ("month", "year"):
        granularity = "month"
    trunc = "month" if granularity == "month" else "year"
    sql = f"""
    SELECT date_trunc('{trunc}', a.date)::date AS period, COUNT(*) as cnt
    FROM articles a
    LEFT JOIN article_topics at ON at.article_id = a.id
    LEFT JOIN topic_dictionary td ON td.id = at.topic_id
    WHERE (td.name ILIKE $1 OR a.topic_id = (SELECT id FROM topic_dictionary WHERE name ILIKE $1 LIMIT 1))
    GROUP BY period
    ORDER BY period
    """
    p = pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(sql, topic_name)
        return [(r["period"].isoformat(), r["cnt"]) for r in rows]


# ---------- ТОП статей по теме ----------
async def get_top_articles_by_topic(topic_name: str, limit: int = 10) -> List[dict]:
    sql = """
    SELECT a.id, a.title, a.date
    FROM articles a
    LEFT JOIN article_topics at ON at.article_id = a.id
    LEFT JOIN topic_dictionary td ON td.id = at.topic_id
    WHERE td.name ILIKE $1 OR a.topic_id = (SELECT id FROM topic_dictionary WHERE name ILIKE $1 LIMIT 1)
    ORDER BY a.date DESC
    LIMIT $2
    """
    p = pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(sql, topic_name, limit)
        return [dict(r) for r in rows]
