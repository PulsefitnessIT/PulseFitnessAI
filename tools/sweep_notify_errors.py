#!/usr/bin/env python3
"""Codemod: sweep `notify.error(err.response?.data?.detail || 'X')` to
`notifyApiError(notify, err, 'X')` and ensure each touched file imports
the helper.

Used during Iter 234/236 to roll smart error toasts across the operator
consoles. Idempotent — running again produces zero changes.

Patterns rewritten (any of `e`, `err`, `error` as the captured var):

  notify.error(e?.response?.data?.detail || 'X')
  notify.error(e.response?.data?.detail || 'X')
  notify.error(e?.response?.data?.detail || 'X', { duration: N })   # duration dropped

Patterns deliberately untouched:
  • notify.error('static string')           — no axios error available
  • notify.error(msg)                       — pre-extracted variable
  • notify.error(`prefix: ${err...}`)       — template literal
  • notify.error('with apos\\' chars')      — apostrophe-escaped strings
                                              (covered by reading the file
                                              & manual review if needed)

Run from repo root:
  python tools/sweep_notify_errors.py --dry-run
  python tools/sweep_notify_errors.py
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend" / "src"

PATTERN = re.compile(
    r"notify\.error\(\s*"
    r"(?P<var>[A-Za-z_]\w*)\??\.response\?\.data\?\.detail\s*\|\|\s*"
    r"(?P<msg>'[^']*'|\"[^\"]*\")"
    r"(?P<dur>\s*,\s*\{\s*duration\s*:\s*\d+\s*\})?"
    r"\s*\)"
)
IMPORT_NOTIFY = re.compile(r"import\s*\{[^}]*\bnotify\b[^}]*\}\s*from\s*['\"]@/components/notifications['\"];")
IMPORT_API_ERR_PRESENT = re.compile(r"\bnotifyApiError\b\s*}?\s*from\s*['\"]@/lib/formatApiError['\"]")


def _has_import(text: str) -> bool:
    return bool(IMPORT_API_ERR_PRESENT.search(text))


def _add_import(text: str) -> str:
    if _has_import(text):
        return text
    if IMPORT_NOTIFY.search(text):
        return IMPORT_NOTIFY.sub(
            lambda m: m.group(0) + "\nimport { notifyApiError } from '@/lib/formatApiError';",
            text, count=1,
        )
    react_import = re.search(r"^import\s+React[^;]*;", text, re.M)
    if react_import:
        idx = react_import.end()
        return text[:idx] + "\nimport { notifyApiError } from '@/lib/formatApiError';" + text[idx:]
    return text


def _rewrite(text: str) -> tuple[str, int]:
    n = 0

    def replace(m: re.Match) -> str:
        nonlocal n
        n += 1
        return f"notifyApiError(notify, {m.group('var')}, {m.group('msg')})"

    new_text = PATTERN.sub(replace, text)
    return new_text, n


def main(dry_run: bool = False) -> None:
    total_files = 0
    total_replacements = 0
    for path in ROOT.rglob("*.js"):
        if "node_modules" in path.parts:
            continue
        if path.name in {"formatApiError.js", "RecentErrorsPanel.js"}:
            continue
        original = path.read_text()
        if "notify.error" not in original:
            continue
        new, count = _rewrite(original)
        if count == 0:
            continue
        if not _has_import(new):
            new = _add_import(new)
        if new == original:
            continue
        total_files += 1
        total_replacements += count
        if dry_run:
            print(f"[dry-run] {path} — {count} replacements")
        else:
            path.write_text(new)
            print(f"  {path} — {count} replacements")
    print(f"\nTotal: {total_files} files, {total_replacements} replacements.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
