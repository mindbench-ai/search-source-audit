# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 MindBench.ai

"""Run the prompt manifest across providers, conditions, and repeats.

Design notes:

* The unit of work is a "cell": (model, search_condition, prompt_id, run_index).
  Every cell is written as one JSON object on one line of a per-model JSONL file.
  The full raw provider response is retained verbatim so extraction can be redone
  later without re-spending API calls.

* Resumability matters more than speed here. A full sweep is thousands of calls
  and will hit rate limits, so the runner reads back what is already on disk and
  skips completed cells. Re-running the script always resumes; it never restarts.

* Each provider's default temperature is left as-is. Repeats are there to measure
  how much retrieval varies between identical calls, so pinning temperature to 0
  would remove the thing being measured. The effective sampling config is recorded
  per call under the "sampling" key (see providers.make_caller).

* A cell that returns zero sources is recorded as-is and never retried. Retrying
  until sources appear drops the zeros and makes the citation rate impossible to
  compute. Only transport and rate-limit failures are retried.

STOPPING A RUN
Three ways to stop, since an unattended sweep spends real money:
  1. Ctrl-C (SIGINT/SIGTERM): no new API calls start; in-flight calls finish. A
     second Ctrl-C exits immediately.
  2. `touch data/STOP`: same effect, and works when the run is backgrounded or in
     another terminal.
  3. --max-cost N: aborts once measured spend crosses N USD.
Each is checked before a call goes out, never mid-call, so stopping never loses a
response that was already paid for.

Provider adapters live in providers.py. This module stays provider-agnostic.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import signal
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import cost as cost_mod
import paths

RAW = paths.RAW
PROMPTS = paths.PROMPTS
STOP_FILE = paths.STOP_FILE

SEARCH_CONDITIONS = ("search_on", "search_off")

# Set by a signal handler, the STOP file, or the cost ceiling. Workers consult it
# before issuing a request, so queued-but-unstarted cells cost nothing.
ABORT = threading.Event()

# Returned by a worker that declined to start. Distinct from an error: nothing
# was spent and nothing should be written.
SKIP = object()


@dataclass(frozen=True)
class Cell:
    model_key: str
    search: str
    prompt_id: str
    run_index: int

    @property
    def cell_id(self) -> str:
        return f"{self.model_key}|{self.search}|{self.prompt_id}|{self.run_index}"


def raw_path(model_key: str) -> pathlib.Path:
    return RAW / f"{model_key}.jsonl"


def install_brakes() -> None:
    def handler(signum, frame):  # noqa: ANN001, ARG001
        if ABORT.is_set():
            print("\nsecond interrupt - exiting now", file=sys.stderr, flush=True)
            os._exit(130)
        ABORT.set()
        print(
            "\ninterrupt received: no new calls will start. "
            "Waiting for in-flight calls (up to ~60s). Ctrl-C again to exit now.",
            file=sys.stderr,
            flush=True,
        )

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def load_completed(model_key: str) -> set[str]:
    """Cell ids already recorded. Tolerates a truncated final line from a kill."""
    path = raw_path(model_key)
    if not path.exists():
        return set()
    done = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not rec.get("error"):
                done.add(rec["cell_id"])
    return done


def build_cells(
    prompts: list[dict],
    model_keys: list[str],
    languages: list[str] | None,
    conditions: tuple[str, ...],
    n_runs: int,
) -> list[Cell]:
    selected = [p for p in prompts if not languages or p["language"] in languages]
    cells = []
    for model_key in model_keys:
        for search in conditions:
            for prompt in selected:
                for run_index in range(1, n_runs + 1):
                    cells.append(Cell(model_key, search, prompt["prompt_id"], run_index))
    return cells


def _record_cost(rec: dict) -> float:
    try:
        return cost_mod.cost_of(
            rec["provider"], rec["model_id"], rec.get("raw") or {}, rec["search"] == "search_on"
        )
    except Exception:  # noqa: BLE001 - accounting must never kill a run
        return 0.0


def run_sweep(
    cells: list[Cell],
    prompts_by_id: dict[str, dict],
    call_fn,
    workers: int,
    max_cost: float | None = None,
    max_retries: int = 3,
) -> float:
    """Execute cells concurrently, appending results grouped by model.

    Writes happen only on the main thread, so the JSONL files stay valid even if
    the process is killed mid-sweep. Returns total measured spend.
    """
    by_model: dict[str, list[Cell]] = {}
    for cell in cells:
        by_model.setdefault(cell.model_key, []).append(cell)

    spent = 0.0
    for model_key, model_cells in by_model.items():
        if ABORT.is_set():
            print(f"{model_key}: skipped (aborted)")
            continue
        path = raw_path(model_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        done = failed = skipped = 0
        total = len(model_cells)
        print(f"\n{model_key}: {total} cells")

        with path.open("a", encoding="utf-8") as out:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        _call_with_retry,
                        call_fn,
                        cell,
                        prompts_by_id[cell.prompt_id],
                        max_retries,
                    ): cell
                    for cell in model_cells
                }
                for future in as_completed(futures):
                    cell = futures[future]
                    try:
                        record = future.result()
                    except Exception:
                        record = {
                            "cell_id": cell.cell_id,
                            "model_key": cell.model_key,
                            "search": cell.search,
                            "prompt_id": cell.prompt_id,
                            "run_index": cell.run_index,
                            "error": traceback.format_exc(limit=3),
                        }
                    if record is SKIP:
                        skipped += 1
                        continue
                    if record.get("error"):
                        failed += 1
                    else:
                        spent += _record_cost(record)
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out.flush()
                    done += 1

                    # Brakes are checked here, between calls, so stopping never
                    # discards a response that has already been paid for.
                    if STOP_FILE.exists() and not ABORT.is_set():
                        ABORT.set()
                        print(
                            f"\nSTOP file present ({STOP_FILE}); halting after in-flight calls.",
                            file=sys.stderr,
                            flush=True,
                        )
                    if max_cost is not None and spent >= max_cost and not ABORT.is_set():
                        ABORT.set()
                        print(
                            f"\ncost ceiling hit: ${spent:.2f} >= ${max_cost:.2f}; halting.",
                            file=sys.stderr,
                            flush=True,
                        )
                    if done % 25 == 0 or done == total:
                        print(
                            f"  {done}/{total} ({failed} failed, {skipped} skipped) "
                            f"${spent:.2f}",
                            file=sys.stderr,
                            flush=True,
                        )
        if skipped:
            print(f"  {model_key}: {skipped} cells never started (resume to finish)")
    return spent


def _call_with_retry(call_fn, cell: Cell, prompt: dict, max_retries: int):
    """Retry transport/rate-limit failures with backoff.

    A successful call that returns no sources is not retried. That is a real
    observation, not a failure.
    """
    if ABORT.is_set():
        return SKIP
    last = None
    for attempt in range(max_retries):
        if ABORT.is_set():
            return SKIP
        try:
            return call_fn(cell, prompt)
        except Exception as exc:  # noqa: BLE001 - provider SDKs raise varied types
            last = exc
            if attempt < max_retries - 1:
                # Interruptible sleep: a stop during backoff takes effect at once.
                if ABORT.wait(timeout=2**attempt * 2):
                    return SKIP
    return {
        "cell_id": cell.cell_id,
        "model_key": cell.model_key,
        "search": cell.search,
        "prompt_id": cell.prompt_id,
        "run_index": cell.run_index,
        "error": f"{type(last).__name__}: {last}",
    }


def write_run_manifest(args, cells: list[Cell], pending: int) -> None:
    """Append a provenance record so a future run can prove it matched this one.

    The prompt fingerprint is the important field: if prompts.json changes, later
    results are not directly comparable to earlier ones, and this is the only
    durable record of which instrument produced which rows.
    """
    import providers

    paths.ensure_data_dirs()
    entry = {
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config_version": paths.load_config().get("config_version"),
        "prompts_sha256": paths.prompts_fingerprint(),
        "prices_retrieved": cost_mod.prices_retrieved(),
        "models": {
            k: v["model_id"] for k, v in providers.load_models().items()
            if k in args.models
        },
        "conditions": args.conditions,
        "runs_per_prompt": args.runs,
        "languages": args.languages or "all",
        "cells_total": len(cells),
        "cells_pending": pending,
        "max_cost_usd": args.max_cost,
    }
    with paths.RUN_MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def main() -> None:
    cfg = paths.load_config()
    ap = argparse.ArgumentParser(
        description="Run the audit sweep. Defaults come from config.json; "
        "flags override them."
    )
    ap.add_argument("--models", nargs="+", default=cfg["active_models"],
                    help="model keys defined in config.json")
    ap.add_argument("--languages", nargs="*", default=None, help="e.g. en es; default all")
    ap.add_argument("--conditions", nargs="+", default=cfg["conditions"])
    ap.add_argument("--runs", type=int, default=cfg["runs_per_prompt"])
    ap.add_argument("--workers", type=int, default=cfg["workers"])
    ap.add_argument(
        "--max-cost",
        type=float,
        default=cfg.get("max_cost_usd"),
        help="abort once measured spend (USD) crosses this",
    )
    ap.add_argument("--dry-run", action="store_true", help="report cell counts and exit")
    ap.add_argument(
        "--force",
        action="store_true",
        help="append even if this dataset already holds runs from different prompts",
    )
    args = ap.parse_args()
    paths.ensure_data_dirs()
    print(f"dataset '{paths.dataset_name()}' -> {paths.DATA}")

    prompts = json.loads(PROMPTS.read_text(encoding="utf-8"))
    prompts_by_id = {p["prompt_id"]: p for p in prompts}

    cells = build_cells(
        prompts, args.models, args.languages, tuple(args.conditions), args.runs
    )

    # Guard against reusing a dataset for a different instrument. This runs ahead
    # of the pending/dry-run check for a reason: if new prompts reuse old
    # prompt_ids, every cell looks "done" and the run would report success on
    # stale data from another study. Comparing prompt fingerprints catches that.
    # Resuming the same study passes (fingerprints match), and a new study in a
    # fresh dataset passes too (no prior manifest).
    prior = paths.last_manifest_fingerprint()
    current = paths.prompts_fingerprint()
    mismatch = bool(prior and prior != current)
    if mismatch:
        msg = (
            f"dataset '{paths.dataset_name()}' already holds runs built from a "
            f"different prompts.json\n  recorded fingerprint: {prior[:16]}\n"
            f"  current prompts.json: {current[:16]}\n"
            f"Give this study its own `dataset` in config.json (or set "
            f"AUDIT_DATASET=<name>) so results don't mix,\nor pass --force to "
            f"append into this dataset anyway."
        )
        if args.dry_run:
            print(f"WARNING: {msg}")
        elif not args.force:
            raise SystemExit("\n" + msg)

    completed: set[str] = set()
    for model_key in args.models:
        completed |= load_completed(model_key)
    cell_ids = {c.cell_id for c in cells}
    pending = [c for c in cells if c.cell_id not in completed]

    print(
        f"{len(cells)} cells total, {len(completed & cell_ids)} done, {len(pending)} pending"
    )
    if args.dry_run or not pending:
        return

    # A stale STOP file from a previous run would abort this one instantly.
    if STOP_FILE.exists():
        print(f"removing stale STOP file at {STOP_FILE}")
        STOP_FILE.unlink()

    install_brakes()
    write_run_manifest(args, cells, len(pending))
    print(f"stop anytime: Ctrl-C, or `touch {STOP_FILE}`")
    if args.max_cost is not None:
        print(f"cost ceiling: ${args.max_cost:.2f} (soft; overshoot bounded by workers x cost/call)")

    from providers import make_caller  # imported late so --dry-run needs no keys

    started = time.time()
    spent = run_sweep(
        pending, prompts_by_id, make_caller(), args.workers, max_cost=args.max_cost
    )
    print(
        f"\nmeasured spend this session: ${spent:.2f} "
        f"in {(time.time() - started) / 60:.1f} min"
    )
    if ABORT.is_set():
        print("run stopped early - rerun the same command to resume where it left off")


if __name__ == "__main__":
    main()
