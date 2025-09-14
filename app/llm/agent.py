# app/llm/agent.py
import json
from typing import List, Dict, Any, Optional
from app.llm.call_llm import call_llm
from app.services.articles import fetch_articles, get_related_articles
from app.services.relations import list_interesting_relations
from app.services.relations import save_relations
from pprint import pprint


MAX_TURNS = 5

# Функции, которые агент может дергать
FUNCTIONS = {
    # "list_interesting_relations": {
    #     "func": list_interesting_relations,
    #     "description": "Находит интересные связи между статьями.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "kind": {
    #                 "type": "string",
    #                 "enum": ["rare", "strong", "recent"],
    #                 "description": "Критерий поиска интересных связей."
    #             },
    #             "limit": {
    #                 "type": "integer",
    #                 "description": "Максимальное количество связей, по умолчанию 5"
    #             }
    #         },
    #         "required": ["kind"]
    #     }
    # },
    "fetch_articles": {
        "func": fetch_articles,
        "description": "Возвращает полный текст статей по списку id.",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Список ID статей"
                }
            },
            "required": ["ids"]
        }
    },
    "get_related_articles": {
    "func": get_related_articles,
    "description": "Находит статьи, связанные с указанной статьёй, и возвращает их краткое описание.",
    "parameters": {
        "type": "object",
        "properties": {
            "article_id": {
                "type": "integer",
                "description": "ID исходной статьи"
            },
            "method": {
                "type": "string",
                "enum": ["semantic", "keywords"],
                "description": "Метод поиска: semantic (по смыслу) или keywords (по тегам)"
            },
            "top_n": {
                "type": "integer",
                "description": "Количество связанных статей для возврата (по умолчанию 10)"
            }
        },
        "required": ["article_id"]
        },
    }
}

async def agent_loop(user_goal: str):
    """
    Итеративный агент. Получает user_goal и сам планирует шаги.
    """
    state: Dict[str, Any] = {"goal": user_goal, "history": []}

    pprint(f'Got the goal: {user_goal}. Have {MAX_TURNS-1} steps to finish')

    for turn in range(MAX_TURNS):
        # 1. Составляем промпт для агента
        prompt = f"""
        История шагов: {state['history']}

        Реши, что делать дальше на этом шаге, чтобы решить задачу:
        - Вызвать одну из функций с аргументами
        - Или завершить работу и выдать финальный текст.
        
        Ограничения:
        - отдавай ответ только СТРОГО в формате JSON по шаблону, не давай объяснения JSON
        - передавай в функции только те параметры, которые явно указаны в описании
        - читай полные тексты интересующих тебя статей, чтобы сделать полноценные выводы
        - в истории шагов указана текущая итерация из {MAX_TURNS-1}, на последней итерации ты обязан выдать финальный текст        
        - когда пишешь текст для телеграм, делай короткий пост на 8–10 предложений, который развивает тему связи и сосредотачивается на 
        самом важном и удовительном
        - используй немного эмодзи, стиль должен быть увлекательный, но без излишней игривости
        - делай отсылки к годам исследований и оценивай развитие науки во времени
        - сохрани научную точность, но избегай сложных терминов, их лучше пояснять простыми словами
        - избегай общих и восторженных выводов, будь реалистом

        Обязательный шаблон ответа в JSON:
        {{
          "action": "function" | "finish",
          "name": "<имя функции>",
          "args": {{...}} | null,
          "final_text": str | null
        }}
        """

        action = await call_llm([
            {"role": "system", "content":
                f"Ты — автор научно-популярного блога, который хорошо исследует связи между статьями и пишет посты."
                f"Ты получаешь задачу: {user_goal}"
                f"Для решения задачи тебе доступны функции в формате JSON Schema:"
                f"{json.dumps({k: {"description": v["description"], "parameters": v["parameters"]} for k, v in FUNCTIONS.items()}, ensure_ascii=False, indent=2)}"},
            {"role": "user", "content": prompt}
        ],
        model='gpt-5-mini')

        # 2. Парсим
        try:
            parsed = action
            pprint(f'Step #{turn}.'
                   f' Model requested:'
                   f' {parsed}')
            print("===================")
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
