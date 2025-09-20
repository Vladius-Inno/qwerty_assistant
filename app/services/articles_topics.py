from __future__ import annotations

from typing import List, Tuple

from app.db.pool import pool


async def get_topic_timeline(topic_name: str, granularity: str = "month") -> List[Tuple[str, int]]:
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

