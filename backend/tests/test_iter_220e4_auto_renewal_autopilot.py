"""Iter 220e4 — Auto-renewal autopilot.

When ``auto_renew == True`` and a contract is within 30 days of expiry,
the autopilot creates a renewal draft with the suggested uplift applied
and emails the customer the branded PDF + accept link. Idempotent
within a 60-day window per contract. Never auto-signs.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


USER = {"id": "u-1", "organization_id": "org-1", "full_name": "Sam"}


def _today_plus(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _build_stub(contracts: list[dict], contact_emails: dict[str, str] | None = None,
                assets: list[dict] | None = None):
    fdb = MagicMock()
    contact_emails = contact_emails or {}

    def _find(query, projection=None):
        rows = []
        for c in contracts:
            ok = True
            for k, v in query.items():
                if k == "end_date" and isinstance(v, dict):
                    val = c.get(k)
                    if not val or val > v.get("$lte", "9999") or val < v.get("$gte", ""):
                        ok = False
                        break
                elif c.get(k) != v:
                    ok = False
                    break
            if ok:
                rows.append({k: vv for k, vv in c.items() if k != "_id"})
        cur = MagicMock()
        cur.sort = MagicMock(return_value=cur)
        cur.to_list = AsyncMock(return_value=rows)
        return cur

    fdb.crm2_contracts.find = MagicMock(side_effect=_find)

    inserted_contracts: list[dict] = []
    inserted_activities: list[dict] = []
    inserted_assets: list[dict] = []
    updates: list[tuple[dict, dict]] = []

    fdb.crm2_contracts.insert_one = AsyncMock(
        side_effect=lambda d: inserted_contracts.append(d),
    )

    async def _upd(q, upd):
        updates.append((q, upd))
        for c in contracts:
            if all(c.get(k) == v for k, v in q.items()):
                c.update(upd.get("$set", {}))
        return MagicMock(modified_count=1)

    fdb.crm2_contracts.update_one = AsyncMock(side_effect=_upd)

    # find_one used by _ensure_accept_token: returns the newly inserted
    # contract (no accept_token yet) so the token-mint branch fires.
    fdb.crm2_contracts.find_one = AsyncMock(
        side_effect=lambda q, p=None: next(
            (d for d in inserted_contracts
             if all(d.get(k) == v for k, v in q.items())), None,
        ),
    )
    fdb.crm2_contacts.find_one = AsyncMock(
        side_effect=lambda q, p=None: (
            {"email": contact_emails.get(q.get("id"))}
            if contact_emails.get(q.get("id")) else None
        ),
    )
    fdb.crm2_contract_assets.find = MagicMock(
        side_effect=lambda q, p=None: (lambda: (
            type("C", (), {
                "to_list": AsyncMock(return_value=[
                    {k: vv for k, vv in a.items() if k != "_id"}
                    for a in (assets or [])
                    if a.get("contract_id") == q.get("contract_id")
                ]),
            })()
        ))(),
    )
    fdb.crm2_contract_assets.insert_one = AsyncMock(
        side_effect=lambda d: inserted_assets.append(d),
    )
    fdb.crm2_activities.insert_one = AsyncMock(
        side_effect=lambda d: inserted_activities.append(d),
    )
    fdb.organizations.find_one = AsyncMock(return_value={
        "name": "GymAxis", "primary_color": "#0055FF",
    })
    return fdb, inserted_contracts, inserted_activities, inserted_assets, updates


def test_autopilot_dispatches_renewal_for_eligible_contract():
    from routes.crm_contract_lifecycle import auto_send_renewals
    contracts = [{
        "id": "c-1", "organization_id": "org-1",
        "status": "active", "auto_renew": True,
        "tier": "gold", "contract_number": "CTR-A",
        "title": "Pulse Annual Cover", "company_id": "co-1",
        "company_name": "Pulse Fitness",
        "billing_contact_id": "ct-bill", "contact_id": "ct-1",
        "start_date": _today_plus(-330), "end_date": _today_plus(15),
        "annual_value": 12000, "version": 1,
        "pricing": {"annual_value": 12000, "vat_percent": 20},
        "inclusions": {"maintenance": ["callout", "labour"]},
        "exclusions_structured": [], "consumables": [],
        "response_times": {"emergency": {"hours": 4, "unit": "hours"}},
    }]
    fdb, inserted, activities, _, updates = _build_stub(
        contracts, contact_emails={"ct-bill": "billing@pulse.com"},
        assets=[{"id": "a1", "contract_id": "c-1", "asset_id": "eq-1",
                 "asset_name": "Treadmill", "coverage_type": "full"}],
    )
    with patch("routes.crm_contract_lifecycle.db", fdb), \
         patch("utils.crm_contract_pdf.build_contract_pdf",
               MagicMock(return_value=b"%PDF-fake")), \
         patch("routes.crm_contract_send.db", fdb), \
         patch("utils.email.send_email", AsyncMock(return_value=True)):
        out = _run(auto_send_renewals(user=USER))
    assert out["totals"]["dispatched"] == 1
    assert out["totals"]["skipped"] == 0
    d = out["dispatched"][0]
    assert d["to"] == "billing@pulse.com"
    assert d["uplift_percent"] >= 5.0
    assert d["new_annual_value"] > 12000  # uplift applied
    assert d["accept_path"].startswith("/contracts/accept/")
    # Renewal contract inserted with status=sent (not active — never auto-signs).
    new_doc = next(c for c in inserted if c["id"] == d["renewal_contract_id"])
    assert new_doc["status"] == "sent"
    assert new_doc["auto_dispatched"] is True
    assert new_doc["contract_number"].endswith("/R2")
    # Asset row copied over to the renewal contract.
    new_assets = [a for a in fdb.crm2_contract_assets.insert_one.await_args_list]
    assert len(new_assets) == 1
    # Original contract marked with auto_renewal_sent_at.
    assert contracts[0]["auto_renewal_sent_at"]
    # Audit activity dropped.
    assert any("Auto-renewal dispatched" in a["subject"] for a in activities)


def test_autopilot_skips_when_recently_dispatched():
    from routes.crm_contract_lifecycle import auto_send_renewals
    recent = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    contracts = [{
        "id": "c-1", "organization_id": "org-1", "status": "active",
        "auto_renew": True, "tier": "gold",
        "contract_number": "CTR-A", "billing_contact_id": "ct-bill",
        "end_date": _today_plus(15), "annual_value": 12000, "version": 1,
        "auto_renewal_sent_at": recent,
    }]
    fdb, _, _, _, _ = _build_stub(
        contracts, contact_emails={"ct-bill": "billing@pulse.com"},
    )
    with patch("routes.crm_contract_lifecycle.db", fdb), \
         patch("utils.email.send_email", AsyncMock(return_value=True)):
        out = _run(auto_send_renewals(user=USER))
    assert out["totals"]["dispatched"] == 0
    assert out["totals"]["skipped"] == 1
    assert out["skipped"][0]["reason"] == "already_dispatched_recently"


def test_autopilot_skips_when_no_contact_email():
    from routes.crm_contract_lifecycle import auto_send_renewals
    contracts = [{
        "id": "c-1", "organization_id": "org-1", "status": "active",
        "auto_renew": True, "contract_number": "CTR-A",
        "end_date": _today_plus(20), "annual_value": 6000,
        "billing_contact_id": "ct-bill", "contact_id": "ct-1",
        "version": 1,
    }]
    fdb, _, _, _, _ = _build_stub(contracts, contact_emails={})
    with patch("routes.crm_contract_lifecycle.db", fdb):
        out = _run(auto_send_renewals(user=USER))
    assert out["totals"]["dispatched"] == 0
    assert out["skipped"][0]["reason"] == "no_contact_email"


def test_autopilot_ignores_contracts_without_auto_renew_flag():
    from routes.crm_contract_lifecycle import auto_send_renewals
    contracts = [
        {"id": "c-1", "organization_id": "org-1", "status": "active",
         "auto_renew": False, "end_date": _today_plus(15), "annual_value": 100},
    ]
    fdb, _, _, _, _ = _build_stub(contracts)
    with patch("routes.crm_contract_lifecycle.db", fdb):
        out = _run(auto_send_renewals(user=USER))
    assert out["totals"]["dispatched"] == 0
    assert out["totals"]["skipped"] == 0
    # No contracts match the find filter at all.


def test_autopilot_button_wired_into_renewals_dashboard():
    from pathlib import Path
    src = Path("/app/frontend/src/pages/CRM/Contracts/ContractDashboards.js").read_text()
    assert "auto-renewal-autopilot-btn" in src
    assert "/crm/v2/contracts/renewals/auto-send" in src
