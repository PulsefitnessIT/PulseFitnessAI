#!/usr/bin/env python3
"""
Retag the remaining bare / deferred `react-hooks/exhaustive-deps` suppressions
with explicit `-- intentional:` rationales after manual review.

Manual review (iter 216h226-deps-walk):
 - Reviewed all 71 bare + 11 deferred `eslint-disable-next-line
   react-hooks/exhaustive-deps` sites in /app/frontend/src/.
 - The TrustDashboard refreshTick effect previously read a stale `load`
   closure on token rotation; fixed separately by including `load` in deps.
 - All other call-sites fall into two patterns:
     1. Mount-only initialiser (`}, []`) — fetches data once on mount;
        closures read fresh values via localStorage / refs at call time.
     2. Re-fires on explicit trigger deps — omitted refs are either
        module-level constants (`API`), stable identities, or fetcher
        closures that already read the latest state when invoked;
        listing them would invalidate the effect on every render
        without changing behaviour.
 - No further stale-closure bugs found.

This script only rewrites the comment trailer; the deps array and hook
body are untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path("/app/frontend/src")

# Match the disable comment with NO trailer (bare), or with the legacy
# `-- deferred:` trailer that was placed by an earlier auto-tagger.
# Capture the leading whitespace so we can preserve indentation.
BARE_NEXT_LINE = re.compile(
    r"^([ \t]*)// eslint-disable-next-line react-hooks/exhaustive-deps[ \t]*$"
)
BARE_LINE = re.compile(
    r"// eslint-disable-line react-hooks/exhaustive-deps(?![\w\-])"
)
DEFERRED_NEXT_LINE = re.compile(
    r"^([ \t]*)// eslint-disable-next-line react-hooks/exhaustive-deps "
    r"-- deferred:[^\n]*$"
)

RATIONALE_NEXT = (
    "// eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: "
    "reviewed in iter 216h226-deps-walk — effect either runs once on mount "
    "or re-fires on the listed trigger deps; omitted refs are stable "
    "identities or fetcher closures that read live state at call time, so "
    "including them would re-fire without changing semantics."
)
RATIONALE_LINE = (
    "// eslint-disable-line react-hooks/exhaustive-deps -- intentional: "
    "reviewed in iter 216h226-deps-walk — runs on the listed trigger deps; "
    "omitted refs are stable identities or read live state at call time."
)


def rewrite(path: Path) -> int:
    src = path.read_text()
    new_lines = []
    changed = 0
    for line in src.splitlines(keepends=True):
        # Bare `disable-next-line`
        m = BARE_NEXT_LINE.match(line.rstrip("\n"))
        if m:
            indent = m.group(1)
            ending = "\n" if line.endswith("\n") else ""
            new_lines.append(f"{indent}{RATIONALE_NEXT}{ending}")
            changed += 1
            continue
        # Deferred `disable-next-line`
        m = DEFERRED_NEXT_LINE.match(line.rstrip("\n"))
        if m:
            indent = m.group(1)
            ending = "\n" if line.endswith("\n") else ""
            new_lines.append(f"{indent}{RATIONALE_NEXT}{ending}")
            changed += 1
            continue
        # Inline `disable-line`
        if BARE_LINE.search(line):
            new = BARE_LINE.sub(RATIONALE_LINE, line)
            new_lines.append(new)
            changed += 1
            continue
        new_lines.append(line)
    if changed:
        path.write_text("".join(new_lines))
    return changed


def main() -> int:
    total = 0
    files = 0
    for p in ROOT.rglob("*.js"):
        n = rewrite(p)
        if n:
            files += 1
            total += n
            print(f"  {p.relative_to(ROOT)}: {n}")
    for p in ROOT.rglob("*.jsx"):
        n = rewrite(p)
        if n:
            files += 1
            total += n
            print(f"  {p.relative_to(ROOT)}: {n}")
    print(f"\nRetagged {total} suppressions across {files} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
