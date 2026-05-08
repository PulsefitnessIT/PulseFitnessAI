"""Stored-XSS regression suite.

After iteration 205 we replaced ``html.escape`` with a tag-stripping
sanitiser (``utils.security.sanitise_string``). React already escapes
JSX text expressions, so over-encoding on the way *in* corrupted real
copy ("they're" → "they&#x27;re").

These tests prove two things:

1. Apostrophes, quotes and ampersands round-trip unchanged so user copy
   is preserved.
2. The classic stored-XSS payloads (script tags, event handlers,
   javascript: URIs, SVG handlers) are neutralised — the surviving
   string can never break out of a JSX text node into raw HTML.

If anyone re-introduces ``html.escape`` (or, equivalently, removes the
``[<>]`` strip), this file fails fast and prevents shipping the
regression to customers.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Make /app/backend importable when pytest is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.security import sanitise_string  # noqa: E402


# Payloads we have seen in real-world stored-XSS reports plus a few from
# OWASP's cheat-sheet. Each pair is (payload, must-not-appear-in-output).
XSS_PAYLOADS: list[str] = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    "<iframe src=javascript:alert(1)></iframe>",
    "<a href='javascript:alert(1)'>x</a>",
    "<body onload=alert(1)>",
    "\"><script>alert(1)</script>",
    "<style>body{background:red}</style>",
    "'-alert(1)-'",
    "<a/href='data:text/html,<script>alert(1)</script>'",
]


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_sanitiser_neutralises_xss(payload: str) -> None:
    """The single security guarantee we make: no ``<`` or ``>`` survives.

    Once tag delimiters are gone, React's automatic text-node escaping
    means whatever text remains is rendered as literal characters in the
    DOM — it cannot break out into raw HTML, attributes, or event
    handlers. So a payload like ``<img onerror=alert(1)>`` becomes the
    inert string ``img onerror=alert(1)`` in the page source.
    """
    cleaned = sanitise_string(payload)
    assert "<" not in cleaned and ">" not in cleaned, (
        f"sanitise_string left tag delimiters in output:\n  in:  {payload!r}\n  out: {cleaned!r}"
    )


@pytest.mark.parametrize(
    "user_text",
    [
        "they're rubbing against something",
        "Steps feel like they're loose",
        'Quote "test" inside body',
        "Q&A on Stripe & Resend",
        "Café résumé — with accents",
        "M&S receipt for £42.00",
        "Don't break apostrophes",
    ],
)
def test_sanitiser_preserves_real_text(user_text: str) -> None:
    """Real user copy must round-trip *unchanged* — we are NOT html-encoding."""
    cleaned = sanitise_string(user_text)
    assert cleaned == user_text, (
        f"sanitise_string mangled real copy:\n  in:  {user_text!r}\n  out: {cleaned!r}"
    )


def test_sanitiser_decodes_legacy_entities() -> None:
    """If existing data was stored html-escaped (pre-iteration-205) the
    sanitiser must decode it on the way through so we converge on plain
    text everywhere — not double-encode."""
    decoded = sanitise_string("they&#x27;re &amp; she&#39;s")
    assert "&#" not in decoded, "Legacy entity encoding survived sanitise_string"
    assert "they're" in decoded
    assert "she's" in decoded


def test_sanitiser_drops_control_chars() -> None:
    """NULL bytes and DEL must not survive — they confuse downstream
    tooling (logs, search indexes, CSV exports)."""
    cleaned = sanitise_string("hello\x00world\x7fend")
    assert "\x00" not in cleaned and "\x7f" not in cleaned
    assert cleaned == "helloworldend"


def test_sanitiser_handles_empty_and_none() -> None:
    """Edge cases that historically threw AttributeError."""
    assert sanitise_string("") == ""
    assert sanitise_string(None) is None  # type: ignore[arg-type]


def test_no_html_escape_regression() -> None:
    """Lock-in: if anyone re-introduces html.escape in this module the
    apostrophe round-trip immediately stops working. This is the canary
    test we point engineers at when the bug returns."""
    cleaned = sanitise_string("don't")
    # Specifically the exact corruption customers saw on the deployed
    # app — never let it ship again.
    assert "&#x27;" not in cleaned
    assert "&apos;" not in cleaned
    assert cleaned == "don't"


def test_brand_url_helper_routes_correctly(monkeypatch) -> None:
    """Sister test — equipment / supplier emails must point at the right
    public domain depending on org account_type. Lives next door because
    both protections were shipped together in iteration 205."""
    from utils.brand_urls import app_url_for

    # Clear any env override so we exercise the brand defaults.
    monkeypatch.delenv("BRAND_URL_GYMAXIS", raising=False)
    monkeypatch.delenv("BRAND_URL_PULSE", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)

    assert re.search(r"gymaxisai\.com$", app_url_for("gymaxis"))
    assert re.search(r"gymaxisai\.com$", app_url_for("lite"))
    assert re.search(r"gymaxisai\.com$", app_url_for(None))
    assert re.search(r"pulsefitness\.ai$", app_url_for("pulse"))
    assert re.search(r"pulsefitness\.ai$", app_url_for("pulse_pro"))
    assert re.search(r"pulsefitness\.ai$", app_url_for("PULSE"))  # case-insensitive

    # Per-brand override wins over the default.
    monkeypatch.setenv("BRAND_URL_PULSE", "https://staging.pulsefitness.ai")
    assert app_url_for("pulse") == "https://staging.pulsefitness.ai"
