"""Phase 3 — Marketing multi-site isolation + RBAC leak proof.

Seeds campaigns/audiences/journeys under TWO sites and proves a restricted
manager sees only their site, never the other, across list endpoints + the
marketing dashboard. Owner sees both.
"""
import asyncio
import uuid

import pytest

from utils.database import db
from utils.site_scope import set_request_site_scope, set_requested_site, clear_request_site_scope
from routes.marketing.campaigns import list_campaigns
from routes.marketing.audiences import list_audiences
from routes.marketing.journeys import list_journeys
from routes.marketing.dashboard import dashboard as mkt_dashboard

ORG = f"test-mkt-iso-{uuid.uuid4().hex[:8]}"
A = f"mkA-{uuid.uuid4().hex[:6]}"
B = f"mkB-{uuid.uuid4().hex[:6]}"
NOW = "2026-06-20T00:00:00+00:00"

OWNER = {"id": "mo", "organization_id": ORG, "role": "owner"}
MGR = {"id": "mm", "organization_id": ORG, "role": "manager", "allowed_site_ids": [A]}


async def _seed():
    await db.marketing_campaigns.insert_many([
        {"id": "caA", "organization_id": ORG, "site_id": A, "name": "MARKER_A_CAMP", "status": "sent", "sent_at": NOW, "metrics": {"sent": 10, "opened": 5}, "created_at": NOW},
        {"id": "caB", "organization_id": ORG, "site_id": B, "name": "MARKER_B_CAMP", "status": "sent", "sent_at": NOW, "metrics": {"sent": 20, "opened": 10}, "created_at": NOW},
    ])
    await db.marketing_audiences.insert_many([
        {"id": "auA", "organization_id": ORG, "site_id": A, "name": "MARKER_A_AUD", "created_at": NOW},
        {"id": "auB", "organization_id": ORG, "site_id": B, "name": "MARKER_B_AUD", "created_at": NOW},
    ])
    await db.marketing_journeys.insert_many([
        {"id": "jA", "organization_id": ORG, "site_id": A, "name": "MARKER_A_J", "status": "active", "created_at": NOW},
        {"id": "jB", "organization_id": ORG, "site_id": B, "name": "MARKER_B_J", "status": "active", "created_at": NOW},
    ])


async def _cleanup():
    for c in ("marketing_campaigns", "marketing_audiences", "marketing_journeys"):
        await db[c].delete_many({"organization_id": ORG})
    clear_request_site_scope()


def _scope(user, requested=None):
    set_request_site_scope(user)
    set_requested_site(requested)


@pytest.mark.asyncio
async def test_marketing_site_isolation():
    await _cleanup()
    await _seed()
    try:
        # Owner — both sites
        _scope(OWNER)
        assert {c["name"] for c in (await list_campaigns(user=OWNER))["campaigns"]} == {"MARKER_A_CAMP", "MARKER_B_CAMP"}

        # Manager — only A across all three list endpoints
        _scope(MGR)
        camps = {c["name"] for c in (await list_campaigns(user=MGR))["campaigns"]}
        assert camps == {"MARKER_A_CAMP"}, f"LEAK campaigns: {camps}"
        auds = {a["name"] for a in (await list_audiences(user=MGR))["audiences"]}
        assert auds == {"MARKER_A_AUD"}, f"LEAK audiences: {auds}"
        js = {j["name"] for j in (await list_journeys(user=MGR))["journeys"]}
        assert js == {"MARKER_A_J"}, f"LEAK journeys: {js}"

        # Manager requesting disallowed site B → 403
        from fastapi import HTTPException
        _scope(MGR, requested=B)
        with pytest.raises(HTTPException) as exc:
            await list_campaigns(user=MGR)
        assert exc.value.status_code == 403 and exc.value.detail["error"] == "site_access_denied"

        # Dashboard — manager sees only A's numbers
        _scope(MGR)
        d = await mkt_dashboard(user=MGR)
        assert d["campaigns_30d"] == 1 and d["messages_sent_30d"] == 10, f"LEAK dashboard: {d}"
        assert d["audiences_total"] == 1 and d["journeys_active"] == 1
        _scope(OWNER)
        do = await mkt_dashboard(user=OWNER)
        assert do["campaigns_30d"] == 2 and do["messages_sent_30d"] == 30
    finally:
        await _cleanup()


if __name__ == "__main__":
    asyncio.run(test_marketing_site_isolation())
    print("PASS: marketing site isolation (no cross-site leak)")
