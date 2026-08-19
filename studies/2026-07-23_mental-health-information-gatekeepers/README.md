# Sources of Truth: mental health audit

This folder documents one run of the tool. Nothing here is needed to use the
tool itself (for that, see the [top-level README](../../README.md)); it's kept so
the published results can be traced back to the exact setup that produced them.

## What we ran

This is the API side of a broader audit of consumer AI search products as
gatekeepers of mental health information. A separate product arm hand-codes the
free logged-out versions of ChatGPT, Gemini, and Perplexity. This arm checks
whether the bare APIs surface the same sources those products show users.

| | |
|---|---|
| Prompts | 76 (`prompts.mindbench.json`) |
| Languages | English, Spanish, Japanese, Hindi, Ukrainian, Nepali, Twi (Akan) |
| Design | each question asked twice: plain, and with a request to list sources |
| Repeats | 5 per prompt |
| Condition | `search_on` only |
| Models | `gpt-5.4-mini`, `gemini-3.5-flash`, `sonar` |
| Calls | 1,140 |
| Cost | about $20 (prices as of 2026-07-23) |

`prompts.mindbench.json` is a frozen copy of the prompts as run. The
`prompts.json` at the repo root can change; this copy shouldn't.

`questions_source.md` holds the original question list, and `build_prompts.py`
turns it into the prompt file. That script assumes the specific line layout of
`questions_source.md`, so it isn't a general importer. Use `editor.html` for any
other question set.

## Notes on the setup

**Model selection.** No provider says which checkpoint backs its free logged-out
product, and they change them without notice, so there's no way to match the
products exactly. We used each provider's current mid-tier model as a reasonable
stand-in. We picked `gpt-5.4-mini` partly for cost: at `gpt-5.5` prices the
OpenAI arm alone came to about $58 of a $90 total, since OpenAI charges for
retrieved search content as input tokens.

`gpt-5.4-mini` also searches less readily than `gpt-5.5` (about 4.5 vs 9.2
sources per call in our pilot, and no sources at all on the plain-question
variants). So model tier is a possible confound for anything we report about
OpenAI specifically, and it should be read as a property of this model rather
than of the OpenAI product.

**No-search condition dropped.** We piloted it and cut it. Every pilot call
returned zero structured citations, across both providers and all languages. The
only remaining signal would be organizations mentioned in prose, and extracting
those reliably would need a separate interpretive step we haven't built.
Perplexity Sonar always retrieves and has no search-off mode anyway, so it
couldn't have contributed to that condition.

**Models sometimes don't search.** Gemini returned no `groundingMetadata` at all
on some prompts. We recorded these as zero-source runs and did not retry them.

**Nepali typo.** The Nepali depression questions start with a stray vowel sign
(`ि`, U+093F) where `डिप्रेशन` was meant. We left it as is so this arm uses the
same string the hand-coded product arm did; it's flagged in the paper's
limitations.

**`tld_class`.** The `tld_class` field is just a TLD bucket (`gov`, `edu`, etc.)
from `extract.py`, not the organizational typology. That typology is a separate
hand-coding step over the extracted domains.

## Reproducing the run

From the repo root:

```bash
cp studies/2026-07-23_mental-health-information-gatekeepers/prompts.mindbench.json prompts.json
python3 src/runner.py --models openai-54mini gemini-35flash pplx-sonar \
                      --conditions search_on --runs 5
python3 src/extract.py --models openai-54mini gemini-35flash pplx-sonar
```

The run manifest records the SHA-256 of the prompt file, so a byte-identical
copy of `prompts.mindbench.json` confirms you're running the same instrument.

Outputs go to `data/2026-07-23_mental-health-information-gatekeepers/`, set by
`dataset` in `config.json`. The runner keys the output folder on that name and
checks it against the prompt fingerprint, so rerunning with these prompts resumes
the existing results instead of starting over or mixing in another study.

Since 2026-08-06 that path is a symlink into this folder's `results/`, so the
run's outputs sit next to the instrument that produced them. Nothing about the
tool changed: it still writes and resumes through `data/`. `results/` is
gitignored; `RESULTS.md` is the tracked inventory (counts and checksums) and
`RESULTS.sha256` verifies a copy with `shasum -a 256 -c`.

Model slugs were checked on 2026-07-23 and will be retired by the providers
eventually, at which point an exact rerun won't be possible. `config.json` and
the run manifest record what was used.
