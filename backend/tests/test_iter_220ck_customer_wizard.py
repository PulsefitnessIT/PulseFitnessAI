"""Iter 220ck — Engineer customer onboarding redesign tests.

User feedback (Feb 2026): "this section needs to be similar to how we
on board on Master Admin. Break the address box up into separate
fields, easier for reporting. Equipment import inside the customer
modal (a separate tab)."

Backend pins:
  * ``CustomerIn`` accepts structured address fields (line1/line2/city/
    county/postcode/country) + ``company_number``.
  * ``_norm_postcode`` formats UK postcodes with a single space before
    the in-bound code (``"ls101ab" → "LS10 1AB"``).
  * ``_compose_address`` stitches the structured fields back into the
    legacy ``site_address`` string for old reports.
  * ``_to_doc`` writes both the structured + legacy columns.

Frontend pins:
  * EngineerCustomers.js exposes a 3-step wizard (Identity / Site /
    Equipment) with the canonical test IDs.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── 1 · Schema accepts structured address ─────────────────────────────


def test_customer_in_accepts_structured_address():
    from routes.svc.engineer_customers import CustomerIn
    obj = CustomerIn(
        name="Acme Gyms",
        email="info@acme.co.uk",
        phone="+447826844544",
        site_name="Acme Leeds",
        address_line1="12 Industrial Way",
        address_line2="Unit 4",
        city="Leeds",
        county="West Yorkshire",
        postcode="ls10 1ab",
        country="United Kingdom",
        company_number="04354059",
    )
    assert obj.address_line1 == "12 Industrial Way"
    assert obj.city == "Leeds"
    assert obj.postcode == "ls10 1ab"  # raw on the model; normalised by _to_doc


def test_customer_in_country_defaults_to_uk():
    from routes.svc.engineer_customers import CustomerIn
    obj = CustomerIn(name="X")
    assert obj.country == "United Kingdom"


def test_norm_postcode_uk_format():
    from routes.svc.engineer_customers import _norm_postcode
    assert _norm_postcode("ls101ab") == "LS10 1AB"
    assert _norm_postcode("LS10 1AB") == "LS10 1AB"
    assert _norm_postcode("ls10  1ab") == "LS10 1AB"
    assert _norm_postcode("  ") is None
    assert _norm_postcode(None) is None
    # Non-UK postcodes returned uppercased without rewrite.
    assert _norm_postcode("90210") == "90210"


def test_compose_address_stitches_structured_fields():
    from routes.svc.engineer_customers import _compose_address, CustomerIn
    payload = CustomerIn(
        name="X",
        address_line1="12 Industrial Way",
        address_line2="Unit 4",
        city="Leeds",
        postcode="LS10 1AB",
    )
    out = _compose_address(payload)
    assert "12 Industrial Way" in out
    assert "Unit 4" in out
    assert "Leeds" in out
    assert "LS10 1AB" in out


def test_compose_address_returns_none_when_empty():
    from routes.svc.engineer_customers import _compose_address, CustomerIn
    assert _compose_address(CustomerIn(name="X")) is None


def test_to_doc_writes_both_structured_and_legacy():
    from routes.svc.engineer_customers import _to_doc, CustomerIn
    payload = CustomerIn(
        name="Acme",
        email="info@acme.co.uk",
        phone="+447826844544",
        site_name="Acme Leeds",
        address_line1="12 Industrial Way",
        city="Leeds",
        postcode="ls101ab",
    )
    doc = _to_doc(payload, org_id="org-1", user_id="u-1")
    # Structured fields preserved.
    assert doc["address_line1"] == "12 Industrial Way"
    assert doc["city"] == "Leeds"
    # Postcode normalised.
    assert doc["postcode"] == "LS10 1AB"
    # Legacy `site_address` composed when not explicitly provided.
    assert "12 Industrial Way" in doc["site_address"]
    assert "Leeds" in doc["site_address"]
    assert "LS10 1AB" in doc["site_address"]
    # Defaults.
    assert doc["country"] == "United Kingdom"


def test_to_doc_preserves_explicit_site_address():
    """When the engineer provides ``site_address`` directly, the
    composer must not overwrite it (back-compat for older clients)."""
    from routes.svc.engineer_customers import _to_doc, CustomerIn
    payload = CustomerIn(
        name="Acme", site_address="Custom address string",
        address_line1="Different", city="London",
    )
    doc = _to_doc(payload, org_id="org-1", user_id="u-1")
    assert doc["site_address"] == "Custom address string"


# ── 2 · Create endpoint writes structured fields ──────────────────────


def test_create_customer_persists_structured_fields():
    from routes.svc.engineer_customers import create_customer, CustomerIn

    fdb = MagicMock()
    fdb.svc_engineer_customers.find_one = AsyncMock(return_value=None)
    fdb.svc_engineer_customers.insert_one = AsyncMock()

    payload = CustomerIn(
        name="Acme",
        email="info@acme.co.uk",
        phone="+447826844544",
        site_name="Acme Leeds",
        address_line1="12 Industrial Way",
        city="Leeds",
        postcode="LS10 1AB",
        company_number="04354059",
    )

    async def go():
        with patch("routes.svc.engineer_customers.db", fdb):
            return await create_customer(payload, {
                "id": "u-1", "organization_id": "org-1",
            })
    out = _run(go())
    fdb.svc_engineer_customers.insert_one.assert_awaited_once()
    doc = fdb.svc_engineer_customers.insert_one.await_args.args[0]
    assert doc["address_line1"] == "12 Industrial Way"
    assert doc["city"] == "Leeds"
    assert doc["postcode"] == "LS10 1AB"
    assert doc["company_number"] == "04354059"
    assert out["merged"] is False


# ── 3 · Frontend wizard wiring pins ───────────────────────────────────


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_engineer_customers_renders_three_step_wizard():
    src = _read("pages/ServiceOps/Engineer/EngineerCustomers.js")
    # Stepper with 3 steps.
    assert 'WIZARD_STEPS' in src
    assert "'identity'" in src
    assert "'site'" in src
    assert "'equip'" in src
    # Stepper testid.
    assert 'data-testid="customer-wizard-stepper"' in src
    # Step pane testids.
    for pane_tid in (
        'customer-wizard-pane-identity',
        'customer-wizard-pane-site',
        'customer-wizard-pane-equipment',
    ):
        assert pane_tid in src, f"missing {pane_tid}"
    # Forward + back nav buttons.
    assert 'data-testid="customer-wizard-next"' in src
    assert 'data-testid="customer-wizard-back"' in src


def test_engineer_customers_uses_structured_address_inputs():
    src = _read("pages/ServiceOps/Engineer/EngineerCustomers.js")
    for tid in (
        'customer-form-address-line1',
        'customer-form-address-line2',
        'customer-form-city',
        'customer-form-county',
        'customer-form-postcode',
        'customer-form-country',
    ):
        assert tid in src, f"missing {tid}"
    # The legacy single-textarea testid must be gone.
    assert 'customer-form-site-address"' not in src
    # Per-field error testids for required address fields.
    for tid in (
        'customer-form-address-line1-error',
        'customer-form-city-error',
        'customer-form-postcode-error',
    ):
        assert tid in src, f"missing {tid}"


def test_form_state_includes_structured_address_defaults():
    src = _read("pages/ServiceOps/Engineer/EngineerCustomers.js")
    # EMPTY_FORM must seed the structured fields so React state is
    # consistent across mount.
    body = re.search(r"const EMPTY_FORM\s*=\s*\{[^}]+\}", src, re.DOTALL)
    assert body, "EMPTY_FORM not found"
    blob = body.group(0)
    for key in (
        "address_line1", "address_line2", "city", "county",
        "postcode", "country", "company_number",
    ):
        assert key in blob, f"EMPTY_FORM missing {key!r}"
    # Country default is the UK.
    assert "'United Kingdom'" in blob


def test_companies_house_pick_populates_structured_address():
    """When the engineer taps a Companies House result, the structured
    address fields must be filled (so the Site step renders pre-filled
    when they navigate forward)."""
    src = _read("pages/ServiceOps/Engineer/EngineerCustomers.js")
    assert "address_line1: addr.address_line_1" in src
    assert "city: addr.locality" in src
    assert "postcode: addr.postal_code" in src
