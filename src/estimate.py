# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 MindBench.ai

"""Estimate what a full sweep will cost, by measuring a small sample first.

Token counts vary enormously across prompts -- longer questions retrieve more,
and non-Latin scripts tokenize worse -- so projecting from one or two calls is
unreliable. This samples across the axes most likely to move cost (language,
variant, prompt length), measures real spend, and extrapolates.

Run before any large sweep:

    python3 src/estimate.py                 # sample the active models
    python3 src/estimate.py --sample 10     # wider sample, tighter estimate
    python3 src/estimate.py --models a b    # specific models

Sampling costs money: roughly `sample x models x conditions` calls.
"""

from __future__ import annotations

import argparse
import json
import statistics

import cost as cost_mod
import paths
import providers
from runner import Cell


def stratified_sample(prompts: list[dict], n: int) -> list[dict]:
    """Pick n prompts spread across languages, variants, and text length.

    Round-robins languages so none dominates, and within a language orders by
    variant then descending length -- the longest and shortest prompts bracket
    the cost range, so hitting both makes the mean more honest.
    """
    by_lang: dict[str, list[dict]] = {}
    for p in prompts:
        by_lang.setdefault(p.get("language") or "?", []).append(p)

    for group in by_lang.values():
        group.sort(key=lambda p: (p.get("variant") or "", -len(p.get("text") or "")))

    picked: list[dict] = []
    langs = sorted(by_lang)
    target = min(n, len(prompts))
    idx = 0
    while len(picked) < target:
        progressed = False
        for lang in langs:
            group = by_lang[lang]
            if idx < len(group):
                picked.append(group[idx])
                progressed = True
                if len(picked) >= target:
                    break
        if not progressed:
            break
        idx += 1
    return picked


def main() -> None:
    cfg = paths.load_config()
    ap = argparse.ArgumentParser(description="Estimate full-sweep cost from a sample.")
    ap.add_argument("--models", nargs="+", default=cfg.get("active_models"))
    ap.add_argument("--conditions", nargs="+", default=cfg["conditions"])
    ap.add_argument("--runs", type=int, default=cfg["runs_per_prompt"],
                    help="runs per prompt in the FULL sweep being projected")
    ap.add_argument("--sample", type=int, default=6, help="prompts to sample")
    args = ap.parse_args()

    paths.ensure_data_dirs()
    prompts = json.loads(paths.PROMPTS.read_text(encoding="utf-8"))
    models = providers.load_models()
    sample = stratified_sample(prompts, args.sample)

    warning = cost_mod.pricing_warning()
    if warning:
        print(f"NOTE: {warning}\n")
    if cost_mod.have_pricing():
        unpriced = cost_mod.unpriced_models(args.models)
        if unpriced:
            print(f"WARNING: no price entry for {', '.join(unpriced)} -- "
                  f"these show as $0.00 and understate the total.\n")

    n_calls = sum(
        len(sample)
        for k in args.models
        for c in args.conditions
        if c == "search_on" or models[k].get("supports_search_off", True)
    )
    print(f"sampling {len(sample)} prompts -> {n_calls} calls\n")

    call = providers.make_caller()
    rows = []
    for model_key in args.models:
        spec = models[model_key]
        for search in args.conditions:
            if search == "search_off" and not spec.get("supports_search_off", True):
                print(f"  skip {model_key} search_off (supports_search_off: false)")
                continue
            for p in sample:
                try:
                    rec = call(Cell(model_key, search, p["prompt_id"], 1), p)
                except Exception as exc:  # noqa: BLE001
                    print(f"  FAIL {model_key} {search} {p['prompt_id']}: {str(exc)[:90]}")
                    continue
                c = cost_mod.cost_of(
                    spec["provider"], spec["model_id"], rec["raw"], search == "search_on"
                )
                u = cost_mod.usage_from_raw(spec["provider"], rec["raw"])
                rows.append({"model_key": model_key, "provider": spec["provider"],
                             "search": search, "prompt_id": p["prompt_id"], "cost": c,
                             "n_sources": len(rec["structured_sources"]), **u})
                print(f"  {model_key:16}{search:11}{p['prompt_id'][:30]:32}"
                      f"${c:.5f} in={u['input_tokens']:6} out={u['output_tokens']:5} "
                      f"src={len(rec['structured_sources']):3}")

    if not rows:
        print("\nno successful calls; nothing to project")
        return

    paths.ESTIMATE_OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    cells_per_arm = len(prompts) * args.runs
    # Some providers report their own billed cost, which is accurate with or
    # without a local price table -- so show the dollar summary whenever any
    # real cost data exists, not only when pricing.json is present.
    priced = cost_mod.have_pricing() or any(r["cost"] > 0 for r in rows)

    # Token and call counts are exact regardless of pricing, and stay valid long
    # after any price table has gone stale. They are the primary output; dollars
    # are a convenience layer over them.
    print("\n" + "=" * 88)
    print(f"{'model':16}{'condition':12}{'calls':>8}{'in tok/call':>13}"
          f"{'out tok/call':>13}{'total in':>12}{'total out':>12}{'src':>7}")
    print("-" * 88)

    totals = {"calls": 0, "in": 0, "out": 0}
    arms = []
    for model_key in args.models:
        for search in args.conditions:
            sub = [r for r in rows
                   if r["model_key"] == model_key and r["search"] == search]
            if not sub:
                continue
            mean_in = statistics.mean(r["input_tokens"] for r in sub)
            mean_out = statistics.mean(r["output_tokens"] for r in sub)
            tot_in, tot_out = mean_in * cells_per_arm, mean_out * cells_per_arm
            totals["calls"] += cells_per_arm
            totals["in"] += tot_in
            totals["out"] += tot_out
            arms.append((model_key, search, sub))
            print(f"{model_key:16}{search:12}{cells_per_arm:>8}{mean_in:>13,.0f}"
                  f"{mean_out:>13,.0f}{tot_in:>12,.0f}{tot_out:>12,.0f}"
                  f"{statistics.mean(r['n_sources'] for r in sub):>7.1f}")
    print("-" * 88)
    print(f"{'TOTAL':28}{totals['calls']:>8}{'':13}{'':13}"
          f"{totals['in']:>12,.0f}{totals['out']:>12,.0f}")
    print("=" * 88)

    if not priced:
        print(f"Projects {len(prompts)} prompts x {args.runs} runs per arm.")
        print("Multiply the token totals by current vendor prices, and add each "
              "provider's\nper-search-call fee x its call count, for a dollar figure.")
        return

    print(f"\n{'model':16}{'condition':12}{'mean $/call':>14}{'projected':>13}")
    print("-" * 55)
    grand = 0.0
    grounded_by_provider: dict[str, int] = {}
    for model_key, search, sub in arms:
        mean = statistics.mean(r["cost"] for r in sub)
        projected = mean * cells_per_arm
        grand += projected
        if search == "search_on":
            prov = sub[0]["provider"]
            grounded_by_provider[prov] = grounded_by_provider.get(prov, 0) + cells_per_arm
        print(f"{model_key:16}{search:12}${mean:>13.5f}${projected:>12.2f}")

    print("-" * 55)
    print(f"{'list price':28}{'':14}${grand:>12.2f}")

    # Free allowances are batch-level, so they are applied once per provider
    # here rather than inside the per-call cost.
    net = grand
    for prov, calls in grounded_by_provider.items():
        allowance = cost_mod.free_search_allowance(prov)
        per_call = cost_mod.search_fee(prov).get("per_call")
        if not allowance or not per_call:
            continue
        covered = min(calls, allowance)
        rebate = covered * float(per_call)
        net -= rebate
        print(f"{prov + ' free tier':28}{covered:>14}$-{rebate:>11.2f}")
    if net != grand:
        print(f"{'NET':28}{'':14}${net:>12.2f}")
    print("-" * 55)
    print(f"Projects {len(prompts)} prompts x {args.runs} runs per arm.")
    print(f"Sample is {len(sample)} prompts; treat as +/-30%, not a quote.")
    if cost_mod.have_pricing():
        print(f"Prices last checked {cost_mod.prices_retrieved()}.")
    else:
        print("No pricing.json: figures above come only from providers that report\n"
              "their own billed cost. Any other model shows $0.00.")


if __name__ == "__main__":
    main()
