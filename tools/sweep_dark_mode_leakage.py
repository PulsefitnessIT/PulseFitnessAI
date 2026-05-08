#!/usr/bin/env python3
"""Codemod: append matching `dark:` variants to JSX className strings
that use `bg-white` / `bg-zinc-50|100` / `bg-gray-50|100` / `bg-slate-50|100`
without one already.

Defaults are based on the existing dark-mode palette in this codebase:
  bg-white         → bg-white dark:bg-zinc-900
  bg-zinc-50       → bg-zinc-50 dark:bg-zinc-950/40
  bg-zinc-100      → bg-zinc-100 dark:bg-zinc-800
  bg-gray-50       → bg-gray-50 dark:bg-gray-950/40
  bg-gray-100      → bg-gray-100 dark:bg-gray-800
  bg-slate-50      → bg-slate-50 dark:bg-slate-950/40
  bg-slate-100     → bg-slate-100 dark:bg-slate-800

We only patch JSX className strings (string literals + simple template
literals with no expressions). Anything dynamic stays untouched — those
warrant human review.

Usage:
  python tools/sweep_dark_mode_leakage.py --dry-run
  python tools/sweep_dark_mode_leakage.py
  python tools/sweep_dark_mode_leakage.py --paths src/pages/Marketing
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend" / "src"

# Pattern → its dark counterpart. Order matters — `bg-zinc-100` is checked
# before `bg-zinc-50` because we want literal substring uniqueness.
RULES = [
    (r"\bbg-white\b", "bg-white dark:bg-zinc-900"),
    (r"\bbg-zinc-100\b", "bg-zinc-100 dark:bg-zinc-800"),
    (r"\bbg-zinc-50\b", "bg-zinc-50 dark:bg-zinc-950/40"),
    (r"\bbg-gray-100\b", "bg-gray-100 dark:bg-gray-800"),
    (r"\bbg-gray-50\b", "bg-gray-50 dark:bg-gray-950/40"),
    (r"\bbg-slate-100\b", "bg-slate-100 dark:bg-slate-800"),
    (r"\bbg-slate-50\b", "bg-slate-50 dark:bg-slate-950/40"),
]
# Compile each rule once.
RULES = [(re.compile(pat), repl) for pat, repl in RULES]

# Match either:
#   className="..."        (static string)
#   className={"..."}      (JSX expression with a literal)
#   className={`...`}      (template literal with no ${} interpolation)
CLASS_PATTERNS = [
    re.compile(r'className="([^"]*)"'),
    re.compile(r"className=\{\s*'([^']*)'\s*\}"),
    re.compile(r"className=\{\s*\"([^\"]*)\"\s*\}"),
    re.compile(r"className=\{\s*`([^`${}]*)`\s*\}"),
]


def _has_dark_variant(class_str: str, light_class: str) -> bool:
    """Heuristic — if a corresponding `dark:bg-…` exists in the same
    className, treat the leak as already addressed."""
    return bool(re.search(r"\bdark:bg-", class_str))


def _patch_class_string(class_str: str) -> tuple[str, int]:
    """Apply each leak→fix rule. Skip if a `dark:bg-` is already present
    on the same className string — the author has explicitly handled it."""
    if _has_dark_variant(class_str, ""):
        return class_str, 0
    new = class_str
    n = 0
    for pat, repl in RULES:
        if pat.search(new) and "dark:bg-" not in new:
            new, count = pat.subn(repl, new, count=1)
            n += count
            # Re-evaluate — once we add a dark: variant the guard above
            # short-circuits subsequent rules. We want at most one
            # dark:bg-* per className string.
            if "dark:bg-" in new:
                break
    return new, n


def _patch_file(text: str) -> tuple[str, int]:
    total = 0

    def patch_match(m: re.Match) -> str:
        nonlocal total
        original = m.group(1)
        new, n = _patch_class_string(original)
        if n == 0:
            return m.group(0)
        total += n
        # Replace just the inner class string within the original match.
        return m.group(0).replace(original, new)

    out = text
    for pat in CLASS_PATTERNS:
        out = pat.sub(patch_match, out)
    return out, total


def main(dry_run: bool = False, paths: list[str] | None = None) -> None:
    targets: list[Path] = []
    if paths:
        for p in paths:
            base = ROOT / p
            if base.is_dir():
                targets.extend(base.rglob("*.js"))
                targets.extend(base.rglob("*.jsx"))
            elif base.is_file():
                targets.append(base)
    else:
        # Default: only the surfaces our ESLint rule covers.
        targets.extend((ROOT / "pages" / "Marketing").rglob("*.js"))
        targets.extend((ROOT / "pages" / "Marketing").rglob("*.jsx"))
        targets.append(ROOT / "components" / "shared" / "CrossModuleTipsBanner.js")

    files = 0
    repls = 0
    for path in targets:
        if not path.exists():
            continue
        original = path.read_text()
        if "className" not in original:
            continue
        new, count = _patch_file(original)
        if count == 0:
            continue
        files += 1
        repls += count
        if dry_run:
            print(f"[dry-run] {path} — {count} replacements")
        else:
            path.write_text(new)
            print(f"  {path} — {count} replacements")
    print(f"\nTotal: {files} files, {repls} replacements.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--paths", nargs="*", help="Optional paths relative to frontend/src")
    args = parser.parse_args()
    main(dry_run=args.dry_run, paths=args.paths)
