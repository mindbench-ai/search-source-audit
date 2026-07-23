# The Sources of Truth mental health audit

This directory records one specific audit run with this tool. Everything outside
`studies/` is general-purpose; everything here is particular to this run.

If you are here to run your own audit, you do not need anything in this
directory — see the top-level [README](../../README.md). This exists so the
published results can be traced to an exact configuration.

## What we ran

The API-side arm of a larger audit of consumer AI search products as gatekeepers
of mental health information. The product arm codes ChatGPT, Gemini, and
Perplexity by hand at their free, logged-out tiers; this arm asks whether bare
API retrieval surfaces the same sources those product wrappers show users.

| | |
|---|---|
| Prompts | 76 — see `prompts.mindbench.json` |
| Languages | English, Spanish, Japanese, Hindi, Ukrainian, Nepali, Twi (Akan) |
| Design | Each question twice: bare, and with a request to list sources |
| Repeats | 5 per prompt |
| Condition | `search_on` only |
| Models | `gpt-5.4-mini`, `gemini-3.5-flash`, `sonar` |
| Calls | 1,140 |
| Measured cost | ~$20 (prices retrieved 2026-07-23) |

`prompts.mindbench.json` is a frozen copy of the instrument as run. The active
`prompts.json` at the repository root may drift; this file should not.

`questions_source.md` is the original question list, and `build_prompts.py`
converts it into the prompt manifest. That script hardcodes line offsets specific
to that file's layout and is not a general importer — for any other question set,
use `editor.html` instead.

## Decisions worth knowing

**Model choice is an assumption, not an equivalence.** No vendor discloses which
checkpoint serves its free logged-out product, and they rotate silently. Each
slug is that provider's current mid-tier offering, chosen as a plausible
analogue. `gpt-5.4-mini` was additionally chosen on cost: at `gpt-5.5` rates the
OpenAI arm alone ran to $58 of a $90 total, because OpenAI bills retrieved search
content as input tokens at full model rates.

**`gpt-5.4-mini` retrieves less eagerly than `gpt-5.5`** — mean 4.5 versus 9.2
sources per call in piloting, and zero sources on bare-variant prompts. This is a
behavioral difference, not merely a cheaper proxy, and the model tier is a
plausible confound for any OpenAI-specific finding.

**The no-search condition was dropped.** Piloted and cut: it returned zero
structured citations in every pilot call across both providers and all languages.
Its only signal would come from organizations named in prose, which needs an
interpretive extractor that does not exist yet.

**Perplexity Sonar has no search-off mode**, being retrieval-native, so it could
not have contributed to that condition regardless.

**Models sometimes decline to search at all.** Gemini returned no
`groundingMetadata` whatsoever on some prompts. Recorded as genuine zero-source
runs, never retried.

**One Nepali prompt contains a typo.** The depression questions open with an
orphaned vowel sign (`ि`, U+093F) where `डिप्रेशन` was intended. Preserved
deliberately so this arm matches the exact string used in the hand-coded product
arm; noted in the paper's limitations.

**`tld_class` is not the organizational typology.** It is a mechanical TLD bucket
produced by `extract.py`. The organizational classification reported in the paper
is a separate, human-validated coding step over the extracted domains.

## Reproducing our run

From the repository root:

```bash
cp studies/2026-07-23_mental-health-information-gatekeepers/prompts.mindbench.json prompts.json
python3 src/runner.py --models openai-54mini gemini-35flash pplx-sonar \
                      --conditions search_on --runs 5
python3 src/extract.py --models openai-54mini gemini-35flash pplx-sonar
```

`prompts.mindbench.json` is the frozen instrument; its SHA-256 is recorded in
the run manifest, so a byte-identical copy confirms you are running what we ran.

Model slugs were verified live on 2026-07-23 and will eventually be retired by
their providers. An exact rerun after that point is not possible; `config.json`
and `data/<dataset>/run_manifest.jsonl` record what was actually used.

This study's outputs live under `data/2026-07-23_mental-health-information-gatekeepers/`
(the `dataset` set in `config.json`). Because the runner keys the output folder on
that name and guards it with the prompt fingerprint, re-running with these frozen
prompts resumes the existing results rather than starting over or mixing studies.
