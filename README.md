# search-source-audit

Which external sources do search-enabled LLM APIs cite when you ask them
questions?

Point this at a set of questions and a set of models. It runs every question
against every model, repeatedly, and extracts every source cited, resolving each
to a real publisher domain, deduplicating, and writing the result as JSON.

It was built for a mental health information audit (see
[`studies/2026-07-23_mental-health-information-gatekeepers/`](studies/2026-07-23_mental-health-information-gatekeepers/README.md)),
but nothing in the tool is specific to that topic. Replace `prompts.json` with
your own questions and `config.json` with your own models. The same approach
works for auditing what an answer engine surfaces in any domain where source
provenance matters (health, legal, financial, electoral, and so on).

## Why this exists

Answer engines write prose and cite a few sources chosen by the system rather
than the user. Studying that choice means running many questions many times and
normalizing what comes back, which is tedious and easy to get wrong in a few
specific ways:

- Retrieval is nondeterministic. The same question asked twice cites different
  sources, so a single query per question mostly measures noise.
- Some providers return redirect URLs that hide the real publisher. Count those
  as-is and the whole corpus collapses to one domain.
- A web-search call can cost far more than a plain completion, because retrieved
  content is often billed as input tokens. It adds up quickly if you don't watch
  it.
- A model that chooses not to search is itself a result. Retrying until sources
  appear throws that away.

The tool is built around these four problems.

## Quickstart

```bash
cp .env.example .env               # add keys for the providers you'll use
cp pricing.example.json pricing.json   # optional; see Cost control below
python3 src/runner.py --dry-run    # how many calls will this be?
python3 src/estimate.py            # what will it cost? (samples ~6 prompts)
python3 src/runner.py              # run it
python3 src/extract.py --models openai-54mini gemini-35flash pplx-sonar
```

Python 3.9+ and no third-party packages: it uses only the standard library, so
there is nothing to install and nothing to break when you come back to it later.

## Configuring an experiment

The quickest way to set up a run is the browser editor:

```bash
python3 src/configure.py
```

This starts a local server (bound to localhost) and opens the page in your
browser. It reads the current `prompts.json` and `config.json`, and its Save
buttons write straight back to those files, so there is no download-and-move
step. Stop it with Ctrl-C when you're done. The page has two tabs:

- **Experiment** edits `config.json`: the dataset name, which models are defined
  and active, conditions, runs per prompt, workers, and the cost ceiling.
- **Prompts** edits `prompts.json`, grouped by language. Each question shows its
  plain and "with source request" text side by side, so the two variants stay
  paired. You can add or remove questions and languages, and the `prompt_id`
  under each box updates as you type. It validates live for duplicate ids, empty
  topics, and questions with no text.

You can also edit the files by hand. A prompt is an object with a stable
`prompt_id` (built from `language`-`topic`-`variant`, so it stays in sync with
those fields), the prompt `text`, and any metadata you want to group by:

```json
{
  "prompt_id": "en-ssri-side-effects-sourced",
  "language": "en", "language_name": "English", "resource_tier": "high",
  "topic": "ssri-side-effects", "category": "medication",
  "variant": "sourced",
  "text": "What are the side effects of SSRIs? List your sources."
}
```

The tool only relies on `language`, `topic`, and `variant`. The `variant` field
supports paired designs, where the same question is asked with and without an
explicit request for sources, but you don't have to use it.

Models live in `config.json` under `models`, and adding one needs no code change:

```json
"models": {
  "my-model": {
    "provider": "openai",
    "model_id": "gpt-5.4-mini",
    "supports_search_off": true,
    "options": { "search_context_size": "low" }
  }
},
"active_models": ["my-model"]
```

| Field | Meaning |
|---|---|
| `provider` | an adapter in `providers.PROVIDERS`; currently `openai`, `gemini`, `perplexity` |
| `model_id` | the provider's own slug |
| `supports_search_off` | `false` for retrieval-native APIs that can't run without search |
| `options` | passed to the adapter; each adapter's docstring lists the keys it reads, and `extra_payload` merges arbitrary fields into the request |

Other config fields: `dataset` (names the `data/<dataset>/` output folder; give
each study its own so results don't collide), `conditions` (`search_on` /
`search_off`), `runs_per_prompt`, `workers`, and `max_cost_usd`. Each can be
overridden with a CLI flag. The `options` field is not exposed in the editor, but
the editor preserves it when you save.

To add a provider, subclass `Provider` in `src/providers.py` with a `call()` and
a `usage()`, then register it. Override `reported_cost()` if the API reports its
own billed cost, and `is_indirect_url()` / `resolve_url()` if it returns redirect
URLs, which extraction then resolves. There is a worked template in the class
docstring.

## Cost control

Web search is the expensive part, and providers bill it differently: some charge
per call, some also bill retrieved content as input tokens, some bundle it. Run
`src/estimate.py` first. It samples across languages and prompt lengths, measures
actual usage, and projects the full sweep.

`pricing.json` is not committed. Vendor prices change often, and a stale price
table gives you a confident number that happens to be wrong, so the estimator's
main output is token and call counts, which don't go out of date:

```
model           condition      calls  in tok/call out tok/call    total in   total out    src
pplx-sonar      search_on        380           22          471       8,487     179,107   12.0
```

Multiply those by current prices and add each provider's per-search-call fee to
get a dollar figure. To have the tool do that arithmetic, copy
`pricing.example.json` to `pricing.json` and fill in prices you've just checked.
It will then print a dollar table, and warn if the file is more than 90 days old,
undated, or missing an entry for a model you're running. Providers that report
their own billed cost (Perplexity) are accurate with or without the file.

The cost machinery has had limited real use — one full sweep and its pilots —
so treat the estimate and the ceiling as aids, not guarantees. Check spend
against the provider's own billing dashboard on anything expensive, and assume
the first run against a new provider or model can surprise you: billing models
change, and a fee the adapter doesn't know about is invisible to both the
estimator and the ceiling.

There are three ways to stop a running sweep:

1. Ctrl-C. No new calls start; in-flight calls finish. Press it again to exit
   immediately.
2. `touch data/STOP`. Same effect, and it works on a backgrounded run.
3. `--max-cost N`. Aborts once measured spend crosses N dollars.

All three are checked between calls, not mid-call, so stopping never throws away
a response you already paid for, and a stop can take up to about 60 seconds. The
cost ceiling is soft: calls already in flight still land, so the overshoot is
bounded by roughly `workers × cost-per-call`.

Runs resume. Re-running the same command skips cells that already completed.

## Output

Everything is written under `data/<dataset>/`, where `<dataset>` comes from the
`dataset` field in `config.json` (or the `AUDIT_DATASET` env var). Each study
gets its own directory and can't overwrite another's results. The runner also
refuses to append to a dataset whose recorded prompt fingerprint differs from the
current `prompts.json`, so pointing new questions at an old dataset fails with a
clear error rather than quietly mixing two studies together (use `--force` to
override). Paths below are relative to the dataset directory.

`raw/<model>.jsonl` holds one line per call, with the complete raw provider
response. Extraction can be rewritten and re-run against these at no API cost;
nothing is dropped at collection time.

`sources.json` is the normalized table. Each source has:

| field | meaning |
|---|---|
| `channel` | `linked_structured` (a citation object) or `linked_intext` (a bare URL in prose) |
| `domain` | registrable domain, lowercased, no `www` |
| `tld_class` | a `gov`/`edu`/`org`/`com`/`other` bucket by TLD, which is not an organizational typology |
| `url` | resolved publisher URL |
| `raw_url` | the pre-resolution URL, if it was a redirect |
| `http_status` | status seen while resolving |

Extraction uses no model, so its output is reproducible from the saved responses.
Sources named in prose without a URL ("the NIMH", "DSM-5") are not extracted;
picking those up reliably takes an interpretive pass that belongs in its own,
separately validated step.

`run_manifest.jsonl` records provenance for each sweep: timestamp, model slugs,
price-table date, and a SHA-256 of `prompts.json`. If that fingerprint changes,
results before and after it are no longer directly comparable, and the runner
enforces that by refusing to mix instruments within one dataset.

## Repository layout

```
config.json          experiment definition: models, conditions, runs
pricing.example.json template for prices (copy to pricing.json)
prompts.json         the active prompt set
editor.html          browser UI for editing prompts and config
src/
  paths.py           path and config resolution
  providers.py       provider registry and API adapters
  configure.py       local server backing editor.html; saves in place
  runner.py          the sweep: resumable, interruptible, cost-capped
  extract.py         raw responses -> normalized source table
  cost.py            cost accounting from pricing.json
  estimate.py        project full-sweep cost from a sample
studies/             one folder per study run with this tool, e.g.
  2026-07-23_mental-health-information-gatekeepers/
data/                all generated output (gitignored)
  <dataset>/         one subfolder per dataset: raw/, sources.json, manifest
```

Each folder under `studies/` records one audit: its frozen prompt set, the price
table in force at the time, and a README covering the design and caveats. The
naming convention is `YYYY-MM-DD_short-slug` so runs sort by date. To reproduce a
study, copy its frozen prompts to the repo root (its README shows the command)
before running the sweep.

## Caveats

- Model slugs get retired, often without much notice. Check them before a run;
  the manifest records what was actually used.
- Prices change. `pricing.json` is local and dated, and the estimator warns once
  it is over 90 days old. Token counts stay valid regardless.
- Redirect resolution relies on undocumented provider behavior. It reads only the
  `Location` header and never fetches the destination page, but a provider could
  change it.
- Some providers retain your prompts. Google keeps grounding data for 30 days and
  this can't be turned off. Check the terms before sending anything sensitive.
- `tld_class` is a TLD bucket, not a source typology. Any organizational
  classification is a separate, hand-validated step.

## License

[GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later).

You can use, modify, and redistribute this freely, including commercially. The
one real condition: if you modify it and offer it to others over a network (a
hosted service, an API, a web app), you have to make your modified source
available to those users under the same license. That keeps derived audit tooling
open rather than closed back up inside a product.

Contributions are accepted under the same license.
