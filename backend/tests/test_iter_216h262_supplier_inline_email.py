"""Iter 216h262 — Supplier inline-email + dark-mode chip readability.

User feedback with screenshot (Feb 21, 2026):
* "Change supplier field — has a black button" — in the Pulse Pro
  dark-mode equipment modal, the SupplierMultiPicker in single-pick
  mode showed the selected supplier as a near-invisible slate-900
  chip on the surrounding dark surface. The chip + button looked
  like one black rectangle.
* "If the owner/manager changes the supplier and the email address
  for the supplier isn't pre-populated they need the ability to add
  the email address for the supplier — otherwise emails won't be
  sent."

Frontend changes only — no schema changes. Reuses the existing
`POST /api/suppliers` endpoint with `send_welcome: false` so we
don't spam the new supplier with an onboarding email until the
manager is ready.
"""
from __future__ import annotations

import pathlib
import re


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. SupplierMultiPicker — single-mode chip readability ─────────


def test_picker_chip_uses_distinct_styling_in_single_mode():
    src = pathlib.Path(
        "/app/frontend/src/components/shared/SupplierMultiPicker.jsx"
    ).read_text()
    # Single-mode chip should use a soft outlined style, not the
    # default slate-900 pill (which was invisible in dark Pulse Pro).
    assert "single" in src
    assert "border-slate-300 bg-slate-100 text-slate-900" in src
    assert "dark:border-zinc-600 bg-zinc-800 text-zinc-100".replace(" ", "") in src.replace(" ", "") \
        or "dark:bg-zinc-800" in src


def test_picker_wrapper_supports_dark_mode():
    src = pathlib.Path(
        "/app/frontend/src/components/shared/SupplierMultiPicker.jsx"
    ).read_text()
    # The outer field wrapper now responds to dark mode so it doesn't
    # render as a stark white rectangle on Pulse Pro modals.
    assert "dark:bg-zinc-900" in src
    assert "dark:text-zinc-100" in src


# ─── 2. SupplierEditor — inline "Add to directory" form ────────────


def test_supplier_editor_accepts_new_props():
    src = pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/LiteDialogs.js"
    ).read_text()
    assert "onSupplierAdded" in src
    assert "authToken" in src
    # Parent must hand the new entry into supplierOptions
    assert "setSupplierOptions((prev) => [...prev, newSupplier])" in src


def test_supplier_editor_renders_email_input_when_missing_from_directory():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/LiteDialogs.js"
    ).read_text())
    assert 'data-testid="lite-equip-supplier-add-email"' in src
    assert 'data-testid="lite-equip-supplier-add-to-directory"' in src
    assert "+ Add to directory" in src


def test_supplier_editor_posts_with_send_welcome_false():
    """Don't spam the supplier — we just want them in the directory so
    fault emails route. The manager can trigger /send-welcome later."""
    src = pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/LiteDialogs.js"
    ).read_text()
    assert "/api/suppliers" in src or "API_BASE}/suppliers" in src
    assert "send_welcome: false" in src


def test_supplier_editor_validates_email_shape():
    src = pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/LiteDialogs.js"
    ).read_text()
    # Loose but useful client-side guard
    assert "[^\\s@]+@[^\\s@]+\\.[^\\s@]+" in src


def test_warning_callout_remains_in_place():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/LiteDashboard/LiteDialogs.js"
    ).read_text())
    # The old warning message must still be present so engineers
    # understand WHY they're being asked for an email.
    assert "isn't in your supplier directory yet" in src or "isn&apos;t in your supplier directory yet" in src
