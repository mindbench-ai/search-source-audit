"""Normalize prompt_text in the product-arm CSVs and extract annotator notes.

prompt_text records the question as submitted. Annotator working notes - run
tallies, observations, truncated pastes - appear inside the column on some
rows. For each (language, topic, variant) the canonical prompt is the most
frequent recorded value; rows with any other value are rewritten to it, and
the recorded value is preserved in a notes file:

  annotator_notes.csv - one row per changed cell: cell_id, recorded_text,
      canonical_text, note_fragment (the recorded text minus the canonical
      question, where one contains the other).

Rows in the sourced condition whose recorded text carries no source-request
suffix are listed separately in the report (suffix_missing): the record
cannot distinguish a lazy transcription from a prompt actually submitted
without the suffix, so these rows need review before the rewrite is applied.

Without --write, only the report and notes file are produced; the CSVs are
untouched. With --write, prompt_text is rewritten in both product files.

Usage (from the study directory):
    python3 hf_prompt_normalize.py [--released DIR] [--out DIR] [--write]

Reads the product CSVs from --out when present there (chaining after
hf_product_fix.py), else from --released. Stdlib only, deterministic.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib

STUDY = pathlib.Path(__file__).resolve().parent
RESULTS = STUDY / "results"

SUFFIX_MARKERS = ("list your sources", "fuente", "情報源", "джерел", "स्रोत",
                  "स्रोतहरू", "wo nsɛm", "sources")


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


def note_fragment(recorded: str, canonical: str) -> str:
    """The recorded text minus the canonical question, where separable."""
    if canonical in recorded:
        return recorded.replace(canonical, "", 1).strip(" -\n\t")
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--released", type=pathlib.Path, default=RESULTS / "hf" / "released")
    ap.add_argument("--out", type=pathlib.Path, default=RESULTS / "hf" / "corrected")
    ap.add_argument("--write", action="store_true",
                    help="rewrite prompt_text in the product CSVs under --out")
    args = ap.parse_args()

    def source_dir(name):
        return args.out if (args.out / name).exists() else args.released

    resp_path = source_dir("product_sources_responses.csv")
    src_path = source_dir("product_sources_annotated.csv")
    resp_fields, resp_rows = read_csv(resp_path / "product_sources_responses.csv")
    src_fields, src_rows = read_csv(src_path / "product_sources_annotated.csv")

    # Canonical prompt per (language, topic, variant): the most frequent value.
    values = collections.defaultdict(collections.Counter)
    for r in resp_rows:
        values[(r["language"], r["topic"], r["variant"])][r["prompt_text"]] += 1
    canonical = {key: ctr.most_common(1)[0][0] for key, ctr in values.items()}

    notes, suffix_missing = [], []
    for r in resp_rows:
        canon = canonical[(r["language"], r["topic"], r["variant"])]
        if r["prompt_text"] == canon:
            continue
        recorded = r["prompt_text"]
        notes.append({
            "cell_id": r["cell_id"],
            "recorded_text": recorded,
            "canonical_text": canon,
            "note_fragment": note_fragment(recorded, canon),
        })
        if r["variant"] == "sourced" and not any(
                m in recorded.lower() for m in SUFFIX_MARKERS):
            suffix_missing.append({"cell_id": r["cell_id"], "recorded_text": recorded})

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "annotator_notes.csv",
              ["cell_id", "recorded_text", "canonical_text", "note_fragment"], notes)
    report = {
        "combos": len(canonical),
        "cells_rewritten": len(notes),
        "suffix_missing": suffix_missing,
        "written": bool(args.write),
    }
    (out / "prompt_normalize_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.write:
        changed = {n["cell_id"]: n["canonical_text"] for n in notes}
        for r in resp_rows:
            if r["cell_id"] in changed:
                r["prompt_text"] = changed[r["cell_id"]]
        for r in src_rows:
            if r["cell_id"] in changed:
                r["prompt_text"] = changed[r["cell_id"]]
        write_csv(out / "product_sources_responses.csv", resp_fields, resp_rows)
        write_csv(out / "product_sources_annotated.csv", src_fields, src_rows)

    print(f"cells rewritten: {len(notes)} ({'written' if args.write else 'preview only'})")
    print(f"sourced rows with no source-request suffix: {len(suffix_missing)}")
    for s in suffix_missing:
        print(f"  {s['cell_id']}: {s['recorded_text'][:70]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
