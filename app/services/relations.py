# app/services/relations.py
from typing import List, Dict, Any
from app.db.pool import pool, connect_db, close_db
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
