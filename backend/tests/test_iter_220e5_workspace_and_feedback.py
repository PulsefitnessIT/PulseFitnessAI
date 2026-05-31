"""Iter 220e5 — Workspace mode + Engineer ↔ CRM contract feedback loop.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


USER = {"id": "u-1", "organization_id": "org-1", "full_name": "Sam"}


# ── 1 · Workspace mode ─────────────────────────────────────────


def _ws_db(user_count=1, site_count=1, approval=0):
    fdb = MagicMock()
    fdb.crm2_users.count_documents = AsyncMock(return_value=user_count)
    fdb.users.count_documents = AsyncMock(return_value=user_count)
    fdb.crm2_sites.count_documents = AsyncMock(return_value=site_count)
    fdb.svc_sites.count_documents = AsyncMock(return_value=site_count)
    fdb.crm2_approval_rules.count_documents = AsyncMock(return_value=approval)
    return fdb


def test_solo_workspace_returns_solo_mode_and_simplified_capabilities():
    from routes.crm_contract_workspace import workspace_mode
    with patch("routes.crm_contract_workspace.db", _ws_db(1, 1, 0)):
        out = _run(workspace_mode(user=USER))
    assert out["mode"] == "solo"
    caps = out["capabilities"]
    assert caps["show_approval_queue"] is False
    assert caps["show_team_assignment"] is False
    assert caps["show_finance_review"] is False
    assert caps["default_engineer_to_self"] is True
    assert caps["primary_cta"] == "Create Contract"
    # Solo still gets the feedback review queue.
    assert caps["show_review_queue"] is True


def test_multi_user_org_returns_enterprise_mode():
    from routes.crm_contract_workspace import workspace_mode
    with patch("routes.crm_contract_workspace.db", _ws_db(5, 3, 0)):
        out = _run(workspace_mode(user=USER))
    assert out["mode"] == "enterprise"
    assert out["capabilities"]["show_approval_queue"] is True
    assert out["capabilities"]["show_team_assignment"] is True


def test_single_user_with_active_approval_rule_is_still_enterprise():
    from routes.crm_contract_workspace import workspace_mode
    with patch("routes.crm_contract_workspace.db", _ws_db(1, 1, 1)):
        out = _run(workspace_mode(user=USER))
    assert out["mode"] == "enterprise"


def test_site_count_above_five_unlocks_region_filters():
    from routes.crm_contract_workspace import workspace_mode
    with patch("routes.crm_contract_workspace.db", _ws_db(3, 8, 0)):
        out = _run(workspace_mode(user=USER))
    assert out["capabilities"]["show_region_filters"] is True


# ── 2 · Engineer-side feedback ─────────────────────────────────


def _feedback_stub(case=None, contract=None):
    fdb = MagicMock()
    default_case = {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "company_id": "co-1",
        "customer_name": "Pulse", "site_id": "s-1",
        "site_name": "London HQ",
    }
    if contract:
        default_case["contract_id"] = contract.get("id")
    if case:
        default_case.update(case)
    fdb.svc_cases.find_one = AsyncMock(return_value=default_case)
    fdb.crm2_contracts.find_one = AsyncMock(return_value=contract)
    inserted_fb, inserted_acts = [], []
    fdb.crm2_contract_feedback.insert_one = AsyncMock(side_effect=lambda d: inserted_fb.append(d))
    fdb.crm2_activities.insert_one = AsyncMock(side_effect=lambda d: inserted_acts.append(d))
    return fdb, inserted_fb, inserted_acts


def test_engineer_can_submit_contract_feedback():
    from routes.crm_contract_workspace import submit_contract_feedback
    fdb, fb, acts = _feedback_stub(contract={
        "id": "ctr-1", "contract_number": "CTR-A", "company_id": "co-1",
        "company_name": "Pulse", "status": "active",
    })
    with patch("routes.crm_contract_workspace.db", fdb):
        out = _run(submit_contract_feedback("case-1", {
            "kind": "exclusion_recommended",
            "body": "Treadmill 7 has chronic belt slippage — recommend exclusion next renewal.",
            "asset_id": "asset-7",
            "severity": "high",
        }, user=USER))
    assert out["kind"] == "exclusion_recommended"
    assert out["status"] == "open"
    assert out["case_reference"] == "GA-100"
    assert out["contract_id"] == "ctr-1"
    assert out["engineer_name"] == "Sam"
    # Activity feed gets a row too so coordinators see it on the contract.
    assert any(a["subject"].startswith("Engineer feedback") for a in acts)


def test_engineer_feedback_rejects_unknown_kind():
    from routes.crm_contract_workspace import submit_contract_feedback
    import pytest as _pytest
    from fastapi import HTTPException
    fdb, _, _ = _feedback_stub()
    with patch("routes.crm_contract_workspace.db", fdb), _pytest.raises(HTTPException) as exc:
        _run(submit_contract_feedback("case-1", {
            "kind": "random_made_up_kind", "body": "x",
        }, user=USER))
    assert exc.value.status_code == 400


# ── 3 · Coordinator review queue ────────────────────────────────


def _queue_stub(feedback_rows: list[dict]):
    fdb = MagicMock()

    def _find(q, p=None):
        rows = [{k: v for k, v in r.items() if k != "_id"} for r in feedback_rows
                if all(r.get(k) == v for k, v in q.items())]
        cur = MagicMock()
        cur.sort = MagicMock(return_value=cur)
        cur.to_list = AsyncMock(return_value=rows)
        return cur

    fdb.crm2_contract_feedback.find = MagicMock(side_effect=_find)

    async def _upd(q, upd):
        for r in feedback_rows:
            if all(r.get(k) == v for k, v in q.items()):
                r.update(upd.get("$set", {}))
        return MagicMock(modified_count=1)

    fdb.crm2_contract_feedback.update_one = AsyncMock(side_effect=_upd)
    fdb.crm2_contract_feedback.find_one = AsyncMock(
        side_effect=lambda q, p=None: next(
            ({k: v for k, v in r.items() if k != "_id"}
             for r in feedback_rows
             if all(r.get(k) == v for k, v in q.items())), None,
        ),
    )
    acts = []
    fdb.crm2_activities.insert_one = AsyncMock(side_effect=lambda d: acts.append(d))
    return fdb, acts


def test_review_queue_filters_by_status():
    from routes.crm_contract_workspace import feedback_queue
    rows = [
        {"id": "f1", "organization_id": "org-1", "status": "open",
         "kind": "renewal_review", "created_at": "2026-02-01"},
        {"id": "f2", "organization_id": "org-1", "status": "rejected",
         "kind": "general_note", "created_at": "2026-02-01"},
    ]
    fdb, _ = _queue_stub(rows)
    with patch("routes.crm_contract_workspace.db", fdb):
        out = _run(feedback_queue(status="open", user=USER))
    assert out["count"] == 1
    assert out["feedback"][0]["id"] == "f1"


def test_accepting_renewal_feedback_drops_renewal_task_activity():
    from routes.crm_contract_workspace import action_feedback
    rows = [{"id": "f1", "organization_id": "org-1", "status": "open",
             "kind": "renewal_review", "contract_id": "ctr-1",
             "company_id": "co-1", "body": "Customer wants more visits"}]
    fdb, acts = _queue_stub(rows)
    with patch("routes.crm_contract_workspace.db", fdb), \
         patch("routes.crm_contract_workspace.record_audit", AsyncMock()):
        out = _run(action_feedback("f1", {
            "action": "accept", "note": "Confirmed with manager",
        }, user=USER))
    assert out["status"] == "actioned"
    assert any(a["type"] == "contract_renewal" for a in acts)
    # Note made it onto the feedback row.
    assert rows[0]["status"] == "actioned"
    assert rows[0]["internal_notes"][0]["note"].startswith("Confirmed")


def test_rejecting_feedback_does_not_create_renewal_task():
    from routes.crm_contract_workspace import action_feedback
    rows = [{"id": "f1", "organization_id": "org-1", "status": "open",
             "kind": "renewal_review", "contract_id": "ctr-1"}]
    fdb, acts = _queue_stub(rows)
    with patch("routes.crm_contract_workspace.db", fdb), \
         patch("routes.crm_contract_workspace.record_audit", AsyncMock()):
        out = _run(action_feedback("f1", {"action": "reject"}, user=USER))
    assert out["status"] == "rejected"
    assert acts == []


# ── 4 · Entitlement panel ──────────────────────────────────────


def test_entitlement_panel_returns_red_when_no_contract():
    from routes.crm_contract_workspace import engineer_entitlement
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
    })
    # First (and only) crm2_contracts.find_one call is the
    # any_contract scan inside the new contract-less guard.
    fdb.crm2_contracts.find_one = AsyncMock(return_value={"id": "other-contract"})
    with patch("routes.crm_contract_workspace.db", fdb):
        out = _run(engineer_entitlement("case-1", user=USER))
    assert out["active"] is False
    assert out["tone"] == "red"
    assert "No contract" in out["label"]


def test_entitlement_panel_returns_covered_fields_when_contract_active():
    from routes.crm_contract_workspace import engineer_entitlement
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1", "contract_id": "ctr-1",
    })
    fdb.crm2_contracts.find_one = AsyncMock(return_value={
        "id": "ctr-1", "contract_number": "CTR-A", "tier": "gold",
        "status": "active", "end_date": "2027-01-01",
        "inclusions": {"maintenance": ["callout", "labour", "wear_tear_parts", "treadmill_belts"]},
        "exclusions_structured": ["misuse"],
        "response_times": {"emergency": {"hours": 4, "unit": "hours"}},
    })
    with patch("routes.crm_contract_workspace.db", fdb):
        out = _run(engineer_entitlement("case-1", user=USER))
    assert out["active"] is True
    assert out["tier"] == "gold"
    # Plain-English yes/no fields.
    field_map = {f["key"]: f["covered"] for f in out["fields"]}
    assert field_map["callout"] is True
    assert field_map["labour"] is True
    assert field_map["wear_tear_parts"] is True
    assert field_map["treadmill_belts"] is True
    assert field_map["treadmill_beds"] is False
    assert field_map["upholstery"] is False
    assert field_map["major_parts"] is False
    assert out["sla_emergency_hours"] == 4
    # Exclusions resolved via the canonical catalog.
    assert out["exclusions"][0]["label"] == "Customer misuse"
