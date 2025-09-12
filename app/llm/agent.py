# app/llm/agent.py
import json
from typing import List, Dict, Any, Optional
from app.llm.call_llm import call_llm
from app.services.articles import fetch_articles
from app.services.relations import list_interesting_relations
from app.services.relations import save_relations
from pprint import pprint


MAX_TURNS = 4

# Функции, которые агент может дергать
FUNCTIONS = {
    "list_interesting_relations": {
        "func": list_interesting_relations,
        "description": "Находит интересные связи между статьями.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["rare", "strong", "recent"],
                    "description": "Критерий поиска интересных связей."
                },
                "limit": {
                    "type": "integer",
                    "description": "Максимальное количество связей, по умолчанию 5"
                }
            },
            "required": ["kind"]
        }
    },
    "fetch_articles": {
        "func": fetch_articles,
        "description": "Получает статьи по списку id.",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Список идентификаторов статей"
                }
            },
            "required": ["ids"]
        }
    }
}

async def agent_loop(user_goal: str):
    """
    Итеративный агент. Получает user_goal и сам планирует шаги.
    """
    state: Dict[str, Any] = {"goal": user_goal, "history": []}

    for turn in range(MAX_TURNS):
        # 1. Составляем промпт для агента
        prompt = f"""
        Ты умный исследователь статей.
        Задача пользователя: {user_goal}

        Тебе доступны функции в формате JSON Schema:
    {json.dumps({k: {"description": v["description"], "parameters": v["parameters"]}
             for k, v in FUNCTIONS.items()}, ensure_ascii=False, indent=2)}
        История шагов: {state['history']}

        Реши, что делать дальше:
        - Вызвать функцию с аргументами
        - Или завершить работу и выдать финальный текст.
        
        Ограничения:
        - передавай в функции только те параметры, которые явно указаны в описании
        - выбирай самую интересную связь и запрашивай по ней дополнительную информацию через вызов функций
        - ограничивай финальный текст 7-10 предложениями
        - добавь несколько эмоджи в финальный текст
        - в истории шагов указана текущая итерация из {MAX_TURNS-1}, на последней ты обязан выдать финальный текст, 
        хотя можешь сделать это и раньше
        - всегда отдавай ответ в json

        Ответ в JSON:
        {{
          "action": "function" | "finish",
          "name": "<имя функции>",
          "args": {{...}} | null,
          "final_text": str | null
        }}
        """

        action = await call_llm([
            {"role": "system", "content":
                "Ты — научный журналист.Твоя задача — писать вдумчивые тексты по связям между научными статьями."},
            {"role": "user", "content": prompt}
        ],
        model='gpt-5-mini')

        # 2. Парсим
        try:
            parsed = action
            pprint(parsed)
                # (json.loads(action))
        except Exception:
            print("⚠️ LLM вернул невалидный JSON:", action)
            break

        if parsed["action"] == "finish":
            print("✅ Агент завершил работу")
            return parsed["final_text"]

        if parsed["action"] == "function":
            fname = parsed["name"]
            fargs = parsed["args"] or {}
            if fname not in FUNCTIONS:
                print(f"⚠️ Неизвестная функция: {fname}")
                break
            # 3. Вызов функции
            try:
                result = await FUNCTIONS[fname]['func'](**fargs)
                # pprint(result)
            except Exception as e:
                result = {"error": str(e)}
                # pprint(result)

            # 4. Сохраняем в историю
            state["history"].append({
                "function": fname,
                "args": fargs,
                "result": result,
                "step": turn
            })

    return "⚠️ Агент не смог достичь цели за отведённые шаги"
