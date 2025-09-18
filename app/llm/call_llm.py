# app/services/llm.py
import os
from typing import List, Dict, Optional
from openai import AsyncOpenAI
import json

from openai.types import ResponseFormatJSONObject
from openai.types.chat.completion_create_params import ResponseFormat

# клиент инициализируется один раз
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def call_llm(
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 1,
        max_completions_tokens: Optional[int] = None,
):
    """
    Вызов LLM модели.

    messages: список сообщений в формате [{"role": "system"/"user"/"assistant", "content": "..."}]
    model: название модели (по умолчанию gpt-4o-mini)
    temperature: креативность
    max_tokens: ограничение длины ответа
    """

    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_completions_tokens,
        # response_format={ "type": "json_object" }
    )

    content = resp.choices[0].message.content
    try:
        content = json.loads(content)
    except ValueError as e:
        return content

    return content