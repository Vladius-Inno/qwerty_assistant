from __future__ import annotations

from typing import List


def _vec_to_pg_literal(vec: List[float]) -> str:
    """Convert Python list of floats to Postgres pgvector literal."""
    return "[" + ",".join(map(str, vec)) + "]"

__all__ = ["_vec_to_pg_literal"]

