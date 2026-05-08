"""
PII redactor — masks emails, phone numbers, UK National Insurance numbers, and
credit card numbers in text BEFORE it hits the LLM.

Design
------
- Deterministic, regex-based (no LLM call — keeps latency low and avoids the
  recursive "LLM to sanitise what you're about to send to an LLM" trap).
- Returns both the masked text AND a reverse map so downstream code can
  selectively un-mask if the response needs a real value (e.g. surfacing a
  supplier's email back to the user).
- Conservative: match patterns err on the side of over-redaction. We'd rather
  mask one neutral phrase than leak a real email.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# Regex patterns, compiled once at module load.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# UK + international loose phone matcher — 10-14 digits w/ optional separators
_PHONE_RE = re.compile(r"(?:(?:\+?\d{1,3}[\s\-])?(?:\(?\d{2,5}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{3,4})")
_CC_RE = re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{3,4}\b")
# UK National Insurance: 2 letters, 6 digits, 1 letter
_NI_RE = re.compile(r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE)


@dataclass
class RedactionResult:
    text: str
    replacements: dict[str, str] = field(default_factory=dict)  # placeholder → original
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def any_found(self) -> bool:
        return sum(self.counts.values()) > 0


def _replace_all(text: str, pattern: re.Pattern, label: str,
                 state: RedactionResult) -> str:
    def repl(match: re.Match) -> str:
        original = match.group(0)
        idx = state.counts.get(label, 0) + 1
        state.counts[label] = idx
        placeholder = f"[{label}_{idx}]"
        state.replacements[placeholder] = original
        return placeholder
    return pattern.sub(repl, text)


def redact_pii(text: str) -> RedactionResult:
    """Scan text for PII and return `{text, replacements, counts}`.

    The returned `text` has each PII match replaced with `[TYPE_N]` (e.g.
    `[EMAIL_1]`) in order of appearance. `replacements` maps placeholder→original
    so callers can selectively un-mask if/when the LLM output references a
    placeholder we know is safe to reveal back to the same user.
    """
    state = RedactionResult(text=text)
    out = text
    # Order matters — credit cards are digit-heavy so run them before phone,
    # otherwise a long phone matcher may gobble them.
    out = _replace_all(out, _CC_RE, "CC", state)
    out = _replace_all(out, _EMAIL_RE, "EMAIL", state)
    out = _replace_all(out, _NI_RE, "NI", state)
    out = _replace_all(out, _PHONE_RE, "PHONE", state)
    state.text = out
    return state


def unmask(text: str, replacements: dict[str, str]) -> str:
    """Replace any `[TYPE_N]` placeholders back to their originals. Used
    sparingly — most of the time we LEAVE the masking in the LLM response."""
    for placeholder, original in replacements.items():
        text = text.replace(placeholder, original)
    return text
