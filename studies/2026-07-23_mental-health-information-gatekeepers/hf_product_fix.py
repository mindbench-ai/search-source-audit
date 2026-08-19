"""Repair concatenated-URL rows in the product-arm CSVs.

A row whose url field holds two URLs pasted together with no separator
("https://a.org/pagehttps://b.org/page") is one of three cases:

  SPLIT. Both halves are complete, distinct URLs: two citations recorded in
      one field. The row becomes two rows, positions renumbered within the
      cell, and each half is derived independently - host/domain/tld,
      classifier columns via source_classifier.py, locality and language
      flags, has_utm.

  KEEP-COMPLETE. The halves are one citation pasted twice: a bare scheme+host
      followed by the full URL of the same host, or the identical URL twice.
      The complete URL is kept.

  URL-IN-PARAMETER. A second scheme preceded by '=' or '?' sits inside a
      query parameter of a single valid URL. The row is left as is.

Splitting changes citation totals. product_fix_report.json lists every row
touched, and the affected response rows are rebuilt (n_sources,
n_unique_domains, n_valid_urls, the n_type_* counts, n_local_source,
n_lang_appropriate, source_urls, source_domains). All other rows in both
files stay byte-identical. --no-split limits the repair to KEEP-COMPLETE
rows.

Left as recorded: "http://v" and "http://msdmanuals" (flagged
is_valid_url=FALSE; the intended URLs are unrecoverable) and annotator notes
inside prompt_text.

Usage (from the study directory):
    python3 hf_product_fix.py --released results/hf/released [--out results/hf/corrected] [--no-split]

Stdlib only, deterministic, offline.
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

CONCAT = re.compile(r"^(https?://\S*?)(https?://\S+)$")

TYPE_COLS = {
    "government/public": "n_type_government_public",
    "academic/journal": "n_type_academic_journal",
    "nonprofit health system": "n_type_nonprofit_health_system",
    "commercial health": "n_type_commercial_health",
    "nonprofit/advocacy": "n_type_nonprofit_advocacy",
    "encyclopedia (wiki)": "n_type_encyclopedia_wiki",
    "news/media": "n_type_news_media",
    "social/video": "n_type_social_video",
    "other": "n_type_other",
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def truthy(v):
    return str(v).strip().lower() in ("true", "1")


def classify_concat(url: str) -> tuple[str, str, str] | None:
    """(case, first, second) for a concatenated url, or None if not corrupt."""
    m = CONCAT.match(url)
    if not m:
        return None
    if url[m.start(2) - 1] in ("=", "?"):
        return None  # URL inside a query parameter - a valid single URL
    a, b = m.group(1), m.group(2)
    host_a = (urlparse(a).netloc or "").lower()
    host_b = (urlparse(b).netloc or "").lower()
    path_a = urlparse(a).path.strip("/")
    if a == b or (host_a == host_b and not path_a):
        return ("keep-complete", a, b)
    return ("split", a, b)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--released", type=pathlib.Path, default=RESULTS / "hf" / "released")
    ap.add_argument("--out", type=pathlib.Path, default=RESULTS / "hf" / "corrected")
    ap.add_argument("--no-split", action="store_true",
                    help="repair only duplicate-pastes; leave two-citation rows unsplit")
    args = ap.parse_args()

    src_fields, src_rows = read_csv(args.released / "product_sources_annotated.csv")
    resp_fields, resp_rows = read_csv(args.released / "product_sources_responses.csv")

    # Vocabularies harvested from the intact rows themselves.
    suffixes = {r["tld"] for r in src_rows if r["tld"]}
    tld_bucket = {r["tld"]: r["tld_bucket"] for r in src_rows if r["tld"] and r["tld_bucket"]}
    cc = collections.defaultdict(set)
    for r in src_rows:
        if r["language"] != "en" and truthy(r["is_local_source"]) and r["tld"]:
            cc[r["language"]].add(r["tld"].split(".")[-1])

    # The file's source-type assignments include per-domain review beyond the
    # rule classifier, so a repaired row inherits the file's own assignment:
    # by host first (nih.gov and google.com type differently by host), then by
    # domain, then the classifier for domains the file does not carry.
    def modal(counter):
        return counter.most_common(1)[0][0]

    host_type = collections.defaultdict(collections.Counter)
    domain_type = collections.defaultdict(collections.Counter)
    for r in src_rows:
        if r["source_type"]:
            if r["host"]:
                host_type[r["host"]][(r["source_type"], r["type_rule"])] += 1
            if r["domain"]:
                domain_type[r["domain"]][(r["source_type"], r["type_rule"])] += 1

    def derive(row: dict, url: str) -> dict:
        """A fresh row for `url`, metadata copied from the annotator's row."""
        host = (urlparse(url).netloc or "").lower().split(":")[0]
        host = host[4:] if host.startswith("www.") and len(host) > 4 else host
        labels = host.split(".")
        domain, tld = host, labels[-1]
        for k in range(len(labels) - 1, 0, -1):
            cand = ".".join(labels[-k:])
            if cand in suffixes:
                domain = ".".join(labels[-(k + 1):]) if k < len(labels) else cand
                tld = cand
                break
        if host in host_type:
            stype, rule = modal(host_type[host])
        elif domain in domain_type:
            stype, rule = modal(domain_type[domain])
        else:
            stype, rule = classify_type(host, domain, tld)
        lang = row["language"]
        local = tld.split(".")[-1] in cc.get(lang, set())
        signal = any(re.search(p, url.lower()) for p in SIG.get(lang, []))
        out = dict(row)
        out.update({
            "url": url, "host": host, "domain": domain, "tld": tld,
            "tld_bucket": tld_bucket.get(tld, f".{tld}"),
            "is_valid_url": "TRUE",
            "source_type": stype, "type_rule": rule,
            "is_local_source": str(local).upper(),
            "lang_signal": str(signal).upper(),
            "lang_appropriate": str(local or signal).upper(),
            "has_utm": str("utm_" in url.lower()).upper(),
        })
        return out

    fixed = {"split": [], "keep-complete": [], "skipped-url-in-query": []}
    out_rows: list[dict] = []
    touched_cells: set[str] = set()
    for r in src_rows:
        verdict = classify_concat(r["url"])
        if verdict is None:
            if CONCAT.match(r["url"]):
                fixed["skipped-url-in-query"].append(r["url"])
            out_rows.append(r)
            continue
        case, a, b = verdict
        if case == "keep-complete":
            out_rows.append(derive(r, b))
            fixed["keep-complete"].append({"cell": r["cell_id"], "kept": b, "dropped_fragment": a})
            touched_cells.add(r["cell_id"])
        elif args.no_split:
            out_rows.append(r)
        else:
            out_rows.append(derive(r, a))
            out_rows.append(derive(r, b))
            fixed["split"].append({"cell": r["cell_id"], "first": a, "second": b})
            touched_cells.add(r["cell_id"])

    # Renumber positions within touched cells, preserving order of appearance.
    counters: collections.Counter = collections.Counter()
    for r in out_rows:
        if r["cell_id"] in touched_cells:
            counters[r["cell_id"]] += 1
            r["source_position"] = str(counters[r["cell_id"]])

    # Rebuild the touched cells' response rows.
    by_cell = collections.defaultdict(list)
    for r in out_rows:
        by_cell[r["cell_id"]].append(r)
    for resp in resp_rows:
        if resp["cell_id"] not in touched_cells:
            continue
        rows = sorted(by_cell[resp["cell_id"]], key=lambda x: int(x["source_position"]))
        resp["n_sources"] = str(len(rows))
        resp["n_unique_domains"] = str(len({x["domain"] for x in rows if x["domain"]}))
        resp["n_valid_urls"] = str(sum(1 for x in rows if truthy(x["is_valid_url"])))
        resp["n_local_source"] = str(sum(1 for x in rows if truthy(x["is_local_source"])))
        resp["n_lang_appropriate"] = str(sum(1 for x in rows if truthy(x["lang_appropriate"])))
        counts = collections.Counter(x["source_type"] for x in rows)
        for cat, col in TYPE_COLS.items():
            resp[col] = str(counts.get(cat, 0))
        resp["source_urls"] = " || ".join(x["url"] for x in rows)
        resp["source_domains"] = " || ".join(x["domain"] for x in rows if x["domain"])

    write_csv(args.out / "product_sources_annotated.csv", src_fields, out_rows)
    write_csv(args.out / "product_sources_responses.csv", resp_fields, resp_rows)

    report = {
        "rows_in": len(src_rows), "rows_out": len(out_rows),
        "cells_touched": sorted(touched_cells),
        "repairs": fixed,
        "left_as_recorded": [
            "http://v and http://msdmanuals (correctly flagged is_valid_url=FALSE)",
            "prompt_text annotator notes",
            "boolean casing TRUE/FALSE",
        ],
    }
    (args.out / "product_fix_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"rows {len(src_rows)} -> {len(out_rows)} "
          f"({len(fixed['split'])} split, {len(fixed['keep-complete'])} deduplicated, "
          f"{len(fixed['skipped-url-in-query'])} url-in-query left alone); "
          f"{len(touched_cells)} response rows rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
