"""Retrieval invocation, read from the raw API responses.

Whether a model chose to search is not in the citation tables: an OpenAI
response that searched carries a web_search_call item in its Responses-API
output list, and a Gemini response that grounded carries groundingMetadata
with a non-empty groundingChunks. Perplexity's sonar always retrieves.
"""
from __future__ import annotations

from .load import pct


def openai_searched(record: dict) -> bool:
    items = record["raw"].get("output") or []
    return any("web_search" in str(item.get("type", "")) for item in items)


def gemini_grounded(record: dict) -> bool:
    candidate = (record["raw"].get("candidates") or [{}])[0]
    metadata = candidate.get("groundingMetadata") or {}
    return bool(metadata.get("groundingChunks"))


def invocation_rate(records: list[dict], detector) -> tuple[int, int, float]:
    """(invoked, total, %) under the given detector."""
    invoked = sum(1 for r in records if detector(r))
    return invoked, len(records), pct(invoked, len(records))
