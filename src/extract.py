# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 MindBench.ai

"""Turn raw run records into a normalized source table.

Two source channels are kept distinct, because collapsing them loses the
difference between what a system formally cites and what it merely mentions:

  linked_structured -- the provider returned it as a citation object, i.e. what a
                       consumer product would render as a clickable source chip.
  linked_intext     -- a bare URL the model typed into its own prose, with no
                       corresponding citation object.

Both are deterministic: no model is used, so the output is reproducible from the
saved raw responses alone. Sources named in prose without any URL ("the NIMH",
"DSM-5") are deliberately NOT extracted here -- recognizing them requires an
interpretive pass that should be built and validated separately rather than
smuggled into a deterministic step.

Providers that return redirect or proxy URLs are resolved through their adapter's
resolve_url(), with results cached so a re-run costs nothing.

Run: python3 src/extract.py --models <model_key> [...]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from urllib.parse import urlsplit

import paths
import providers

RAW = paths.RAW
OUT = paths.SOURCES_OUT
REDIRECT_CACHE = paths.REDIRECT_CACHE

# Bare URLs in prose. Stops at whitespace or the characters that typically
# terminate a link in markdown/CJK text rather than belonging to it.
URL_RE = re.compile(r"https?://[^\s<>\"'\)\]\},;、。）】]+", re.UNICODE)

# Trailing characters that are almost always punctuation, not part of the path.
TRAILING = ".,;:!?'\"”’）】)]}>*_"

# Public suffixes needing two labels to reach the registrable domain. This is a
# curated subset, not the full Public Suffix List -- a complete PSL would mean a
# third-party dependency, and this pipeline is deliberately dependency-free.
# Add entries here if your prompt set targets regions not covered below.
MULTI_SUFFIXES = {
    "co.uk", "org.uk", "nhs.uk", "ac.uk", "gov.uk", "net.uk", "sch.uk",
    "com.au", "org.au", "net.au", "gov.au", "edu.au",
    "co.jp", "or.jp", "ne.jp", "go.jp", "ac.jp", "ed.jp", "lg.jp",
    "co.in", "org.in", "net.in", "gov.in", "nic.in", "ac.in", "edu.in",
    "com.np", "gov.np", "org.np", "edu.np",
    "com.ua", "gov.ua", "org.ua", "edu.ua", "in.ua",
    "com.gh", "gov.gh", "org.gh", "edu.gh",
    "com.br", "org.br", "gov.br", "com.mx", "gob.mx", "com.ar", "gob.ar",
    "com.es", "gob.es", "org.es", "co.za", "org.za", "gov.za",
    "co.nz", "org.nz", "govt.nz", "co.kr", "or.kr", "go.kr",
    "com.cn", "org.cn", "gov.cn", "com.hk", "gov.hk", "com.sg", "gov.sg",
    "com.tr", "gov.tr", "com.ru", "org.ru",
}


def clean_url(url: str) -> str:
    return url.rstrip(TRAILING)


def registrable_domain(url_or_host: str) -> str | None:
    """Reduce a URL or host to its registrable domain, lowercased, no www."""
    if not url_or_host:
        return None
    host = url_or_host
    if "//" in host or host.startswith("http"):
        host = urlsplit(host).netloc
    host = host.split("@")[-1].split(":")[0].strip().lower().rstrip(".")
    if not host or " " in host:
        return None
    # Strip www BEFORE the suffix logic below. Some entries in MULTI_SUFFIXES are
    # also live sites in their own right (nhs.uk, gob.mx), so leaving www attached
    # would keep three labels and split-count www.nhs.uk against nhs.uk.
    if host.startswith("www."):
        host = host[4:]
    # Some providers return a bare domain rather than a URL, so plain hosts
    # arrive here too and must pass through unchanged.
    parts = host.split(".")
    if len(parts) < 2:
        return None
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def tld_class(domain: str | None) -> str | None:
    """Factual TLD bucket. NOT the organizational typology -- that is coded separately."""
    if not domain:
        return None
    for suffix, label in (
        (".gov", "gov"), (".gov.uk", "gov"), (".nhs.uk", "gov"), (".gov.au", "gov"),
        (".gov.in", "gov"), (".nic.in", "gov"), (".go.jp", "gov"), (".gov.np", "gov"),
        (".gov.ua", "gov"), (".gov.gh", "gov"), (".gov.za", "gov"), (".govt.nz", "gov"),
        # Spanish- and French-convention government suffixes: without these the
        # non-English arms systematically under-count government sources.
        (".gob.mx", "gov"), (".gob.es", "gov"), (".gob.ar", "gov"), (".gob.cl", "gov"),
        (".gob.pe", "gov"), (".gouv.fr", "gov"), (".go.kr", "gov"), (".gov.br", "gov"),
        (".edu", "edu"), (".ac.uk", "edu"), (".edu.au", "edu"), (".ac.jp", "edu"),
        (".ac.in", "edu"), (".edu.in", "edu"), (".edu.np", "edu"), (".ac.nz", "edu"),
        (".org", "org"), (".org.uk", "org"), (".or.jp", "org"), (".org.au", "org"),
        (".org.in", "org"), (".org.np", "org"), (".org.ua", "org"), (".org.za", "org"),
    ):
        if domain.endswith(suffix):
            return label
    if domain.endswith(".com") or domain.endswith(".co.uk"):
        return "com"
    return "other"


def load_redirect_cache() -> dict:
    if REDIRECT_CACHE.exists():
        return json.loads(REDIRECT_CACHE.read_text())
    return {}


def save_redirect_cache(cache: dict) -> None:
    REDIRECT_CACHE.write_text(json.dumps(cache, indent=1))


def _provider(rec: dict):
    """Adapter that produced a record, for URL resolution. None if unknown."""
    return providers.PROVIDERS.get(rec.get("provider") or "")


def extract_record(rec: dict, cache: dict) -> dict:
    """Build the per-run source list. Mutates `cache` with any new resolutions."""
    text = rec.get("text") or ""
    provider = _provider(rec)
    sources: list[dict] = []
    seen: set[tuple] = set()

    def indirect(u):
        return bool(provider) and provider.is_indirect_url(u)

    def add(url, title, channel, provider_field=None):
        url = clean_url(url) if url else None
        resolved_url, status = url, None
        if indirect(url):
            if url not in cache:
                r, s = provider.resolve_url(url)
                cache[url] = {"resolved": r, "status": s}
            entry = cache[url]
            resolved_url, status = entry["resolved"] or url, entry["status"]
        domain = registrable_domain(resolved_url) if resolved_url else None
        # Some providers put the bare domain in the title field, which is the
        # only recoverable signal when an indirect URL fails to resolve.
        if not domain or indirect(resolved_url):
            domain = registrable_domain(title) or domain
        key = (channel, domain, resolved_url)
        if key in seen:
            return
        seen.add(key)
        sources.append(
            {
                "channel": channel,
                "domain": domain,
                "tld_class": tld_class(domain),
                "url": resolved_url,
                "raw_url": url if url != resolved_url else None,
                "title": title,
                "http_status": status,
                "provider_field": provider_field,
            }
        )

    for s in rec.get("structured_sources") or []:
        add(s.get("url"), s.get("title"), "linked_structured", s.get("provider_field"))

    structured_domains = {s["domain"] for s in sources}
    for url in URL_RE.findall(text):
        url = clean_url(url)
        d = registrable_domain(url)
        # A URL the model typed that also came back as a citation is the same
        # source surfaced twice, not a second source.
        if d and d in structured_domains:
            continue
        add(url, None, "linked_intext")

    out = {k: v for k, v in rec.items() if k not in ("raw", "structured_sources")}
    out["sources"] = sources
    out["n_linked_structured"] = sum(
        1 for s in sources if s["channel"] == "linked_structured"
    )
    out["n_linked_intext"] = sum(1 for s in sources if s["channel"] == "linked_intext")
    out["n_unique_domains"] = len({s["domain"] for s in sources if s["domain"]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    cache = load_redirect_cache()
    records, errors = [], 0
    for model_key in args.models:
        path = RAW / f"{model_key}.jsonl"
        if not path.exists():
            print(f"missing {path}, skipping")
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("error"):
                errors += 1
                continue
            records.append(extract_record(rec, cache))

    save_redirect_cache(cache)
    pathlib.Path(args.out).write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = sum(len(r["sources"]) for r in records)
    domains = {s["domain"] for r in records for s in r["sources"] if s["domain"]}
    zero = sum(1 for r in records if not r["sources"])
    print(f"{len(records)} runs ({errors} errored runs skipped)")
    print(f"{total} source mentions, {len(domains)} unique domains")
    print(f"{zero} runs returned zero sources ({zero/max(len(records),1):.1%})")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
