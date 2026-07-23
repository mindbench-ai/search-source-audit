# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 MindBench.ai

"""Build this study's prompt manifest from its questions_source.md.

questions_source.md is a flat list grouped into language blocks. Within each
block the naked variants come first, then the same questions again with a source
request appended, in the same order. This script pairs them up and emits the
repository-root prompts.json with stable ids so runs are joinable across models.

Self-contained on purpose: it resolves paths relative to its own location and
imports nothing from the core tool, so a study folder stays portable and the
core tool never needs to know a study exists.

Run from anywhere: python3 build_prompts.py
"""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent            # studies/<this-study>/
REPO = HERE.parent.parent                                 # repository root
QUESTIONS = HERE / "questions_source.md"
OUT = REPO / "prompts.json"

# 1-indexed line spans in questions.md, as (naked_start, naked_end, sourced_start,
# sourced_end). Hardcoded rather than inferred from blank lines because the blank
# line between the Nepali and Ukrainian blocks is missing.
BLOCKS = [
    # lang_code, lang_name, resource_tier, naked span, sourced span
    ("es", "Spanish", "high", (1, 3), (4, 6)),
    ("tw", "Twi (Akan)", "low", (8, 10), (11, 13)),
    ("ne", "Nepali", "low", (15, 17), (18, 20)),
    ("uk", "Ukrainian", "medium", (21, 23), (24, 26)),
    ("ja", "Japanese", "high", (28, 30), (31, 33)),
    ("hi", "Hindi", "medium", (35, 37), (38, 40)),
    ("en", "English", "high", (42, 61), (62, 81)),
]

# Topic slugs, in block order. The non-English blocks all cover the same three
# topics. Note the Twi third question asks about coping strategies and where the
# advice comes from rather than naming trustworthy sources outright -- it is the
# nearest analogue in that block but is not a strict translation.
TOPICS_SHORT = ["dx-depression", "crisis-suicide", "trustworthy-sources"]
TOPICS_EN = [
    "meds-depression",
    "meds-anxiety",
    "meds-schizophrenia",
    "dx-depression",
    "dx-anxiety",
    "dx-ptsd",
    "signs-depression",
    "signs-ocd",
    "sx-anxiety",
    "sx-bipolar",
    "eff-clozapine",
    "eff-exposure-ocd",
    "eff-cbt-anxiety",
    "crisis-psychosis",
    "crisis-mania",
    "crisis-suicide",
    "trustworthy-sources",
    "sideeffects-ssri",
    "firstline-antidepressants",
    "ptsd-guidelines",
]

# Coarse category for downstream grouping.
CATEGORY = {
    "meds": "medication",
    "dx": "diagnosis",
    "signs": "symptoms",
    "sx": "symptoms",
    "eff": "treatment-efficacy",
    "crisis": "crisis-resources",
    "trustworthy": "source-recommendation",
    "sideeffects": "medication",
    "firstline": "medication",
    "ptsd": "treatment-guidelines",
}


def main() -> None:
    lines = QUESTIONS.read_text(encoding="utf-8").splitlines()

    def span(a: int, b: int) -> list[str]:
        got = [lines[i - 1].strip() for i in range(a, b + 1)]
        if any(not t for t in got):
            raise ValueError(f"blank line inside span {a}-{b}; line numbers drifted")
        return got

    prompts = []
    for lang, lang_name, tier, naked_span, sourced_span in BLOCKS:
        naked = span(*naked_span)
        sourced = span(*sourced_span)
        if len(naked) != len(sourced):
            raise ValueError(f"{lang}: {len(naked)} naked vs {len(sourced)} sourced")

        topics = TOPICS_EN if lang == "en" else TOPICS_SHORT
        if len(topics) != len(naked):
            raise ValueError(f"{lang}: {len(topics)} topics vs {len(naked)} questions")

        for topic, n_text, s_text in zip(topics, naked, sourced):
            for variant, text in (("naked", n_text), ("sourced", s_text)):
                prompts.append(
                    {
                        "prompt_id": f"{lang}-{topic}-{variant}",
                        "language": lang,
                        "language_name": lang_name,
                        "resource_tier": tier,
                        "topic": topic,
                        "category": CATEGORY[topic.split("-")[0]],
                        "variant": variant,
                        "text": text,
                    }
                )

    ids = [p["prompt_id"] for p in prompts]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate prompt_id")

    OUT.write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(prompts)} prompts to {OUT}")
    for lang, name, *_ in BLOCKS:
        n = sum(1 for p in prompts if p["language"] == lang)
        print(f"  {lang} ({name}): {n}")


if __name__ == "__main__":
    main()
