"""Iter 216h284 — First-7-days activation checklist (Gap 5).

Closes Gap 5 from the BA audit: newly-approved engineers had nothing
to do next. The checklist surfaces 6 milestones, most auto-resolved
server-side from the existing partner record + referrals + compliance.

What we pin:
* build_checklist returns 6 steps in stable order
* each step's `done` flag derives from the right partner field
* `complete` flips true only when all 6 steps are done
* only `referral_link_copied` is user-ackable
* GET /partners/me/checklist returns the structure unchanged
* POST /partners/me/checklist/ack rejects un-ackable keys
* POST /partners/me/checklist/ack persists the timestamp + is
  idempotent (re-acking is a no-op)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.partner_checklist import (
    CHECKLIST_KEYS,
    ACKABLE_KEYS,
    ack_field_name,
    build_checklist,
    is_ackable,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _partner_user():
    return {"id": "u-jane", "organization_id": "gymaxis-ai-admin"}


def _empty_partner():
    return {
        "id": "p1", "user_id": "u-jane", "status": "approved",
        "approved_at": datetime.now(timezone.utc),
        "subscription": {}, "compliance_docs": {}, "service_postcode": "", "travel_radius_km": 0,
    }


# ── Pure function: build_checklist ────────────────────────────────


def test_build_checklist_keys_in_stable_order():
    out = build_checklist(_empty_partner(), referrals_count=0)
    keys = [s["key"] for s in out["steps"]]
    assert keys == list(CHECKLIST_KEYS)
    # Iter 220m hardening: live CHECKLIST_KEYS is now 7 (added
    # `stripe_connect_ready` between `subscribed` and `compliance_uploaded`).
    # Pin against the source of truth so the count auto-tracks.
    assert out["total"] == len(CHECKLIST_KEYS)


def test_build_checklist_approved_step_always_done_for_approved_partners():
    out = build_checklist(_empty_partner(), referrals_count=0)
    approved = next(s for s in out["steps"] if s["key"] == "approved")
    assert approved["done"] is True


def test_subscribed_step_resolves_from_stripe_subscription_id():
    p = _empty_partner()
    p["subscription"] = {"stripe_subscription_id": "sub_123"}
    out = build_checklist(p, 0)
    subscribed = next(s for s in out["steps"] if s["key"] == "subscribed")
    assert subscribed["done"] is True


def test_compliance_uploaded_resolves_from_any_doc_kind():
    p = _empty_partner()
    p["compliance_docs"] = {"rtw": {"file": {"original_filename": "passport.png"}}}
    out = build_checklist(p, 0)
    step = next(s for s in out["steps"] if s["key"] == "compliance_uploaded")
    assert step["done"] is True


def test_referral_link_copied_only_done_via_ack_timestamp():
    p = _empty_partner()
    out = build_checklist(p, 0)
    assert next(s for s in out["steps"] if s["key"] == "referral_link_copied")["done"] is False
    p["checklist"] = {"referral_link_copied_at": datetime.now(timezone.utc)}
    out2 = build_checklist(p, 0)
    assert next(s for s in out2["steps"] if s["key"] == "referral_link_copied")["done"] is True


def test_first_referral_resolves_from_referrals_count():
    p = _empty_partner()
    assert next(s for s in build_checklist(p, 0)["steps"] if s["key"] == "first_referral")["done"] is False
    assert next(s for s in build_checklist(p, 1)["steps"] if s["key"] == "first_referral")["done"] is True


def test_service_area_step_needs_postcode_and_radius():
    p = _empty_partner()
    # Only postcode set → not done
    p["service_postcode"] = "SW1A 1AA"
    assert next(s for s in build_checklist(p, 0)["steps"] if s["key"] == "service_area_set")["done"] is False
    # Postcode + radius → done
    p["travel_radius_km"] = 25
    assert next(s for s in build_checklist(p, 0)["steps"] if s["key"] == "service_area_set")["done"] is True


def test_complete_flag_only_true_when_all_steps_done():
    p = _empty_partner()
    p["subscription"] = {"stripe_subscription_id": "sub_1"}
    # Iter 220m — Stripe Connect Express now a separately-resolved step.
    p["payout"] = {"stripe_connect": {"charges_enabled": True}}
    p["compliance_docs"] = {"dbs": {"file": {"original_filename": "dbs.png"}}}
    p["checklist"] = {"referral_link_copied_at": datetime.now(timezone.utc)}
    p["service_postcode"] = "SW1A 1AA"
    p["travel_radius_km"] = 25
    total = len(CHECKLIST_KEYS)
    # All-but-first_referral done
    out = build_checklist(p, 0)
    assert out["done"] == total - 1
    assert out["complete"] is False
    out2 = build_checklist(p, 1)
    assert out2["done"] == total
    assert out2["complete"] is True


# ── Ackability ────────────────────────────────────────────────────


def test_only_referral_link_copied_is_user_ackable():
    assert is_ackable("referral_link_copied") is True
    assert is_ackable("subscribed") is False
    assert is_ackable("first_referral") is False
    assert {"referral_link_copied"} == ACKABLE_KEYS


def test_ack_field_name_uses_dotted_path():
    assert ack_field_name("referral_link_copied") == "checklist.referral_link_copied_at"


# ── Endpoints ────────────────────────────────────────────────────


def test_get_checklist_endpoint_returns_six_steps():
    from routes.partners import get_my_checklist
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=_empty_partner())
    fake_db.partner_referrals.count_documents = AsyncMock(return_value=0)
    with patch("routes.partners.db", fake_db):
        out = _run(get_my_checklist(user=_partner_user()))
    # Iter 220m — CHECKLIST_KEYS grew to 7; assert against the canon.
    assert out["checklist"]["total"] == len(CHECKLIST_KEYS)
    assert out["checklist"]["done"] == 1  # only "approved"


def test_ack_endpoint_rejects_unackable_key():
    from routes.partners import ack_my_checklist_step
    with pytest.raises(Exception) as exc:
        _run(ack_my_checklist_step(body={"key": "first_referral"}, user=_partner_user()))
    assert "not user-ackable" in str(exc.value.detail)


def test_ack_endpoint_persists_timestamp():
    from routes.partners import ack_my_checklist_step
    fake_db = MagicMock()
    partner = _empty_partner()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    captured = {}

    async def cap(_filt, update):
        captured.update(update)
    fake_db.partner_engineers.update_one = AsyncMock(side_effect=cap)
    fake_db.partner_referrals.count_documents = AsyncMock(return_value=0)
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()):
        out = _run(ack_my_checklist_step(body={"key": "referral_link_copied"}, user=_partner_user()))
    assert out["ok"] is True
    assert "checklist.referral_link_copied_at" in captured["$set"]
    # _now() returns an ISO string in this codebase; just confirm it's truthy.
    assert captured["$set"]["checklist.referral_link_copied_at"]


def test_ack_endpoint_is_idempotent_for_already_acked():
    """Re-acking a step that's already done is a no-op write."""
    from routes.partners import ack_my_checklist_step
    fake_db = MagicMock()
    partner = _empty_partner()
    partner["checklist"] = {"referral_link_copied_at": datetime.now(timezone.utc)}
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_engineers.update_one = AsyncMock()
    fake_db.partner_referrals.count_documents = AsyncMock(return_value=0)
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()):
        out = _run(ack_my_checklist_step(body={"key": "referral_link_copied"}, user=_partner_user()))
    assert out["ok"] is True
    fake_db.partner_engineers.update_one.assert_not_called()


def test_get_checklist_404s_for_non_partner():
    from routes.partners import get_my_checklist
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    with patch("routes.partners.db", fake_db), pytest.raises(Exception) as exc:
        _run(get_my_checklist(user=_partner_user()))
    assert "apply first" in str(exc.value.detail)
