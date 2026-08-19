"""Build the API-arm CSVs for the HuggingFace dataset release.

Reads an input pair of API tables (--released) plus this folder's results/
and writes the release pair (--out). Three transformations:

  1. Topic vocabulary. The API and product instruments name eight of the twenty
     English topics differently; the product slugs and their functional
     categories are canonical. Topics go through the crosswalk below (each
     pair is the identical question) and every row carries a topic_category.

  2. Citation channels. Gemini cites two ways: structured groundingChunks
     metadata, and markdown links written into the response prose (the
     `linked_intext` channel in results/sources.json). Both become rows, with a
     `channel` column ("structured" / "in_text"), so either definition of a
     citation can be selected downstream.

  3. Redirect resolution. Gemini returns citation URLs as opaque redirects via
     vertexaisearch.cloud.google.com. `resolved_url` carries the destination
     recorded in results/redirect_cache.json, populated exactly where a
     resolution exists; `url` stays as returned.

Host and domain follow the product arm's conventions: hosts carry no leading
www, and a site living directly on a public suffix has domain == tld.

In-text rows are typed with source_classifier.py, the same rules that type
the product arm. Suffix, bucket, and locality vocabularies come from the input
API file at runtime, and the locality rule must reproduce every input row
before it labels a new one.

Usage (from the study directory):
    python3 hf_api_export.py --released results/hf/released [--out results/hf/corrected]

  --released holds the input api_sources_annotated.csv and api_responses.csv.
  Output goes under the gitignored results/ tree, with an export_report.json
  recording every count changed and every fallback taken.

Deterministic and offline: no network, no model, stdlib only.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from source_classifier import SIG, classify_type  # noqa: E402

STUDY = pathlib.Path(__file__).resolve().parent
RESULTS = STUDY / "results"

REDIRECT_HOST = "vertexaisearch.cloud.google.com"

# API-instrument topic slug -> product-arm slug (canonical). Each pair is the
# identical question, matched on question text; the twelve other topics
# already share slugs.
TOPIC_XWALK = {
    "meds-depression": "med-depression",            # What medications are there for Depression?
    "meds-anxiety": "med-anxiety",                  # What medications are there for Anxiety?
    "meds-schizophrenia": "med-schizophrenia",      # What medications are there for Schizophrenia?
    "sx-anxiety": "symptoms-anxiety",               # What are the symptoms of anxiety?
    "sx-bipolar": "symptoms-bipolar",               # What are the symptoms of bipolar disorder?
    "sideeffects-ssri": "side-effects-ssri",        # What are the side effects of SSRIs?
    "firstline-antidepressants": "first-line-antidepressant",  # first-line treatment for depression
    "ptsd-guidelines": "tx-ptsd",                   # How is PTSD treated according to clinical guidelines?
}

# Product-arm topic -> functional category, copied from product_sources_*.csv.
TOPIC_CATEGORY = {
    "med-depression": "medications",
    "med-anxiety": "medications",
    "med-schizophrenia": "medications",
    "dx-depression": "diagnosis",
    "dx-anxiety": "diagnosis",
    "dx-ptsd": "diagnosis",
    "signs-depression": "signs/symptoms",
    "signs-ocd": "signs/symptoms",
    "symptoms-anxiety": "signs/symptoms",
    "symptoms-bipolar": "signs/symptoms",
    "eff-clozapine": "treatment effectiveness",
    "eff-exposure-ocd": "treatment effectiveness",
    "eff-cbt-anxiety": "treatment effectiveness",
    "crisis-psychosis": "crisis resources",
    "crisis-mania": "crisis resources",
    "crisis-suicide": "crisis resources",
    "trustworthy-sources": "trustworthy sources",
    "side-effects-ssri": "side effects",
    "first-line-antidepressant": "treatment guidelines",
    "tx-ptsd": "treatment guidelines",
}


def read_csv(path: pathlib.Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: pathlib.Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "1")


def parse_host(url: str) -> str:
    """Hostname, lowercased, port stripped, leading www. stripped (product convention)."""
    host = (urlparse(url).netloc or "").lower().split(":")[0].strip(".")
    return host[4:] if host.startswith("www.") and len(host) > 4 else host


def split_suffix(host: str, suffixes: set[str], report: dict) -> tuple[str, str]:
    """(registrable domain, public suffix) via longest match over the harvested
    suffix vocabulary; falls back to the last label and reports the miss."""
    labels = host.split(".")
    for k in range(len(labels) - 1, 0, -1):
        cand = ".".join(labels[-k:])
        if cand in suffixes and k < len(labels):
            return ".".join(labels[-(k + 1):]), cand
    if host in suffixes:  # site directly on a public suffix: domain == tld
        return host, host
    report["suffix_fallbacks"].append(host)
    return ".".join(labels[-2:]) if len(labels) >= 2 else host, labels[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--released", type=pathlib.Path, default=RESULTS / "hf" / "released")
    ap.add_argument("--out", type=pathlib.Path, default=RESULTS / "hf" / "corrected")
    args = ap.parse_args()

    report: dict = {"suffix_fallbacks": [], "bucket_fallbacks": []}

    src_fields, src_rows = read_csv(args.released / "api_sources_annotated.csv")
    resp_fields, resp_rows = read_csv(args.released / "api_responses.csv")
    local = json.loads((RESULTS / "sources.json").read_text(encoding="utf-8"))
    cache = json.loads((RESULTS / "redirect_cache.json").read_text(encoding="utf-8"))
    local_by_cell = {r["cell_id"]: r for r in local}

    if len(resp_rows) != len(local) or {r["cell_id"] for r in resp_rows} != set(local_by_cell):
        raise SystemExit("input api_responses.csv does not cover the run's 1,140 cells")

    # ---- vocabularies taken from the input file itself ----------------------------
    suffixes = {r["tld"] for r in src_rows if r["tld"]}
    tld_bucket = {r["tld"]: r["tld_bucket"] for r in src_rows if r["tld"] and r["tld_bucket"]}
    cc: dict[str, set[str]] = collections.defaultdict(set)
    for r in src_rows:
        if r["language"] != "en" and truthy(r["is_local_source"]) and r["tld"]:
            cc[r["language"]].add(r["tld"].split(".")[-1])

    # The locality rule must reproduce every input row before it labels a new one.
    bad = sum(
        1
        for r in src_rows
        if r["language"] != "en"
        and truthy(r["is_local_source"])
        != ((r["tld"].split(".")[-1] if r["tld"] else "") in cc.get(r["language"], set()))
    )
    if bad:
        raise SystemExit(f"is_local rule fails on {bad} input rows - inspect before exporting")

    # Redirect destinations, from the cache first; sources.json fills tokens
    # the cache misses.
    resolved: dict[str, str] = {
        u: v["resolved"] for u, v in cache.items() if isinstance(v, dict) and v.get("resolved")
    }
    for rec in local:
        for s in rec.get("sources") or []:
            if s.get("raw_url") and s.get("url") and s["url"] != s["raw_url"]:
                resolved.setdefault(s["raw_url"], s["url"])

    # ---- normalize the input citation rows ----------------------------------------
    n = collections.Counter()
    by_cell: dict[str, list[dict]] = collections.defaultdict(list)
    for r in src_rows:
        r = dict(r)
        if r["topic"] in TOPIC_XWALK:
            r["topic"] = TOPIC_XWALK[r["topic"]]
            n["topics_renamed"] += 1
        if not r["topic_category"]:
            r["topic_category"] = TOPIC_CATEGORY[r["topic"]]
            n["categories_filled"] += 1
        if REDIRECT_HOST in r["url"] and not r["resolved_url"]:
            dest = resolved.get(r["url"], "")
            r["resolved_url"] = dest
            n["resolved_backfilled" if dest else "resolved_unavailable"] += 1
        elif r["resolved_url"] and r["resolved_url"] == r["url"]:
            r["resolved_url"] = ""  # a copy is not a resolution
            n["resolved_copies_blanked"] += 1
        if r["host"].startswith("www.") and r["host"][4:] == r["tld"]:
            r["host"] = r["tld"]
            r["domain"] = r["tld"]
            n["suffix_sites_normalized"] += 1
        r["channel"] = "structured"
        by_cell[r["cell_id"]].append(r)

    # ---- pass 2: append the in-text rows -----------------------------------------
    resp_by_cell = {r["cell_id"]: r for r in resp_rows}
    for cell_id, rec in local_by_cell.items():
        intext = [s for s in (rec.get("sources") or []) if s["channel"] == "linked_intext"]
        if not intext:
            continue
        meta = resp_by_cell[cell_id]
        topic = TOPIC_XWALK.get(meta["topic"], meta["topic"])
        pos = len(by_cell[cell_id])
        for s in intext:
            pos += 1
            as_written = s.get("raw_url") or s["url"]
            dest = s["url"] if s.get("raw_url") and s["url"] != s["raw_url"] else ""
            host = parse_host(dest or as_written)
            domain, tld = split_suffix(host, suffixes, report)
            if tld not in tld_bucket:
                is_cc = len(tld.split(".")[-1]) == 2
                tld_bucket[tld] = f".{tld}" + (" (ccTLD)" if is_cc else "")
                report["bucket_fallbacks"].append(tld)
            source_type, type_rule = classify_type(host, domain, tld)
            lang = meta["language"]
            local_src = tld.split(".")[-1] in cc.get(lang, set())
            signal = any(re.search(p, as_written.lower()) for p in SIG.get(lang, []))
            by_cell[cell_id].append({
                "model": meta["model"], "provider": meta["provider"],
                "model_id": meta["model_id"], "language": lang,
                "variant": meta["variant"], "topic": topic,
                "run_index": meta["run_index"], "cell_id": cell_id,
                "source_position": str(pos), "url": as_written,
                "host": host, "domain": domain, "tld": tld,
                "language_name": meta["language_name"],
                "variant_label": meta["variant_label"],
                "topic_category": TOPIC_CATEGORY[topic],
                "source_type": source_type, "type_rule": type_rule,
                "tld_bucket": tld_bucket[tld],
                "is_local_source": str(local_src),
                "lang_signal": str(signal),
                "lang_appropriate": str(local_src or signal),
                "resolved_url": dest, "channel": "in_text",
            })
            n["intext_added"] += 1

    # ---- assemble, in the input response-row order ---------------------------------
    out_src = [row for r in resp_rows for row in by_cell.get(r["cell_id"], [])]
    out_resp = []
    for r in resp_rows:
        r = dict(r)
        if r["topic"] in TOPIC_XWALK:
            r["topic"] = TOPIC_XWALK[r["topic"]]
        if not r["topic_category"]:
            r["topic_category"] = TOPIC_CATEGORY[r["topic"]]
        rows = by_cell.get(r["cell_id"], [])
        r["n_sources"] = str(len(rows))
        r["n_unique_domains"] = str(len({x["domain"] for x in rows if x["domain"]}))
        r["has_sources"] = str(bool(rows))
        out_resp.append(r)

    # ---- invariants ---------------------------------------------------------------
    assert len(out_src) == len(src_rows) + n["intext_added"]
    untouched = [f for f in src_fields if f not in
                 ("topic", "topic_category", "resolved_url", "host", "domain")]
    structured = [r for r in out_src if r["channel"] == "structured"]
    assert len(structured) == len(src_rows)
    for old, new in zip(src_rows, structured):
        assert all(old[f] == new[f] for f in untouched), old["cell_id"]
    assert all(r["topic_category"] for r in out_src) and all(r["topic_category"] for r in out_resp)
    assert sorted({r["topic_category"] for r in out_src}) == sorted(set(TOPIC_CATEGORY.values()))

    write_csv(args.out / "api_sources_annotated.csv", src_fields + ["channel"], out_src)
    write_csv(args.out / "api_responses.csv", resp_fields, out_resp)

    n["rows_out"] = len(out_src)
    n["zero_citation_responses"] = sum(1 for r in out_resp if r["has_sources"] == "False")
    per_model = collections.Counter(r["model"] for r in out_src)
    report.update(counts=dict(n), citations_per_model=dict(per_model))
    (args.out / "export_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for k, v in sorted(n.items()):
        print(f"{k:28s} {v:6,}")
    print(f"{'per model':28s} {dict(per_model)}")
    if report["suffix_fallbacks"] or report["bucket_fallbacks"]:
        print(f"fallbacks to eyeball -> {args.out / 'export_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
