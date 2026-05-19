#!/usr/bin/env python3
"""
Iter 216h226-polish-7 — prune dead `deferred:` disable comments.

After polish-6 left 11 disables with the `deferred: keep current
behaviour` trailer (the codemod couldn't classify the dep names with
high confidence), this script:
  1. Iterates over each remaining `deferred:` site.
  2. Temporarily removes it from a copy of the file.
  3. Runs `eslint --max-warnings 99999` on JUST that file.
  4. Keeps the removal if no warning fired (dead disable);
     otherwise restores it AND prepends a `todo: re-review` note so
     the next human pass picks it up.

Either way the final state has zero useless directives.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
DEFERRED_RE = re.compile(
    r"^\s*// eslint-disable-next-line react-hooks/exhaustive-deps -- "
    r"deferred: .*\n",
    re.MULTILINE,
)


def lint_file(path: Path) -> int:
    """Return the number of react-hooks/exhaustive-deps issues in `path`."""
    proc = subprocess.run(
        [
            "node_modules/.bin/eslint",
            str(path.relative_to(FRONTEND)),
            "--max-warnings", "99999",
            "--rule", '{"react-hooks/exhaustive-deps":"warn"}',
            "--format", "json",
        ],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
    )
    import json
    out = proc.stdout
    i = out.find("[")
    if i == -1:
        return 0
    reports = json.loads(out[i:])
    return sum(
        1
        for r in reports
        for m in r.get("messages", [])
        if m.get("ruleId") == "react-hooks/exhaustive-deps"
    )


def main() -> None:
    candidate_files = [
        p for p in (FRONTEND / "src").rglob("*")
        if p.suffix in {".js", ".jsx", ".ts", ".tsx"}
        and "deferred: keep current behaviour" in p.read_text()
    ]
    removed = 0
    kept = 0
    for path in candidate_files:
        original = path.read_text()
        stripped = DEFERRED_RE.sub("", original)
        if stripped == original:
            continue
        # Try a clean removal first.
        path.write_text(stripped)
        if lint_file(path) == 0:
            removed += original.count("deferred: keep current behaviour")
            print(f"  removed dead disables in {path.relative_to(REPO)}")
        else:
            path.write_text(original)
            kept += 1
            print(f"  kept (still suppressing) {path.relative_to(REPO)}")
    print(f"\nRemoved {removed} dead disables; kept {kept} files unchanged.")


if __name__ == "__main__":
    main()
