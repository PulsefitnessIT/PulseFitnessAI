"""Iter 219g — Smart "Send sign-in link" endpoint.

One master-admin button that auto-routes between:
  • Activation email (welcome + set-password link) when the engineer
    hasn't activated yet — i.e. no user account exists for their email.
  • Password-reset email when the engineer already has an account but
    can't sign in.

Pins the contract via httpx against the live preview server.
"""
from __future__ import annotations

import io
import os
import sys
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://sicon-sync-hub.preview.emergentagent.com",
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


def _non_admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('engineer.smoke@gymaxisai.com', 'EngTest123!')}"}


def _seed_application(email: str | None = None) -> tuple[str, str]:
    cv_bytes = b"%PDF-1.4\nFake CV body.\n%%EOF"
    files = {"cv_file": ("cv.pdf", io.BytesIO(cv_bytes), "application/pdf")}
    email = email or f"iter219g-{uuid.uuid4().hex[:8]}@example.com"
    data = {
        "full_name": "Signin Link Test",
        "email": email,
        "phone": "07000000001",
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


# ─────────────────── Activation path (no user account) ───────────────────


def test_send_signin_link_sends_activation_when_user_does_not_exist():
    application_id, email = _seed_application()
    _approve(application_id)
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/send-signin-link",
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "activation"
    assert body["sent_to"].lower() == email.lower()
    # Activation token must now be present on the application row.
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    doc = db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    assert doc["activation_token"]


def test_send_signin_link_reissues_activation_token_when_expired():
    """Pre-existing engineers approved before iter 219f have no token.
    The endpoint must still mint one so they get a working link."""
    application_id, _ = _seed_application()
    _approve(application_id)
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    # Simulate "approved before iter 219f" — strip the token.
    db.partner_applications.update_one(
        {"id": application_id},
        {"$unset": {"activation_token": "", "activation_token_expires_at": ""}},
    )
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/send-signin-link",
            headers=_admin_headers(),
        )
    assert r.status_code == 200
    assert r.json()["kind"] == "activation"
    doc = db.partner_applications.find_one({"id": application_id}, {"_id": 0})
    assert doc["activation_token"]
    assert len(doc["activation_token"]) >= 32


# ─────────────────── Password reset path (user account exists) ───────────


def test_send_signin_link_sends_password_reset_when_user_exists():
    """If the engineer has already activated (or registered separately),
    we mint a real password_reset_tokens row and send the standard
    reset email instead — covers the "I had an account, can't sign in"
    case the operator reported."""
    email = f"iter219g-pwd-{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(timeout=15.0) as c:
        c.post(
            f"{BASE}/api/auth/register",
            json={"email": email, "password": "OriginalPwd123!", "full_name": "Existing"},
            headers=_bypass_headers(),
        )
    application_id, _ = _seed_application(email=email)
    _approve(application_id)
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/send-signin-link",
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "password_reset"
    assert body["sent_to"].lower() == email.lower()
    # A password_reset_tokens row must have been minted.
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    tokens = list(db.password_reset_tokens.find(
        {"email": {"$regex": f"^{email}$", "$options": "i"}, "used": False},
        {"_id": 0},
    ))
    assert tokens, "No password_reset_tokens row written"
    # Iter 230 — reset minting was extracted into the shared
    # `_mint_and_send_password_reset` helper, which stamps the
    # consolidated `admin_partner` source tag.
    assert tokens[-1].get("issued_via") == "admin_partner"


# ─────────────────── Boundary checks ───────────────────


def test_send_signin_link_400_when_pending():
    application_id, _ = _seed_application()
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/send-signin-link",
            headers=_admin_headers(),
        )
    assert r.status_code == 400


def test_send_signin_link_404_when_missing():
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/missing-{uuid.uuid4().hex[:8]}/send-signin-link",
            headers=_admin_headers(),
        )
    assert r.status_code == 404


def test_send_signin_link_403_for_non_admin():
    application_id, _ = _seed_application()
    _approve(application_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/send-signin-link",
            headers=_non_admin_headers(),
        )
    assert r.status_code == 403


# ─────────────────── Audit trail ───────────────────


def test_send_signin_link_writes_audit_entry_kind_specific():
    """Both paths leave an audit log entry tagged with the action,
    so we can prove which kind of email went out and by whom."""
    application_id, _ = _seed_application()
    approve = _approve(application_id)
    pid = approve["partner_id"]
    with httpx.Client(timeout=30.0) as c:
        c.post(
            f"{BASE}/api/partners/applications/{application_id}/send-signin-link",
            headers=_admin_headers(),
        )
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    actions = [e.get("action") for e in db.partner_audit_log.find({"partner_id": pid}, {"_id": 0})]
    assert "send_activation_link" in actions


# ─────────────────── Unit: brand URL helper used for reset ───────────────────


def test_password_reset_helper_called_via_send_signin_when_user_exists():
    """Verify the route source delegates to send_password_reset_email
    rather than the partner-specific welcome helper for the
    password-reset branch — pinning the wiring so a future refactor
    can't accidentally send the wrong email."""
    src_path = os.path.join(os.path.dirname(__file__), "..", "routes", "partners.py")
    src = open(src_path, encoding="utf-8").read()
    block = src.split('@router.post("/partners/applications/{application_id}/send-signin-link")')[1]
    block = block.split("@router.")[0]
    # Iter 230 — the reset branch was extracted into the shared
    # `_mint_and_send_password_reset` helper. Pin the delegation AND
    # that the helper itself still sends the standard reset email.
    assert "_mint_and_send_password_reset" in block, (
        "Password-reset branch must delegate to _mint_and_send_password_reset."
    )
    helper = src.split("async def _mint_and_send_password_reset")[1].split("\nasync def ")[0]
    assert "send_password_reset_email" in helper, (
        "_mint_and_send_password_reset must call send_password_reset_email."
    )
    assert "send_application_approved" in block, (
        "Activation branch must call send_application_approved."
    )


_ = pytest
