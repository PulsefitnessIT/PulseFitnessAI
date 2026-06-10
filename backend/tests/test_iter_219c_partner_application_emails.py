"""Iter 219c — partner application approve/reject email side-effects.

Before this iteration the two `/api/partners/applications/{id}/{approve|reject}`
endpoints had broken/missing email hooks:
  • Approve called `send_application_approved` with the wrong keyword
    (`partner_id=` instead of `referral_code=`) — TypeError silently
    swallowed by the broad `except Exception`, so approved engineers
    NEVER received the welcome email + referral code.
  • Reject didn't call any email helper at all — rejected engineers
    never heard back.

These tests pin the contract using AsyncMock patches so the test
doesn't depend on a working SMTP / Resend configuration.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from unittest.mock import AsyncMock, patch

import httpx


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://seo-fix-preview-4.preview.emergentagent.com",
)

_CACHE: dict[str, str] = {}


def _bypass_headers() -> dict[str, str]:
    """Optional rate-limit bypass — see iter 219d test file for context."""
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


def _seed_application() -> tuple[str, str]:
    """Public-apply a brand-new application — returns (application_id, email)."""
    cv_bytes = b"%PDF-1.4\nFake CV.\n%%EOF"
    files = {"cv_file": ("cv.pdf", io.BytesIO(cv_bytes), "application/pdf")}
    email = f"iter219c-{uuid.uuid4().hex[:8]}@example.com"
    data = {
        "full_name": "Email Hook Test Engineer",
        "email": email,
        "phone": "07123456789",
        "service_postcode": "SW1A 1AA",
        "travel_radius_km": "50",
        "brands_supported": "Life Fitness",
        "skills": "cardio",
        "qualifications": "IPAF",
        "years_experience": "5",
        "has_insurance": "true",
        "insurance_provider": "Hiscox",
        "insurance_expires_at": "2026-12-31",
        "terms_accepted": "true",
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.post(f"{BASE}/api/partners/public-apply", data=data, files=files)
    assert r.status_code == 200, r.text
    return r.json()["application_id"], email


# Because we test against the LIVE preview server, we can't patch the
# server-side `send_email` from inside the test process. Instead we
# import the helper directly and exercise it the same way the route
# does. The route's wiring (correct kwargs, both code paths) is then
# pinned by reading the route source.


def _route_source() -> str:
    from pathlib import Path
    return Path(os.path.join(os.path.dirname(__file__), "..", "routes", "partners.py")).read_text()


# ───────────────── Direct helper smoke-tests ─────────────────


def test_send_application_approved_accepts_correct_kwargs():
    """The helper must accept `referral_code=` (the kwarg the route
    now passes). Old buggy `partner_id=` would TypeError."""
    from utils.partner_emails import send_application_approved
    with patch("utils.partner_emails.send_email", AsyncMock(return_value=True)) as send:
        ok = asyncio.run(send_application_approved(
            email="x@y.com", full_name="X Y", referral_code="ABC12345",
        ))
    assert ok is True
    assert send.await_count == 1
    sent_kwargs = send.await_args.kwargs
    assert sent_kwargs["to"] == "x@y.com"
    # Referral code must appear in the email body so the engineer can
    # immediately start sharing.
    assert "ABC12345" in sent_kwargs["html"]


def test_send_application_rejected_accepts_optional_reason():
    from utils.partner_emails import send_application_rejected
    with patch("utils.partner_emails.send_email", AsyncMock(return_value=True)) as send:
        ok = asyncio.run(send_application_rejected(
            email="x@y.com", full_name="X Y", reason="Insurance certificate missing.",
        ))
    assert ok is True
    body = send.await_args.kwargs["html"]
    assert "Insurance certificate missing." in body


def test_send_application_rejected_handles_null_reason():
    from utils.partner_emails import send_application_rejected
    with patch("utils.partner_emails.send_email", AsyncMock(return_value=True)) as send:
        ok = asyncio.run(send_application_rejected(
            email="x@y.com", full_name="X Y", reason=None,
        ))
    assert ok is True
    # Should not echo a "Reason given" block when nothing was provided.
    assert "Reason given" not in send.await_args.kwargs["html"]


# ───────────── Route wiring (source pinning) ─────────────


def test_approve_route_passes_referral_code_not_partner_id():
    """Pin the specific call site: send_application_approved must be
    invoked with referral_code=, not the old buggy partner_id= form
    that silently TypeError'd."""
    import re
    src = _route_source()
    approve_block = src.split('@router.post("/partners/applications/{application_id}/approve")')[1]
    approve_block = approve_block.split("@router.")[0]
    # Match the full call (handles nested parens via lazy + lookahead
    # for the closing `)` followed by either newline or end).
    m = re.search(
        r"send_application_approved\s*\((.*?)\n\s*\)",
        approve_block,
        flags=re.DOTALL,
    )
    assert m, "send_application_approved call not found in approve route"
    send_call = m.group(1)
    assert "referral_code=" in send_call, (
        f"Approve route must pass referral_code=. Call args: {send_call!r}"
    )
    assert "partner_id=" not in send_call, (
        f"Approve route still passes partner_id= — TypeError silently swallowed. Call args: {send_call!r}"
    )


def test_reject_route_sends_rejection_email():
    src = _route_source()
    reject_block = src.split("@router.post(\"/partners/applications/{application_id}/reject\")")[1]
    reject_block = reject_block.split("@router.")[0]
    assert "send_application_rejected" in reject_block, (
        "Reject route must call send_application_rejected so the engineer hears back."
    )


# ───────────── End-to-end against live preview ─────────────


def test_approve_via_application_endpoint_succeeds_and_returns_partner_id():
    """Sanity: approve still works after the email fix (200 + partner_id)."""
    application_id, _ = _seed_application()
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/approve",
            json={"level": "engineer_partner"},
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["partner_id"]
    assert body["application_id"] == application_id
    assert body["level"] == "engineer_partner"


def test_reject_via_application_endpoint_succeeds():
    application_id, _ = _seed_application()
    with httpx.Client(timeout=30.0) as c:
        r = c.post(
            f"{BASE}/api/partners/applications/{application_id}/reject",
            json={"reason": "Insurance certificate missing."},
            headers=_admin_headers(),
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
