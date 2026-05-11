"""
Iter 216h12 — Carshalton invoice import: missing details + supplier matching.

Pins:
  1. `_PDF_TEXT_MAX_CHARS` lifted from 12 000 → 40 000 so multi-page
     invoices like Carshalton (24 090 chars; 88 line items) don't get
     chopped halfway through. The bug surface (truncation cap) is
     pinned as a regression so any future "let's downsize the prompt"
     refactor explicitly trips this test.
  2. `_build_extraction_prompt` actually uses the new cap.
  3. `_normalise_supplier_name` collapses 'Pulse Fitness Limited' →
     'Pulse Fitness' → 'PULSE FITNESS LTD.' to the same key.
  4. `match_supplier` returns None when no org match.
  5. `match_supplier` finds exact-name matches, normalised-name
     matches, and VAT-number matches in the org's directory.

These tests stub the LLM call — they do NOT consume Emergent LLM
budget. The end-to-end Carshalton extraction will need a budget top-up
on the universal key before it can be verified against a live invoice.
"""
from __future__ import annotations

import os
import uuid

import pytest
from pymongo import MongoClient

from routes.equipment_import import (  # noqa: E402
    _PDF_TEXT_MAX_CHARS,
    _build_extraction_prompt,
    _normalise_supplier_name,
    match_supplier,
)

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def db():
    assert MONGO_URL and DB_NAME
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(autouse=True)
def patch_motor_to_current_loop(monkeypatch):
    """The module-level Motor client in `utils.database` is bound to the
    server's startup event loop. Pytest-anyio spawns a fresh loop per
    test, so any awaited Motor call from inside `match_supplier` will
    raise 'Future attached to a different loop'. Rebind a Motor client
    in the test's own loop and monkey-patch the equipment_import
    module's `db` reference to it for the duration of the test."""
    from motor.motor_asyncio import AsyncIOMotorClient
    fresh_client = AsyncIOMotorClient(MONGO_URL)
    fresh_db = fresh_client[DB_NAME]
    import routes.equipment_import as ei
    monkeypatch.setattr(ei, "db", fresh_db)
    yield
    fresh_client.close()


def test_truncation_cap_covers_carshalton_size():
    """The Carshalton invoice was 24 090 chars; the previous 12 000 cap
    silently dropped half the line items + totals. Lock the cap at
    >= 24 000 so this regression can't reappear silently."""
    assert _PDF_TEXT_MAX_CHARS >= 24_000


def test_build_prompt_uses_the_full_text_when_under_cap():
    """A 20 K-char invoice must be passed through in full."""
    text = "X" * 20_000
    prompt = _build_extraction_prompt(text)
    assert text in prompt


def test_build_prompt_truncates_oversized_text_at_cap():
    """Above the cap, only the first N chars are sent (cost + latency).
    Compare body length by subtracting the template length."""
    base_prompt_len = len(_build_extraction_prompt(""))
    big_text = "Y" * (_PDF_TEXT_MAX_CHARS + 5_000)
    big_prompt_len = len(_build_extraction_prompt(big_text))
    # body_len = big_prompt_len - base_prompt_len → should equal exactly
    # _PDF_TEXT_MAX_CHARS (the truncation kept first N chars).
    body_len = big_prompt_len - base_prompt_len
    assert body_len == _PDF_TEXT_MAX_CHARS


def test_normalise_supplier_strips_company_suffixes_and_case():
    """All four shapes must collapse to the same key."""
    targets = [
        "Pulse Fitness",
        "Pulse Fitness Limited",
        "PULSE FITNESS LTD.",
        "pulse-fitness ltd",
    ]
    keys = {_normalise_supplier_name(t) for t in targets}
    assert keys == {"pulsefitness"}


def test_normalise_empty_returns_empty():
    assert _normalise_supplier_name("") == ""
    assert _normalise_supplier_name(None) == ""


@pytest.fixture
def seeded_org_and_supplier(db):
    org_id = f"test-org-216h12-{uuid.uuid4().hex[:8]}"
    sup_id = f"test-sup-216h12-{uuid.uuid4().hex[:8]}"
    db.suppliers.insert_one({
        "id": sup_id,
        "organization_id": org_id,
        "name": "Pulse Fitness",
        "vat_number": "785413509",
        "email": "info@pulsefitness.com",
        "phone": "+44 (0)1260 294600",
        "address": "Radnor Park Greenfield Road, Congleton, CW12 4TW",
    })
    yield org_id, sup_id
    db.suppliers.delete_many({"id": sup_id})


@pytest.mark.anyio
async def test_match_supplier_exact_name(seeded_org_and_supplier):
    org_id, sup_id = seeded_org_and_supplier
    match = await match_supplier(org_id, "Pulse Fitness")
    assert match is not None
    assert match["id"] == sup_id
    assert "_id" not in match  # Pydantic-clean response


@pytest.mark.anyio
async def test_match_supplier_case_insensitive_name(seeded_org_and_supplier):
    org_id, _ = seeded_org_and_supplier
    match = await match_supplier(org_id, "PULSE FITNESS")
    assert match is not None


@pytest.mark.anyio
async def test_match_supplier_normalised_name(seeded_org_and_supplier):
    """The AI sometimes outputs 'Pulse Fitness Limited' even when the
    stored supplier is just 'Pulse Fitness' — must still match."""
    org_id, sup_id = seeded_org_and_supplier
    match = await match_supplier(org_id, "Pulse Fitness Limited")
    assert match is not None
    assert match["id"] == sup_id


@pytest.mark.anyio
async def test_match_supplier_by_vat_number(seeded_org_and_supplier):
    """When the AI couldn't pin the name but did extract the VAT
    number, we still link to the existing supplier."""
    org_id, sup_id = seeded_org_and_supplier
    match = await match_supplier(org_id, "Different Name LLC", vat_number="785413509")
    assert match is not None
    assert match["id"] == sup_id


@pytest.mark.anyio
async def test_match_supplier_no_match_returns_none(seeded_org_and_supplier):
    org_id, _ = seeded_org_and_supplier
    match = await match_supplier(org_id, "Life Fitness")
    assert match is None


@pytest.mark.anyio
async def test_match_supplier_wrong_org_returns_none(seeded_org_and_supplier):
    """Tenant isolation — a supplier in org A must NOT match for org B."""
    other_org = f"unrelated-org-{uuid.uuid4().hex[:8]}"
    match = await match_supplier(other_org, "Pulse Fitness")
    assert match is None


@pytest.mark.anyio
async def test_match_supplier_handles_missing_args():
    """No org_id or no name → None (don't crash on a blank invoice)."""
    assert await match_supplier("", "Pulse Fitness") is None
    assert await match_supplier("some-org", "") is None


def test_prompt_schema_includes_new_invoice_fields():
    """The prompt schema must instruct the AI to extract the fields
    that operators reported as 'missing': totals, bank details, customer
    info, supplier VAT/company number, due-date, payment terms."""
    text = "stub"
    prompt = _build_extraction_prompt(text)
    expected_keys = [
        "supplier_vat_number",
        "supplier_company_number",
        "customer_name",
        "customer_reference",
        "due_date",
        "payment_terms",
        "bank_details",
        "account_number",
        "sort_code",
        "totals",
        "net",
        "vat",
        "gross",
    ]
    for k in expected_keys:
        assert k in prompt, f"Prompt missing schema key: {k}"
