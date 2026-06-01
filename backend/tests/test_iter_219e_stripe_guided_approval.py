"""Iter 219e — Stripe-guided welcome email + auto-claim + checklist.

Pins three coupled changes:
  1. Approval email now leads with the £30/mo Stripe Partner Plan
     subscription. CTA deep-links to /partner-engineer?action=subscribe
     so the dashboard auto-fires Stripe Checkout once the engineer
     signs in.
  2. New util `claim_pending_partner_for_user` (wired into /auth/register
     and /auth/login) relinks any partner_engineers row whose user_id
     sits at `pending:<partner_id>` to the real authenticated user.
     Without this, 37 of 40 already-approved engineers were stranded.
  3. Activation checklist gained a 7th `stripe_connect_ready` step
     that auto-resolves from `payout.stripe_connect.charges_enabled`.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from unittest.mock import AsyncMock, patch

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────── Email body / CTA shape ───────────────────


def test_approval_email_subject_mentions_stripe_and_thirty_pounds():
    """Subject line must telegraph the action up front so the
    engineer doesn't bury it in their inbox."""
    from utils.partner_emails import send_application_approved
    with patch("utils.partner_emails.send_email", AsyncMock(return_value=True)) as send:
        asyncio.run(send_application_approved(
            email="x@y.com", full_name="X Y", referral_code="ABC12345",
        ))
    subject = send.await_args.kwargs["subject"]
    assert "Stripe" in subject or "Partner Plan" in subject
    assert "£30" in subject


def test_approval_email_cta_deep_links_to_subscribe_action():
    """The CTA button must take the engineer to the subscribe
    auto-trigger URL so they land in Stripe Checkout in 2 clicks
    (sign in → Stripe). The dashboard handles the auto-fire."""
    from utils.partner_emails import send_application_approved
    with patch("utils.partner_emails.send_email", AsyncMock(return_value=True)) as send:
        asyncio.run(send_application_approved(
            email="x@y.com", full_name="X Y", referral_code="ABC12345",
        ))
    body = send.await_args.kwargs["html"]
    assert "?action=subscribe" in body
    assert "Stripe" in body
    assert "ABC12345" in body  # referral code still embedded
    # Subscription should be the LEAD message — appear before
    # "Connect Stripe Express" (the payouts step).
    sub_idx = body.find("£30")
    connect_idx = body.find("Connect Stripe Express")
    assert sub_idx != -1
    assert connect_idx != -1
    assert sub_idx < connect_idx, (
        "Partner Plan subscription should come before the Stripe Connect Express step in the email."
    )


# ─────────────────── Auto-claim helper ───────────────────


def test_claim_pending_partner_for_user_relinks_matching_pending_row():
    """End-to-end: seed a pending partner row, register a user with
    the same email through the real `/auth/register` route, then
    verify the partner row was claimed via the auth hook."""
    import httpx
    from pymongo import MongoClient
    sync_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    base = os.environ.get(
        "TEST_BASE_URL",
        "https://service-ops-hub-6.preview.emergentagent.com",
    )
    bypass = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
    pid = str(uuid.uuid4())
    email = f"iter219e-claim-{uuid.uuid4().hex[:8]}@example.com"
    sync_db.partner_engineers.insert_one({
        "id": pid,
        "user_id": f"pending:{pid}",
        "email": email,
        "status": "approved",
        "level": "engineer_partner",
        "referral_code": "TESTREF",
    })
    user_id_created = None
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{base}/api/auth/register",
                json={
                    "email": email,
                    "password": "TestPass123!",
                    "full_name": "Claim Test User",
                },
                headers=bypass,
            )
        assert r.status_code == 200, r.text
        # Decode the freshly-issued JWT to get the user id we expect
        # to see in the partner row.
        import jwt
        token = r.json()["token"]
        user_id_created = jwt.decode(token, options={"verify_signature": False})["user_id"]
        row = sync_db.partner_engineers.find_one({"id": pid}, {"_id": 0})
        assert row["user_id"] == user_id_created, (
            f"Expected user_id={user_id_created!r}, got {row['user_id']!r}"
        )
    finally:
        sync_db.partner_engineers.delete_one({"id": pid})
        if user_id_created:
            sync_db.users.delete_one({"id": user_id_created})


def test_claim_pending_partner_for_user_is_case_insensitive_on_email():
    """End-to-end: seed a partner row with mixed-case email, register
    with lower-case email — claim must still link them."""
    import httpx
    from pymongo import MongoClient
    sync_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    base = os.environ.get(
        "TEST_BASE_URL",
        "https://service-ops-hub-6.preview.emergentagent.com",
    )
    bypass = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
    pid = str(uuid.uuid4())
    suffix = uuid.uuid4().hex[:8]
    mixed_email = f"MixedCase{suffix}@Example.com"
    lower_email = mixed_email.lower()
    sync_db.partner_engineers.insert_one({
        "id": pid,
        "user_id": f"pending:{pid}",
        "email": mixed_email,
        "status": "approved",
    })
    user_id_created = None
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{base}/api/auth/register",
                json={
                    "email": lower_email,
                    "password": "TestPass123!",
                    "full_name": "Case Test User",
                },
                headers=bypass,
            )
        assert r.status_code == 200, r.text
        import jwt
        token = r.json()["token"]
        user_id_created = jwt.decode(token, options={"verify_signature": False})["user_id"]
        row = sync_db.partner_engineers.find_one({"id": pid}, {"_id": 0})
        assert row["user_id"] == user_id_created
    finally:
        sync_db.partner_engineers.delete_one({"id": pid})
        if user_id_created:
            sync_db.users.delete_one({"id": user_id_created})


def test_register_route_calls_claim_helper():
    """Pin the wiring — `/auth/register` must call the claim helper
    so newly-registered engineers immediately link to their pending
    partner row."""
    from pathlib import Path
    src = Path(os.path.join(os.path.dirname(__file__), "..", "routes", "auth.py")).read_text()
    register_block = src.split("@router.post(\"/auth/register\")")[1].split("@router.")[0]
    assert "claim_pending_partner_for_user" in register_block


def test_login_route_calls_claim_helper():
    """Same for `/auth/login` — every existing approved engineer is
    waiting at the login screen, so this hook is what unblocks them."""
    from pathlib import Path
    src = Path(os.path.join(os.path.dirname(__file__), "..", "routes", "auth.py")).read_text()
    # The helper lives inside `_finalise_successful_login`, which is
    # invoked from every successful login path.
    finalise_block = src.split("async def _finalise_successful_login")[1].split("\nasync def ")[0]
    assert "claim_pending_partner_for_user" in finalise_block


# ─────────────────── Activation checklist ───────────────────


def test_checklist_now_has_seven_steps_including_stripe_connect():
    from utils.partner_checklist import build_checklist, CHECKLIST_KEYS
    assert len(CHECKLIST_KEYS) == 7
    assert "stripe_connect_ready" in CHECKLIST_KEYS
    cl = build_checklist({}, referrals_count=0)
    assert cl["total"] == 7
    keys = [s["key"] for s in cl["steps"]]
    assert "stripe_connect_ready" in keys


def test_stripe_connect_step_resolves_from_payout_flag():
    """Connect step turns green the instant Stripe's onboarding
    callback writes `charges_enabled=true` into the partner row."""
    from utils.partner_checklist import build_checklist
    cl_off = build_checklist({"payout": {"stripe_connect": {"charges_enabled": False}}}, referrals_count=0)
    cl_on  = build_checklist({"payout": {"stripe_connect": {"charges_enabled": True}}},  referrals_count=0)
    step_off = next(s for s in cl_off["steps"] if s["key"] == "stripe_connect_ready")
    step_on  = next(s for s in cl_on["steps"]  if s["key"] == "stripe_connect_ready")
    assert step_off["done"] is False
    assert step_on["done"] is True


def test_stripe_connect_step_is_third_after_approved_and_subscribed():
    """Sequence matters for the user — Approved → Subscribe → Connect
    is the order the welcome email promises."""
    from utils.partner_checklist import build_checklist
    cl = build_checklist({}, referrals_count=0)
    seq = [s["key"] for s in cl["steps"]]
    assert seq[0] == "approved"
    assert seq[1] == "subscribed"
    assert seq[2] == "stripe_connect_ready"


def test_checklist_fully_complete_requires_stripe_connect_too():
    """Trophy banner shouldn't fire until Stripe Connect is also green —
    that's an explicit operator preference: no engineer should be
    "fully set up" while still unable to receive customer payments."""
    from utils.partner_checklist import build_checklist
    fully = build_checklist(
        {
            "approved_at": "2026-05-25T00:00:00+00:00",
            "subscription": {"stripe_subscription_id": "sub_123"},
            "payout": {"stripe_connect": {"charges_enabled": True}},
            "compliance_docs": {"dbs": {"file": "abc"}},
            "checklist": {"referral_link_copied_at": "2026-05-25T00:00:00+00:00"},
            "service_postcode": "SW1A 1AA",
            "travel_radius_km": 25,
        },
        referrals_count=1,
    )
    assert fully["done"] == 7
    assert fully["complete"] is True

    no_connect = build_checklist(
        {
            "approved_at": "2026-05-25T00:00:00+00:00",
            "subscription": {"stripe_subscription_id": "sub_123"},
            "compliance_docs": {"dbs": {"file": "abc"}},
            "checklist": {"referral_link_copied_at": "2026-05-25T00:00:00+00:00"},
            "service_postcode": "SW1A 1AA",
            "travel_radius_km": 25,
        },
        referrals_count=1,
    )
    assert no_connect["done"] == 6
    assert no_connect["complete"] is False


# Quiet pytest about unused import on some lint configs.
_ = pytest
