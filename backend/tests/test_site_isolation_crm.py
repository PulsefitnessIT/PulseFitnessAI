"""Phase 2 — CRM multi-site isolation + RBAC leak proof.

CRM uses a SEPARATE auth path (get_crm_user). This proves the shared
_org_filter narrows a restricted manager to their site(s) across
companies, contacts, deals (opportunities) and the dashboard, and never
leaks site B. Owner sees both.
"""
import asyncio
import uuid

import pytest

from utils.database import db
from utils.site_scope import set_request_site_scope, set_requested_site, clear_request_site_scope
from routes.crm_core import list_companies, list_contacts, list_deals, crm_dashboard

ORG = f"test-crm-iso-{uuid.uuid4().hex[:8]}"
SITE_A = f"crmA-{uuid.uuid4().hex[:6]}"
SITE_B = f"crmB-{uuid.uuid4().hex[:6]}"

OWNER = {"id": "co", "organization_id": ORG, "role": "owner"}
MANAGER_A = {"id": "cm", "organization_id": ORG, "role": "manager", "allowed_site_ids": [SITE_A]}


async def _seed():
    await db.crm_companies.insert_many([
        {"id": "cA", "organization_id": ORG, "site_id": SITE_A, "name": "MARKER_A_CO", "created_at": "2026-06-01T00:00:00+00:00"},
        {"id": "cB", "organization_id": ORG, "site_id": SITE_B, "name": "MARKER_B_CO", "created_at": "2026-06-01T00:00:00+00:00"},
    ])
    await db.crm_contacts.insert_many([
        {"id": "ctA", "organization_id": ORG, "site_id": SITE_A, "first_name": "MARKER_A", "created_at": "2026-06-01T00:00:00+00:00"},
        {"id": "ctB", "organization_id": ORG, "site_id": SITE_B, "first_name": "MARKER_B", "created_at": "2026-06-01T00:00:00+00:00"},
    ])
    await db.crm_deals.insert_many([
        {"id": "dA", "organization_id": ORG, "site_id": SITE_A, "title": "MARKER_A_DEAL", "stage": "lead", "value": 100, "created_at": "2026-06-01T00:00:00+00:00"},
        {"id": "dB", "organization_id": ORG, "site_id": SITE_B, "title": "MARKER_B_DEAL", "stage": "lead", "value": 200, "created_at": "2026-06-01T00:00:00+00:00"},
    ])


async def _cleanup():
    for c in ("crm_companies", "crm_contacts", "crm_deals"):
        await db[c].delete_many({"organization_id": ORG})
    clear_request_site_scope()


def _scope(user, requested=None):
    set_request_site_scope(user)
    set_requested_site(requested)


@pytest.mark.asyncio
async def test_crm_site_isolation():
    await _cleanup()
    await _seed()
    try:
        # Owner — all sites
        _scope(OWNER)
        cos = await list_companies(user=OWNER)
        assert {c["name"] for c in cos["companies"]} == {"MARKER_A_CO", "MARKER_B_CO"}

        # Owner drilling into B via header
        _scope(OWNER, requested=SITE_B)
        cos_b = await list_companies(user=OWNER)
        assert {c["name"] for c in cos_b["companies"]} == {"MARKER_B_CO"}

        # Manager restricted to A — companies/contacts/deals narrowed, NO B leak
        _scope(MANAGER_A)
        cos = await list_companies(user=MANAGER_A)
        assert {c["name"] for c in cos["companies"]} == {"MARKER_A_CO"}, f"LEAK: {cos}"
        cts = await list_contacts(user=MANAGER_A)
        assert {c["first_name"] for c in cts["contacts"]} == {"MARKER_A"}, f"LEAK: {cts}"
        dls = await list_deals(user=MANAGER_A)
        assert {d["title"] for d in dls["deals"]} == {"MARKER_A_DEAL"}, f"LEAK: {dls}"

        # Manager requesting disallowed site B → 403
        from fastapi import HTTPException
        _scope(MANAGER_A, requested=SITE_B)
        with pytest.raises(HTTPException) as exc:
            await list_companies(user=MANAGER_A)
        assert exc.value.status_code == 403 and exc.value.detail["error"] == "site_access_denied"

        # Dashboard counts narrowed for the manager
        _scope(MANAGER_A)
        d = await crm_dashboard(user=MANAGER_A)
        assert d["total_companies"] == 1, f"LEAK in dashboard companies: {d['total_companies']}"
        assert d["total_contacts"] == 1, f"LEAK in dashboard contacts: {d['total_contacts']}"
        _scope(OWNER)
        do = await crm_dashboard(user=OWNER)
        assert do["total_companies"] == 2 and do["total_contacts"] == 2
    finally:
        await _cleanup()


if __name__ == "__main__":
    asyncio.run(test_crm_site_isolation())
    print("PASS: CRM site isolation (no cross-site leak, incl. separate auth path)")
