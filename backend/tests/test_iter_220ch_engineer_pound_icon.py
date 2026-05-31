"""Iter 220ch — Engineer-app currency-icon localisation (UK GBP).

The engineer dashboard preview showed a Lucide ``Receipt`` icon (which
renders a literal ``$`` glyph inside the receipt) next to the
"New invoice" quick action, the "Invoiced" KPI tile, and the
"Invoices" workspace tab. The user (UK fitness-industry product)
reported "Engineer app — Change $ to £".

The fix swaps ``Receipt`` for ``ReceiptPoundSterling`` (aliased as
``Receipt`` in each file so the rest of the JSX stays untouched).
This test pins that swap by reading the engineer-page source files
and asserting:

  1. The bare ``Receipt`` import is gone.
  2. ``ReceiptPoundSterling as Receipt`` is imported instead.

If anyone reverts to ``Receipt`` (or copy-pastes from a US-locale
template), this test fails immediately.
"""
from __future__ import annotations

import os
import re

ENGINEER_PAGES = [
    "/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js",
    "/app/frontend/src/pages/ServiceOps/Engineer/EngineerQuotes.js",
    "/app/frontend/src/pages/ServiceOps/Engineer/EngineerInvoices.js",
    "/app/frontend/src/pages/ServiceOps/Engineer/EngineerWorkspace.js",
    "/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js",
    "/app/frontend/src/pages/ServiceOps/Engineer/EngineerCustomers.js",
]


def _imports_block(text: str) -> str:
    """Grab the top-level ``import { … } from 'lucide-react';`` block."""
    match = re.search(
        r"import\s*\{([^}]*)\}\s*from\s*['\"]lucide-react['\"]\s*;",
        text, flags=re.DOTALL,
    )
    assert match, "expected a lucide-react import block"
    return match.group(1)


def test_engineer_files_use_pound_receipt_icon():
    for path in ENGINEER_PAGES:
        assert os.path.exists(path), path
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        block = _imports_block(src)
        # Must alias the pound-sterling receipt as Receipt — keeps the
        # rest of the JSX (`icon={Receipt}`, `<Receipt size={…} />`)
        # working without further diff.
        assert "ReceiptPoundSterling as Receipt" in block, (
            f"{path}: expected `ReceiptPoundSterling as Receipt` in "
            f"lucide-react import block (got: {block.strip()})"
        )
        # Must NOT contain a bare `Receipt` import (no comma-separated
        # `Receipt,` or trailing `Receipt` token) outside the alias.
        # Tokenise on commas and strip whitespace.
        tokens = [t.strip() for t in block.split(",") if t.strip()]
        bare = [t for t in tokens if t == "Receipt"]
        assert not bare, (
            f"{path}: bare `Receipt` import found — must be aliased "
            f"from ReceiptPoundSterling (tokens: {tokens})"
        )


def test_engineer_pages_have_no_dollar_glyph_in_jsx_strings():
    """Sanity — no literal '$' glyph in user-facing JSX strings.
    Skips template-literal interpolations (``${var}``), env vars, and
    regex/escape sequences."""
    bad: list[str] = []
    for path in ENGINEER_PAGES:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                # Strip ${...} interpolations.
                stripped = re.sub(r"\$\{[^}]*\}", "", line)
                # Skip env vars and regex anchors.
                if "process.env" in stripped or "/\\$/" in stripped:
                    continue
                # Look for a bare $ next to a digit or in a JSX text node.
                # JSX text nodes appear as `>$` or `"$"` literal strings.
                if re.search(r'>[^<>{]*\$[^<>{]*<', stripped) or re.search(r'["\']\$[0-9 ]', stripped):
                    bad.append(f"{path}:{lineno}: {line.rstrip()}")
    assert not bad, "Literal $ glyphs found in engineer JSX:\n" + "\n".join(bad)
