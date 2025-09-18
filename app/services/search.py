import inspect
import math
from typing import List, Dict, Optional
from app.db.pool import pool, connect_db
from app.models.schemas import ArticleMeta
from app.services.embeddings import get_query_embedding
import ast


async def combined_search_agent(query: str, limit: int = 10, preselect: int = 200, alpha: float = 0.7) -> [dict]:
    await connect_db()

    try:
        result = await combined_search(query, limit, preselect, alpha)
    except Exception as e:
        return {"error": str(e)}

    result =  [
        {
            "id": r.id,
            "title": r.title,
            "date": r.date.isoformat() if hasattr(r.date, "isoformat") else r.date,
            "score": r.score,
            # "distance": r.distance,
            # "ft_score_norm": r.ft_score_norm,
        }
        for r in result[:limit]
    ]
    return result

async def combined_search(
    query: str,
    limit: int = 20,
    preselect: int = 200,    # сколько кандидатов взять по эмбеддингу (в БД)
    alpha: float = 0.7       # вклад эмбеддинга в финальный скор (1-alpha = вклад full-text)
) -> List[ArticleMeta]:
    """
    Двухступенчатый поиск:
      1) берём N ближайших кандидатов по эмбеддингу (pgvector, ORDER BY distance)
      2) считаем full-text score (ts_rank_cd) только для этих кандидатов
      3) нормализуем ft_score и преобразуем distance -> similarity, комбинируем
    Возвращает список словарей {id, title, date, score, distance, ft_score_norm}
    """

    # --- 1) получение эмбеддинга запроса (поддерживаем sync/async get_query_embedding) ---
    emb = get_query_embedding(query)
    # если get_query_embedding — coroutine, await её
    if inspect.isawaitable(emb):
        emb = await emb

    if not emb:
        return []

    # --- 2) сериализация эмбеддинга в строку для передачи в $1::vector ---
    # Используем формат без лишних пробелов: [0.123456,0.234567,...]
    def to_pgvector(embedding: List[float]) -> str:
        # безопасно приведение в float и формат с достаточной точностью
        parts = (format(float(x), ".8f") for x in embedding)
        return "[" + ",".join(parts) + "]"

    emb_literal = to_pgvector(emb)

    # ограничим preselect, чтобы не перегружать память/снять нагрузку
    preselect = max(10, min(int(preselect), 2000))

    p = pool()

    async with p.acquire() as conn:
        # 1) отбираем кандидатов по расстоянию (distance) — делаем вычисление в БД
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
            preselect
        )

        if not candidates:
            return []

        ids = [r["id"] for r in candidates]

        # 2) получаем full-text ранги только для этих id
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
            ids
        )
        ft_scores = {r["id"]: float(r["ft_score"] or 0.0) for r in ft_rows}

        # --- 3) нормализация ft_score и комбинирование ---
        max_ft = max(ft_scores.values()) if ft_scores else 0.0
        # защитим от деления на ноль
        if max_ft <= 0.0:
            max_ft = 1.0

        results = []
        for r in candidates:
            aid = r["id"]
            distance = float(r["distance"])  # расстояние >= 0
            # преобразуем расстояние в similarity в диапазоне (0,1], где больше лучше
            emb_sim = 1.0 / (1.0 + distance)

            ft_raw = ft_scores.get(aid, 0.0)
            ft_norm = ft_raw / max_ft  # теперь в [0,1]

            final_score = alpha * emb_sim + (1.0 - alpha) * ft_norm

            results.append(
                ArticleMeta(
                id=aid,
                title=r["title"],
                date=r["date"],
                release_number=r["release_number"],
                # "distance": distance,
                # "emb_sim": emb_sim,
                # "ft_score": ft_raw,
                # "ft_score_norm": ft_norm,
                score=final_score
                )
            )

        # сортируем финально и возвращаем топ-N
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

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


def embedding_distance(vec1, vec2):
    """L2 расстояние (Postgres <-> использует cosine/euclidean)."""
    if isinstance(vec1, str):  # пришёл pgvector как текст
        vec1 = ast.literal_eval(vec1)
    return sum((a - b) ** 2 for a, b in zip(vec1, vec2)) ** 0.5
