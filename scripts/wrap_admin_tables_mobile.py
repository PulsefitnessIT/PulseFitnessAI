#!/usr/bin/env python3
"""Iter 216h229 Wave 3 — wrap MasterAdmin tables in horizontal-scroll
containers so they stop clipping their right edge on mobile.

Strategy: for every `.js` under /app/frontend/src/pages/MasterAdmin/
that contains `<table` but NOT `overflow-x-auto`, insert an
`overflow-x-auto` div around the table's immediate `<div` parent.

We use a simple pattern: find the LAST `<div class=` line directly
above the `<table` line and append `overflow-x-auto` to its class
attribute. This is brittle but covers the canonical idiom these
admin pages use (`<div className="… overflow-hidden …"><table … >`).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/app/frontend/src/pages/MasterAdmin")

# Pattern: `<div className="..."` followed (on next non-empty line) by `<table`.
# Add `overflow-x-auto` to the className.
DIV_BEFORE_TABLE = re.compile(
    r'(<div\s+className=")([^"]*)"(\s*[^>]*>\s*\n\s*<table)',
)


def patch(path: Path) -> int:
    src = path.read_text()
    if "<table" not in src or "overflow-x-auto" in src:
        return 0
    changed = 0

    def _rewrite(m: re.Match) -> str:
        nonlocal changed
        prefix, classes, suffix = m.group(1), m.group(2), m.group(3)
        if "overflow-x-auto" in classes:
            return m.group(0)
        # If the wrapper currently has overflow-hidden, swap it; else
        # append. overflow-hidden + overflow-x-auto don't compose.
        if "overflow-hidden" in classes:
            new_classes = classes.replace("overflow-hidden", "overflow-x-auto")
        else:
            new_classes = (classes + " overflow-x-auto").strip()
        changed += 1
        return f'{prefix}{new_classes}"{suffix}'

    new_src = DIV_BEFORE_TABLE.sub(_rewrite, src)
    if changed:
        path.write_text(new_src)
    return changed


def main() -> int:
    total = 0
    for p in sorted(ROOT.glob("*.js")):
        n = patch(p)
        if n:
            print(f"  {p.name}: wrapped {n} table(s)")
            total += n
    print(f"\nTotal: {total} table wrappers patched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
