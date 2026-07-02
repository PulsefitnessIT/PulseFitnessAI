"""Iter 219f — single-use activation link flow.

End-to-end test of the welcome-email → activation page → Stripe Checkout
deep-link path. Pins the three new endpoints + the approval flow's
token side-effects against the live preview server.
"""
from __future__ import annotations

import io
import os
import sys
import uuid

import httpx
import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://comms-email-hub.preview.emergentagent.com",
)

_CACHE: dict[str, str] = {}


def _bypass_headers() -> dict[str, str]:
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": secret} if secret else {}


def _login(email: str, password: str) -> str:
    key = f"login::{email}"
    if _CACHE.get(key):
        return _CACHE[key]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
            headers=_bypass_headers(),
        )
        r.raise_for_status()
    _CACHE[key] = r.json()["token"]
    return _CACHE[key]


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


def _seed_application(email: str | None = None) -> tuple[str, str]:
    cv_bytes = b"%PDF-1.4\nFake CV body.\n%%EOF"
    files = {"cv_file": ("cv.pdf", io.BytesIO(cv_bytes), "application/pdf")}
    email = email or f"iter219f-{uuid.uuid4().hex[:8]}@example.com"
    data = {
        "full_name": "Activation Test Engineer",
        "email": email,
        "phone": "07123456789",
        "service_postcode": "LS1 1AA",
        "travel_radius_km": "30",
        "brands_supported": "Life Fitness",
        "skills": "cardio",
        "qualifications": "IPAF",
        "years_experience": "4",
        "has_insurance": "true",
        "insurance_provider": "Hiscox",
        "insurance_expires_at": "2026-12-31",
        "terms_accepted": "true",
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.post(f"{BASE}/api/partners/public-apply", data=data, files=files)
    assert r.status_code == 200, r.text
    return r.json()["application_id"], email


def _approve(application_id: str) -> dict:
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/approve",
            json={"level": "engineer_partner"},
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    return r.json()


def _read_token(application_id: str) -> str:
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    doc = db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    return doc["activation_token"]


# ─────────────────── Approval generates a token ───────────────────


def test_approval_writes_activation_token_with_14d_expiry():
    application_id, _ = _seed_application()
    _approve(application_id)
    from pymongo import MongoClient
    from datetime import datetime, timezone, timedelta
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    doc = db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    assert doc["activation_token"]
    assert len(doc["activation_token"]) >= 32
    expires = doc["activation_token_expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    delta = expires - datetime.now(timezone.utc)
    assert timedelta(days=13) < delta < timedelta(days=15), (
        f"Expected ~14d expiry, got {delta}"
    )
    assert doc.get("activation_completed_at") is None


# ─────────────────── /partners/activation/info ───────────────────


def test_activation_info_returns_prefill_for_valid_token():
    application_id, email = _seed_application()
    _approve(application_id)
    token = _read_token(application_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/partners/activation/info", json={"token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"].lower() == email.lower()
    assert body["full_name"] == "Activation Test Engineer"
    assert body["has_existing_account"] is False


def test_activation_info_404_for_unknown_token():
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/partners/activation/info", json={"token": "garbage" * 8})
    assert r.status_code == 404


def test_activation_info_404_for_empty_token():
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/partners/activation/info", json={"token": ""})
    assert r.status_code == 404


# ─────────────────── /partners/activation/complete ───────────────────


def test_activation_complete_creates_user_and_returns_stripe_url():
    application_id, email = _seed_application()
    _approve(application_id)
    token = _read_token(application_id)
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/activation/complete",
            json={"token": token, "password": "ActivateMe123!"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["email"].lower() == email.lower()
    assert body["user"]["role"] == "engineer_partner"
    assert "/partner-engineer?action=subscribe" in body["next_url"]
    # User exists in DB and is auto-linked to the partner row.
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    u = db.users.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}}, {"_id": 0})
    assert u and u.get("is_partner_engineer") is True
    p = db.partner_engineers.find_one({"email": email}, {"_id": 0})
    assert p and p["user_id"] == u["id"]
    # Token consumed.
    app = db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    assert app["activation_completed_at"] is not None


def test_activation_complete_token_cannot_be_replayed():
    application_id, _ = _seed_application()
    _approve(application_id)
    token = _read_token(application_id)
    with httpx.Client(timeout=30.0) as c:
        first = c.post(
            f"{BASE}/api/partners/activation/complete",
            json={"token": token, "password": "ActivateMe123!"},
        )
        assert first.status_code == 200
        second = c.post(
            f"{BASE}/api/partners/activation/complete",
            json={"token": token, "password": "AnotherPwd456!"},
        )
    assert second.status_code == 404


def test_activation_complete_rejects_short_password():
    application_id, _ = _seed_application()
    _approve(application_id)
    token = _read_token(application_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/activation/complete",
            json={"token": token, "password": "short"},
        )
    assert r.status_code == 400
    # Token must still be valid for a retry with a longer password.
    with httpx.Client(timeout=15.0) as c:
        r2 = c.post(f"{BASE}/api/partners/activation/info", json={"token": token})
    assert r2.status_code == 200


def test_activation_complete_409_when_user_already_exists():
    """If somebody registered with the same email elsewhere, the
    activation endpoint must refuse to silently overwrite their
    password and redirect them to /login."""
    # Pre-create a user with the email we'll then apply with.
    email = f"iter219f-pre-{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(timeout=15.0) as c:
        reg = c.post(
            f"{BASE}/api/auth/register",
            json={"email": email, "password": "OriginalPwd123!", "full_name": "Existing User"},
            headers=_bypass_headers(),
        )
        assert reg.status_code == 200, reg.text
    application_id, _ = _seed_application(email=email)
    _approve(application_id)
    token = _read_token(application_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/activation/complete",
            json={"token": token, "password": "BrandNew123!"},
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "sign in" in detail.lower()


def test_activation_info_flags_existing_account():
    email = f"iter219f-exists-{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(timeout=15.0) as c:
        c.post(
            f"{BASE}/api/auth/register",
            json={"email": email, "password": "OriginalPwd123!", "full_name": "X"},
            headers=_bypass_headers(),
        )
    application_id, _ = _seed_application(email=email)
    _approve(application_id)
    token = _read_token(application_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/partners/activation/info", json={"token": token})
    assert r.status_code == 200
    assert r.json()["has_existing_account"] is True


# ─────────────────── Email body shape ───────────────────


def test_approval_email_uses_activation_url_when_token_provided():
    """Pin the email helper — when called with `activation_token` the
    CTA URL must include /partner-engineer/activate?token=..."""
    import asyncio
    from unittest.mock import AsyncMock, patch
    from utils.partner_emails import send_application_approved
    with patch("utils.partner_emails.send_email", AsyncMock(return_value=True)) as send:
        asyncio.run(send_application_approved(
            email="x@y.com", full_name="X Y", referral_code="ABC123",
            activation_token="THISISTHEACTIVATIONTOKEN",
        ))
    body = send.await_args.kwargs["html"]
    subject = send.await_args.kwargs["subject"]
    assert "/partner-engineer/activate?token=THISISTHEACTIVATIONTOKEN" in body
    assert "1 min" in subject.lower() or "set up" in subject.lower()


# Quiet pytest about unused import in some lint configs.
_ = pytest
