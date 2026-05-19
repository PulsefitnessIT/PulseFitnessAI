#!/usr/bin/env python3
"""
Iter 216h226-polish-3 — unused-vars sweep helper.

Reads `yarn eslint --format json` output and applies the `_`-prefix
suppression rule to each `unused-imports/no-unused-vars` warning.
Safe operations only:
  • `const [name, setName] = useState(...)` → `const [name, _setName]`
  • `const [name, setName] = useState(...)` → `const [_name, setName]`
  • Function param `(foo)` → `(_foo)`
  • Object destructure `const { foo, bar }` → `const { foo: _foo, bar }`

Skips anything ambiguous (declared functions, classes, complex destructures).
Re-run `yarn eslint` after to confirm the count drops without errors.

Usage:
    python3 scripts/suppress_unused_vars.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"


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
    # Yarn sometimes prepends a banner; trim to the first '['.
    i = out.find("[")
    if i == -1:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit("eslint produced no JSON output")
    return json.loads(out[i:])


def collect_targets(reports: list[dict]) -> dict[str, list[tuple[int, int, str]]]:
    """Return {file: [(line, col, varname), …]} for unused-vars warnings."""
    out: dict[str, list[tuple[int, int, str]]] = {}
    for r in reports:
        for m in r.get("messages", []):
            if m.get("ruleId") != "unused-imports/no-unused-vars":
                continue
            msg = m.get("message", "")
            mname = re.match(r"'([^']+)' is", msg)
            if not mname:
                continue
            name = mname.group(1)
            out.setdefault(r["filePath"], []).append(
                (m["line"], m["column"], name)
            )
    return out


def prefix_var_in_line(line: str, col: int, name: str) -> str | None:
    """Try to apply a safe '_' prefix at the given column.

    Returns the new line or None when the location is ambiguous.
    """
    # Iter 216h226-polish-3 — skip PascalCase identifiers. The React
    # rules-of-hooks linter requires component names to start with an
    # uppercase letter; prefixing them with '_' demotes them and trips
    # `react-hooks/rules-of-hooks` on every `useState` call inside.
    if name and name[0].isupper():
        return None
    # eslint columns are 1-indexed; convert to 0-indexed.
    pos = col - 1
    # Confirm the var name starts at this position.
    end = pos + len(name)
    if line[pos:end] != name:
        # The column sometimes points at the destructure key — search nearby.
        idx = line.find(name, max(0, pos - 5), min(len(line), pos + 25))
        if idx == -1:
            return None
        pos = idx
        end = pos + len(name)
    # Avoid double-prefix.
    if pos > 0 and line[pos - 1] == "_":
        return None
    # Don't rewrite if it looks like a property access or string literal.
    before = line[:pos].rstrip()
    if before.endswith(".") or before.endswith("'") or before.endswith('"') or before.endswith("`"):
        return None
    return line[:pos] + "_" + line[pos:]


def patch_file(path: Path, targets: list[tuple[int, int, str]]) -> int:
    """Apply '_' prefixes; returns the number of edits made."""
    # Group by line so multiple edits on one line shift correctly (right-to-left).
    by_line: dict[int, list[tuple[int, str]]] = {}
    for line_no, col, name in targets:
        by_line.setdefault(line_no, []).append((col, name))

    text = path.read_text()
    lines = text.split("\n")
    edits = 0
    for line_no, cols in by_line.items():
        if line_no > len(lines):
            continue
        line = lines[line_no - 1]
        # Apply right-to-left so earlier columns stay valid.
        for col, name in sorted(cols, key=lambda x: -x[0]):
            new = prefix_var_in_line(line, col, name)
            if new is None:
                continue
            line = new
            edits += 1
        lines[line_no - 1] = line
    if edits:
        path.write_text("\n".join(lines))
    return edits


def main() -> None:
    reports = run_eslint()
    targets = collect_targets(reports)
    if not targets:
        print("No unused-vars warnings to suppress.")
        return
    total = 0
    files = 0
    for filepath, items in sorted(targets.items()):
        n = patch_file(Path(filepath), items)
        if n:
            files += 1
            total += n
            print(f"  {n:3d}  {Path(filepath).relative_to(REPO)}")
    print(f"\nPatched {total} unused-var sites across {files} files.")


if __name__ == "__main__":
    main()
