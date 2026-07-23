# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 MindBench.ai

"""Repository paths and experiment config in one place.

Every script resolves paths through here, so the layout can change in one place
and nothing writes outside the gitignored data/ directory by accident.

Output is namespaced per dataset, under data/<dataset>/, so two studies with
different questions or models never write to the same files even from the same
checkout. The dataset name comes from the AUDIT_DATASET env var, else config
`dataset`, else config `experiment`, else "default". See dataset_name().
"""

from __future__ import annotations

import json
import os
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent

# Committed inputs. Nothing here points at the studies/ folder: the core tool is
# study-agnostic, and each study under studies/ resolves its own materials
# relative to its own location.
PROMPTS = REPO / "prompts.json"
CONFIG = REPO / "config.json"
PRICING = REPO / "pricing.json"           # gitignored; user-supplied
PRICING_EXAMPLE = REPO / "pricing.example.json"  # committed template
ENV = REPO / ".env"


def load_config() -> dict:
    """Experiment definition. CLI flags override these; the file is the default."""
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def load_pricing() -> dict:
    """Price tables. Absent or malformed, estimates degrade to zero rather than fail."""
    try:
        return json.loads(PRICING.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _slug(name: str) -> str:
    """Reduce an arbitrary name to a safe single-segment directory name."""
    safe = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in str(name).strip())
    return safe.strip("-.") or "default"


def dataset_name() -> str:
    """Directory namespace for this run's outputs.

    Resolution order: AUDIT_DATASET env var, then config `dataset`, then config
    `experiment`, then "default". The env var wins so a one-off run can redirect
    output without editing config; config `dataset` is the usual per-study
    setting. Falls back to "default" instead of raising if config.json can't be
    read, so importing this module never fails.
    """
    env = os.environ.get("AUDIT_DATASET")
    if env:
        return _slug(env)
    try:
        cfg = load_config()
    except (OSError, json.JSONDecodeError):
        return "default"
    return _slug(cfg.get("dataset") or cfg.get("experiment") or "default")


# Generated output, gitignored, namespaced by dataset so studies never collide.
DATA = REPO / "data" / dataset_name()
RAW = DATA / "raw"
STOP_FILE = DATA / "STOP"
SOURCES_OUT = DATA / "sources.json"
REDIRECT_CACHE = DATA / "redirect_cache.json"
ESTIMATE_OUT = DATA / "estimate.json"
RUN_MANIFEST = DATA / "run_manifest.jsonl"


def ensure_data_dirs() -> None:
    RAW.mkdir(parents=True, exist_ok=True)


def prompts_fingerprint() -> str:
    """SHA-256 of the prompt manifest.

    Recorded with every sweep so a future run can prove it used the same
    instrument. If this changes, results are not directly comparable.
    """
    import hashlib

    return hashlib.sha256(PROMPTS.read_bytes()).hexdigest()


def last_manifest_fingerprint() -> str | None:
    """prompts_sha256 of the most recent run in this dataset, or None.

    Lets the runner catch a dataset being reused for a different set of prompts,
    which would otherwise interleave two studies in one set of files.
    """
    if not RUN_MANIFEST.exists():
        return None
    last = None
    for line in RUN_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return (last or {}).get("prompts_sha256")
