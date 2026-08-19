"""Check that source_classifier.py matches the notebook.

Exits nonzero unless the classifier cell and the SIG dict are verbatim
substrings of product_audit_reproduction.ipynb. Reads the notebook from the
working tree, or from origin/main when the file is absent.

    python3 check_classifier_sync.py

On failure, re-extract from the notebook; the notebook is the source of truth
for the rules.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

STUDY = pathlib.Path(__file__).resolve().parent
NB_RELPATH = ("studies/2026-07-23_mental-health-information-gatekeepers/"
              "product_audit_reproduction.ipynb")


def notebook_text() -> str:
    local = STUDY / "product_audit_reproduction.ipynb"
    if local.exists():
        return local.read_text(encoding="utf-8")
    got = subprocess.run(["git", "show", f"origin/main:{NB_RELPATH}"],
                         capture_output=True, text=True, cwd=STUDY)
    if got.returncode != 0:
        sys.exit("notebook not in working tree and origin/main unavailable")
    return got.stdout


def main() -> int:
    nb = json.loads(notebook_text())
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]

    classifier = next((c for c in cells if c.lstrip().startswith("TYPE_ORDER")), None)
    if classifier is None:
        sys.exit("could not find the classifier cell (starts with TYPE_ORDER)")

    sig_cell = next((c for c in cells if "SIG = {" in c), None)
    if sig_cell is None:
        sys.exit("could not find the SIG cell")
    start, depth, i = sig_cell.index("SIG = {"), 0, sig_cell.index("SIG = {")
    while True:
        if sig_cell[i] == "{":
            depth += 1
        elif sig_cell[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    sig = sig_cell[start:i + 1]

    module = (STUDY / "source_classifier.py").read_text(encoding="utf-8")
    problems = []
    if classifier.rstrip() not in module:
        problems.append("classifier cell (TYPE_ORDER ... classify_type)")
    if sig not in module:
        problems.append("SIG language-signal dict")
    if problems:
        print("source_classifier.py differs from the notebook in:")
        for p in problems:
            print(f"  - {p}")
        print("Re-extract from the notebook.")
        return 1
    print("in sync: both blocks are verbatim substrings of the notebook")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
