"""Iter 220cj — frontend wiring pins for the 5-feature batch.

Read-only checks that the JS surface for the user-reported items is in
place; behavioural validation is done by the testing agent.

  * EngineerQueue.js — has a 'View details' button on each row + a
    PreviewModal component reachable via ``setPreviewFor``.
  * EngineerNewJob.js — Estimated time renders two ``<select>``s
    (hours / minutes) instead of a single number input.
  * EngineerCustomers.js — Companies House lookup block, mandatory
    field markers, per-field error testids.
  * EngineerEquipment.js — CSV template + Import buttons.
  * WorkVisitMachinesCard.js — "From site" trigger + the
    SiteEquipmentPicker component below it.
"""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_queue_has_preview_modal_and_button():
    src = _read("pages/ServiceOps/Engineer/EngineerQueue.js")
    assert "PreviewModal" in src
    assert 'data-testid="queue-preview-modal"' in src
    assert 'data-testid="queue-preview-allocate"' in src
    # Row exposes a "View details" trigger that opens the preview.
    assert 'queue-preview-' in src  # row-level testid pattern
    # Wired into state.
    assert "setPreviewFor" in src
    # Fetches the new endpoint.
    assert "/svc/engineer/queue/" in src and "/preview" in src


def test_new_job_hours_minutes_dropdowns():
    src = _read("pages/ServiceOps/Engineer/EngineerNewJob.js")
    assert 'data-testid="newjob-estimated-hours"' in src
    assert 'data-testid="newjob-estimated-minutes"' in src
    # Old single-input testid must be gone — the form now uses 2
    # dropdowns that compose into estimated_minutes.
    assert 'data-testid="newjob-estimated"' not in src
    # Hours dropdown spans 0..8.
    assert 'length: 9' in src


def test_new_customer_modal_companies_house_and_mandatory():
    src = _read("pages/ServiceOps/Engineer/EngineerCustomers.js")
    # Companies House lookup block.
    assert 'data-testid="customer-form-ch-block"' in src
    assert 'data-testid="customer-form-ch-search"' in src
    # Per-field error testids — iter 220ck split the address into
    # structured fields, so the legacy ``site-address-error`` was
    # replaced by ``address-line1-error`` + ``city-error`` +
    # ``postcode-error``. Required: name, email, phone, site_name,
    # address_line1, city, postcode (7 fields).
    for tid in (
        "customer-form-name-error",
        "customer-form-email-error",
        "customer-form-phone-error",
        "customer-form-site-name-error",
        "customer-form-address-line1-error",
        "customer-form-city-error",
        "customer-form-postcode-error",
    ):
        assert tid in src, f"missing {tid}"
    # Required asterisks on labels (defensive — match the CRM form).
    assert "Email *" in src
    assert "Phone *" in src
    assert "Site name *" in src
    assert "Address line 1 *" in src
    # Email-format regex actually present.
    assert "/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/" in src


def test_equipment_csv_actions_present():
    """SUPERSEDED by Iter 220cl — CSV actions were moved off the
    Engineer Equipment page and into the per-customer drawer
    (see ``test_iter_220cl_engineer_csv_move.py``). Kept as a stub
    so the iter trail stays auditable but no longer asserts the
    legacy testids."""
    src = _read("pages/ServiceOps/Engineer/EngineerEquipment.js")
    # Sanity: the legacy testids really are gone.
    assert 'data-testid="equipment-csv-actions"' not in src
    assert 'data-testid="equipment-csv-download"' not in src
    assert 'data-testid="equipment-csv-import"' not in src


def test_machines_card_has_from_site_picker():
    src = _read("pages/ServiceOps/Engineer/WorkVisitMachinesCard.js")
    assert 'data-testid="machines-load-from-site-btn"' in src
    assert "SiteEquipmentPicker" in src
    assert 'data-testid="site-equipment-picker"' in src
    assert 'data-testid="site-equipment-picker-select-all"' in src
    assert 'data-testid="site-equipment-picker-attach"' in src
    # Picker fetches the new backend endpoint.
    assert "/site-equipment" in src
    assert "/machines/bulk-from-site" in src


def test_picker_select_all_handles_toggle():
    """Sanity: the SiteEquipmentPicker toggleAll uses a Set + the
    ``selectable`` (non-disabled) collection — so 'Select all' never
    flags already-attached items as selected."""
    src = _read("pages/ServiceOps/Engineer/WorkVisitMachinesCard.js")
    assert "toggleAll" in src
    assert "already_on_job" in src
    # The CTA disables when nothing is ticked.
    assert "selected.size === 0" in src
