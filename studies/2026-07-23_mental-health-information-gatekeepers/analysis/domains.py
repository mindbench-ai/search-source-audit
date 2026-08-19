"""Domain diversity and concentration over the citation tables."""
from __future__ import annotations

import collections

from .load import pct


def distinct_domains(citations: list[dict]) -> int:
    return len({r["domain"] for r in citations if r["domain"]})


def top_share(citations: list[dict], n: int) -> float:
    """% of citations going to the n most-cited registrable domains."""
    counts = collections.Counter(r["domain"] for r in citations if r["domain"])
    return pct(sum(c for _, c in counts.most_common(n)), len(citations))


def cumulative_shares(citations: list[dict], n: int) -> list[tuple[str, float]]:
    """(domain, cumulative %) through the top n domains."""
    counts = collections.Counter(r["domain"] for r in citations if r["domain"])
    out, running = [], 0
    for domain, c in counts.most_common(n):
        running += c
        out.append((domain, pct(running, len(citations))))
    return out


def topics_citing(citations: list[dict], domain: str) -> list[tuple[str, str]]:
    """The (language, topic) pairs on which a domain was cited."""
    return sorted({(r["language"], r["topic"]) for r in citations if r["domain"] == domain})


def rows_with_url_substring(citations: list[dict], needle: str) -> list[dict]:
    return [r for r in citations if needle in r["url"]]
