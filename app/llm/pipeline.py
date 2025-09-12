import asyncio
from typing import List
from app.services.articles import get_article, get_related_articles
from app.services.relations import save_relations
from app.models.schemas import ArticleFull, ArticleMeta

# тут будет твой вызов к LLM (например, OpenAI, Ollama и т.п.)
from app.llm.call_llm import call_llm


async def analyze_article(article_id: int, top_n: int = 5) -> List[dict]:
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

    print(f'For article {article_id} there are candidates: {[c.id for c in candidates]}')

    # 3. Вызов LLM для анализа связей
    prompt = f"""
    У тебя есть статья (article_id={article.id}::
    Заголовок: {article.title}
    Саммари: {article.summary}

    И кандидаты на связь:
    {[(c.id, c.title, c.summary) for c in candidates]}

    Определи, какие статьи связаны с исходной, и укажи тип связи 
    (relation_type, например: "развитие", "применение на практике", "противоречие", "продолжение",
    "подтверждение гипотезы").
    Комментарии укажи в заметках (connection_text).
    
    Важно:
    - Верни результат строго в формате JSON-объекта с ключом "relations" без лишних символов перед открывающей скобокой
    и после закрывающей скобки.
    - Внутри "relations" должен быть список словарей.
    - Каждый словарь содержит поля:
        - "article_id": int (всегда {article.id})
        - "related_article_id": int (id из кандидатов)
        - "relation_type": str (например: "развитие", "противоречие", "продолжение" и т.п.)
        - "score": float (от 0 до 1), уверенность в связи
        - "connection_text": str (короткое пояснение)
    - Оценивай score по шкале 0.0–1.0 по правилам:  
        - 0.9–1.0 — есть прямое упоминание / экспериментальное подтверждение.
        - 0.7–0.89 — статьи обсуждают один и тот же объект/явление, но без прямого пересечения данных.
        - 0.5–0.69 — тематическая близость, но слабая связь.
        - <0.5 — не сохраняем (считаем, что это шум).
    - Особое внимание уделяй неожиданным, редким и потенциально прорывным связям.Игнорируй слишком общие совпадения 
    (например, "обе статьи про физику").
        
    Примеры:
    
    Саммари исходной статьи: "Новая модель тёмной материи предсказывает взаимодействие с нейтрино".  
    Саммари статьи кандидата: "Эксперимент IceCube сообщил об аномалиях в данных по нейтрино".  
    Ответ:
    {{
        "relations": [
            {{
              "article_id": {article.id},
              "related_article_id": 42,
              "relation_type": "Подтверждение гипотезы",
              "score": 0.87,
              "connection_text": "Модель тёмной материи связана с наблюдаемыми нейтринными аномалиями IceCube."
            }}
        ]
    }}
    
    СТАТЬЯ: "Обнаружено новое свойство квантовых точек".  
    КАНДИДАТ: "Анализ фотонных кристаллов".  
    
    Ответ: 
        {{
        "relations": []
    }}
    (нет прямой связи)
    
    """

    result = await call_llm([
        {"role": "system", "content":
            "Ты — исследовательский ассистент.Твоя задача — находить связи между научными статьями."},
        {"role": "user", "content": prompt}
    ])
    # 4. Сохраняем найденные связи
    await save_relations(result)

    return result
