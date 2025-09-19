from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from app.db.pool import connect_db, pool
from app.models.schemas import ArticleFull
import json


async def get_article(article_id: int) -> Optional[ArticleFull]:
    sql = """
    SELECT
      a.id,
      a.title,
      a.body,
      a.date,
      a.source_link,
      a.article_link,
      a.release_number,
      (
        SELECT td.name
        FROM article_topics at
        JOIN topic_dictionary td ON td.id = at.topic_id
        WHERE at.article_id = a.id
        LIMIT 1
      ) AS topic_name,
      COALESCE(
        (SELECT array_agg(k.keyword) FROM keywords k WHERE k.article_id = a.id),
        ARRAY[]::text[]
      ) AS keywords,
      COALESCE(
        (SELECT array_agg(t.name)
         FROM tags t
         JOIN article_tags at ON at.tag_id = t.id
         WHERE at.article_id = a.id),
        ARRAY[]::text[]
      ) AS tags,
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

        article = dict(row)

        kws = article.get("keywords")
        article["keywords"] = [str(x) for x in (kws or [])]

        tgs = article.get("tags")
        article["tags"] = [str(x) for x in (tgs or [])]

        extra = article.get("extra_links")
        if isinstance(extra, str):
            try:
                article["extra_links"] = json.loads(extra)
            except Exception:
                article["extra_links"] = {}
        elif extra is None:
            article["extra_links"] = {}

        return ArticleFull(**article)


async def fetch_articles(ids: List[int]) -> Dict[str, Any]:
    query = """
        SELECT id, title, body
        FROM articles
        WHERE id = ANY($1::int[])
    """
    await connect_db()
    p = pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(query, ids)

    result = [dict(r) for r in rows]
    return {i['id']: {"Название": i['title'], "Текст статьи": i["body"]} for i in result}


async def list_articles(
    limit: int = 20,
    offset: int = 0,
    topic: Optional[str] = None,
    tag: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    q: Optional[str] = None,
    order_by: str = "date",
) -> List[dict]:
    filters = []
    args: List[Any] = []
    idx = 1
    if topic:
        filters.append("(td.name ILIKE $%d OR a.topic_id = (SELECT id FROM topic_dictionary WHERE name ILIKE $%d LIMIT 1))" % (idx, idx))
        args.append(topic)
        idx += 1
    if tag:
        filters.append("EXISTS (SELECT 1 FROM article_tags at2 JOIN tags t2 ON t2.id = at2.tag_id WHERE at2.article_id = a.id AND t2.name ILIKE $%d)" % idx)
        args.append(tag)
        idx += 1
    if date_from:
        filters.append("a.date >= $%d" % idx)
        args.append(date_from)
        idx += 1
    if date_to:
        filters.append("a.date <= $%d" % idx)
        args.append(date_to)
        idx += 1
    if q:
        filters.append("(a.title ILIKE $%d OR a.body ILIKE $%d)" % (idx, idx))
        args.append(f"%{q}%")
        idx += 1

    where_sql = ("WHERE " + " AND ".join(filters)) if filters else ""
    sql = f"""
        SELECT 
            a.id, a.title, a.date, a.source_link, a.article_link, a.release_number,
            COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.id IS NOT NULL), '{{}}') AS tags,
            COALESCE(array_agg(DISTINCT k.keyword) FILTER (WHERE k.keyword IS NOT NULL), '{{}}') AS keywords,
            COALESCE(array_agg(DISTINCT td.name) FILTER (WHERE td.id IS NOT NULL), '{{}}') AS topics
        FROM articles a
        LEFT JOIN article_tags at ON at.article_id = a.id
        LEFT JOIN tags t ON t.id = at.tag_id
        LEFT JOIN keywords k ON k.article_id = a.id
        LEFT JOIN article_topics atp ON atp.article_id = a.id
        LEFT JOIN topic_dictionary td ON td.id = atp.topic_id
        {where_sql}
        GROUP BY a.id
        ORDER BY a.{order_by} DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """
    args.extend([limit, offset])

    p = pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]

