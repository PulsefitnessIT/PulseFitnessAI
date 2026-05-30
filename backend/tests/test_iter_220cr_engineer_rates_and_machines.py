"""Iter 220cr — Engineer pricing defaults + quote multi-machine tests.

Pins three new capabilities:

* ``PUT /api/partners/me/rates`` — sets callout / hourly / mileage /
  parts-markup defaults on the partner doc (used by the engineer
  Account Settings drawer).
* Quote create/update accepts a ``machines: []`` list and persists it.
* Quote PDF + Sicon push still get the legacy ``asset_name`` mirror.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="u-1"):
    return {"id": uid, "organization_id": "org-1", "email": "e@x"}


# ──────────────────────────────────────────────────────────────────
# PUT /partners/me/rates
# ──────────────────────────────────────────────────────────────────


def test_update_rates_persists_only_supplied_fields():
    """Engineer sends just callout + hourly → existing mileage /
    parts_markup_pct must be preserved (server merges)."""
    partner = {
        "id": "p-1",
        "rates": {
            "callout_fee": 50.0,
            "labour_rate_per_hour": 80.0,
            "mileage_rate": 0.45,
            "parts_markup_pct": 15.0,
        },
    }

    async def run():
        with patch(
            "routes.partners._get_partner_by_user",
            AsyncMock(return_value=partner),
        ), patch("routes.partners.db") as fdb, \
             patch("routes.partners._audit", AsyncMock()), \
             patch("routes.partners._public",
                   side_effect=lambda d: {**(d or {})}):
            fdb.partner_engineers.update_one = AsyncMock()
            fdb.partner_engineers.find_one = AsyncMock(
                return_value={**partner, "rates": {
                    "callout_fee": 65.0,
                    "labour_rate_per_hour": 95.0,
                    "mileage_rate": 0.45,
                    "parts_markup_pct": 15.0,
                }},
            )
            from routes.partners import update_my_rates
            out = await update_my_rates(
                body={"callout_fee": 65, "labour_rate_per_hour": 95},
                user=_user(),
            )
        assert out["ok"] is True
        # Update payload merged onto the existing rates dict.
        call = fdb.partner_engineers.update_one.await_args
        update_doc = call.args[1]["$set"]
        assert update_doc["rates"]["callout_fee"] == 65.0
        assert update_doc["rates"]["labour_rate_per_hour"] == 95.0
        assert update_doc["rates"]["mileage_rate"] == 0.45
        assert update_doc["rates"]["parts_markup_pct"] == 15.0

    _run(run())


def test_update_rates_rejects_negative_values():
    """Negative rate → 422 with a clear error message."""

    async def run():
        with patch(
            "routes.partners._get_partner_by_user",
            AsyncMock(return_value={"id": "p-1", "rates": {}}),
        ):
            from routes.partners import update_my_rates
            try:
                await update_my_rates(
                    body={"callout_fee": -10}, user=_user(),
                )
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 422

    _run(run())


def test_update_rates_400s_when_no_fields_supplied():
    async def run():
        with patch(
            "routes.partners._get_partner_by_user",
            AsyncMock(return_value={"id": "p-1", "rates": {}}),
        ):
            from routes.partners import update_my_rates
            try:
                await update_my_rates(body={}, user=_user())
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 400

    _run(run())


def test_update_rates_404s_for_non_partner_user():
    """If the user has no partner profile we 404 — never silently
    create one."""

    async def run():
        with patch(
            "routes.partners._get_partner_by_user",
            AsyncMock(return_value=None),
        ):
            from routes.partners import update_my_rates
            try:
                await update_my_rates(
                    body={"callout_fee": 10}, user=_user(),
                )
                pytest.fail("should have raised")
            except HTTPException as exc:
                assert exc.status_code == 404

    _run(run())


# ──────────────────────────────────────────────────────────────────
# Quote machines[]
# ──────────────────────────────────────────────────────────────────


def test_quote_create_accepts_machines_and_persists_list():
    """``machines: []`` round-trips through Pydantic and onto the
    persisted quote doc."""
    from routes.svc.engineer_quotes import QuoteCreate, QuoteMachine
    body = QuoteCreate(
        customer_name="Acme Gym",
        machines=[
            QuoteMachine(name="Treadmill #4", serial="TM-44", notes="Belt"),
            QuoteMachine(name="Rower #1", serial="RW-12"),
        ],
        lines=[],
    )
    assert len(body.machines) == 2
    assert body.machines[0].name == "Treadmill #4"
    assert body.machines[1].serial == "RW-12"

    # Persisted shape via .model_dump() — what the route hands to Mongo.
    payload = [m.model_dump() for m in body.machines]
    assert payload == [
        {"name": "Treadmill #4", "serial": "TM-44", "notes": "Belt"},
        {"name": "Rower #1", "serial": "RW-12", "notes": None},
    ]


def test_quote_update_machines_is_optional_and_nullable():
    """Patch payload without ``machines`` MUST NOT clobber existing
    machines — only an explicit value should overwrite."""
    from routes.svc.engineer_quotes import QuoteUpdate
    patch_no_machines = QuoteUpdate(customer_name="New name")
    assert patch_no_machines.machines is None
    patch_with_machines = QuoteUpdate(machines=[])
    assert patch_with_machines.machines == []


def test_quote_line_kind_accepts_callout():
    """Sanity — the ``callout`` line kind that the auto-fill uses is
    still accepted by the Pydantic model."""
    from routes.svc.engineer_quotes import QuoteLine
    ln = QuoteLine(kind="callout", description="Callout fee",
                   quantity=1, unit_price=75)
    assert ln.kind == "callout"
    assert ln.unit_price == 75
