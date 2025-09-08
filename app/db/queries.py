from typing import List, Dict, Optional
from app.db.pool import pool
from app.services.embeddings import get_query_embedding
import ast


async def combined_search(
    query: str,
    limit: int = 20,
    preselect: int = 200  # сколько кандидатов брать по эмбеддингу
) -> List[Dict]:
    """
    Двухступенчатый поиск:
    1. Находим N кандидатов по эмбеддингу.
    2. Сортируем их с учётом full-text совпадений.
    """

    def to_pgvector(embedding: list[float]) -> str:
        return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"

    p = pool()
    embedding = get_query_embedding(query)
    embedding_str = to_pgvector(embedding)

    async with p.acquire() as conn:
        # 1. Отбираем кандидатов по близости вектора
        candidates = await conn.fetch(
            """
            SELECT a.id, a.title, a.date, a.body, e.embedding
            FROM articles a
            JOIN article_embeddings e ON a.id = e.article_id
            ORDER BY e.embedding <-> $1::vector
            LIMIT $2
            """,
            embedding_str,
            preselect
        )

        if not candidates:
            return []

        # 2. Пересчёт full-text рейтинга только для кандидатов
        ids = [c["id"] for c in candidates]
        rows = await conn.fetch(
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
            ids
        )
        ft_scores = {r["id"]: r["ft_score"] for r in rows}

    # 3. Комбинируем эмбеддинг + full-text
    results = []
    for c in candidates:
        emb_sim = 1.0 - float(embedding_distance(c["embedding"], embedding))
        ft_score = ft_scores.get(c["id"], 0.0)
        final_score = 0.7 * emb_sim + 0.3 * ft_score

        results.append({
            "id": c["id"],
            "title": c["title"],
            "date": c["date"],
            "score": final_score
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def embedding_distance(vec1, vec2):
    """L2 расстояние (Postgres <-> использует cosine/euclidean)."""
    if isinstance(vec1, str):  # пришёл pgvector как текст
        vec1 = ast.literal_eval(vec1)
    return sum((a - b) ** 2 for a, b in zip(vec1, vec2)) ** 0.5
