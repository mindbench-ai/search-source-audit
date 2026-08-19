"""Data loading and shared definitions for the audit analyses.

Both citation tables count occurrences: one row per citation as presented in a
response, so a source cited three times in one answer contributes three rows.
Boolean columns are parsed case-insensitively (the product arm writes
TRUE/FALSE, the API arm True/False).
"""
from __future__ import annotations

import csv
import json
import pathlib

STUDY = pathlib.Path(__file__).resolve().parent.parent
RESULTS = STUDY / "results"

DEFAULT_API = RESULTS / "hf" / "corrected"
DEFAULT_PRODUCT = RESULTS / "hf" / "released"
DEFAULT_RAW = RESULTS / "raw"

# (product provider slug, product display name, paired API model)
PAIRS = [
    ("chatgpt", "ChatGPT", "gpt-5.4-mini"),
    ("google", "Google AI Overview", "gemini-3.5-flash"),
    ("perplexity", "Perplexity", "sonar"),
]

# The nine-category organizational typology, in reporting order.
TYPE_ORDER = [
    "government/public", "academic/journal", "nonprofit health system",
    "commercial health", "nonprofit/advocacy", "encyclopedia (wiki)",
    "news/media", "social/video", "other",
]

LANGUAGES = [("hi", "Hindi"), ("ja", "Japanese"), ("ne", "Nepali"),
             ("es", "Spanish"), ("tw", "Twi"), ("uk", "Ukrainian")]

# The three questions administered in all seven languages.
COMMON_TOPICS = frozenset({"crisis-suicide", "dx-depression", "trustworthy-sources"})


def read_csv(path: pathlib.Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_tables(api_dir: pathlib.Path = DEFAULT_API,
                product_dir: pathlib.Path = DEFAULT_PRODUCT) -> dict:
    """The four citation/response tables, with n_sources as int."""
    tables = {
        "api_src": read_csv(api_dir / "api_sources_annotated.csv"),
        "api_resp": read_csv(api_dir / "api_responses.csv"),
        "product_src": read_csv(product_dir / "product_sources_annotated.csv"),
        "product_resp": read_csv(product_dir / "product_sources_responses.csv"),
    }
    for r in tables["api_resp"] + tables["product_resp"]:
        r["n_sources"] = int(r["n_sources"])
    return tables


def load_raw(raw_dir: pathlib.Path, model_file: str) -> list[dict]:
    """One record per API call, with the full provider response under `raw`."""
    records = []
    with open(raw_dir / model_file, encoding="utf-8") as fh:
        for line in fh:
            records.append(json.loads(line))
    return records


def truthy(value) -> bool:
    return str(value).strip().lower() in ("true", "1")


def pct(part: float, whole: float) -> float:
    return 100.0 * part / whole if whole else 0.0
