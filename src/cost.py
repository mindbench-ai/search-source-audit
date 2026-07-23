# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 MindBench.ai

"""Cost accounting, driven by an optional local pricing.json.

pricing.json is deliberately NOT committed. Vendor prices change often, and a
stale table is worse than no table: it yields a confident number that is quietly
wrong. Copy pricing.example.json, fill in prices you have just checked, and keep
it local.

Everything here degrades rather than fails when prices are missing or partial.
Token counts and call counts -- which never go stale -- remain available, so a
run with no pricing.json still reports the measurements you would multiply by
current prices yourself.

Cost is computed from *measured* token usage, never from prompt length. Some
providers inject retrieved search content into the billed prompt, so a grounded
call's input token count can bear no relation to the question asked.
"""

from __future__ import annotations

import datetime
import functools

import paths
import providers

# Beyond this, a price table is treated as untrustworthy and callers warn loudly.
STALE_AFTER_DAYS = 90


@functools.lru_cache(maxsize=1)
def _pricing() -> dict:
    return paths.load_pricing()


def have_pricing() -> bool:
    return bool(_pricing().get("token_prices") or _pricing().get("search_fees"))


def prices_retrieved() -> str:
    return _pricing().get("retrieved", "unknown")


def pricing_age_days() -> int | None:
    """Days since the price table was checked. None if undated or unparseable."""
    raw = _pricing().get("retrieved")
    if not raw:
        return None
    try:
        when = datetime.date.fromisoformat(str(raw))
    except ValueError:
        return None
    return (datetime.date.today() - when).days


def pricing_warning() -> str | None:
    """A one-line caveat to print above any dollar figure, or None if prices are fresh."""
    if not have_pricing():
        return (
            f"No pricing.json found, so dollar figures are unavailable. "
            f"Token and call counts below are exact. To get costs, copy "
            f"{paths.PRICING_EXAMPLE.name} to {paths.PRICING.name} and fill in current prices."
        )
    age = pricing_age_days()
    if age is None:
        return (
            f"{paths.PRICING.name} has no valid `retrieved` date; its age cannot be "
            f"checked. Verify the prices before trusting any figure below."
        )
    if age > STALE_AFTER_DAYS:
        return (
            f"{paths.PRICING.name} was last checked {age} days ago "
            f"({prices_retrieved()}). Vendor prices change often -- re-check them "
            f"before trusting any figure below."
        )
    return None


def token_price(model_id: str) -> dict | None:
    return (_pricing().get("token_prices") or {}).get(model_id)


def search_fee(provider_name: str) -> dict:
    return (_pricing().get("search_fees") or {}).get(provider_name) or {}


def free_search_allowance(provider_name: str) -> int:
    return int(search_fee(provider_name).get("free_per_month") or 0)


def usage_from_raw(provider_name: str, raw: dict) -> dict:
    """Normalize a provider's usage block to {input_tokens, output_tokens}."""
    provider = providers.PROVIDERS.get(provider_name)
    if not provider:
        return {"input_tokens": 0, "output_tokens": 0}
    try:
        return provider.usage(raw)
    except Exception:  # noqa: BLE001 - accounting must never break a run
        return {"input_tokens": 0, "output_tokens": 0}


def cost_of(provider_name: str, model_id: str, raw: dict, searched: bool) -> float:
    """USD for a single call.

    A provider that reports its own billed total takes precedence over the local
    price table. Batch-level free allowances are NOT applied here -- this is the
    marginal list price for one call; estimate.py applies allowances, since
    headroom is a property of the batch.

    Returns 0.0 for a model absent from pricing.json rather than raising, so an
    unpriced model degrades the estimate instead of stopping the sweep. Callers
    that care should check unpriced_models() up front.
    """
    provider = providers.PROVIDERS.get(provider_name)
    if provider:
        try:
            reported = provider.reported_cost(raw)
        except Exception:  # noqa: BLE001
            reported = None
        if reported is not None:
            return reported

    price = token_price(model_id)
    if not price:
        return 0.0

    u = usage_from_raw(provider_name, raw)
    total = (
        u["input_tokens"] / 1_000_000 * price["input"]
        + u["output_tokens"] / 1_000_000 * price["output"]
    )
    if searched:
        per_call = search_fee(provider_name).get("per_call")
        if per_call:
            total += float(per_call)
    return total


def unpriced_models(model_keys: list[str]) -> list[str]:
    """Active models with no pricing.json entry, so callers can warn up front."""
    models = providers.load_models()
    missing = []
    for key in model_keys:
        spec = models.get(key)
        if not spec:
            continue
        provider = providers.PROVIDERS.get(spec["provider"])
        # A provider that reports its own cost needs no local price entry.
        if provider and type(provider).reported_cost is not providers.Provider.reported_cost:
            continue
        if not token_price(spec["model_id"]):
            missing.append(f"{key} ({spec['model_id']})")
    return missing
