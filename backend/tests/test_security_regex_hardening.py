"""Regression tests for SEC-001 — Mongo $regex injection / ReDoS hardening.

Verifies the central helpers escape every regex metacharacter so untrusted
search input can never be interpreted as a regex pattern (preventing ReDoS
and regex-injection), while preserving case-insensitive match semantics.
"""
import re

from utils.security_plus import safe_regex, safe_regex_exact


def test_safe_regex_escapes_metacharacters():
    clause = safe_regex(".*+[(a+)+")
    # The stored pattern must be the LITERAL escaped string, never a live regex.
    assert clause["$regex"] == re.escape(".*+[(a+)+")
    assert clause["$options"] == "i"
    # A genuine substring still matches after escaping.
    assert re.search(clause["$regex"], "x.*+[(a+)+y", re.I)


def test_safe_regex_redos_payload_is_literal():
    # Classic catastrophic-backtracking pattern — must be treated literally,
    # so matching against a long string is instant, not exponential.
    payload = "(a+)+$"
    clause = safe_regex(payload)
    assert re.search(clause["$regex"], "the (a+)+$ token", re.I)
    # And it must NOT behave like the dangerous live regex.
    assert re.fullmatch(clause["$regex"], "a" * 30) is None


def test_safe_regex_handles_none_and_whitespace():
    assert safe_regex(None)["$regex"] == ""
    assert safe_regex("  hi  ")["$regex"] == re.escape("hi")


def test_safe_regex_exact_is_anchored_and_escaped():
    clause = safe_regex_exact("a.b+c")
    assert clause["$regex"] == f"^{re.escape('a.b+c')}$"
    # Whole-string match only.
    assert re.fullmatch(clause["$regex"], "a.b+c", re.I)
    assert re.fullmatch(clause["$regex"], "aXbYc") is None  # '.' / '+' are literal


def test_safe_regex_exact_none():
    assert safe_regex_exact(None)["$regex"] == "^$"
