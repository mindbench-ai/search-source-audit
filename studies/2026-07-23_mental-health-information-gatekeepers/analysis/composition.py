"""Source-type composition and its comparisons across surfaces and conditions."""
from __future__ import annotations

import collections
import statistics

from .load import TYPE_ORDER, pct


def type_shares(citations: list[dict]) -> dict[str, float]:
    """% of citations per source type, over the nine-category typology."""
    counts = collections.Counter(r["source_type"] for r in citations)
    return {t: pct(counts.get(t, 0), len(citations)) for t in TYPE_ORDER}


def share_difference(a: dict[str, float], b: dict[str, float]) -> tuple[float, float]:
    """(mean, max) absolute percentage-point difference across the typology."""
    diffs = [abs(a[t] - b[t]) for t in TYPE_ORDER]
    return statistics.mean(diffs), max(diffs)


def variant_shift(citations: list[dict]) -> dict[str, float]:
    """Percentage-point change in each type's share, sourced minus naked."""
    naked = type_shares([r for r in citations if r["variant"] == "naked"])
    sourced = type_shares([r for r in citations if r["variant"] == "sourced"])
    return {t: sourced[t] - naked[t] for t in TYPE_ORDER}
