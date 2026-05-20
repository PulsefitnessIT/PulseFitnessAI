"""Iter 216h244 — PageHeader title+subtitle suppression (Operations).

Single-source fix: the shared ``components/shared/PageHeader.js``
wrapper is used by every Operations sub-tab (Faults, Documents,
Staffing, Equipment, Reports, Check Sheets, Suppliers, etc.). The
title + subtitle render path is now suppressed and the component
returns ``null`` when no actions are provided, so the redundant
header collapses entirely.

This test guards against any future PR that re-renders the H2.
"""
from __future__ import annotations

import pathlib


def test_page_header_returns_null_when_no_actions():
    src = pathlib.Path("/app/frontend/src/components/shared/PageHeader.js").read_text()
    # The suppressed render path must short-circuit on missing actions.
    assert "if (!actions) return null;" in src, (
        "PageHeader must return null when called without an actions prop"
    )


def test_page_header_does_not_render_h2_or_subtitle():
    src = pathlib.Path("/app/frontend/src/components/shared/PageHeader.js").read_text()
    assert "<h2" not in src, "PageHeader must not render an H2 anymore"
    assert "page-header-title" not in src, "PageHeader title testid must be gone"
    assert "page-header-subtitle" not in src, "PageHeader subtitle testid must be gone"


def test_page_header_helphint_import_removed():
    """``HelpHint`` was only used by the now-deleted title block."""
    src = pathlib.Path("/app/frontend/src/components/shared/PageHeader.js").read_text()
    assert "HelpHint" not in src, "HelpHint import must be removed once the title block is gone"


def test_page_header_back_compat_props_swallowed():
    """Callers across the platform still pass ``title``/``subtitle``/
    ``icon``/``helpId``/``badge``. The component must accept (and
    discard) them silently via rest-spread."""
    src = pathlib.Path("/app/frontend/src/components/shared/PageHeader.js").read_text()
    assert "...rest" in src, (
        "PageHeader must absorb the legacy title/subtitle props via "
        "rest-spread so callers don't need edits"
    )
