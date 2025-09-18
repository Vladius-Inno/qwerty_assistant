import json
import os
import inspect
from typing import Any, Dict, Optional, Callable
from openai import AsyncOpenAI
from app.services.articles import fetch_articles
from app.services.relations import get_related_articles_agent
from app.services.search import combined_search_agent
from pprint import pprint

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = 'gpt-5-mini'
MAX_PREVIEW = 5

# Optional progress reporter callback. If set, logged_function will send
# human-readable messages before and after each tool/function call the agent makes.
_progress_cb: Optional[Callable[[str], None]] = None

def set_progress_callback(cb: Optional[Callable[[str], None]]) -> None:
    global _progress_cb
    _progress_cb = cb

def _safe_get(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default

def _format_result(result: Any, max_items: int = MAX_PREVIEW) -> str:
    """Универсальный человекочитаемый форматтер для результатов функций агента."""
    if result is None:
        return "None"

    # -------- DICT variants --------
    if isinstance(result, dict):
        # case: {"related": [ {id, score}, ... ]}
        if "related" in result and isinstance(result["related"], list):
            items = result["related"]
            n = len(items)
            preview = []
            for it in items[:max_items]:
                # it может быть dict или tuple-ish
                if isinstance(it, dict):
                    id_ = _safe_get(it, "id", "article_id", default=str(it))
                    score = _safe_get(it, "score", "similarity", default=None)
                else:
                    id_, score = (str(it), None)
                if isinstance(score, (int, float)):
                    preview.append(f"{id_} (score={float(score):.3f})")
                else:
                    preview.append(str(id_))
            more = "..." if n > max_items else ""
            return f"Найдено {n} связанных статей: " + ", ".join(preview) + more

        # case: fetch_articles -> { id: {"Заголовок": ..., "Полный текст статьи": ...}, ... }
        values = list(result.values())
        if values and isinstance(values[0], dict) and any(k in values[0] for k in ("Заголовок", "Полный текст статьи", "title", "body")):
            n = len(result)
            previews = []
            for k, v in list(result.items())[:max_items]:
                title = _safe_get(v, "Заголовок", "title", default="—")
                body = _safe_get(v, "Полный текст статьи", "body", default="")
                snippet = " ".join(body.splitlines())[:140]
                previews.append(f"{k}: «{title}» — {snippet}{'...' if len(body) > 140 else ''}")
            more = "..." if n > max_items else ""
            return f"Получено {n} статей: " + " | ".join(previews) + more

        # generic dict that looks like single article metadata: {"id": ..., "title": ..., "score": ...}
        if "id" in result and any(k in result for k in ("title", "Заголовок", "score")):
            title = _safe_get(result, "title", "Заголовок", default="—")
            date = result.get("date")
            score = _safe_get(result, "score", "similarity")
            s = f"Статья {result.get('id')}: «{title}»"
            if date:
                s += f", {date}"
            if isinstance(score, (int, float)):
                s += f", score={float(score):.3f}"
            return s

        # fallback for dicts
        keys = list(result.keys())[:10]
        return f"Dict keys={keys} (size={len(result)})"

    # -------- LIST variants --------
    if isinstance(result, list):
        if len(result) == 0:
            return "Пустой список"

        # list of dicts (обычно combined_search возвращает list[dict])
        if all(isinstance(x, dict) for x in result):
            # обнаруживаем статью-подобную структуру
            sample = result[0]
            if "id" in sample and any(k in sample for k in ("title", "score", "date")):
                n = len(result)
                preview = []
                for it in result[:max_items]:
                    id_ = _safe_get(it, "id", default="?")
                    title = _safe_get(it, "title", "Заголовок", default="—")
                    score = _safe_get(it, "score", default=None)
                    if isinstance(score, (int, float)):
                        preview.append(f"{id_}: «{title}» (score={float(score):.3f})")
                    else:
                        preview.append(f"{id_}: «{title}»")
                more = "..." if n > max_items else ""
                return f"Список из {n} статей: " + " | ".join(preview) + more

            # generic list of dicts
            return f"Список из {len(result)} словарей, пример ключей: {list(result[0].keys())}"

        # list of ids
        if all(isinstance(x, (int, str)) for x in result):
            preview = result[:max_items]
            more = "..." if len(result) > max_items else ""
            return f"Список id ({len(result)}): {preview}{more}"

        # fallback for other lists
        preview = result[:max_items]
        more = "..." if len(result) > max_items else ""
        return f"Список из {len(result)} элементов, пример: {preview}{more}"

    # -------- STR / other --------
    if isinstance(result, str):
        s = result.strip()
        short = s[:300] + ("..." if len(s) > 300 else "")
        return f"Текст (len={len(s)}): {short}"

    # numbers, booleans, etc.
    try:
        return str(result)
    except Exception:
        return repr(result)

def logged_function(fn):
    """Логирующая обёртка: печатает человекочитаемый статус, но возвращает оригинал."""
    if inspect.iscoroutinefunction(fn):
        async def wrapper(*args, **kwargs):
            pprint(f"\n[Function call] {fn.__name__}")
            if args:
                pprint(f"  args: {args}")
            if kwargs:
                pprint(f"  kwargs: {kwargs}")
            if _progress_cb:
                try:
                    _progress_cb(f"{fn.__name__}: starting with args={args} kwargs={kwargs}")
                except Exception:
                    pass
            result = await fn(*args, **kwargs)
            pretty = _format_result(result)
            pprint(f"[Function result] {pretty}\n")
            if _progress_cb:
                try:
                    _progress_cb(f"{fn.__name__}: {pretty}")
                except Exception:
                    pass
            return result
        return wrapper
    else:
        def wrapper(*args, **kwargs):
            pprint(f"\n[Function call] {fn.__name__}")
            if args:
                pprint(f"  args: {args}")
            if kwargs:
                pprint(f"  kwargs: {kwargs}")
            if _progress_cb:
                try:
                    _progress_cb(f"{fn.__name__}: starting with args={args} kwargs={kwargs}")
                except Exception:
                    pass
            result = fn(*args, **kwargs)
            pretty = _format_result(result)
            pprint(f"[Function result] {pretty}\n")
            if _progress_cb:
                try:
                    _progress_cb(f"{fn.__name__}: {pretty}")
                except Exception:
                    pass
            return result
        return wrapper

FUNCTIONS = {
    "fetch_articles": logged_function(fetch_articles),
    "get_related_articles": logged_function(get_related_articles_agent),
    "combined_search": logged_function(combined_search_agent)
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "combined_search",
            "description": "Ищет релевантные статьи по пользовательскому запросу (семантический поиск + full-text).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Запрос пользователя (тема, вопрос, ключевые слова)."},
                    "limit": {"type": "integer", "description": "Сколько статей вернуть (по умолчанию 20)."},
                    "preselect": {"type": "integer", "description": "Сколько кандидатов взять по эмбеддингу (по умолчанию 200)."},
                    "alpha": {"type": "number", "description": "Вклад эмбеддинга в общий скор (0.0–1.0, по умолчанию 0.7)."},
                },
                "required": ["query"]
            },
        },
    },
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
             "Ты — помощник автора научно-популярного блога. Он пишет статьи для своего блога с 2017 года, выбирая только интересные ему события. "
             "Используй доступные функции, чтобы работать с базой его статей."
             "Ограничения:"
             f"- ты можешь сделать не более {max_turns-1} вызовов функций (например, поиска или получения связанных статей) за весь запуск, если тебе не хватает данных, остановись и дай ответ по имеющейся информации"
             "- ты не имеешь права делать выводы только на основе кратких описаний, всегда проверяй полный текст, в т.ч. оригинальной статьи"
             "- все запросы к функциям поиска (combined_search) нужно формировать на русском языке, так как база и индексы русскоязычные; старайся использовать короткие запросы"
             "- разрешён только один основной поисковый запрос + при необходимости одно уточнение (не более 2 запросов подряд)"
             "- когда пишешь текст для телеграм, делай короткий пост на 500-900 знаков, который развивает тему связи и сосредотачивается на самом важном и удивительном. Пиши заголовок / хук"
             "- используй 2-4 эмодзи, стиль должен быть увлекательный, но без излишней игривости-"
             "- делай отсылки к годам исследований и оценивай развитие науки во времени"
             "- сохрани научную точность, но избегай сложных терминов, их лучше пояснять простыми словами"
             "- избегай восторженных выводов, но формулируй финальую мысль в духе развития науки"
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
                # pprint(f"[Tool response] {fname} -> {result}")

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
