import asyncio
from typing import List
from app.services.articles import get_article, get_related_articles
from app.services.relations import save_relations
from app.models.schemas import ArticleFull, ArticleMeta

# тут будет твой вызов к LLM (например, OpenAI, Ollama и т.п.)
from app.llm.call_llm import call_llm


async def analyze_article(article_id: int, top_n: int = 10) -> List[dict]:
    """
    Пайплайн анализа одной статьи:
    1. Загружаем статью.
    2. Находим кандидатов по семантике и ключевым словам.
    3. Отдаём LLM на анализ связей.
    4. Сохраняем связи в базу.
    """

    # 1. Загружаем статью
    article: ArticleFull = await get_article(article_id)
    if not article:
        raise ValueError(f"Article {article_id} not found")

    # 2. Находим кандидатов
    candidates_semantic: List[ArticleMeta] = await get_related_articles(
        article_id, method="semantic", top_n=top_n
    )
    candidates_keywords: List[ArticleMeta] = await get_related_articles(
        article_id, method="keywords", top_n=top_n
    )

    candidates = {c.id: c for c in candidates_semantic
                  + candidates_keywords
                  }.values()

    print(candidates)

    # 3. Вызов LLM для анализа связей
    prompt = f"""
    У тебя есть статья (article_id={article.id}::
    Заголовок: {article.title}
    Саммари: {article.summary}

    И кандидаты на связь:
    {[(c.id, c.title, c.summary) for c in candidates]}

    Определи, какие статьи связаны с исходной, и укажи тип связи 
    (relation_type, например: "развитие", "применение на практике", "контраст", "продолжение").
    Комментарии укажи в заметках (connection_text).
    Важно:
    - Верни результат строго в формате JSON-объекта с ключом "relations".
    - Внутри "relations" должен быть список словарей.
    - Каждый словарь содержит поля:
        - "article_id": int (всегда {article.id})
        - "related_article_id": int (id из кандидатов)
        - "relation_type": str (например: "по теме", "цитирование", "контраст", "продолжение")
        - "score": float (от 0 до 1), уверенность в связи
        - "connection_text": str (короткое пояснение)
        
    Пример правильного ответа:
    {{
        "relations": [
            {{
              "article_id": {article.id},
              "related_article_id": 42,
              "relation_type": "по теме",
              "score": 0.87,
              "connection_text": "Обе статьи обсуждают один и тот же эксперимент"
            }}
        ]
    }}
    """

    result = await call_llm([
        {"role": "system", "content": "Ты аналитик, ищи связи между статьями."},
        {"role": "user", "content": prompt}
    ])

    # 4. Сохраняем найденные связи
    await save_relations(result)

            # "article_id": article_id,
            # "related_article_id": rel["related_article_id"],
            # "relation_type": rel["relation_type"],
            # "confidence": rel.get("confidence", 0.8),
            # "notes": rel.get("notes")

    return result
