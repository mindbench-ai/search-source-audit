"""Print the audit's reported statistics, one section per analysis area.

Usage (from the study directory):
    python3 -m analysis [--api DIR] [--product DIR] [--raw DIR]
"""
from __future__ import annotations

import argparse
import pathlib
import statistics

from .load import (COMMON_TOPICS, DEFAULT_API, DEFAULT_PRODUCT, DEFAULT_RAW,
                   LANGUAGES, PAIRS, TYPE_ORDER, load_raw, load_tables, truthy, pct)
from . import composition, crosslingual, domains, retrieval, volume


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--api", type=pathlib.Path, default=DEFAULT_API)
    ap.add_argument("--product", type=pathlib.Path, default=DEFAULT_PRODUCT)
    ap.add_argument("--raw", type=pathlib.Path, default=DEFAULT_RAW)
    a = ap.parse_args()

    t = load_tables(a.api, a.product)
    api_src, api_resp = t["api_src"], t["api_resp"]
    p_src, p_resp = t["product_src"], t["product_resp"]
    p_src_en = [r for r in p_src if r["language"] == "en"]
    api_src_en = [r for r in api_src if r["language"] == "en"]
    p_resp_en = [r for r in p_resp if r["language"] == "en"]
    api_resp_en = [r for r in api_resp if r["language"] == "en"]
    P = print

    P("== Citation volume and coverage ==")
    P(f"citations: product {len(p_src):,}   API {len(api_src):,}")
    P(f"citations/response: product {len(p_src)/len(p_resp):.1f}   API {len(api_src)/len(api_resp):.1f}")
    pz, pzr = volume.zero_citation(p_resp)
    az, azr = volume.zero_citation(api_resp)
    P(f"no-citation responses: product {pz}/{len(p_resp)} = {pzr:.1f}%   API {az}/{len(api_resp)} = {azr:.1f}%")
    for prov, label, model in PAIRS:
        pr = [r for r in p_resp if r["provider"] == prov]
        ar = [r for r in api_resp if r["model"] == model]
        P(f"  {label:18s} {volume.mean_citations(pr):5.1f} c/r, {volume.zero_citation(pr)[1]:4.1f}% no-cite"
          f"  |  {model:16s} {volume.mean_citations(ar):5.1f} c/r, {volume.zero_citation(ar)[1]:4.1f}% no-cite")
    gpt_zero = [r for r in api_resp if r["model"] == "gpt-5.4-mini" and r["n_sources"] == 0]
    P(f"gpt-5.4-mini zero-citation responses, mean chars: {volume.mean_response_chars(gpt_zero):.1f}")
    ne_src = [r for r in p_src if r["language"] != "en"]
    P(f"product EN: {len(p_src_en):,} citations, {domains.distinct_domains(p_src_en):,} domains, "
      f"{len(p_resp_en)} responses   non-EN: {len(ne_src):,} citations, "
      f"{domains.distinct_domains(ne_src):,} domains, {len(p_resp) - len(p_resp_en)} responses")
    for prov, label, _ in PAIRS:
        xs = [r["n_sources"] for r in p_resp_en if r["provider"] == prov]
        P(f"  {label:18s} EN mean {statistics.mean(xs):.2f}  SD {statistics.stdev(xs):.2f}  "
          f"median {statistics.median(xs):.0f}")
    big = volume.largest(p_resp_en, 10)
    P("largest EN product responses: " + ", ".join(f"{r['provider']}/{r['topic_category']}" for r in big))
    for prov, label, _ in PAIRS[:1]:
        en3 = [r for r in p_resp_en if r["provider"] == prov and r["topic"] in COMMON_TOPICS]
        en20 = [r for r in p_resp_en if r["provider"] == prov]
        P(f"{label} EN mean citations: {volume.mean_citations(en3):.1f} on the 3 common questions, "
          f"{volume.mean_citations(en20):.2f} on all 20")

    P("\n== Domain concentration ==")
    P(f"distinct domains: product {domains.distinct_domains(p_src):,}   API {domains.distinct_domains(api_src):,}")
    for rank, (dom, share) in enumerate(domains.cumulative_shares(p_src_en, 10), 1):
        if rank in (9, 10):
            P(f"product EN cumulative share through top {rank}: {share:.1f}%  (rank {rank}: {dom})")
    for prov, label, model in PAIRS:
        am = [r for r in api_src if r["model"] == model]
        am_en = [r for r in am if r["language"] == "en"]
        pm_en = [r for r in p_src_en if r["provider"] == prov]
        P(f"  {model:16s} {domains.distinct_domains(am):4d} domains ({domains.distinct_domains(am_en):3d} EN), "
          f"top-10 EN {domains.top_share(am_en, 10):.1f}%  |  {label}: "
          f"{domains.distinct_domains(pm_en):3d} EN, top-10 {domains.top_share(pm_en, 10):.1f}%")

    P("\n== Volume and composition by question category (English) ==")
    cats = sorted({r["topic_category"] for r in p_resp_en})
    for cat in cats:
        resp_cat = [r for r in p_resp_en if r["topic_category"] == cat]
        src_cat = [r for r in p_src_en if r["topic_category"] == cat]
        shares_cat = composition.type_shares(src_cat)
        top = max(TYPE_ORDER, key=lambda t2: shares_cat[t2])
        P(f"  {cat:24s} mean {volume.mean_citations(resp_cat):5.1f} c/r | top type {top} {shares_cat[top]:.1f}% | commercial {shares_cat['commercial health']:.1f}%")

    P("\n== Named-domain shares within each platform's English citations ==")
    for dom in ("wikipedia.org", "youtube.com"):
        row = f"  {dom:15s}"
        for prov, label, _ in PAIRS:
            sub = [r for r in p_src_en if r["provider"] == prov]
            hits = sum(1 for r in sub if r["domain"] == dom)
            row += f"  {label[:10]} {pct(hits, len(sub)):4.1f}%"
        P(row)

    P("\n== Source-type composition (English) ==")
    ps = composition.type_shares(p_src_en)
    as_ = composition.type_shares(api_src_en)
    pair_shares = {label: (composition.type_shares([r for r in p_src_en if r["provider"] == prov]),
                           composition.type_shares([r for r in api_src_en if r["model"] == model]))
                   for prov, label, model in PAIRS}
    P(f"{'':26s}{'prod':>6s}{'API':>6s}" + "".join(f"{lbl[:14]:>22s}" for _, lbl, _ in PAIRS))
    for stype in TYPE_ORDER:
        row = f"{stype:26s}{ps[stype]:6.1f}{as_[stype]:6.1f}"
        for _, label, _ in PAIRS:
            pp, aa = pair_shares[label]
            row += f"{pp[stype]:10.1f} vs {aa[stype]:5.1f}   "
        P(row)
    P("product-API share difference by pair (mean / max, pp):")
    for _, label, _ in PAIRS:
        m, mx = composition.share_difference(*pair_shares[label])
        P(f"  {label:18s} {m:.1f} / {mx:.1f}")

    P("\n== Effect of requesting sources (English) ==")
    for tag, resp in (("product", p_resp_en), ("API", api_resp_en)):
        by = volume.mean_by_variant(resp)
        P(f"{tag:8s} mean citations naked -> sourced: {by['naked']:.1f} -> {by['sourced']:.1f}")
    for tag, src in (("product", p_src_en), ("API", api_src_en)):
        shift = composition.variant_shift(src)
        P(f"{tag} share shift (pp): " + ", ".join(
            f"{t.split('/')[0].split(' ')[0]} {shift[t]:+.1f}" for t in TYPE_ORDER))

    P("\n== Cross-lingual routing ==")
    for code, name in LANGUAGES:
        pr = crosslingual.routing_rates([r for r in p_src if r["language"] == code])
        ar = crosslingual.routing_rates([r for r in api_src if r["language"] == code])
        P(f"  {name:10s} product ccTLD {pr['cctld']:5.1f} lang-approp {pr['lang_appropriate']:5.1f}"
          f"  |  API ccTLD {ar['cctld']:5.1f} lang-approp {ar['lang_appropriate']:5.1f}")
    ne = [r for r in api_src if r["language"] == "ne"]
    for model in ("sonar", "gpt-5.4-mini"):
        sub = [r for r in ne if r["model"] == model]
        rate = crosslingual.routing_rates(sub)["lang_appropriate"] if sub else 0.0
        P(f"  {model} Nepali lang-appropriate: "
          f"{sum(truthy(r['lang_appropriate']) for r in sub)}/{len(sub)} = {rate:.1f}%")

    P("\n== Retrieval invocation ==")
    oa = load_raw(a.raw, "openai-54mini.jsonl")
    k, n, r = retrieval.invocation_rate(oa, retrieval.openai_searched)
    P(f"gpt-5.4-mini web search: {k}/{n} = {r:.1f}%")
    for cond in ("naked", "sourced"):
        sub = [x for x in oa if x["variant"] == cond]
        k, n, r = retrieval.invocation_rate(sub, retrieval.openai_searched)
        sub_en = [x for x in sub if x["language"] == "en"]
        ke, ne_, re_ = retrieval.invocation_rate(sub_en, retrieval.openai_searched)
        P(f"  {cond:7s} all-language {k}/{n} = {r:.1f}%   EN {ke}/{ne_} = {re_:.1f}%")
    for cond in ("naked", "sourced"):
        xs = [x["n_sources"] for x in api_resp if x["model"] == "gpt-5.4-mini" and x["variant"] == cond]
        P(f"  gpt-5.4-mini mean citations, {cond}: {statistics.mean(xs):.2f}")
    gm = load_raw(a.raw, "gemini-35flash.jsonl")
    k, n, r = retrieval.invocation_rate(gm, retrieval.gemini_grounded)
    P(f"gemini-3.5-flash grounding: {k}/{n} = {r:.1f}%")
    for cond in ("naked", "sourced"):
        sub = [x for x in gm if x["variant"] == cond]
        k, n, r = retrieval.invocation_rate(sub, retrieval.gemini_grounded)
        P(f"  {cond:7s} {k}/{n} = {r:.1f}%")

    P("\n== Lexically anomalous citations ==")
    for dom in ("dsm-firmenich.com", "synology.com", "pcl.com", "hamiltonmusical.com"):
        P(f"  {dom}: {domains.topics_citing(p_src, dom)}")
    mayo = domains.rows_with_url_substring(p_src, "wiki/Mayonnaise")
    P(f"  wikipedia Mayonnaise: {[r['cell_id'] for r in mayo]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
