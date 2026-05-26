"""
docs_verify — fail CI if any GymAxis Markdown doc carries a stale
iteration banner.

Why this exists
---------------
Across `/app/memory/`, `/app/docs/`, repo-root README, etc. we put a
"Status — Iter XXX" banner near the top of each doc so a future
reader can tell, at a glance, "is this doc current?". Over time it
drifts — the iter bumps with every release, the banners don't, and
the doc starts lying.

This script reads the canonical current iter from
`/app/memory/.current_iter`, scans every shipped Markdown doc, and
exits 1 if any of them is stamped against a different iter.

Run
---
    make docs-verify              # called from CI / pre-commit too

Bumping
-------
When you cut a release, edit `/app/memory/.current_iter` to the new
iter token (e.g. `220n`). The `Iter XXXm refresh (...)` headers in
each shipped doc must match it.

Skiplist
--------
Files that intentionally contain historical iter labels in their
body (e.g. `PRD.md` — the running session log) live in `_SKIP`.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path("/app")
CURRENT_ITER_FILE = ROOT / "memory" / ".current_iter"

# Status-banner shapes we emit across the codebase.
BANNER_PATTERNS = [
    re.compile(r"^> \*\*📋 Status — Iter (?P<iter>[0-9a-zA-Z]+)(?: refresh| update)? \([^)]+\)\*\*", re.MULTILINE),
    re.compile(r"^## Iter (?P<iter>[0-9a-zA-Z]+)(?: refresh| update)? \([^)]+\)", re.MULTILINE),
]

# Scanned roots — every shipped doc location.
SCAN_GLOBS = [
    ROOT / "memory" / "*.md",
    ROOT / "docs" / "*.md",
    ROOT / "*.md",
    ROOT / "marketing" / "**/*.md",  # iter 220m sweep — marketing campaigns
]

# Files allowed to skip (canonical changelogs that *should* reference
# historical iters in their body).
_SKIP = {
    ROOT / "memory" / "PRD.md",
    ROOT / "memory" / "CHANGELOG.md",  # in case we adopt this split later
}


def _load_current_iter() -> str:
    if not CURRENT_ITER_FILE.exists():
        sys.stderr.write(
            f"[docs-verify] {CURRENT_ITER_FILE} missing — create it with a single "
            "line containing the current iter token (e.g. `220m`).\n"
        )
        sys.exit(2)
    value = CURRENT_ITER_FILE.read_text().strip()
    if not value:
        sys.stderr.write(f"[docs-verify] {CURRENT_ITER_FILE} is empty.\n")
        sys.exit(2)
    return value


def _first_banner_iter(text: str) -> str | None:
    """Return the iter from the FIRST status banner found in ``text``,
    scanning both banner shapes. Returns None if no banner is present
    (doc isn't iter-stamped — that's allowed)."""
    earliest_pos = -1
    earliest_iter: str | None = None
    for pat in BANNER_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if earliest_pos == -1 or m.start() < earliest_pos:
            earliest_pos = m.start()
            earliest_iter = m.group("iter")
    return earliest_iter


def main() -> int:
    current = _load_current_iter()
    stale: list[tuple[pathlib.Path, str]] = []
    checked = 0
    for glob in SCAN_GLOBS:
        if "**" in glob.parts:
            # Recursive glob — use rglob from the parent that precedes the **.
            star_idx = glob.parts.index("**")
            anchor = pathlib.Path(*glob.parts[:star_idx])
            pattern = "/".join(glob.parts[star_idx + 1:])
            results = sorted(anchor.rglob(pattern))
        else:
            results = sorted(glob.parent.glob(glob.name))
        for p in results:
            if p in _SKIP:
                continue
            checked += 1
            iter_label = _first_banner_iter(p.read_text())
            if iter_label is None:
                continue  # untagged docs allowed
            if iter_label != current:
                stale.append((p, iter_label))

    if stale:
        print(f"[docs-verify] ✗ {len(stale)} doc(s) stale (current iter = {current}):")
        for p, label in stale:
            rel = p.relative_to(ROOT)
            print(f"   · {rel}  →  banner reads `Iter {label}`")
        print(
            "\nFix: either bump the banner in the affected file to "
            f"`Iter {current}`, or — if the doc is now a pure changelog — "
            "add its path to `_SKIP` in /app/scripts/docs_verify.py."
        )
        return 1

    print(f"[docs-verify] ✓ {checked} docs scanned, all consistent at iter {current}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
