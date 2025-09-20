from __future__ import annotations

import os
import json
from typing import Dict, List, Optional

from openai import AsyncOpenAI

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot call LLM")
    _client = AsyncOpenAI(api_key=api_key)
    return _client


async def call_llm(
    messages: List[Dict[str, str]],
    model: str = "gpt-4o-mini",
    temperature: float = 1,
    max_completions_tokens: Optional[int] = None,
):
    """Call OpenAI chat completions and return parsed content when JSON."""
    client = _get_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_completions_tokens,
    )
    content = resp.choices[0].message.content
    try:
        return json.loads(content)
    except Exception:
        return content

