from __future__ import annotations

import os

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Avoid crashing at import time in CI; raise only when used
        raise RuntimeError("OPENAI_API_KEY is not set; cannot create embeddings client")
    _client = OpenAI(api_key=api_key)
    return _client


def get_query_embedding(text: str) -> list[float]:
    """Return an embedding vector for the given text (OpenAI)."""
    client = _get_client()
    resp = client.embeddings.create(model="text-embedding-3-small", input=text)
    return resp.data[0].embedding

