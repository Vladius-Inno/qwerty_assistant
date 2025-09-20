from __future__ import annotations

import inspect
from typing import List

from app.db.pool import connect_db, pool
from app.models.schemas import ArticleMeta
from app.services.embeddings import get_query_embedding


async def combined_search_agent(query: str, limit: int = 10, preselect: int = 200, alpha: float = 0.7) -> list[dict]:
    await connect_db()
    try:
        result = await combined_search(query, limit, preselect, alpha)
    except Exception as e:
        return {"error": str(e)}
    return [
        {
            "id": r.id,
            "title": r.title,
            "date": r.date.isoformat() if hasattr(r.date, "isoformat") else r.date,
            "score": r.score,
        }
        for r in result[:limit]
    ]


async def combined_search(
    query: str,
    limit: int = 20,
    preselect: int = 200,
    alpha: float = 0.7,
) -> List[ArticleMeta]:
    emb = get_query_embedding(query)
    if inspect.isawaitable(emb):
        emb = await emb
    if not emb:
        return []

    def to_pgvector(embedding: List[float]) -> str:
        parts = (format(float(x), ".8f") for x in embedding)
        return "[" + ",".join(parts) + "]"

    emb_literal = to_pgvector(emb)
    preselect = max(10, min(int(preselect), 2000))
    p = pool()
    async with p.acquire() as conn:
        candidates = await conn.fetch(
            """
            SELECT a.id, a.title, a.date, a.release_number,
                   e.embedding <-> $1::vector AS distance
            FROM article_embeddings e
            JOIN articles a ON a.id = e.article_id
            ORDER BY distance
            LIMIT $2;
            """,
            emb_literal,
            preselect,
        )
        if not candidates:
            return []
        ids = [r["id"] for r in candidates]
        ft_rows = await conn.fetch(
            """
            SELECT a.id,
                   ts_rank_cd(
                       to_tsvector('russian', a.title || ' ' || a.body),
                       plainto_tsquery('russian', $1)
                   ) AS ft_score
            FROM articles a
            WHERE a.id = ANY($2::int[])
            """,
            query,
            ids,
        )
        ft_scores = {r["id"]: float(r["ft_score"] or 0.0) for r in ft_rows}

        rows = []
        import math

        for r in candidates:
            rid = r["id"]
            distance = float(r["distance"] or 0.0)
            ft_score = ft_scores.get(rid, 0.0)
            similarity = 1.0 / (1.0 + distance)
            score = alpha * similarity + (1 - alpha) * (1.0 / (1.0 + math.exp(-5 * ft_score)))
            rows.append(
                ArticleMeta(
                    id=rid,
                    title=r["title"],
                    date=r["date"],
                    release_number=r.get("release_number"),
                    score=score,
                )
            )
        rows.sort(key=lambda x: (x.score or 0.0), reverse=True)
        return rows

