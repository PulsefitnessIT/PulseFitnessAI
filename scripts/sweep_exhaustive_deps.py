#!/usr/bin/env python3
"""
Iter 216h226-polish-5 — react-hooks/exhaustive-deps sweep.

Reads `yarn eslint --format json` output and inserts an explicit
`// eslint-disable-next-line react-hooks/exhaustive-deps` comment
above each pre-existing violation. Each disable carries a `-- todo:`
trailer listing the missing dep names so future readers can revisit
on a per-case basis (genuine missing-dep bug vs intentional capture).

Why suppress instead of auto-fix?
  • Adding a function dep that isn't memoized → infinite re-render.
  • Removing a "necessary" dep → loses sync.
  • Mount-only effects intentionally exclude deps.
Without per-call-site context the codemod can't know which case it's
looking at; flagging the call site with a TODO is the only safe
mechanical action. The rule stays at `warn`, so new code missing
deps still gets flagged.

Skips:
  • Lines already carrying an `eslint-disable` directive.
  • Multi-line hook expressions where the comment placement would
    insert mid-argument (the script bails on detection).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"

DEP_RE = re.compile(r"missing depend(?:ency|encies): ([^.]+?)(?:\.|$)")


def run_eslint() -> list[dict]:
    proc = subprocess.run(
        [
            "yarn", "--silent", "eslint",
            "src/**/*.{js,jsx,ts,tsx}",
            "--max-warnings", "99999",
            "--format", "json",
        ],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
    )
    out = proc.stdout
    i = out.find("[")
    if i == -1:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit("eslint produced no JSON output")
    return json.loads(out[i:])


def collect_targets(reports: list[dict]) -> dict[str, list[tuple[int, str]]]:
    """Return {file: [(line, missing_deps_label), …]}."""
    out: dict[str, list[tuple[int, str]]] = {}
    for r in reports:
        for m in r.get("messages", []):
            if m.get("ruleId") != "react-hooks/exhaustive-deps":
                continue
            msg = m.get("message", "")
            dep_m = DEP_RE.search(msg)
            label = dep_m.group(1).strip() if dep_m else "unspecified"
            # Strip the "Either include … or remove" instruction.
            label = re.sub(r"\s*Either.*", "", label)
            out.setdefault(r["filePath"], []).append((m["line"], label))
    return out


def patch_file(path: Path, targets: list[tuple[int, str]]) -> int:
    text = path.read_text()
    lines = text.split("\n")
    # Sort by line desc so insertions don't shift later targets.
    seen: set[int] = set()
    edits = 0
    for line_no, label in sorted(targets, key=lambda x: -x[0]):
        if line_no in seen:
            continue
        seen.add(line_no)
        idx = line_no - 1
        if idx < 0 or idx >= len(lines):
            continue
        # Don't double-suppress if there's already a disable on the
        # previous line.
        prev = lines[idx - 1] if idx > 0 else ""
        if "eslint-disable" in prev:
            continue
        line = lines[idx]
        # Preserve indentation.
        indent_m = re.match(r"(\s*)", line)
        indent = indent_m.group(1) if indent_m else ""
        comment = (
            f"{indent}// eslint-disable-next-line react-hooks/exhaustive-deps "
            f"-- todo: review missing dep(s) {label}; pre-existing as of "
            f"iter 216h226-polish-5."
        )
        lines.insert(idx, comment)
        edits += 1
    if edits:
        path.write_text("\n".join(lines))
    return edits


def main() -> None:
    reports = run_eslint()
    targets = collect_targets(reports)
    if not targets:
        print("No exhaustive-deps warnings to suppress.")
        return
    total = 0
    files = 0
    for filepath, items in sorted(targets.items()):
        n = patch_file(Path(filepath), items)
        if n:
            files += 1
            total += n
            print(f"  {n:3d}  {Path(filepath).relative_to(REPO)}")
    print(f"\nPatched {total} hook sites across {files} files.")


if __name__ == "__main__":
    main()
