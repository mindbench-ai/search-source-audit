# Results inventory — 2026-07-23 sweep

The outputs of this study's run live in `results/`, next to the instrument that
produced them. **`results/` is gitignored**, so this file is the tracked record
of what exists, how big it is, and what it hashes to. If a clone of this repo
has no `results/` directory, that is expected — the bytes travel separately
(see "Where the bytes live" below).

Verify an existing copy against this file:

```bash
cd studies/2026-07-23_mental-health-information-gatekeepers
shasum -a 256 -c RESULTS.sha256
```

## What the run produced

| | |
|---|---|
| Sweep | 1,140 / 1,140 cells complete, **0 errors**, 380 per model |
| Models | `gpt-5.4-mini`, `gemini-3.5-flash`, `sonar` (slugs `openai-54mini`, `gemini-35flash`, `pplx-sonar`) |
| Design | 76 prompts x 7 languages x 2 phrasings x 5 repeats, `search_on` only |
| Instrument | `prompts.mindbench.json`, SHA-256 `230188202b4e659925b20723cc3cd0c69bd0874ddb3fab0b740df73b2ae3e4e9` |
| Started | 2026-07-23T15:10:44Z |
| Sources extracted | **9,849** across **998 unique domains** |
| Channel split | 9,606 `linked_structured` / 243 `linked_intext` |
| TLD buckets | org 3,043 · gov 2,806 · com 2,155 · other 1,568 · edu 277 |
| Zero-source calls | openai-54mini 189 · gemini-35flash 37 · pplx-sonar 0 |

The zero-source counts are a result, not a failure: a model that chose not to
search is signal, and those calls were recorded rather than retried.

`tld_class` is a TLD bucket from `extract.py`, not the organizational typology.
That typology is a separate hand-coding step over the extracted domains, and it
is not in these files.

## Files

| File | Bytes | SHA-256 |
|---|---:|---|
| `results/raw/gemini-35flash.jsonl` | 14,357,803 | `822dc8ffc0dbbec88a1cccc51564ab0261243f6a081828c5be95e561a0b84f85` |
| `results/raw/pplx-sonar.jsonl` | 6,082,067 | `50a165e436019b5b027bcd18d8a0ecf828fb8978775c20a1c4ce8adddec086c0` |
| `results/raw/openai-54mini.jsonl` | 3,317,050 | `f3336f3653fc0f36f58f5faf1764f3179fc2916651ff7a1e6cee7ea0f00dcb13` |
| `results/sources.json` | 9,019,415 | `6b92c383489bd9ac82855a6e1a0064cd072c9b8c40b7d6bfa73de6c1a1368d16` |
| `results/redirect_cache.json` | 1,452,314 | `57159012f2d14f38b1f093d160abf3a42d35ab45c265aa78d2c02ac5f8558860` |
| `results/run_manifest.jsonl` | 428 | `2e7a9b5417d675fd261ec7c39a36c8c6e42714216fba9202e49c72aafd0daa68` |
| `results/estimate.json` | 481 | `e060e1fd7ae02fab90f9e8ffa36ef89e738ba8d6e8737ac077809d42ff0e4728` |

Total 34,229,558 bytes (~32.6 MiB). Checksums recorded 2026-08-06, after the
move from `data/` into this folder; every file verified byte-identical across
the move.

`raw/*.jsonl` is one line per call with the complete provider response.
`sources.json` is the normalized table — one row per call, carrying the full
response text plus resolved sources and per-call counts. There is **no
aggregate rollup** (domain x model x language counts); the numbers in the table
above were computed ad hoc from `sources.json` and are not stored anywhere.

## Where the bytes live

On disk in this working tree, at `results/`, with `data/<dataset>` kept as a
symlink pointing here so the tool resolves paths exactly as before (resume,
re-extraction, and the prompt-fingerprint guard all still work unchanged).

They are **not** in git and **not** on any remote. As of 2026-08-06 this working
tree is the only copy. That is a deliberate hold, not an oversight — see
`.gitignore` for the reasoning and the one-line change that reverses it. The
documented destination for result data of this kind is a Zenodo deposit with the
DOI pointed to from here (`docs/repo-naming.csv` row 16); until that exists,
back this folder up somewhere that is not this laptop.

## Reproducing

Extraction is deterministic and uses no model, so `sources.json` can be rebuilt
from `raw/` at zero API cost:

```bash
python3 src/extract.py --models openai-54mini gemini-35flash pplx-sonar
```

Re-collection is a different matter: the model slugs above were current on
2026-07-23 and providers retire them without much notice, so an exact rerun has
a shelf life. Treat `raw/` as a one-time capture.
