# platform/ — integrating with mindbench-platform

Important notes for working the seam between this repo and mindbench-platform.
Everything platform-specific in this repo lives in this folder.

- **Artifact**: `audit-cube.v0` — a model x language x domain citation cube,
  one payload per study. The authoritative schema is the platform's
  `packages/artifact-schemas/schemas/audit-cube.v0.schema.json`.
- **Build**: `python3 platform/export_platform_artifact.py` writes payloads to
  `platform/out/` (gitignored). Stdlib only, like the rest of the repo.
- **Import (platform side)**: `npx tsx server/scripts/import/audit-cubes.ts
  <dir> --producer mindbench-ai/search-source-audit [--promote]`.
- **Data locality**: the exporter reads `studies/<slug>/results/`, which is
  gitignored — it runs from a working tree that holds the run's outputs, not
  from a fresh clone. `studies/<slug>/RESULTS.md` records what the data is
  and how to verify a copy.
- **Hazard**: the platform's public audit page
  (`web/src/components/audits/SourcesOfTruthPage.tsx`) hard-codes headline
  numbers from this repo rather than reading the promoted cube. If a number
  on this side changes, update that page in the same pass — it goes stale
  silently otherwise.
- **Counting definition**: the published dataset and the cube count citation
  occurrences as presented, not deduplicated sources; `sources.json` collapses
  repeats within a call. State which definition a new consumer uses.

## Working in this repo

Integration work touches the study data; these keep it intact.

- **The run data is irreplaceable.** Providers retire model slugs, so the raw
  responses are a one-time capture. Never delete, overwrite, or "regenerate" a
  dataset directory; a corrected run gets its own `dataset` name.
  `studies/<slug>/RESULTS.md` + `RESULTS.sha256` are the inventory - keep them
  current if the data ever changes.
- **Re-extract, never re-collect.** `extract.py` is deterministic over
  `raw/*.jsonl`, so any extraction bug is fixed by re-running it over the
  saved responses at zero API cost - not by new API calls.
- **Studies are frozen instruments.** `studies/<date>_<slug>/` records what
  ran; don't edit those files to match a later `prompts.json`. The runner
  guards each dataset with a SHA-256 prompt fingerprint; `--force` past a
  mismatch mixes two instruments and is essentially never right.
- **Deliberate flaws stay.** The Nepali depression prompts carry a stray
  vowel sign (`ि`, U+093F) matching the string the hand-coded product arm
  used; it is documented in the study README and the paper's limitations.
  Do not "fix" it.
- **`.env` holds live provider keys** (`.env.example` is the committed
  shape), and `pricing.json` is deliberately local - a stale price table
  produces a confident wrong number.
