# mindbench-api-search-audit

**Which external sources do search-enabled LLM APIs cite when you ask them
questions?**

Point this at a set of questions and a set of models. It runs every question
against every model, repeatedly, and extracts every source cited — resolved to
real publisher domains, deduplicated, and written as JSON you can analyze.

Built for a mental health information audit (see
[`studies/2026-07-23_mental-health-information-gatekeepers/`](studies/2026-07-23_mental-health-information-gatekeepers/README.md)),
but nothing in the tool is specific to that topic. Swap `prompts.json` for your
own questions and `config.json` for your own models.

Useful for auditing what any answer engine routes users toward: health, legal,
financial, electoral, or any domain where source provenance matters.

## Why this exists

Answer engines synthesize prose and cite a handful of sources chosen by the
system, not the user. Auditing that choice means running many questions many
times and normalizing what comes back — which is tedious, and easy to get subtly
wrong. In particular:

- Retrieval is **nondeterministic**: the same question asked twice cites
  different sources. Single-shot testing measures noise.
- Some providers return **redirect URLs** that hide the real publisher. Counting
  those naively gives you one domain for the entire corpus.
- Web-search calls can cost **50× a plain completion**, because retrieved content
  is often billed as input tokens. Unmeasured, a sweep gets expensive fast.
- A model that **declines to search** is a finding. Retrying until sources appear
  silently deletes it.

This handles all four.

## Quickstart

```bash
cp .env.example .env               # add keys for the providers you'll use
cp pricing.example.json pricing.json   # optional; see Cost control below
python3 src/runner.py --dry-run    # how many calls will this be?
python3 src/estimate.py            # what will it cost? (samples ~6 prompts)
python3 src/runner.py              # run it
python3 src/extract.py --models openai-54mini gemini-35flash pplx-sonar
```

Python 3.9+. **No third-party packages** — everything is standard library, so
there is nothing to install and no dependency drift when you rerun this in a year.

## Using your own questions

Open **`editor.html`** in a browser for a table UI over `prompts.json`: add,
edit, delete, filter by language. It validates as you type — duplicate ids, empty
text, and topics missing a variant counterpart. Click **Download prompts.json**
and move it over the repo copy.

A prompt is an object with a stable `prompt_id` (derived from
`language`-`topic`-`variant`, so it can't drift from its fields) plus `text` and
whatever metadata you want to group by:

```json
{
  "prompt_id": "en-ssri-side-effects-sourced",
  "language": "en", "language_name": "English", "resource_tier": "high",
  "topic": "ssri-side-effects", "category": "medication",
  "variant": "sourced",
  "text": "What are the side effects of SSRIs? List your sources."
}
```

`language`, `topic`, and `variant` are the only fields the tool relies on.
`variant` supports paired designs — asking the same question with and without an
explicit request for sources — but nothing forces you to use it.

## Using your own models

Everything is declared in `config.json`; no code changes needed.

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
| `provider` | an adapter in `providers.PROVIDERS` — currently `openai`, `gemini`, `perplexity` |
| `model_id` | the provider's own slug |
| `supports_search_off` | `false` for retrieval-native APIs that can't run tool-free |
| `options` | passed to the adapter; each adapter's docstring lists honored keys, and `extra_payload` merges arbitrary fields into the request |

Other config: `dataset` (names the `data/<dataset>/` output folder — give each
study its own so results never collide), `conditions` (`search_on` /
`search_off`), `runs_per_prompt`, `workers`, `max_cost_usd`. All overridable by
CLI flag.

**Adding a provider** means subclassing `Provider` in `src/providers.py` with a
`call()` and a `usage()`, then registering it. If the API reports its own billed
cost, override `reported_cost()`; if it returns redirect URLs, override
`is_indirect_url()` and `resolve_url()` and extraction resolves them
automatically. The class docstring has a worked template.

## Cost control

Web search is the expensive part, and providers bill it differently — some charge
per call, some also bill retrieved content as input tokens, some bundle it. Run
`src/estimate.py` first: it samples across languages and prompt lengths, measures
actual usage, and projects the full sweep.

**`pricing.json` is not committed, on purpose.** Vendor prices change often, and a
stale table is worse than none — it produces a confident number that is quietly
wrong. So the estimator's primary output is **token counts and call counts**,
which never go stale:

```
model           condition      calls  in tok/call out tok/call    total in   total out    src
pplx-sonar      search_on        380           22          471       8,487     179,107   12.0
```

Multiply those by current vendor prices, and add each provider's per-search-call
fee, for a dollar figure. To have the tool do that arithmetic, copy
`pricing.example.json` to `pricing.json` and fill in prices you have just checked.
It then also prints a dollar table — and warns if the file is over 90 days old,
undated, or missing an entry for a model you're running. Providers that report
their own billed cost (Perplexity) are accurate either way.

Three independent brakes on a running sweep:

1. **Ctrl-C** — no new calls start; in-flight calls finish. Again to exit now.
2. **`touch data/STOP`** — same, and works on a backgrounded run.
3. **`--max-cost N`** — aborts once measured spend crosses N USD.

All are checked *between* calls, so stopping never discards a response you paid
for — which means a stop takes up to ~60s. The cost ceiling is soft: in-flight
calls still land, so overshoot is bounded by roughly `workers × cost-per-call`.

Runs are **resumable**. Re-running the same command skips completed cells.

## Output

All output lands under **`data/<dataset>/`**, where `<dataset>` is set by the
`dataset` field in `config.json` (or the `AUDIT_DATASET` env var). Each distinct
study therefore gets its own directory and can never overwrite another's results.
The runner refuses to append to a dataset whose recorded prompt fingerprint
differs from the current `prompts.json` — so pointing new questions at an old
dataset fails loudly instead of silently interleaving two studies (override with
`--force`). Paths below are relative to that dataset directory.

**`raw/<model>.jsonl`** — one line per call, retaining the **complete raw
provider response**. Extraction can be redesigned and re-run at zero API cost;
nothing is discarded at collection time.

**`sources.json`** — the normalized table. Each source carries:

| field | meaning |
|---|---|
| `channel` | `linked_structured` (a real citation object) or `linked_intext` (a bare URL in prose) |
| `domain` | registrable domain, lowercased, no `www` |
| `tld_class` | mechanical `gov`/`edu`/`org`/`com`/`other` bucket — **not** an organizational typology |
| `url` | resolved publisher URL |
| `raw_url` | the pre-resolution URL, if it was a redirect |
| `http_status` | status seen while resolving |

Extraction is fully deterministic — no model is involved, so results are
reproducible from the saved responses. Sources *named* in prose without a URL
("the NIMH", "DSM-5") are deliberately not extracted; recognizing those needs an
interpretive pass that belongs in a separate, separately-validated step.

**`run_manifest.jsonl`** — provenance per sweep: timestamp, model slugs,
price-table date, and a SHA-256 of `prompts.json`. If that fingerprint changes,
results from before and after are not directly comparable — and the runner
enforces this, refusing to mix instruments within one dataset.

## Repository layout

```
config.json          experiment definition: models, conditions, runs
pricing.example.json committed template for prices (copy to pricing.json)
prompts.json         the active prompt set
editor.html          browser UI for editing prompts
src/
  paths.py           path and config resolution
  providers.py       provider registry and API adapters
  runner.py          the sweep: resumable, interruptible, cost-capped
  extract.py         raw responses -> normalized source table
  cost.py            cost accounting from pricing.json
  estimate.py        project full-sweep cost from a sample
studies/             one folder per study run with this tool, e.g.
  2026-07-23_mental-health-information-gatekeepers/
data/                all generated output (gitignored)
  <dataset>/         one subfolder per dataset; raw/, sources.json, manifest
```

Each folder under `studies/` is a self-contained record of one audit: its frozen
prompt set, the price table in force at the time, and a README documenting the
design and caveats. Naming convention is `YYYY-MM-DD_short-slug`, so runs sort
chronologically. To reproduce a study, copy its frozen prompts to the repo root
(see that study's README) before running the sweep.

## Caveats

- **Model slugs expire.** Providers retire them without much notice. Verify before
  any run; the manifest records what was actually used.
- **Prices change.** `pricing.json` is local and stamped with a retrieval date;
  the estimator warns past 90 days. Token counts stay valid indefinitely.
- **Redirect resolution is undocumented behavior.** It reads only the `Location`
  header and never fetches the destination page, but providers can change it.
- **Some providers retain your prompts.** Google retains grounding data for 30
  days and this cannot be disabled. Check terms before sending sensitive prompts.
- **`tld_class` is not a source typology.** Any organizational classification is a
  separate, human-validated step.

## License

[GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later).

You may use, modify, and redistribute this freely, including commercially. The
one condition that matters: if you modify it and offer it to others **over a
network** — a hosted service, an API, a web app — you must make your modified
source available to those users under the same license. This keeps derived
audit tooling open rather than folded into a closed product.

Contributions are accepted under the same license.
