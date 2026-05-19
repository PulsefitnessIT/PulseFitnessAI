#!/usr/bin/env python3
"""
Iter 216h226-polish-4 — light-mode leakage sweep.

Reads `yarn eslint --format json` output and appends the matching
`dark:` Tailwind variant to every className flagged by
`gymaxis/no-dark-mode-leakage`. Touches only the className value
(string literal OR template literal) — never restructures JSX.

Mapping (kept aligned with `/theme/themes/_root-css-vars.js`):
  bg-white / bg-{slate,zinc,gray,neutral,stone}-50 → dark:bg-zinc-900
  bg-{slate,zinc,gray,neutral,stone}-100         → dark:bg-zinc-800
  text-{slate,zinc,gray,neutral}-900             → dark:text-zinc-100
  border-{slate,zinc,gray}-{100,200}             → dark:border-zinc-800

The script never rewrites the same class twice (it bails out if the
`dark:` variant is already present anywhere in the className string).
Gradient leaks are NOT handled here — they are one-offs that need
human eyes (5 sites flagged, fix manually).

Usage:
    python3 scripts/sweep_dark_mode_leakage.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"

# (regex that matches the bad class, regex that proves dark variant exists, dark variant to add)
RULES = [
    # Backgrounds
    (re.compile(r"\bbg-white(?!/)\b"),           re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-900"),
    (re.compile(r"\bbg-slate-50(?!/)\b"),        re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-900"),
    (re.compile(r"\bbg-slate-100(?!/)\b"),       re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-800"),
    (re.compile(r"\bbg-zinc-50(?!/)\b"),         re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-900"),
    (re.compile(r"\bbg-zinc-100(?!/)\b"),        re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-800"),
    (re.compile(r"\bbg-gray-50(?!/)\b"),         re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-900"),
    (re.compile(r"\bbg-gray-100(?!/)\b"),        re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-800"),
    (re.compile(r"\bbg-neutral-50(?!/)\b"),      re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-900"),
    (re.compile(r"\bbg-neutral-100(?!/)\b"),     re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-800"),
    (re.compile(r"\bbg-stone-50(?!/)\b"),        re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-900"),
    (re.compile(r"\bbg-stone-100(?!/)\b"),       re.compile(r"\bdark:(?:[a-z-]+:)*bg-"),     "dark:bg-zinc-800"),
    # Text — only the 900 tier
    (re.compile(r"\btext-slate-900\b"),          re.compile(r"\bdark:(?:[a-z-]+:)*text-"),   "dark:text-zinc-100"),
    (re.compile(r"\btext-zinc-900\b"),           re.compile(r"\bdark:(?:[a-z-]+:)*text-"),   "dark:text-zinc-100"),
    (re.compile(r"\btext-gray-900\b"),           re.compile(r"\bdark:(?:[a-z-]+:)*text-"),   "dark:text-zinc-100"),
    (re.compile(r"\btext-neutral-900\b"),        re.compile(r"\bdark:(?:[a-z-]+:)*text-"),   "dark:text-zinc-100"),
    # Borders
    (re.compile(r"\bborder-slate-100(?!/)\b"),   re.compile(r"\bdark:(?:[a-z-]+:)*border-"), "dark:border-zinc-800"),
    (re.compile(r"\bborder-slate-200(?!/)\b"),   re.compile(r"\bdark:(?:[a-z-]+:)*border-"), "dark:border-zinc-800"),
    (re.compile(r"\bborder-zinc-100(?!/)\b"),    re.compile(r"\bdark:(?:[a-z-]+:)*border-"), "dark:border-zinc-800"),
    (re.compile(r"\bborder-zinc-200(?!/)\b"),    re.compile(r"\bdark:(?:[a-z-]+:)*border-"), "dark:border-zinc-800"),
    (re.compile(r"\bborder-gray-100(?!/)\b"),    re.compile(r"\bdark:(?:[a-z-]+:)*border-"), "dark:border-zinc-800"),
    (re.compile(r"\bborder-gray-200(?!/)\b"),    re.compile(r"\bdark:(?:[a-z-]+:)*border-"), "dark:border-zinc-800"),
]


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


def collect_targets(reports: list[dict]) -> dict[str, list[int]]:
    """Return {file: [line, …]} for dark-mode-leakage warnings (deduped)."""
    out: dict[str, set[int]] = {}
    for r in reports:
        for m in r.get("messages", []):
            if m.get("ruleId") != "gymaxis/no-dark-mode-leakage":
                continue
            out.setdefault(r["filePath"], set()).add(m["line"])
    return {f: sorted(v) for f, v in out.items()}


# A className= attribute can stretch over multiple lines; collect the
# whole string (literal or template) starting on the flagged line.
CLASSNAME_OPEN_RE = re.compile(r'className\s*=\s*(?P<q>["\'`{])')


def patch_classname_block(lines: list[str], start_line_idx: int) -> tuple[bool, int]:
    """Try to add missing dark: variants to a className= block that begins
    at-or-after `start_line_idx`. Returns (changed?, end_line_idx_inclusive).
    """
    # Find the className= on this line; if absent, scan ± a few lines.
    block_start = None
    for i in range(start_line_idx, max(-1, start_line_idx - 4), -1):
        if 0 <= i < len(lines) and "className" in lines[i]:
            block_start = i
            break
    if block_start is None:
        return False, start_line_idx

    # Identify the opening quote.
    open_m = CLASSNAME_OPEN_RE.search(lines[block_start])
    if not open_m:
        return False, start_line_idx
    open_quote = open_m.group("q")

    # `{`/`}` JSX expression — could wrap a string or template. For safety
    # only attempt when the literal opens with " ' or ` AND closes on the
    # same line (single-line className is by far the most common case).
    if open_quote == "{":
        return False, start_line_idx

    line = lines[block_start]
    close_idx = line.find(open_quote, open_m.end())
    if close_idx == -1:
        # Multi-line literal — skip to keep the rewrite safe.
        return False, start_line_idx
    cls_str = line[open_m.end():close_idx]

    # Apply each rule once. Insert missing dark: variants at the END of the
    # className string so existing word order is preserved.
    new_cls = cls_str
    appended: list[str] = []
    for bad_re, expects_dark_re, dark_token in RULES:
        if not bad_re.search(new_cls):
            continue
        if expects_dark_re.search(new_cls):
            # An equivalent `dark:` variant already exists — skip.
            continue
        if dark_token in appended:
            continue
        appended.append(dark_token)

    if not appended:
        return False, start_line_idx

    suffix = " " + " ".join(appended)
    new_cls_full = new_cls.rstrip() + suffix if new_cls.strip() else " ".join(appended)
    lines[block_start] = line[:open_m.end()] + new_cls_full + line[close_idx:]
    return True, block_start


def main() -> None:
    reports = run_eslint()
    targets = collect_targets(reports)
    if not targets:
        print("No dark-mode-leakage warnings to suppress.")
        return
    total = 0
    files = 0
    for filepath, line_numbers in sorted(targets.items()):
        path = Path(filepath)
        text = path.read_text()
        lines = text.split("\n")
        edits = 0
        for ln in line_numbers:
            idx = ln - 1
            changed, _ = patch_classname_block(lines, idx)
            if changed:
                edits += 1
        if edits:
            path.write_text("\n".join(lines))
            files += 1
            total += edits
            print(f"  {edits:3d}  {path.relative_to(REPO)}")
    print(f"\nPatched {total} className sites across {files} files.")


if __name__ == "__main__":
    main()
