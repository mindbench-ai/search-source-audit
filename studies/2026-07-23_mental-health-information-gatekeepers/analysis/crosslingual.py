"""Cross-lingual routing: how often citations land on language-appropriate sources.

Two measures per citation, both shipped as columns on the tables:
`is_local_source` (the domain sits on a ccTLD of a country where the query
language is spoken) and `lang_appropriate` (that, or the URL carries a
native-language signal such as a path locale or percent-encoded native script).
"""
from __future__ import annotations

from .load import pct, truthy


def routing_rates(citations: list[dict]) -> dict[str, float]:
    """{'cctld': %, 'lang_appropriate': %} over the given citations."""
    return {
        "cctld": pct(sum(truthy(r["is_local_source"]) for r in citations), len(citations)),
        "lang_appropriate": pct(sum(truthy(r["lang_appropriate"]) for r in citations),
                                len(citations)),
    }
