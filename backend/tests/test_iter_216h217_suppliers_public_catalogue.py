"""Iter 216h217 — Public supplier catalogue endpoint.

Drops the curated supplier list onto an unauth surface so the public
engineer apply wizard can offer a dropdown + "Add new" multi-picker
without requiring login.

Run: pytest backend/tests/test_iter_216h217_suppliers_public_catalogue.py -q
"""
from __future__ import annotations

import asyncio


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_public_catalogue_returns_curated_only():
    from routes import suppliers_catalogue as sc

    out = _run(sc.suppliers_catalogue_public())

    assert out["total"] > 0
    assert all(s.get("source") == "curated" for s in out["all"])
    # Custom suppliers (per-org user-submitted) must never leak here.
    assert out["custom"] == []
    # Returns the same shape as the auth endpoint so the frontend
    # component can swap providers transparently.
    assert {"curated", "custom", "all", "total"} <= set(out.keys())


def test_public_catalogue_contains_known_uk_suppliers():
    """Sanity guard — the curated list should contain household-name UK
    fitness suppliers so the dropdown is actually useful."""
    from routes import suppliers_catalogue as sc

    out = _run(sc.suppliers_catalogue_public())
    names = {s["name"] for s in out["all"]}
    must_have = {"Pulse Fitness", "Technogym", "Life Fitness", "Matrix Fitness"}
    missing = must_have - names
    assert not missing, f"Missing core suppliers: {missing}"
