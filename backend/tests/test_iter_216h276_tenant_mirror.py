"""Iter 216h276 — Auto-mirror Pulse tenants into the master CRM (P1).

Customer ask (verbatim, from h275 turn): *"Pulse Fitness Limited
are on Pulse Pro with all modules unlocked but they are not
showing as an organisation on CRM."*

This iter mirrors every Pulse-branded tenant into the master
admin's CRM as a `crm_v2_companies` row, tagged with
`source="tenant_mirror"` + the source `tenant_org_id`.

* Boot-time reconciliation in `server.py` startup hooks
* On-demand reconciliation on subscription / org-details PUTs
* Manual reconcile via `POST /api/master-admin/integrity/tenant-mirror-reconcile`
* Mirrors visible in CRM Companies with a "Tenant ↺" badge
"""
from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _async_iter(items):
    class _Cur:
        def __init__(self, xs):
            self._xs = list(xs)

        def __aiter__(self):
            self._i = 0
            return self

        async def __anext__(self):
            if self._i >= len(self._xs):
                raise StopAsyncIteration
            x = self._xs[self._i]
            self._i += 1
            return x
    return _Cur(items)


# ─── 1. Tenant qualification ────────────────────────────────────


def test_is_pulse_tenant_recognises_subscription_tier():
    from utils.tenant_mirror import _is_pulse_tenant
    assert _is_pulse_tenant({"id": "x", "subscription_tier": "pulse_pro"}) is True
    assert _is_pulse_tenant({"id": "x", "subscription_tier": "pulse_lite"}) is True
    assert _is_pulse_tenant({"id": "x", "subscription_tier": "pulse_pro_plus"}) is True
    # Account-type also qualifies (some orgs store it there)
    assert _is_pulse_tenant({"id": "x", "account_type": "lite"}) is True
    # Non-Pulse orgs (MOD / GymAxis / enterprise) do NOT qualify
    assert _is_pulse_tenant({"id": "x", "subscription_tier": "enterprise"}) is False
    assert _is_pulse_tenant({"id": "x", "account_type": "mod_org"}) is False
    # Master admin's own org is excluded explicitly
    assert _is_pulse_tenant({"id": "x", "subscription_tier": "pulse_pro", "is_master_org": True}) is False
    # No id → no
    assert _is_pulse_tenant({}) is False
    assert _is_pulse_tenant({"id": None, "subscription_tier": "pulse_pro"}) is False


# ─── 2. Projection ──────────────────────────────────────────────


def test_project_org_to_company_maps_canonical_fields():
    from utils.tenant_mirror import _project_org_to_company
    out = _project_org_to_company({
        "id": "tenant-1",
        "name": "Pulse Fitness Limited",
        "subscription_tier": "pulse_pro",
        "account_type": "pulse_pro",
        "website_url": "https://pulsefitness.com",
        "phone": "020 7946 0000",
        "contact_email": "ops@pulsefitness.com",
        "country": "United Kingdom",
    }, master_org_id="master-org")
    assert out["organization_id"] == "master-org"
    assert out["source"] == "tenant_mirror"
    assert out["tenant_org_id"] == "tenant-1"
    assert out["name"] == "Pulse Fitness Limited"
    assert out["website"] == "https://pulsefitness.com"
    assert out["phone"] == "020 7946 0000"
    assert out["email"] == "ops@pulsefitness.com"
    assert out["type"] == "customer"
    assert out["status"] == "active"


def test_project_falls_back_to_untitled_when_name_missing():
    from utils.tenant_mirror import _project_org_to_company
    out = _project_org_to_company({"id": "t1"}, "master-org")
    assert out["name"] == "Untitled tenant"


# ─── 3. Reconciliation: create + update + mark former ───────────


def test_mirror_creates_new_company_when_no_existing():
    from utils.tenant_mirror import mirror_pulse_tenants_to_crm

    fake_db = MagicMock()
    # Master admin lookup
    fake_db.users.find_one = AsyncMock(return_value={"organization_id": "master-org"})
    # Pulse tenant orgs
    fake_db.organizations.find = MagicMock(return_value=_async_iter([
        {"id": "tenant-A", "name": "Acme Pulse Gym", "subscription_tier": "pulse_pro"},
    ]))
    # No existing mirror
    fake_db.crm2_companies.find_one = AsyncMock(return_value=None)
    fake_db.crm2_companies.insert_one = AsyncMock(return_value=MagicMock())
    # No existing former-mark sweep candidates
    fake_db.crm2_companies.find = MagicMock(return_value=_async_iter([]))

    with patch("utils.tenant_mirror.db", fake_db):
        summary = _run(mirror_pulse_tenants_to_crm())

    assert summary["created"] == 1
    assert summary["updated"] == 0
    assert summary["pulse_tenants_found"] == 1
    args, _ = fake_db.crm2_companies.insert_one.call_args
    inserted = args[0]
    assert inserted["source"] == "tenant_mirror"
    assert inserted["tenant_org_id"] == "tenant-A"
    assert inserted["name"] == "Acme Pulse Gym"


def test_mirror_updates_existing_company_on_rename():
    from utils.tenant_mirror import mirror_pulse_tenants_to_crm

    fake_db = MagicMock()
    fake_db.users.find_one = AsyncMock(return_value={"organization_id": "master-org"})
    fake_db.organizations.find = MagicMock(return_value=_async_iter([
        {"id": "tenant-A", "name": "Acme Pulse Gym (Renamed)", "subscription_tier": "pulse_pro"},
    ]))
    # Existing mirror row with the OLD name
    fake_db.crm2_companies.find_one = AsyncMock(return_value={
        "id": "tenant-tenant-A", "name": "Acme Pulse Gym",
    })
    fake_db.crm2_companies.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    fake_db.crm2_companies.find = MagicMock(return_value=_async_iter([]))

    with patch("utils.tenant_mirror.db", fake_db):
        summary = _run(mirror_pulse_tenants_to_crm())

    assert summary["created"] == 0
    assert summary["updated"] == 1
    args, _ = fake_db.crm2_companies.update_one.call_args
    update_doc = args[1]["$set"]
    assert update_doc["name"] == "Acme Pulse Gym (Renamed)"


def test_mirror_marks_company_former_when_tenant_gone():
    from utils.tenant_mirror import mirror_pulse_tenants_to_crm

    fake_db = MagicMock()
    fake_db.users.find_one = AsyncMock(return_value={"organization_id": "master-org"})
    # No live tenants
    fake_db.organizations.find = MagicMock(return_value=_async_iter([]))
    # But there's a previously-mirrored company referencing a now-deleted tenant
    fake_db.crm2_companies.find = MagicMock(return_value=_async_iter([
        {"id": "tenant-gone", "tenant_org_id": "deleted-tenant"},
    ]))
    fake_db.crm2_companies.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    with patch("utils.tenant_mirror.db", fake_db):
        summary = _run(mirror_pulse_tenants_to_crm())

    assert summary["marked_former"] == 1
    # The status update was issued
    assert fake_db.crm2_companies.update_one.call_count == 1
    args, _ = fake_db.crm2_companies.update_one.call_args
    assert args[1]["$set"]["status"] == "former"


def test_mirror_noop_when_no_master_admin():
    from utils.tenant_mirror import mirror_pulse_tenants_to_crm

    fake_db = MagicMock()
    fake_db.users.find_one = AsyncMock(return_value=None)

    with patch("utils.tenant_mirror.db", fake_db):
        summary = _run(mirror_pulse_tenants_to_crm())

    assert summary == {"created": 0, "updated": 0, "marked_former": 0, "skipped": 0}


# ─── 4. mirror_single_tenant on org PUT ─────────────────────────


def test_mirror_single_tenant_upserts_on_subscription_change():
    from utils.tenant_mirror import mirror_single_tenant

    fake_db = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value={
        "id": "tenant-X", "name": "New Pulse Customer", "subscription_tier": "pulse_pro",
    })
    fake_db.users.find_one = AsyncMock(return_value={"organization_id": "master-org"})
    update_result = MagicMock(matched_count=0, modified_count=0, upserted_id="abc123")
    fake_db.crm2_companies.update_one = AsyncMock(return_value=update_result)

    with patch("utils.tenant_mirror.db", fake_db):
        out = _run(mirror_single_tenant("tenant-X"))

    assert out["status"] == "ok"
    assert out["upserted_id"] == "abc123"
    # The update_one call used upsert=True
    args, kwargs = fake_db.crm2_companies.update_one.call_args
    assert kwargs.get("upsert") is True or (len(args) >= 3 and args[2] is True)
    # $set carries the canonical projection
    set_doc = args[1]["$set"]
    assert set_doc["tenant_org_id"] == "tenant-X"
    assert set_doc["source"] == "tenant_mirror"


def test_mirror_single_tenant_returns_not_a_pulse_when_non_pulse():
    """Subscription change FROM Pulse TO non-Pulse must NOT create a
    mirror — the next reconciliation will mark the existing mirror
    as 'former'."""
    from utils.tenant_mirror import mirror_single_tenant

    fake_db = MagicMock()
    fake_db.organizations.find_one = AsyncMock(return_value={
        "id": "tenant-X", "subscription_tier": "enterprise",
    })

    with patch("utils.tenant_mirror.db", fake_db):
        out = _run(mirror_single_tenant("tenant-X"))

    assert out["status"] == "not_a_pulse_tenant"


# ─── 5. Manual reconcile endpoint ──────────────────────────────


def test_manual_reconcile_endpoint_requires_master_admin():
    from routes.master_admin_integrity import reconcile_tenant_mirror
    from fastapi import HTTPException

    def deny(_):
        raise HTTPException(403, "Master admin access required")

    with patch("routes.master_admin_integrity.require_master_admin", side_effect=deny), pytest.raises(HTTPException) as exc:
        _run(reconcile_tenant_mirror(user={"is_master_admin": False}))
    assert exc.value.status_code == 403


def test_manual_reconcile_endpoint_returns_mirror_summary():
    from routes.master_admin_integrity import reconcile_tenant_mirror

    fake_summary = {"created": 1, "updated": 0, "marked_former": 0, "skipped": 0, "pulse_tenants_found": 1}
    with patch("routes.master_admin_integrity.require_master_admin", return_value=None), \
         patch("utils.tenant_mirror.mirror_pulse_tenants_to_crm", new=AsyncMock(return_value=fake_summary)):
        out = _run(reconcile_tenant_mirror(user={"is_master_admin": True}))
    assert out == fake_summary


# ─── 6. Wired into server startup + admin org PUTs ─────────────


def test_server_startup_runs_tenant_mirror():
    src = pathlib.Path("/app/backend/server.py").read_text()
    assert "from utils.tenant_mirror import" in src
    assert "ensure_tenant_mirror_indexes()" in src
    assert "mirror_pulse_tenants_to_crm()" in src


def test_subscription_change_triggers_mirror_refresh():
    src = pathlib.Path("/app/backend/routes/master_admin_orgs.py").read_text()
    # Both the subscription-change PUT and the details PUT call mirror_single_tenant
    sub_block = src.split('@router.put("/master-admin/organizations/{org_id}/subscription")')[1].split('@router')[0]
    assert "mirror_single_tenant" in sub_block

    detail_block = src.split('@router.put("/master-admin/organizations/{org_id}/details")')[1].split('@router')[0]
    assert "mirror_single_tenant" in detail_block


# ─── 7. UI badge on tenant-mirror companies ────────────────────


def test_companies_list_shows_tenant_mirror_badge():
    src = pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text()
    assert "co.source === 'tenant_mirror'" in src
    assert 'data-testid={`company-tenant-mirror-badge-${co.id}`}' in src
    # Should also surface the 'former' state for archived tenants
    assert "co.status === 'former'" in src
