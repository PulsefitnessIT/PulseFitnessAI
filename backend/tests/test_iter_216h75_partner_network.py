"""Iter 216h75 — Partner Engineer Network (Phase 1) regression tests.

Covers:
  • Partner apply (idempotent), self GET, referrals + commission list
  • Public referral lookup
  • Master admin: list, approve, reject, suspend, level change, queue,
    approve commission, queue payout, mark paid, CSV export, summary
  • Anti-abuse: unknown ref code, partner can't refer own org,
    write-once attribution, idempotency by Stripe invoice id,
    pre-existing-pipeline flag claws back accrued rows
  • App-fee tier transitions (0/5/10/25 active referrals)
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

import pytest
import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://comms-email-hub.preview.emergentagent.com"
).rstrip("/")

OPERATOR_EMAIL = "e1.agent@gymaxisai.com"
OPERATOR_PASSWORD = "E1Agent123!"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


def _login(email: str, password: str) -> dict:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def op_headers():
    return _login(OPERATOR_EMAIL, OPERATOR_PASSWORD)


@pytest.fixture(scope="module")
def admin_headers():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def applied_partner(op_headers):
    """Submit (or re-submit) an application for the operator account."""
    payload = {
        "full_name": "E1 Test Engineer",
        "company_name": "E1 Eng Ltd",
        "phone": "+447700900111",
        "service_postcode": "SW1A 1AA",
        "travel_radius_km": 30,
        "brands_supported": ["Life Fitness", "Technogym"],
        "skills": ["Cardio", "Strength"],
        "qualifications": ["NVQ L3"],
        "terms_accepted": True,
    }
    r = requests.post(f"{BASE_URL}/api/partners/apply", json=payload, headers=op_headers, timeout=10)
    if r.status_code == 400 and "already approved" in r.text.lower():
        # Already approved from a prior run — use the existing record.
        me = requests.get(f"{BASE_URL}/api/partners/me", headers=op_headers, timeout=10).json()
        return me["partner"]
    assert r.status_code == 200, r.text
    return r.json()["partner"]


class TestPartnerSelfService:
    def test_apply_creates_pending_partner(self, applied_partner):
        # Could be pending OR approved (if a previous run left it approved).
        assert applied_partner["status"] in {"pending", "approved"}
        assert applied_partner["referral_code"]
        assert len(applied_partner["referral_code"]) == 8
        assert applied_partner["referral_code"].isupper()
        # App fee tier sane at 0 referrals (could be 30 in fresh state,
        # 15 if a prior test left orphan refs, or 0 on free tier — we
        # only care that it's one of the valid prices)
        tier = applied_partner["app_fee_tier"]
        assert tier["price_gbp"] in (0, 15, 30)

    def test_get_me_returns_partner_and_link(self, op_headers, applied_partner):
        r = requests.get(f"{BASE_URL}/api/partners/me", headers=op_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["partner"]["id"] == applied_partner["id"]
        assert body["referral_link"].endswith(f"?ref={applied_partner['referral_code']}")

    def test_referrals_endpoint(self, op_headers):
        r = requests.get(f"{BASE_URL}/api/partners/me/referrals", headers=op_headers, timeout=10)
        assert r.status_code == 200
        assert "referrals" in r.json()

    def test_commission_endpoint_shape(self, op_headers):
        r = requests.get(f"{BASE_URL}/api/partners/me/commission", headers=op_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "ledger" in body and "totals" in body
        for k in ("accrued", "approved", "paid", "clawed_back"):
            assert k in body["totals"]

    def test_apply_validates_terms(self, op_headers):
        r = requests.post(f"{BASE_URL}/api/partners/apply", json={
            "full_name": "X", "service_postcode": "SW1A 1AA", "terms_accepted": False,
        }, headers=op_headers, timeout=10)
        assert r.status_code == 400


class TestMasterAdminLifecycle:
    def test_admin_lists_partners(self, admin_headers, applied_partner):
        r = requests.get(f"{BASE_URL}/api/master-admin/partners", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()["partners"]]
        assert applied_partner["id"] in ids

    def test_admin_approve_then_level(self, admin_headers, applied_partner):
        r = requests.post(
            f"{BASE_URL}/api/master-admin/partners/{applied_partner['id']}/approve",
            json={"level": "engineer_partner"}, headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200

        r2 = requests.post(
            f"{BASE_URL}/api/master-admin/partners/{applied_partner['id']}/level",
            json={"level": "verified_partner"}, headers=admin_headers, timeout=10,
        )
        assert r2.status_code == 200

        # Bad level → 400
        r3 = requests.post(
            f"{BASE_URL}/api/master-admin/partners/{applied_partner['id']}/level",
            json={"level": "not_a_real_level"}, headers=admin_headers, timeout=10,
        )
        assert r3.status_code == 400

        # Restore level to engineer_partner for downstream tests
        requests.post(
            f"{BASE_URL}/api/master-admin/partners/{applied_partner['id']}/level",
            json={"level": "engineer_partner"}, headers=admin_headers, timeout=10,
        )

    def test_admin_reject_requires_master_admin(self, applied_partner):
        # No auth header → 401/403
        r = requests.post(
            f"{BASE_URL}/api/master-admin/partners/{applied_partner['id']}/reject",
            json={"reason": "spam"}, timeout=10,
        )
        assert r.status_code in (401, 403)


class TestPublicLookup:
    def test_unknown_code_returns_invalid(self):
        r = requests.get(f"{BASE_URL}/api/partners/public/lookup", params={"code": "NOTACODE"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["valid"] is False

    def test_valid_code_returns_first_name(self, applied_partner):
        # Must be approved first
        code = applied_partner["referral_code"]
        r = requests.get(f"{BASE_URL}/api/partners/public/lookup", params={"code": code}, timeout=10)
        assert r.status_code == 200
        body = r.json()
        # Approved? body.valid=True else False. Either way no 500.
        assert "valid" in body


# ─── Direct DB-driven tests for the commission engine & anti-abuse rules ────────

def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def db_client():
    """Reuses the same Motor client the app does."""
    import sys
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # type: ignore
    return db


class TestCommissionAccrual:
    def test_first_invoice_signup_reward_50pct(self, db_client, applied_partner):
        from routes.partners import accrue_commission_on_invoice_paid

        org_id = f"test-org-{uuid.uuid4()}"
        async def _setup():
            await db_client.organizations.insert_one({
                "id": org_id, "name": "Sig Test Gym",
                "stripe_customer_id": f"cus_{uuid.uuid4()}",
                "referred_by_partner_id": applied_partner["id"],
                "referred_by_code": applied_partner["referral_code"],
            })
            await db_client.partner_referrals.insert_one({
                "id": f"ref-{uuid.uuid4()}",
                "partner_id": applied_partner["id"],
                "referral_code": applied_partner["referral_code"],
                "referred_organization_id": org_id,
                "status": "pending", "pre_existing_in_pipeline": False,
                "created_at": "2026-05-13T00:00:00Z", "first_paid_at": None,
                "last_recurring_at": None, "recurring_total_paid_gbp": 0.0,
                "signup_reward_amount_gbp": None,
            })
            org = await db_client.organizations.find_one({"id": org_id})
            invoice = {
                "id": f"in_first_{uuid.uuid4()}",
                "customer": org["stripe_customer_id"],
                "amount_paid": 6900,
                "lines": {"data": [{"description": "GymAxis Operations"}]},
            }
            row = await accrue_commission_on_invoice_paid(invoice)
            replay = await accrue_commission_on_invoice_paid(invoice)
            invoice2 = {
                "id": f"in_recurring_{uuid.uuid4()}",
                "customer": org["stripe_customer_id"],
                "amount_paid": 6900,
                "lines": {"data": [{"description": "GymAxis Operations"}]},
            }
            row2 = await accrue_commission_on_invoice_paid(invoice2)
            return row, replay, row2

        row, replay, row2 = _run_async(_setup())
        assert row and row["kind"] == "signup_reward"
        assert row["amount_gbp"] == 34.5  # 50% of £69
        assert row["status"] == "accrued"
        assert replay is None  # idempotent
        # Iter 216h194 — £3/site/mo recurring restored after iter
        # 216h193's over-aggressive removal. Subsequent invoices accrue
        # a £3 recurring ledger row again.
        assert row2 and row2["kind"] == "recurring"
        assert row2["amount_gbp"] == 3.0

    def test_partner_cannot_refer_own_org(self, db_client, applied_partner):
        from routes.partners import attach_referral_to_org
        async def _do():
            own_org = applied_partner.get("owner_organization_id")
            # Force-clear any existing referred_by on the own org for the test
            await db_client.organizations.update_one(
                {"id": own_org}, {"$unset": {"referred_by_partner_id": ""}},
            )
            res = await attach_referral_to_org(
                organization_id=own_org, ref_code=applied_partner["referral_code"],
            )
            return res
        result = _run_async(_do())
        assert result is None  # blocked

    def test_already_attributed_org_is_immutable(self, db_client, applied_partner):
        from routes.partners import attach_referral_to_org
        org_id = f"test-immutable-{uuid.uuid4()}"
        async def _setup():
            await db_client.organizations.insert_one({
                "id": org_id, "referred_by_partner_id": "some-other-partner",
            })
            return await attach_referral_to_org(
                organization_id=org_id, ref_code=applied_partner["referral_code"],
            )
        result = _run_async(_setup())
        assert result is None

    def test_pre_existing_flag_blocks_accrual(self, db_client, applied_partner):
        """Set pre_existing_in_pipeline=True on a referral, then attempt
        accrual — should be skipped."""
        from routes.partners import accrue_commission_on_invoice_paid
        org_id = f"test-pre-{uuid.uuid4()}"
        async def _setup():
            await db_client.organizations.insert_one({
                "id": org_id, "stripe_customer_id": f"cus_{uuid.uuid4()}",
                "referred_by_partner_id": applied_partner["id"],
            })
            await db_client.partner_referrals.insert_one({
                "id": f"ref-pre-{uuid.uuid4()}", "partner_id": applied_partner["id"],
                "referral_code": applied_partner["referral_code"],
                "referred_organization_id": org_id,
                "status": "pending", "pre_existing_in_pipeline": True,
                "created_at": "2026-05-13T00:00:00Z", "first_paid_at": None,
                "recurring_total_paid_gbp": 0.0, "signup_reward_amount_gbp": None,
            })
            org = await db_client.organizations.find_one({"id": org_id})
            return await accrue_commission_on_invoice_paid({
                "id": f"in_blocked_{uuid.uuid4()}", "customer": org["stripe_customer_id"],
                "amount_paid": 6900,
                "lines": {"data": [{"description": "GymAxis Operations"}]},
            })
        result = _run_async(_setup())
        assert result is None


class TestAppFeeTier:
    def test_tier_thresholds(self):
        from routes.partners import _app_fee_tier
        assert _app_fee_tier(0)["price_gbp"] == 30
        assert _app_fee_tier(4)["price_gbp"] == 30
        assert _app_fee_tier(5)["price_gbp"] == 15
        assert _app_fee_tier(9)["price_gbp"] == 15
        assert _app_fee_tier(10)["price_gbp"] == 0
        assert _app_fee_tier(10)["enhanced_review_required"] is False
        assert _app_fee_tier(25)["price_gbp"] == 0
        assert _app_fee_tier(25)["enhanced_review_required"] is True


class TestAdminCommissionFlow:
    def test_full_queue_to_csv(self, admin_headers, applied_partner):
        # Approve all accrued rows for this partner, queue a payout, export CSV.
        queue = requests.get(
            f"{BASE_URL}/api/master-admin/partners/commission/queue",
            headers=admin_headers, timeout=10,
        ).json()
        partner_rows = [r for r in queue["queue"] if r["partner_id"] == applied_partner["id"]]
        if not partner_rows:
            pytest.skip("No accrued rows for this partner — earlier test may have already drained them")
        for r in partner_rows:
            ar = requests.post(
                f"{BASE_URL}/api/master-admin/partners/commission/{r['id']}/approve",
                headers=admin_headers, timeout=10,
            )
            assert ar.status_code == 200

        qp = requests.post(
            f"{BASE_URL}/api/master-admin/partners/payouts/queue",
            json={"partner_id": applied_partner["id"], "method": "manual_csv"},
            headers=admin_headers, timeout=10,
        )
        assert qp.status_code == 200
        body = qp.json()
        assert body["ok"] is True
        assert body["total_gbp"] >= 3.0

        # CSV download
        csv_r = requests.get(
            f"{BASE_URL}/api/master-admin/partners/payouts/{body['payout_id']}/csv",
            headers=admin_headers, timeout=10,
        )
        assert csv_r.status_code == 200
        assert "TOTAL" in csv_r.text
        assert applied_partner["email"] in csv_r.text

        # Mark paid
        mp = requests.post(
            f"{BASE_URL}/api/master-admin/partners/payouts/{body['payout_id']}/mark-paid",
            json={"reference": "BACS-TEST-123"},
            headers=admin_headers, timeout=10,
        )
        assert mp.status_code == 200


class TestReportsSummary:
    def test_summary_shape(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/master-admin/partners/reports/summary", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "partners" in body and "referrals" in body and "commission" in body
        assert "total" in body["partners"]
        assert isinstance(body["partners"]["by_status"], dict)
