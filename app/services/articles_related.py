from __future__ import annotations

from typing import List

from app.db.pool import connect_db, pool
from app.models.schemas import ArticleMeta
from app.services.utils import _vec_to_pg_literal


async def get_related_articles(article_id: int, method: str = "semantic", top_n: int = 10) -> List[ArticleMeta]:
    await connect_db()
    p = pool()
    async with p.acquire() as conn:
        if method == "semantic":
            emb_row = await conn.fetchrow("SELECT embedding FROM article_embeddings WHERE article_id = $1", article_id)
            if not emb_row:
                return []
            emb = emb_row["embedding"]
            v_lit = _vec_to_pg_literal(emb) if isinstance(emb, list) else str(emb)
            sql = """
            SELECT a.id, a.title, a.date, a.release_number, s.summary, e.embedding <-> $1::vector AS score
            FROM article_embeddings e
            LEFT JOIN articles a ON a.id = e.article_id
            LEFT JOIN summaries s ON a.id = s.article_id
            WHERE e.article_id <> $2
            ORDER BY score DESC
            LIMIT $3
            """
            rows = await conn.fetch(sql, v_lit, article_id, top_n)
            return [ArticleMeta(**dict(r)) for r in rows]
        else:
            sql = """
            SELECT a.id, a.title, a.date, a.release_number, s.summary, COUNT(*) as score
            FROM keywords k
            JOIN articles a ON a.id = k.article_id
            JOIN summaries s ON a.id = s.article_id
            WHERE k.keyword IN (
                SELECT keyword FROM keywords WHERE article_id = $1
            ) AND a.id <> $1
            GROUP BY a.id, a.title, s.summary
            ORDER BY score DESC
            LIMIT $2
            """
            rows = await conn.fetch(sql, article_id, top_n)
            return [ArticleMeta(**dict(r)) for r in rows]

