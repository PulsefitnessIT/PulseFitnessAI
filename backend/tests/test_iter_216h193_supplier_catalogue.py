"""Iter 216h193 — coverage for the operations standardisation pass:

1. Supplier catalogue endpoint returns the curated UK list + custom
   org suppliers, deduped and merged.
2. Photo-lookup endpoint surfaces the spec-sheet photo when the
   supplier (and optionally model) match.

Run: pytest backend/tests/test_iter_216h193_supplier_catalogue.py -q
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_curated_supplier_list_contains_key_uk_brands() -> None:
    from routes.suppliers_catalogue import CURATED_SUPPLIERS
    names = {s["name"].lower() for s in CURATED_SUPPLIERS}
    # The brands Lee specifically called out in the Feb 2026 ask.
    for must in [
        "pulse fitness", "technogym", "life fitness", "precor",
        "matrix fitness", "cybex", "star trac", "hoist fitness",
        "concept2", "wattbike", "keiser", "trx",
        "eleiko", "hammer strength", "origin fitness", "escape fitness",
        "physical company", "fitness superstore",
        "sole fitness", "nordictrack", "proform",
    ]:
        assert must in names, f"curated list missing {must}"


def test_catalogue_merges_curated_and_custom_and_dedupes() -> None:
    from routes.suppliers_catalogue import suppliers_catalogue

    org_id = "org-1"
    user = {"id": "u1", "organization_id": org_id, "role": "owner"}

    # Org has 2 suppliers: one collides with curated ("Pulse Fitness"),
    # one is brand new ("Bob's Bespoke Rigs"). Expect dedupe.
    org_suppliers = [
        {"id": "s1", "name": "Pulse Fitness", "supplier_types": ["cardio"]},
        {"id": "s2", "name": "Bob's Bespoke Rigs", "supplier_types": ["functional"]},
    ]

    fake_suppliers = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.sort = lambda *_a, **_k: fake_cursor
    fake_cursor.to_list = AsyncMock(return_value=org_suppliers)
    fake_suppliers.find = MagicMock(return_value=fake_cursor)

    fake_db = MagicMock()
    fake_db.suppliers = fake_suppliers

    with patch("routes.suppliers_catalogue.db", fake_db):
        result = _run(suppliers_catalogue(user=user))

    curated_names = [s["name"] for s in result["curated"]]
    custom_names = [s["name"] for s in result["custom"]]
    assert "Pulse Fitness" in curated_names
    assert "Pulse Fitness" not in custom_names, "curated entry must dedupe org row"
    assert "Bob's Bespoke Rigs" in custom_names
    # Combined view: every curated row + the unique custom rows.
    all_names = [s["name"] for s in result["all"]]
    assert "Bob's Bespoke Rigs" in all_names
    # `all` is alphabetically sorted.
    assert all_names == sorted(all_names, key=str.lower)
    assert result["total"] == len(curated_names) + len(custom_names)


def test_photo_lookup_returns_exact_spec_sheet_match() -> None:
    from routes.suppliers_catalogue import supplier_photo_lookup

    user = {"id": "u1", "organization_id": "org-1"}
    fake_spec = MagicMock()
    fake_spec.find_one = AsyncMock(side_effect=[
        # 1st call: (supplier+model) exact lookup
        {"photo_url": "https://cdn/specs/technogym-skillrun.jpg"},
    ])
    fake_db = MagicMock()
    fake_db.spec_sheets = fake_spec

    with patch("routes.suppliers_catalogue.db", fake_db):
        out = _run(supplier_photo_lookup(
            supplier="Technogym", model="Skillrun", _user=user,
        ))

    assert out["photo_url"].endswith("technogym-skillrun.jpg")
    assert out["source"] == "spec_sheet_exact"


def test_photo_lookup_falls_back_to_supplier_level_match() -> None:
    from routes.suppliers_catalogue import supplier_photo_lookup

    user = {"id": "u1", "organization_id": "org-1"}
    fake_spec = MagicMock()
    fake_spec.find_one = AsyncMock(side_effect=[
        None,  # exact match miss
        {"image_url": "https://cdn/specs/technogym-generic.jpg"},  # supplier fallback
    ])
    fake_db = MagicMock()
    fake_db.spec_sheets = fake_spec

    with patch("routes.suppliers_catalogue.db", fake_db):
        out = _run(supplier_photo_lookup(
            supplier="Technogym", model="UnknownX", _user=user,
        ))

    assert out["photo_url"].endswith("technogym-generic.jpg")
    assert out["source"] == "spec_sheet_supplier"


def test_photo_lookup_returns_none_when_unmatched() -> None:
    from routes.suppliers_catalogue import supplier_photo_lookup

    user = {"id": "u1", "organization_id": "org-1"}
    fake_spec = MagicMock()
    fake_spec.find_one = AsyncMock(return_value=None)
    fake_db = MagicMock()
    fake_db.spec_sheets = fake_spec

    with patch("routes.suppliers_catalogue.db", fake_db):
        out = _run(supplier_photo_lookup(
            supplier="NoSuchBrand", model="", _user=user,
        ))

    assert out["photo_url"] == ""
    assert out["source"] == "none"


def test_photo_lookup_empty_supplier_short_circuits() -> None:
    from routes.suppliers_catalogue import supplier_photo_lookup

    user = {"id": "u1", "organization_id": "org-1"}
    out = _run(supplier_photo_lookup(supplier="", model="", _user=user))
    assert out["photo_url"] == ""
    assert out["source"] == "none"
