import json
import os
import inspect
from typing import Any, Dict
from openai import AsyncOpenAI
from app.services.articles import fetch_articles
from app.services.relations import get_related_articles_agent
from pprint import pprint

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = 'gpt-5-mini'

def logged_function(fn):
    if inspect.iscoroutinefunction(fn):
        # Обёртка для async функций
        async def wrapper(*args, **kwargs):
            pprint(f"\n[Function call] {fn.__name__}")
            if args:
                pprint(f"  args: {args}")
            if kwargs:
                pprint(f"  kwargs: {kwargs}")

            result = await fn(*args, **kwargs)
            pprint(f"[Function result] {result}\n")
            return result
        return wrapper
    else:
        # Обёртка для sync функций
        def wrapper(*args, **kwargs):
            pprint(f"\n[Function call] {fn.__name__}")
            if args:
                pprint(f"  args: {args}")
            if kwargs:
                pprint(f"  kwargs: {kwargs}")

            result = fn(*args, **kwargs)
            pprint(f"[Function result] {result}\n")
            return result
        return wrapper

FUNCTIONS = {
    "fetch_articles": logged_function(fetch_articles),
    "get_related_articles": logged_function(get_related_articles_agent),
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_articles",
            "description": "Возвращает полные тексты статей по списку id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_articles",
            "description": "Находит статьи, связанные с указанной, и возвращает их ID и score связи, чем меньше, тем ближе сходство.",
            "parameters": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "integer"},
                    "method": {"type": "string", "enum": ["semantic", "keywords"]},
                    "top_n": {"type": "integer"},
                },
                "required": ["article_id"],
            },
        },
    },
]


# ---------- Агент ----------
async def agent_loop(user_goal: str, max_turns: int = 5) -> str:
    history = [
        {"role": "system",
         "content": (
             "Ты — автор научно-популярного блога. Используй доступные функции, чтобы глубоко анализировать статьи."
             "Ограничения:"
             "- ты не имеешь права делать выводы только на основе кратких описаний, всегда проверяй полный текст, в т.ч. оригинальной статьи"
             "- когда пишешь текст для телеграм, делай короткий пост на 8–10 предложений, который развивает тему связи и сосредотачивается на самом важном и удивительном"
             "- используй немного эмодзи, стиль должен быть увлекательный, но без излишней игривости-"
             "- делай отсылки к годам исследований и оценивай развитие науки во времени"
             "- сохрани научную точность, но избегай сложных терминов, их лучше пояснять простыми словами"
             "- избегай общих и восторженных выводов"
            )
         },
        {"role": "user", "content": user_goal},
    ]

    for turn in range(max_turns):
        response = await client.chat.completions.create(
            model=MODEL,
            messages=history,
            tools=TOOLS,
        )

        msg = response.choices[0].message

        # Если модель решила завершить работу
        if msg.content:
            return msg.content

        # Если модель вызвала функции
        if msg.tool_calls:
            # Добавляем сам запрос функций (assistant message с tool_calls)
            history.append(msg)

            tool_messages = []
            for tool_call in msg.tool_calls:
                fname = tool_call.function.name
                try:
                    fargs = json.loads(tool_call.function.arguments)
                except Exception as e:
                    fargs = {}
                    result = {"error": f"Ошибка разбора аргументов: {e}"}
                    pprint(f"[Function args error] {fname}: {e}")
                else:
                    if fname not in FUNCTIONS:
                        result = {"error": f"⚠️ Неизвестная функция: {fname}"}
                    else:
                        try:
                            fn = FUNCTIONS[fname]
                            if inspect.iscoroutinefunction(fn):
                                result = await fn(**fargs)
                            else:
                                result = fn(**fargs)
                        except Exception as e:
                            result = {"error": str(e)}

                # Логируем результат
                pprint(f"[Tool response] {fname} -> {result}")

                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fname,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            # Добавляем все ответы функций в историю
            history.extend(tool_messages)
            continue

    return "⚠️ Агент не смог достичь цели за отведённые шаги"
