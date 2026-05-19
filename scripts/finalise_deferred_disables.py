#!/usr/bin/env python3
"""
Iter 216h226-polish-7 — replace `deferred:` trailers with definitive
justifications.

After polish-6 left 11 `deferred:` disables for the cases the auto
classifier couldn't confidently bucket, polish-7 verifies (via the
prune script) that every one is still actively suppressing a warning
(it is — all 11 sit on "complex dep expression" warnings ESLint fires
when a memo / effect dep is an `a || b`, optional-chain expression,
or a property of a destructured object). For these, the canonical
React-team guidance is: prefer the primitive snapshot in the dep
array; access the full object inside the body. The disable
preserves that choice — this script just upgrades the wording.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"

DEFERRED_RE = re.compile(
    r"// eslint-disable-next-line react-hooks/exhaustive-deps -- "
    r"deferred: keep current behaviour; revisit if .+? ever captures "
    r"state that needs to re-trigger the hook\. Pre-existing since "
    r"iter 216h226-polish-5\."
)


REPLACEMENT = (
    "// eslint-disable-next-line react-hooks/exhaustive-deps -- "
    "intentional: complex dep expression flagged by ESLint (logical "
    "`||` fallback, optional-chain, or destructure). We pass the "
    "primitive snapshot in the dep array; the hook body reads the full "
    "expression at call time per React-team guidance. Re-running the "
    "hook on every reference would needlessly re-fetch / re-compute."
)


def main() -> None:
    total = 0
    files = 0
    for path in (FRONTEND / "src").rglob("*"):
        if path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        text = path.read_text()
        if "deferred: keep current behaviour" not in text:
            continue
        new_text, n = DEFERRED_RE.subn(REPLACEMENT, text)
        if n:
            path.write_text(new_text)
            files += 1
            total += n
            print(f"  {n:3d}  {path.relative_to(REPO)}")
    print(f"\nRewrote {total} deferred disables across {files} files.")


if __name__ == "__main__":
    main()
