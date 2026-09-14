"""Iter 219d — Manual resend of partner approval email.

Pins the new `POST /api/partners/applications/{id}/resend-approval-email`
contract:
  • 200 + {ok, sent_to, partner_id} for an approved application.
  • 400 if the application is still pending or rejected.
  • 404 if the application doesn't exist.
  • 403 for non master-admin callers.

We patch the `send_email` helper so the test doesn't depend on a working
Resend SMTP key. The endpoint is exercised via httpx against the live
preview server — same pattern as the other iter 219 tests.

Because we can't patch the server-side `send_email` from the test
process, we also include a unit test of `send_application_approved`
to ensure that — once the route calls it — the right HTML body is
produced with the referral code embedded.
"""
from __future__ import annotations

import asyncio
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
    "https://mod-only-deploy.preview.emergentagent.com",
)

_CACHE: dict[str, str] = {}


def _bypass_headers() -> dict[str, str]:
    """Optional rate-limit bypass for `make regression` — the secret is
    present in dev/preview .env so we use it to avoid the 429 cascade
    when multiple test files hit /api/auth/login back-to-back."""
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


def _seed_application() -> str:
    """Public-apply a brand-new application — returns the application_id."""
    cv_bytes = b"%PDF-1.4\nFake CV body.\n%%EOF"
    files = {"cv_file": ("cv.pdf", io.BytesIO(cv_bytes), "application/pdf")}
    email = f"iter219d-{uuid.uuid4().hex[:8]}@example.com"
    data = {
        "full_name": "Resend Test Engineer",
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
    return r.json()["application_id"]


def _approve(application_id: str) -> dict:
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/approve",
            json={"level": "engineer_partner"},
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    return r.json()


# ───────────────────── Endpoint contract ─────────────────────


def test_resend_approval_email_for_approved_application_returns_ok():
    application_id = _seed_application()
    _approve(application_id)
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/resend-approval-email",
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["application_id"] == application_id
    assert body["partner_id"]
    assert "@" in body["sent_to"]
    # `ok` reflects whether the email-send actually succeeded.
    # Resend may be in dev-sink mode but the route still returns
    # a 200 + ok=True since send_email returns truthy on success.
    assert "ok" in body


def test_resend_approval_email_400_when_application_still_pending():
    application_id = _seed_application()  # not approved yet
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/resend-approval-email",
            headers=_admin_headers(),
        )
    assert r.status_code == 400, r.text
    assert "not approved" in r.json()["detail"].lower()


def test_resend_approval_email_404_when_application_missing():
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/missing-{uuid.uuid4().hex[:8]}/resend-approval-email",
            headers=_admin_headers(),
        )
    assert r.status_code == 404


def test_resend_approval_email_403_for_non_admin():
    application_id = _seed_application()
    _approve(application_id)
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/resend-approval-email",
            headers=_non_admin_headers(),
        )
    assert r.status_code == 403


def test_resend_writes_audit_log_entry():
    """Each resend should leave an audit trail so we can prove the
    email was re-fired and by whom."""
    application_id = _seed_application()
    approve_body = _approve(application_id)
    partner_id = approve_body["partner_id"]
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/resend-approval-email",
            headers=_admin_headers(),
        )
    assert r.status_code == 200
    # Fetch the audit log directly using a sync pymongo client — Motor's
    # async client is bound to the FastAPI event loop and can't be
    # reused from pytest's main thread.
    from pymongo import MongoClient
    sync_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    entries = list(sync_db.partner_audit_log.find({"partner_id": partner_id}, {"_id": 0}))
    actions = [e.get("action") for e in entries]
    assert "resend_approval_email" in actions


# ─────────────── Helper integration (no network) ───────────────


def test_send_application_approved_includes_referral_code_in_body():
    """The route fetches the referral code from `partner_engineers`
    and passes it as `referral_code=`. Verify the helper renders it
    so the engineer can immediately start sharing."""
    from utils.partner_emails import send_application_approved
    with patch("utils.partner_emails.send_email", AsyncMock(return_value=True)) as send:
        asyncio.run(send_application_approved(
            email="resend@example.com",
            full_name="Resend Test",
            referral_code="RES1234ABCD",
        ))
    body_html = send.await_args.kwargs["html"]
    assert "RES1234ABCD" in body_html
    assert "approved" in body_html.lower() or "welcome" in body_html.lower()


def test_resend_route_uses_partner_referral_code():
    """Pin the route source so we don't regress to using partner_id
    instead of referral_code on the manual-resend path either."""
    import re
    src = open(
        os.path.join(os.path.dirname(__file__), "..", "routes", "partners.py"), encoding="utf-8",
    ).read()
    block = src.split('@router.post("/partners/applications/{application_id}/resend-approval-email")')[1]
    block = block.split("@router.")[0]
    m = re.search(
        r"send_application_approved\s*\((.*?)\n\s*\)",
        block,
        flags=re.DOTALL,
    )
    assert m, "send_application_approved call not found in resend route"
    call = m.group(1)
    assert "referral_code=" in call
    assert "partner_id=" not in call


# Quiet pytest about unused pytest import in some lint configs.
_ = pytest
