"""Iter 220e3 — Contracts Phases D/E/F/G: PDF, send/accept, renewals,
reports and AI assistance.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _today_plus(days: int) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


USER = {"id": "u-1", "organization_id": "org-1", "full_name": "Sam"}


# ── PDF builder ───────────────────────────────────────────────


def test_build_contract_pdf_outputs_bytes_starting_with_pdf_header():
    from utils.crm_contract_pdf import build_contract_pdf
    catalog = {
        "inclusion_groups": [{
            "key": "maintenance", "label": "Maintenance",
            "items": [{"key": "callout", "label": "Callout"},
                      {"key": "labour", "label": "Labour"}],
        }],
        "exclusion_items": [{"key": "misuse", "label": "Customer misuse"}],
        "response_time_bands": [{"key": "emergency", "label": "Emergency", "default_hours": 4}],
        "consumable_presets": [],
    }
    contract = {
        "id": "c-1", "contract_number": "CTR-ABCDEF",
        "title": "Pulse Annual Cover", "tier": "gold",
        "company_name": "Pulse", "site_name": "London HQ",
        "start_date": "2026-01-01", "end_date": "2027-01-01",
        "inclusions": {"maintenance": ["callout", "labour"]},
        "exclusions_structured": ["misuse"],
        "response_times": {"emergency": {"hours": 4, "unit": "hours"}},
        "pricing": {"annual_value": 12000, "monthly_value": 1000,
                    "setup_fee": 500, "vat_percent": 20},
        "annual_value": 12000,
        "consumables": [{"name": "Belt lubricant", "included": True, "charge": 0}],
        "terms_md": "### Terms\n- Cover starts on the start date.\n",
    }
    out = build_contract_pdf(contract, {"name": "GymAxis", "primary_color": "#0055FF"}, catalog)
    assert isinstance(out, bytes) and out.startswith(b"%PDF")
    # Length > a trivial empty PDF so we know the story has content.
    assert len(out) > 2500


# ── Renewals pipeline + reminders ─────────────────────────────


def _renewal_stub_db(contracts: list[dict]):
    fdb = MagicMock()

    def _find(query, projection=None):
        rows = [{k: v for k, v in c.items() if k != "_id"} for c in contracts
                if all(_match(c, query))]
        cur = MagicMock()
        cur.sort = MagicMock(return_value=cur)
        cur.to_list = AsyncMock(return_value=rows)
        return cur

    def _match(doc, query):
        for k, v in query.items():
            if isinstance(v, dict):
                # support $lte / $gte
                end_val = doc.get(k)
                if not end_val:
                    yield False
                    return
                if "$lte" in v and end_val > v["$lte"]:
                    yield False
                    return
                if "$gte" in v and end_val < v["$gte"]:
                    yield False
                    return
            elif doc.get(k) != v:
                yield False
                return
        yield True

    fdb.crm2_contracts.find = MagicMock(side_effect=_find)
    fdb.crm2_activities.find_one = AsyncMock(return_value=None)
    fdb.crm2_activities.insert_one = AsyncMock()
    return fdb


def test_renewal_pipeline_buckets_by_30_60_90_days():
    from routes.crm_contract_lifecycle import renewals_pipeline
    contracts = [
        {"id": "c1", "organization_id": "org-1", "status": "active",
         "title": "A", "contract_number": "CTR-A",
         "end_date": _today_plus(15), "annual_value": 12000, "tier": "gold"},
        {"id": "c2", "organization_id": "org-1", "status": "active",
         "title": "B", "contract_number": "CTR-B",
         "end_date": _today_plus(45), "annual_value": 6000, "tier": "silver"},
        {"id": "c3", "organization_id": "org-1", "status": "active",
         "title": "C", "contract_number": "CTR-C",
         "end_date": _today_plus(85), "annual_value": 24000, "tier": "platinum"},
        {"id": "c4", "organization_id": "org-1", "status": "active",
         "title": "D-too-far", "contract_number": "CTR-D",
         "end_date": _today_plus(200), "annual_value": 99},  # filtered out
    ]
    fdb = _renewal_stub_db(contracts)
    with patch("routes.crm_contract_lifecycle.db", fdb):
        out = _run(renewals_pipeline(user=USER))
    assert {b["id"] for b in out["buckets"]["30"]} == {"c1"}
    assert {b["id"] for b in out["buckets"]["60"]} == {"c2"}
    assert {b["id"] for b in out["buckets"]["90"]} == {"c3"}
    # Suggested uplift surfaces.
    assert out["buckets"]["30"][0]["suggested_uplift_percent"] >= 5.0
    assert out["totals"]["contracts"] == 3
    assert out["totals"]["annual_value_at_risk"] == 42000.0


def test_renewal_reminders_are_idempotent_for_same_threshold():
    from routes.crm_contract_lifecycle import run_renewal_reminders
    contracts = [{"id": "c1", "organization_id": "org-1", "status": "active",
                  "contract_number": "CTR-A", "title": "A",
                  "company_id": "co-1", "company_name": "Pulse",
                  "end_date": _today_plus(20), "annual_value": 12000}]
    fdb = _renewal_stub_db(contracts)
    inserts: list[dict] = []
    fdb.crm2_activities.insert_one = AsyncMock(side_effect=lambda d: inserts.append(d))
    with patch("routes.crm_contract_lifecycle.db", fdb):
        first = _run(run_renewal_reminders(user=USER))
    assert first["reminders_created"] == 1
    assert inserts and inserts[0]["threshold_days"] == 30

    # Second run: activities.find_one now resolves to the previous row
    # so the threshold-30 reminder is skipped.
    fdb.crm2_activities.find_one = AsyncMock(return_value=inserts[0])
    with patch("routes.crm_contract_lifecycle.db", fdb):
        second = _run(run_renewal_reminders(user=USER))
    assert second["reminders_created"] == 0


# ── Reports dashboard ─────────────────────────────────────────


def test_reports_dashboard_aggregates_tier_status_and_coverage():
    from routes.crm_contract_lifecycle import contracts_report_dashboard
    fdb = MagicMock()

    def _aggregate(pipeline):
        cur = MagicMock()
        first_match = pipeline[0].get("$match", {})
        is_active_match = first_match.get("status") == "active"
        end_filter = first_match.get("end_date")
        if "$group" in pipeline[-1]:
            group_id = pipeline[-1]["$group"].get("_id")
            if group_id == "$tier" and is_active_match:
                cur.to_list = AsyncMock(return_value=[
                    {"_id": "silver", "count": 3, "annual_value": 18000.0},
                    {"_id": "gold", "count": 1, "annual_value": 12000.0},
                ])
            elif group_id == "$status":
                cur.to_list = AsyncMock(return_value=[
                    {"_id": "active", "count": 4},
                    {"_id": "draft", "count": 2},
                ])
            elif is_active_match and not end_filter:
                # Total ARR.
                cur.to_list = AsyncMock(return_value=[{"_id": None, "total": 30000.0}])
            elif is_active_match and end_filter:
                # Expiring buckets — simulate increasing.
                lte = end_filter.get("$lte", "")
                gte = end_filter.get("$gte", "")
                window = max(0, (datetime.fromisoformat(lte) - datetime.fromisoformat(gte)).days)
                if window <= 30:
                    cur.to_list = AsyncMock(return_value=[{"_id": None, "total": 5000.0}])
                elif window <= 60:
                    cur.to_list = AsyncMock(return_value=[{"_id": None, "total": 12000.0}])
                else:
                    cur.to_list = AsyncMock(return_value=[{"_id": None, "total": 18000.0}])
            else:
                cur.to_list = AsyncMock(return_value=[])
        return cur

    fdb.crm2_contracts.aggregate = MagicMock(side_effect=_aggregate)
    fdb.equipment.count_documents = AsyncMock(return_value=12)
    fdb.crm2_contract_assets.distinct = AsyncMock(return_value=["a1", "a2", "a3", ""])
    with patch("routes.crm_contract_lifecycle.db", fdb):
        out = _run(contracts_report_dashboard(user=USER))
    assert out["arr"] == 30000.0
    assert out["mrr"] == 2500.0
    assert out["expiring_30d_value"] == 5000.0
    assert out["expiring_60d_value"] == 12000.0
    assert out["expiring_90d_value"] == 18000.0
    assert out["coverage"]["assets_covered"] == 3
    assert out["coverage"]["assets_uncovered"] == 9
    assert any(t["tier"] == "silver" for t in out["by_tier"])


# ── AI suggestions (deterministic baseline path) ──────────────


def test_ai_recommend_cover_falls_back_to_deterministic_baseline():
    from routes.crm_contract_lifecycle import ai_recommend_cover
    fdb = MagicMock()
    fdb.crm2_contracts.find_one = AsyncMock(return_value={
        "id": "c-1", "organization_id": "org-1", "tier": "silver",
        "title": "Pulse", "annual_value": 8000,
    })
    fdb.crm2_contract_assets.count_documents = AsyncMock(return_value=15)
    with patch("routes.crm_contract_lifecycle.db", fdb), \
         patch("routes.crm_contract_lifecycle._llm_chat",
               AsyncMock(return_value="")):
        out = _run(ai_recommend_cover("c-1", user=USER))
    assert out["recommended_tier"] == "gold"
    assert out["uses_ai"] is False


def test_ai_suggest_uplift_returns_uplift_percent():
    from routes.crm_contract_lifecycle import ai_suggest_uplift
    fdb = MagicMock()
    fdb.crm2_contracts.find_one = AsyncMock(return_value={
        "id": "c-1", "organization_id": "org-1", "tier": "gold",
        "annual_value": 12000,
        "pricing": {"cost_estimate": 9500},  # > 70% cost ratio → +3
    })
    with patch("routes.crm_contract_lifecycle.db", fdb), \
         patch("routes.crm_contract_lifecycle._llm_chat",
               AsyncMock(return_value="")):
        out = _run(ai_suggest_uplift("c-1", user=USER))
    assert out["uplift_percent"] == 8.0
    assert "CPI" in out["rationale"]


def test_ai_draft_terms_returns_fallback_when_no_llm_key():
    from routes.crm_contract_lifecycle import ai_draft_terms
    fdb = MagicMock()
    fdb.crm2_contracts.find_one = AsyncMock(return_value={
        "id": "c-1", "organization_id": "org-1", "tier": "platinum",
    })
    with patch("routes.crm_contract_lifecycle.db", fdb), \
         patch("routes.crm_contract_lifecycle._llm_chat",
               AsyncMock(return_value="")):
        out = _run(ai_draft_terms(
            "c-1", {"brief": "Emergency response uplift for treadmills"},
            user=USER,
        ))
    assert out["uses_ai"] is False
    assert "Bespoke clause" in out["draft"]


# ── Public accept token round-trip ────────────────────────────


def test_public_sign_marks_contract_active_and_is_idempotent():
    from routes.crm_contract_send import public_contract_sign
    state = {"id": "c-1", "organization_id": "org-1",
             "accept_token": "tok-" + "x" * 22,
             "status": "sent", "company_id": "co-1",
             "tier": "gold", "contract_number": "CTR-X"}
    fdb = MagicMock()
    fdb.crm2_contracts.find_one = AsyncMock(side_effect=lambda q, p=None: state.copy())

    async def _upd(q, upd):
        state.update(upd.get("$set", {}))
        return MagicMock(modified_count=1)

    fdb.crm2_contracts.update_one = AsyncMock(side_effect=_upd)
    fdb.crm2_activities.insert_one = AsyncMock()
    with patch("routes.crm_contract_send.db", fdb):
        out = _run(public_contract_sign("tok-" + "x" * 22, {
            "signer_name": "Alice", "signature": "data:image/png;base64,abc",
        }))
    assert out["success"] is True
    assert out["status"] == "active"
    # Second call is idempotent — already signed.
    with patch("routes.crm_contract_send.db", fdb):
        again = _run(public_contract_sign("tok-" + "x" * 22, {
            "signer_name": "Alice", "signature": "abc",
        }))
    assert again.get("already_signed") is True


def test_public_snapshot_strips_internal_pricing_fields():
    from routes.crm_contract_send import public_contract_snapshot
    fdb = MagicMock()
    fdb.crm2_contracts.find_one = AsyncMock(return_value={
        "id": "c-1", "contract_number": "CTR-X", "title": "Pulse",
        "tier": "gold", "company_name": "Pulse", "site_name": "London",
        "start_date": "2026-01-01", "end_date": "2027-01-01",
        "annual_value": 12000,
        "pricing": {
            "annual_value": 12000, "vat_percent": 20,
            "cost_estimate": 8000,  # internal
            "margin_percent": 33,   # internal
        },
        "organization_id": "org-1", "status": "sent",
    })
    fdb.organizations.find_one = AsyncMock(return_value={"name": "GymAxis"})
    with patch("routes.crm_contract_send.db", fdb):
        out = _run(public_contract_snapshot("tok-" + "x" * 22))
    # Public payload never leaks cost / margin.
    assert "cost_estimate" not in out["pricing"]
    assert "margin_percent" not in out["pricing"]
    assert out["pricing"]["annual_value"] == 12000
    assert out["organization"]["name"] == "GymAxis"
