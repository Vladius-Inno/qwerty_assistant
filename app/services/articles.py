# app/services/articles.py
from typing import Optional, List, Dict, Any, Tuple
from app.db.pool import pool
import asyncio
from datetime import date
import json

# -----------------------
# НИЖЕ — функции чтения
# -----------------------

async def get_article(article_id: int) -> Optional[dict]:
    """
    Вернуть полную статью по id (включая body и метаданные).
    """
    sql = """
    SELECT id, title, body, date, source_link, article_link, raw_json, release_number, extra_links, created_at, topic_id
    FROM articles
    WHERE id = $1
    """
    p = pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(sql, article_id)
        article = dict(row)
        if isinstance(article.get("extra_links"), str):
            try:
                article["extra_links"] = json.loads(article["extra_links"])
            except json.JSONDecodeError:
                article["extra_links"] = {}
        return article if article else None


async def get_article_metadata(article_id: int) -> Optional[dict]:
    """
    Быстрая мета-информация (без тела).
    """
    sql = """
    SELECT id, title, date, source_link, article_link, release_number, topic_id, extra_links
    FROM articles
    WHERE id = $1
    """
    p = pool()
    async with p.acquire() as conn:
        row = await conn.fetchrow(sql, article_id)
        return dict(row) if row else None


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


async def get_articles_by_period(start_date: str, end_date: str) -> List[dict]:
    sql = """
    SELECT id, title, date
    FROM articles
    WHERE date BETWEEN $1 AND $2
    ORDER BY date
    """
    p = pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(sql, start_date, end_date)
        return [dict(r) for r in rows]


# ---------- Поиск по ключевым словам ----------
async def search_by_keywords(
    keywords: List[str],
    mode: str = "any",        # "any" или "all"
    partial: bool = False,    # False = exact (case-insensitive), True = substring (ILIKE)
    limit: int = 20,
) -> List[Dict]:
    """
    Search articles by keywords table.
    - keywords: список слов (например ["космос","галактика"])
    - mode: "any" или "all"
    - partial: если True — ищем как ILIKE '%kw%', иначе точное сравнение по lower()
    """

# Поведение и точности
# partial=False + mode=any — быстро и строго (совпадение по слову, но без учёта регистра).
# partial=True — медленнее, но гибче; лучше использовать вместе с pg_trgm.
# mode=all — полезно, когда хочешь статьи, которые упоминают все термины.

    if not keywords:
        return []

    # Нормализация: убираем пустые, тримим
    kws = [k.strip() for k in keywords if k and k.strip()]
    if not kws:
        return []

    p = pool()
    async with p.acquire() as conn:
        if not partial:
            # exact (case-insensitive) — используем lower(keyword) = ANY(...)
            kws_lower = [k.lower() for k in kws]

            if mode == "any":
                sql = """
                SELECT DISTINCT a.id, a.title, a.date
                FROM articles a
                JOIN keywords k ON k.article_id = a.id
                WHERE lower(k.keyword) = ANY($1::text[])
                ORDER BY a.date DESC
                LIMIT $2;
                """
                rows = await conn.fetch(sql, kws_lower, limit)
                return [dict(r) for r in rows]

            else:  # mode == "all"
                # нам нужно чтобы для статьи был найден весь набор слов
                needed = len(set(kws_lower))
                sql = """
                SELECT a.id, a.title, a.date
                FROM articles a
                JOIN keywords k ON k.article_id = a.id
                WHERE lower(k.keyword) = ANY($1::text[])
                GROUP BY a.id, a.title, a.date
                HAVING COUNT(DISTINCT lower(k.keyword)) >= $2
                ORDER BY a.date DESC
                LIMIT $3;
                """
                rows = await conn.fetch(sql, kws_lower, needed, limit)
                return [dict(r) for r in rows]

        else:
            # partial = True -> ищем по паттернам '%kw%'
            patterns = [f"%{k}%" for k in kws]

            if mode == "any":
                # EXISTS + unnest позволяет пользоваться массивом шаблонов
                sql = """
                SELECT DISTINCT a.id, a.title, a.date
                FROM articles a
                JOIN keywords k ON k.article_id = a.id
                WHERE EXISTS (
                  SELECT 1 FROM unnest($1::text[]) AS patt WHERE k.keyword ILIKE patt
                )
                ORDER BY a.date DESC
                LIMIT $2;
                """
                rows = await conn.fetch(sql, patterns, limit)
                return [dict(r) for r in rows]

            else:
                # mode == "all": для каждой статьи считаем, сколько шаблонов нашли среди её ключевых слов
                # и сравниваем с требуемым количеством
                needed = len(set(patterns))
                sql = """
                SELECT a.id, a.title, a.date
                FROM articles a
                WHERE (
                  SELECT COUNT(DISTINCT patt)
                  FROM unnest($1::text[]) AS patt
                  WHERE EXISTS (
                    SELECT 1 FROM keywords k WHERE k.article_id = a.id AND k.keyword ILIKE patt
                  )
                ) >= $2
                ORDER BY a.date DESC
                LIMIT $3;
                """
                rows = await conn.fetch(sql, patterns, needed, limit)
                return [dict(r) for r in rows]

# ---------- Семантический поиск (требует эмбеддинг запроса) ----------
def _vec_to_pg_literal(vec: List[float]) -> str:
    # Преобразует Python list в Postgres vector literal: '[0.1,0.2,...]'
    return "[" + ",".join(map(str, vec)) + "]"

# async def search_articles_semantic(embedding: List[float], limit: int = 10) -> List[dict]:
#     """
#     Семантический поиск по эмбеддингу.
#     Важно: driver/adapter может потребовать регистрировать vector-тип.
#     Мы передаём literal и используем ::vector каст.
#     """
#     v_lit = _vec_to_pg_literal(embedding)
#     sql = f"""
#     SELECT a.id, a.title, a.date
#     FROM article_embeddings e
#     JOIN articles a ON a.id = e.article_id
#     ORDER BY e.embedding <-> $1::vector
#     LIMIT $2
#     """
#     p = pool()
#     async with p.acquire() as conn:
#         rows = await conn.fetch(sql, v_lit, limit)
#         return [dict(r) for r in rows]


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
