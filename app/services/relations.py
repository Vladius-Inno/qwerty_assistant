# app/services/relations.py
from typing import List, Dict
from app.db.pool import pool
import json

async def save_relations(relations: Dict):
    """
    Сохраняет связи между статьями в таблицу article_relations.
    Ожидает список словарей с ключами:
        - article_id
        - related_article_id
        - relation_type_id
        - confidence (float, опционально)
        - notes (str, опционально)
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
