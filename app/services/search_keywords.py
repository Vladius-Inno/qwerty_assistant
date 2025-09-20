from __future__ import annotations

from typing import List
from app.db.pool import pool


async def search_by_keywords(
    keywords: List[str],
    *,
    mode: str = "any",
    partial: bool = False,
    limit: int = 20,
) -> list[dict]:
    if not keywords:
        return []
    kws = [k.strip() for k in keywords if k and k.strip()]
    if not kws:
        return []

    p = pool()
    async with p.acquire() as conn:
        if not partial:
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
            else:
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
            patterns = [f"%{k}%" for k in kws]
            if mode == "any":
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


def embedding_distance(vec1, vec2):
    import ast
    if isinstance(vec1, str):
        vec1 = ast.literal_eval(vec1)
    return sum((a - b) ** 2 for a, b in zip(vec1, vec2)) ** 0.5

__all__ = ["search_by_keywords", "embedding_distance"]

