# app/services/llm.py
import os
from typing import List, Dict, Optional
from openai import AsyncOpenAI
import json

# клиент инициализируется один раз
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def call_llm(
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
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
        max_tokens=max_tokens,
    )

    content = resp.choices[0].message.content
    return json.loads(content)