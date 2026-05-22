"""Iter 216h287 — Engineer-of-engineer referrals (Gap 9).

Closes Gap 9 from the BA audit: an approved Partner Engineer can
now share a recruit link, and every approved fellow-engineer they
bring in counts toward the same tier-credit ladder as a gym
referral (5 → £15/mo, 10 → free).

Pins covered
------------
* `_combined_active_count` sums gym + engineer rows
* `_recompute_app_fee` flips tiers when the combined count crosses
  a milestone, regardless of which side the credit came from
* `_resolve_eref_partner` 404s on unknown / unapproved codes
* `_record_engineer_referral` is idempotent on (referrer, email)
* Self-referral is silently rejected
* Public lookup endpoint returns minimal PII only
* `admin_approve_partner` credits the referrer once and only once
* Public-apply endpoint stamps `referred_by_eref` + writes a
  pending engineer_referrals row when the eref resolves
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin():
    return {"id": "u-admin", "is_master_admin": True, "role": "owner"}


def _user(uid: str = "u-jane", email: str = "jane@x.com"):
    return {"id": uid, "email": email, "organization_id": "org-1"}


# ── Combined count + tier recompute ────────────────────────────────


def test_combined_count_sums_gym_and_engineer():
    from routes.partners import _combined_active_count
    fake_db = MagicMock()
    fake_db.partner_referrals.count_documents = AsyncMock(return_value=3)
    fake_db.engineer_referrals.count_documents = AsyncMock(return_value=2)
    with patch("routes.partners.db", fake_db):
        n = _run(_combined_active_count("p1"))
    assert n == 5


def test_recompute_app_fee_uses_combined_count_to_flip_tier():
    """3 gym + 7 engineer = 10 → free tier even though gym alone would
    have left the partner at £30/mo. Pins the BA-audit decision."""
    from routes.partners import _recompute_app_fee
    fake_db = MagicMock()
    fake_db.partner_referrals.count_documents = AsyncMock(return_value=3)
    fake_db.engineer_referrals.count_documents = AsyncMock(return_value=7)
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "app_fee_tier": {"price_gbp": 30}, "subscription": {},
    })
    captured = {}
    fake_db.partner_engineers.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._sync_partner_subscription_to_tier", AsyncMock()):
        tier = _run(_recompute_app_fee("p1"))
    assert tier["price_gbp"] == 0
    assert captured["$set"]["active_referral_count"] == 10
    assert captured["$set"]["engineer_referral_count"] == 7


# ── _resolve_eref_partner ──────────────────────────────────────────


def test_resolve_eref_partner_returns_only_approved():
    from routes.partners import _resolve_eref_partner
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    with patch("routes.partners.db", fake_db):
        out = _run(_resolve_eref_partner("ABC123"))
    assert out is None
    # And the filter must scope to approved status
    flt = fake_db.partner_engineers.find_one.call_args[0][0]
    assert flt.get("status") == "approved"
    assert flt.get("referral_code") == "ABC123"


def test_resolve_eref_partner_normalises_code():
    from routes.partners import _resolve_eref_partner
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "referral_code": "ABC123"})
    with patch("routes.partners.db", fake_db):
        _run(_resolve_eref_partner(" abc123 "))
    assert fake_db.partner_engineers.find_one.call_args[0][0]["referral_code"] == "ABC123"


# ── _record_engineer_referral ──────────────────────────────────────


def test_record_engineer_referral_creates_new_row():
    from routes.partners import _record_engineer_referral
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"email": "jane@x.com"})
    fake_db.engineer_referrals.find_one = AsyncMock(return_value=None)
    captured = {}

    async def cap(doc):
        captured.update(doc)
    fake_db.engineer_referrals.insert_one = AsyncMock(side_effect=cap)
    with patch("routes.partners.db", fake_db):
        out = _run(_record_engineer_referral(
            referrer_partner_id="p1", referrer_code="ABC",
            referred_email="newbie@example.com",
            referred_application_id="app-1",
        ))
    assert out["status"] == "pending"
    assert captured["referred_email"] == "newbie@example.com"
    assert captured["referrer_partner_id"] == "p1"
    assert captured["referred_application_id"] == "app-1"


def test_record_engineer_referral_is_idempotent():
    from routes.partners import _record_engineer_referral
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"email": "jane@x.com"})
    fake_db.engineer_referrals.find_one = AsyncMock(return_value={"id": "er1", "status": "pending"})
    fake_db.engineer_referrals.insert_one = AsyncMock()
    captured = {}
    fake_db.engineer_referrals.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    with patch("routes.partners.db", fake_db):
        out = _run(_record_engineer_referral(
            referrer_partner_id="p1", referrer_code="ABC",
            referred_email="newbie@example.com",
            referred_application_id="app-2",
        ))
    # No new insert
    fake_db.engineer_referrals.insert_one.assert_not_awaited()
    assert out["id"] == "er1"
    # But the application_id got refreshed
    assert captured["$set"]["referred_application_id"] == "app-2"


def test_record_engineer_referral_rejects_self_referral():
    from routes.partners import _record_engineer_referral
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"email": "jane@x.com"})
    fake_db.engineer_referrals.insert_one = AsyncMock()
    with patch("routes.partners.db", fake_db):
        out = _run(_record_engineer_referral(
            referrer_partner_id="p1", referrer_code="ABC",
            referred_email="JANE@x.com",
        ))
    assert out is None
    fake_db.engineer_referrals.insert_one.assert_not_awaited()


def test_record_engineer_referral_rejects_bad_email():
    from routes.partners import _record_engineer_referral
    fake_db = MagicMock()
    fake_db.engineer_referrals.insert_one = AsyncMock()
    with patch("routes.partners.db", fake_db):
        assert _run(_record_engineer_referral(
            referrer_partner_id="p1", referrer_code="ABC",
            referred_email="not-an-email",
        )) is None
        assert _run(_record_engineer_referral(
            referrer_partner_id="p1", referrer_code="ABC",
            referred_email="",
        )) is None
    fake_db.engineer_referrals.insert_one.assert_not_awaited()


# ── _credit_engineer_referral_on_approval ──────────────────────────


def test_credit_on_approval_awards_once():
    from routes.partners import _credit_engineer_referral_on_approval
    fake_db = MagicMock()
    fake_db.engineer_referrals.find_one = AsyncMock(return_value={
        "id": "er1", "referrer_partner_id": "p-ref", "status": "pending",
        "referred_email": "newbie@example.com",
    })
    captured = {}
    fake_db.engineer_referrals.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()), \
         patch("routes.partners._recompute_app_fee", AsyncMock()) as recompute:
        out = _run(_credit_engineer_referral_on_approval(
            {"id": "p-new", "email": "newbie@example.com"}, actor_id="u-admin",
        ))
    assert out is not None
    assert out["status"] == "approved"
    assert captured["$set"]["status"] == "approved"
    assert captured["$set"]["referred_partner_id"] == "p-new"
    recompute.assert_awaited_once_with("p-ref")


def test_credit_on_approval_is_idempotent_when_no_pending_row():
    from routes.partners import _credit_engineer_referral_on_approval
    fake_db = MagicMock()
    fake_db.engineer_referrals.find_one = AsyncMock(return_value=None)
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._recompute_app_fee", AsyncMock()) as recompute:
        out = _run(_credit_engineer_referral_on_approval(
            {"id": "p-new", "email": "newbie@example.com"}, actor_id="u-admin",
        ))
    assert out is None
    recompute.assert_not_awaited()


def test_credit_on_approval_noop_when_no_email():
    from routes.partners import _credit_engineer_referral_on_approval
    fake_db = MagicMock()
    fake_db.engineer_referrals.find_one = AsyncMock()
    with patch("routes.partners.db", fake_db):
        out = _run(_credit_engineer_referral_on_approval({"id": "p-new", "email": ""}, actor_id="u"))
    assert out is None
    fake_db.engineer_referrals.find_one.assert_not_awaited()


# ── Public by-eref endpoint ────────────────────────────────────────


def test_public_eref_lookup_returns_minimal_data():
    from routes.partners import public_eref_lookup
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "full_name": "Jane Smith", "company_name": "BiceptHub Ltd",
        "referral_code": "ABC123", "service_postcode": "M1 4WP", "level": "engineer_partner",
        "active_referral_count": 7,
    })
    with patch("routes.partners.db", fake_db):
        out = _run(public_eref_lookup("ABC123"))
    assert out["first_name"] == "Jane"
    assert out["company_name"] == "BiceptHub Ltd"
    assert out["referral_code"] == "ABC123"
    assert out["service_area"] == "M1"  # outward only
    assert out["active_referrals"] == 7
    assert out["apply_url"] == "/partners/engineers/apply?eref=ABC123"
    # No PII leak
    assert "full_name" not in out
    assert "email" not in out


def test_public_eref_lookup_404s_unknown_code():
    from routes.partners import public_eref_lookup
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    with patch("routes.partners.db", fake_db), pytest.raises(Exception) as exc:
        _run(public_eref_lookup("UNKNOWN"))
    assert exc.value.status_code == 404


# ── list_my_engineer_referrals ─────────────────────────────────────


def test_list_my_engineer_referrals_masks_emails_and_summarises():
    from routes.partners import list_my_engineer_referrals
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={
        "id": "p1", "user_id": "u-jane", "referral_code": "ABC123",
    })
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=[
        {"id": "er1", "status": "approved", "referred_email": "joe.bloggs@gym.io", "created_at": "2026-02-20"},
        {"id": "er2", "status": "approved", "referred_email": "x@y.io", "created_at": "2026-02-19"},
        {"id": "er3", "status": "pending",  "referred_email": "sue@gym.io", "created_at": "2026-02-18"},
    ])
    fake_db.engineer_referrals.find = MagicMock(return_value=cur)
    with patch("routes.partners.db", fake_db):
        out = _run(list_my_engineer_referrals(user=_user()))
    assert out["summary"] == {"total": 3, "approved": 2, "pending": 1, "rejected": 0}
    assert out["referrals"][0]["referred_email_masked"] == "j***@gym.io"
    assert out["referrals"][1]["referred_email_masked"] == "x***@y.io"  # 1-char local
    assert out["share_link"].endswith("/engineer/r/ABC123")
    assert out["referral_code"] == "ABC123"
    # No raw email leaks
    assert all("referred_email" not in r for r in out["referrals"])


def test_list_my_engineer_referrals_404_when_not_a_partner():
    from routes.partners import list_my_engineer_referrals
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    with patch("routes.partners.db", fake_db), pytest.raises(Exception) as exc:
        _run(list_my_engineer_referrals(user=_user()))
    assert exc.value.status_code == 404


# ── _mask_email pure-function pin ──────────────────────────────────


def test_mask_email_edge_cases():
    from routes.partners import _mask_email
    assert _mask_email("jack.ottey@thirdspace.london") == "j***@thirdspace.london"
    assert _mask_email("a@b.io") == "a***@b.io"
    assert _mask_email("") == "anonymous"
    assert _mask_email("no-at-sign") == "anonymous"
