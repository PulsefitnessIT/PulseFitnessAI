"""Iter 220dz / 220e0 — Hide empty custom-field placeholders + cover-aware close-out.

Two operator-driven adjustments from the next screenshot round:

  1. **Empty machine-row custom fields no longer clog the Equipment
     tab.** Previously every machine row rendered an
     "No custom fields yet for this machine type. Tap + Custom
     field to add one" placeholder (~80px tall) even when the org
     had nothing pre-configured. Now we collapse the entire panel
     to a tiny "+ Custom field" link until either:
       * an admin pre-configures a field for the job-type /
         equipment scope in Account Settings,
       * the engineer has saved a value on this row, or
       * the engineer actively opens the create editor.

  2. **Close-out flow respects warranty / contract cover.** When
     the case carries an active warranty or service contract:
       * Top of the Outcome card surfaces a green "Under … cover"
         banner with detail + a "Misuse — bill anyway" checkbox.
       * Close-out button defaults to ``target='repaired'``
         (not ``'closed'``) and ``chargeable=False``.
       * Invoice draft generation is skipped — only the branded
         service report goes to the customer.
       * Fast-path CTA label flips to "close & send the report".
       * "Close & invoice" chip becomes "Close (no invoice)".
     The misuse override re-enables the invoice path so engineers
     can still charge for chargeable mis-use.
"""
from __future__ import annotations

from pathlib import Path


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── 1 · MachineRowCustomFields collapses when empty ──────────────


def test_machine_row_custom_fields_collapses_when_no_fields():
    src = _read("pages/ServiceOps/Engineer/MachineRowCustomFields.js")
    # New collapsed branch pinned by testid.
    assert "data-testid={`mrcf-collapsed-${row.id}`}" in src
    # Guard logic: hide only when fields empty AND not creating AND
    # no saved values on this row.
    assert "fields.length === 0 && !creating && !hasSavedValues" in src
    # Old verbose placeholder copy removed.
    assert "No custom fields yet for this machine type" not in src


def test_machine_row_custom_fields_still_renders_with_existing_values():
    """If the engineer already saved a value on a row, we MUST keep
    the panel open so the value stays visible/editable."""
    src = _read("pages/ServiceOps/Engineer/MachineRowCustomFields.js")
    assert "hasSavedValues = Object.keys(row.custom_fields || {}).length > 0" in src


# ── 2 · Cover-aware Outcome card ──────────────────────────────────


def test_complete_tab_renders_cover_banner_when_covered():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # New computed cover state + banner testids.
    assert "const coverState = useMemo" in src
    assert 'data-testid="complete-cover-banner"' in src
    assert 'data-testid="complete-cover-label"' in src
    # Banner is gated on covered cases only.
    assert "coverState.covered ? (" in src
    # Misuse override checkbox lives inside the banner.
    assert 'data-testid="complete-misuse-override"' in src


def test_close_chip_label_swaps_to_no_invoice_when_covered():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The Close chip label adapts to cover state.
    assert (
        "coverState.covered && !misuseOverride ? 'Close (no invoice)' : 'Close & invoice'"
        in src
    )


def test_auto_invoice_toggle_hidden_when_covered():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Auto-invoice toggle conditional on NOT covered. The misuse
    # override controls billing for covered cases instead.
    assert "{!coverState.covered && (" in src


# ── 3 · Cover-aware close-out submit ──────────────────────────────


def test_complete_submit_honours_will_bill_flag():
    """`chargeable: true` was hard-coded on every complete call;
    iter 220e0 makes it follow the cover-aware `willBill` flag."""
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert "chargeable: willBill," in src
    # And the legacy hard-coded true is gone from the manual path.
    assert "summary: summary.trim(), target, chargeable: true," not in src


def test_fast_path_skips_invoice_when_covered_and_no_misuse():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The fast-path generates an invoice ONLY when willBill is true.
    assert "if (willBill) {" in src
    # And the close-out target flips to "repaired" instead of
    # "closed" when covered (so the case isn't auto-locked to the
    # invoice workflow).
    assert (
        "coverState.covered && !misuseOverride ? 'repaired' : 'closed'"
        in src
    )


def test_fast_path_button_label_swaps_when_covered():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Covered + no misuse → "close & send the report"
    assert "close & send the report" in src
    # Otherwise → existing "close & send the invoice"
    assert "close & send the invoice" in src


def test_cover_state_recognises_contract_warranty_and_explicit_cover_type():
    """The `coverState` memo must consider all three cover signals:
       * `source_meta.coverage_status === 'covered'`
       * `source_meta.warranty_active`
       * a non-default `cover_type` on the case
    plus drive the friendly label off the active source."""
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert "warrantyActive = !!meta.warranty_active" in src
    assert "Under manufacturer warranty" in src
    assert "service contract" in src
    # The 'chargeable' / 'none' cover slugs are treated as "no cover".
    assert "cover !== 'chargeable' && cover !== 'none'" in src
