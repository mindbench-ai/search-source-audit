#!/usr/bin/env python3
"""Export a source audit as a MindBench platform artifact (audit-cube.v0).

Writes one payload per study under platform/out/ (gitignored), in the shape the
platform's importer consumes:

    mindbench-platform: npx tsx server/scripts/import/audit-cubes.ts <dir> \\
        --producer mindbench-ai/search-source-audit [--promote]

WHAT IT MEASURES. Which publisher domains search-enabled LLM APIs actually cite.
The cube is model x language x domain, counting citations. The 2026-07-23 study
is 3 models x 7 languages x 998 domains = 20,958 cells, ~80 KB packed.

The cube is the study's aggregate rollup - the domain x model x language
counts behind any headline number - in a shape the platform ingests directly,
so downstream displays read the artifact rather than hand-copied constants.

Standard library only, matching the rest of src/ — no third-party deps.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "platform" / "out"

NOTES = [
    "Retrieval is nondeterministic; counts are over 5 runs per prompt, not one shot.",
    "A call that returned no sources is a RESULT, not a failure, and is counted "
    "in the denominator rather than dropped.",
    "Domains are resolved through provider redirect wrappers; a domain here is "
    "the publisher, not the URL the provider returned.",
]


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return None


def build_cube(study: pathlib.Path, sources: list[dict]) -> dict:
    models = sorted({r["model_key"] for r in sources})
    langs = sorted({r["language"] for r in sources})

    counts: dict[tuple, int] = collections.Counter()
    calls: dict[tuple, int] = collections.Counter()
    zero: dict[str, int] = collections.Counter()
    tld: dict[str, str | None] = {}
    for r in sources:
        calls[(r["model_key"], r["language"])] += 1
        if not r["sources"]:
            zero[r["model_key"]] += 1
        for s in r["sources"]:
            counts[(r["model_key"], r["language"], s["domain"])] += 1
            tld.setdefault(s["domain"], s.get("tld_class"))

    # Domains ordered by total citations, descending — the order a reader wants
    # and, because the cube declares it, one nothing else has to know about.
    totals = collections.Counter()
    for (_, _, d), n in counts.items():
        totals[d] += n
    domains = [d for d, _ in totals.most_common()]

    citations = [[[counts[(m, l, d)] for d in domains] for l in langs] for m in models]
    # Calls per (model, language). Not per-domain, so it declares two dims where
    # `citations` declares three — a denominator, not a parallel measure.
    call_counts = [[calls[(m, l)] for l in langs] for m in models]

    dicts = []
    for name in ("prompts.json", "config.json"):
        p = ROOT / name
        if p.exists():
            entries = json.loads(p.read_text())
            dicts.append({
                "name": name,
                "sha256": sha256(p),
                "n_entries": len(entries) if isinstance(entries, list) else None,
            })

    manifest = study / "results" / "run_manifest.jsonl"
    generated_at = "1970-01-01T00:00:00Z"
    if manifest.exists():
        lines = [l for l in manifest.read_text().splitlines() if l.strip()]
        if lines:
            generated_at = json.loads(lines[-1]).get("started_utc", generated_at)

    return {
        "schema_version": 0,
        "audit_slug": "search-source-domains",
        "run_id": study.name,
        "generated_at": generated_at,
        "inputs": {"code_sha": code_sha(), "dictionaries": dicts},
        "dims": {
            "model": [{"k": m} for m in models],
            "language": [{"k": l} for l in langs],
            # `group` is the TLD class (gov/edu/org/com/other) — the axis the
            # study's headline finding is read along.
            "domain": [{"k": d, "group": tld.get(d)} for d in domains],
        },
        "measures": [
            {"key": "citations", "label": "Citations", "unit": "count",
             "dims": ["model", "language", "domain"], "scale": 1, "data": citations},
            {"key": "calls", "label": "Calls made", "unit": "count",
             "dims": ["model", "language"], "scale": 1, "data": call_counts},
        ],
        "notes": NOTES + [
            "Calls returning zero sources: "
            + ", ".join(f"{m} {zero.get(m, 0)}" for m in models) + ".",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("study", nargs="?", type=pathlib.Path,
                    help="studies/<slug>/ (defaults to the only one present)")
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args()

    study = args.study
    if study is None:
        candidates = sorted(p for p in (ROOT / "studies").iterdir() if p.is_dir())
        if len(candidates) != 1:
            print(f"specify a study: {[p.name for p in candidates]}", file=sys.stderr)
            return 1
        study = candidates[0]

    sources_path = study / "results" / "sources.json"
    if not sources_path.exists():
        print(f"missing {sources_path} — results/ is gitignored, so this only "
              f"runs where the sweep was run.", file=sys.stderr)
        return 1

    cube = build_cube(study, json.loads(sources_path.read_text()))
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / f"{cube['audit_slug']}--{cube['run_id']}.json"
    dest.write_text(json.dumps(cube, sort_keys=True, separators=(",", ":")))

    d = cube["dims"]
    cited = sum(sum(sum(x) for x in l) for l in cube["measures"][0]["data"])
    print(f"wrote {dest}")
    print(f"  {len(d['model'])} models x {len(d['language'])} languages x {len(d['domain'])} domains")
    print(f"  {cited:,} citations, {dest.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
