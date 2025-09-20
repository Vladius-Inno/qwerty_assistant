"""Compatibility façade that re-exports article service functions.

This preserves existing import paths while organizing implementation
into focused modules following SRP and DRY principles.
"""

from .articles_read import get_article, fetch_articles, list_articles  # noqa: F401
from .articles_related import get_related_articles  # noqa: F401
from .articles_topics import get_topic_timeline, get_top_articles_by_topic  # noqa: F401
from .utils import _vec_to_pg_literal  # noqa: F401

__all__ = [
    "get_article",
    "fetch_articles",
    "list_articles",
    "get_related_articles",
    "get_topic_timeline",
    "get_top_articles_by_topic",
    "_vec_to_pg_literal",
]

