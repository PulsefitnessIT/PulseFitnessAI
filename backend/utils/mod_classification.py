"""MOD Classification sanitiser.

Iter 216h115 — scans free-text fields submitted to MOD endpoints for
patterns that suggest the user has accidentally typed information ABOVE
OFFICIAL (the classification the portal is approved for). Returns a
list of flagged tokens. The caller decides whether to refuse, warn, or
silently flag the record for HQ review.

Patterns covered (conservative — high precision, low recall, since
false positives erode trust):

  • UK NSN (NATO Stock Number)         13-digit dash pattern: 1234-12-123-1234
  • DefenceConnect callsign-style      "C/S xxx", "callsign xxx"
  • Operation names                    "OPERATION xxx" or "OP xxx"
  • SECRET / TOP SECRET literal mentions

The list is intentionally short — extend only after legal review.
"""
from __future__ import annotations

import re
from typing import Iterable

# Compiled once on import. Each entry: (label, pattern).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "NSN",
        re.compile(r"\b\d{4}-\d{2}-\d{3}-\d{4}\b"),
    ),
    (
        "Callsign",
        re.compile(r"\b(?:c\s*/?\s*s|callsign)\s+[a-z0-9]{2,6}\b", re.IGNORECASE),
    ),
    (
        "Operation name",
        re.compile(r"(?i)\b(?:operation|op)\b\s+(?-i:[A-Z][A-Z0-9]{3,})\b"),
    ),
    (
        "Higher classification",
        re.compile(r"\b(?:SECRET|TOP\s+SECRET|UK\s+SECRET)\b"),
    ),
]


def scan_text(value: str | None) -> list[dict]:
    """Return a list of ``{label, match}`` for each suspect token found.

    Empty list means the text scanned clean. The caller is free to:
      • Block the submission outright (strict mode).
      • Persist the flag and email HQ for review (default).
      • Display a banner asking the user to confirm classification.
    """
    if not value:
        return []
    flags: list[dict] = []
    for label, pattern in _PATTERNS:
        for m in pattern.finditer(value):
            flags.append({"label": label, "match": m.group(0)[:120]})
            if len(flags) >= 10:
                return flags
    return flags


def scan_many(values: Iterable[str | None]) -> list[dict]:
    """Convenience helper — scan every value and return all flags
    deduplicated by ``(label, match)``."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for v in values:
        for flag in scan_text(v):
            key = (flag["label"], flag["match"].lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(flag)
    return out
