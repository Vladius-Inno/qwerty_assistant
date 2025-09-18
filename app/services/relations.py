# app/services/relations.py
from typing import List, Dict, Any
from app.db.pool import pool, connect_db, close_db
from app.services.articles import _vec_to_pg_literal
import json

async def save_relations(relations: Dict):
    """
    Сохраняет связи между статьями в таблицу article_relations.
    Ожидает список словарей с ключами:
        - article_id
        - related_article_id
        - relation_type_id
        - confidence (float, опционально)
        - connection_text (str, опционально)
    """

    print(relations)

    if not relations:
        return

    # Если прилетела строка — парсим
    if isinstance(relations, str):
        try:
            relations = json.loads(relations)
        except json.JSONDecodeError:
            raise ValueError("Невалидный JSON в save_relations")

    if not isinstance(relations, dict):
        raise ValueError("save_relations ожидает словарь или JSON-строку")

    query = """
        INSERT INTO article_relations
            (article_id, related_article_id, relation_type, score, connection_text)
        VALUES ($1, $2, $3, $4, $5)
    """

    p = pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            for r in relations['relations']:
                await conn.execute(
                    query,
                    r["article_id"],
                    r["related_article_id"],
                    r["relation_type"],
                    r.get("score", 0.0),
                    r.get("connection_text"),
                )

async def get_related_articles_agent(article_id: int, method: str = "semantic", top_n: int = 10) -> Dict[str, Any]:
    """
        Находит статьи, связанные с указанной статьёй.

        Args:
            article_id (int): ID исходной статьи.
            method (str, optional): Метод поиска связей:
                - "semantic" — по близости embedding'ов текста (по смыслу).
                - "keywords" — по совпадению ключевых слов/тегов.
                По умолчанию: "semantic".
            top_n (int, optional): Сколько наиболее релевантных статей вернуть. По умолчанию 10.

        Returns:
            Словарь с id статей, связанных с исходной.
    """
    await connect_db()
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
            SELECT a.id, e.embedding <-> $1::vector AS score
            FROM article_embeddings e
            LEFT JOIN articles a ON a.id = e.article_id
            WHERE e.article_id <> $2
            ORDER BY score ASC
            LIMIT $3
            """
            rows = await conn.fetch(sql, v_lit, article_id, top_n)
            result = [dict(r) for r in rows]
            return {"related": [
                {"id": i['id'], "score": i["score"]} for i in result
            ]}

        else:
            # keywords/tags based:
            sql = """
            SELECT a.id, COUNT(*) as score
            FROM keywords k
            JOIN articles a ON a.id = k.article_id
            WHERE k.keyword IN (
                SELECT keyword FROM keywords WHERE article_id = $1
            ) AND a.id <> $1
            GROUP BY a.id
            ORDER BY score DESC
            LIMIT $2
            """
            rows = await conn.fetch(sql, article_id, top_n)
            result = [dict(r) for r in rows]
            return {"related": [
                {"id": i['id'], "score": i["score"]} for i in result
            ]}

async def list_interesting_relations(kind: str = "rare", limit: int = 5) -> List[Dict[str, Any]]:
    """
    Возвращает список интересных связей между статьями.

    kind:
      - "rare": редкие типы связей (по частоте использования relation_type)
      - "strong": связи с высоким confidence
      - "recent": связи, у которых статьи новые

    Возвращает список словарей:
      - id (id связи)
      - article_id
      - related_article_id
      - relation_type
      - score
      - connection_text
    """
    sql = """
    SELECT id, article_id, related_article_id, relation_type, score, connection_text
    FROM article_relations
    """

    if kind == "rare":
        sql += """
        WHERE relation_type IN (
            SELECT relation_type
            FROM article_relations
            GROUP BY relation_type
            HAVING COUNT(*) < 10
        )
        ORDER BY random()
        LIMIT $1
        """
        args = [limit]

    elif kind == "strong":
        sql += "WHERE score >= 0.8 ORDER BY score DESC LIMIT $1"
        args = [limit]

    elif kind == "recent":
        sql = """
        SELECT ar.id, ar.article_id, ar.related_article_id, ar.relation_type, ar.score, ar.connection_text
        FROM article_relations ar
        JOIN articles a ON a.id = ar.article_id
        ORDER BY a.date DESC
        LIMIT $1
        """
        args = [limit]

    else:
        sql += " ORDER BY random() LIMIT $1"
        args = [limit]
    await connect_db()
    p = pool()
    async with p.acquire() as conn:
        rows = await conn.fetch(sql, *args)
        # await close_db()
        return [dict(r) for r in rows]
