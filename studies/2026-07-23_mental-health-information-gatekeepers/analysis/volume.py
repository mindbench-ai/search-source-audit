"""Citation volume: counts per response, zero-citation rates, response sizes."""
from __future__ import annotations

import statistics

from .load import pct


def mean_citations(responses: list[dict]) -> float:
    """Mean citations per response, zero-citation responses included."""
    return statistics.mean(r["n_sources"] for r in responses) if responses else 0.0


def zero_citation(responses: list[dict]) -> tuple[int, float]:
    """(count, %) of responses that cited nothing."""
    zero = sum(1 for r in responses if r["n_sources"] == 0)
    return zero, pct(zero, len(responses))


def mean_response_chars(responses: list[dict]) -> float:
    """Mean generated-text length in characters (API arm's n_chars column)."""
    return statistics.mean(int(r["n_chars"]) for r in responses) if responses else 0.0


def largest(responses: list[dict], n: int = 10) -> list[dict]:
    """The n responses with the most citations."""
    return sorted(responses, key=lambda r: -r["n_sources"])[:n]


def mean_by_variant(responses: list[dict]) -> dict[str, float]:
    """Mean citations per response under each prompt condition."""
    return {
        variant: mean_citations([r for r in responses if r["variant"] == variant])
        for variant in ("naked", "sourced")
    }
