"""Iter 220ca — Trial-signup competitor blocklist.

Two layers of coverage:

  1. ``utils.competitor_blocklist`` rule-engine — case-insensitive,
     suffix-aware, handles malformed input gracefully.
  2. ``POST /api/auth/register`` rejects ``is_trial=True`` signups
     from a blocked domain (with a friendly "email sales" message)
     while still accepting regular non-trial registrations from the
     same domain (so the CRM team can invite a competitor's
     employee as a B2B contact — that's a different code path that
     never sets ``is_trial``).
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ══════════════════ 1 · Rule engine ══════════════════════════════════


def test_is_competitor_email_user_named_domains():
    """The two domains the CEO specifically called out must match."""
    from utils.competitor_blocklist import is_competitor_email
    assert is_competitor_email("ceo@orbit4.com")
    assert is_competitor_email("ceo@orbit4.co.uk")
    assert is_competitor_email("anyone@servicesport.co.uk")


@pytest.mark.parametrize("email", [
    "anyone@trainerize.com",
    "team@mindbodyonline.com",
    "ops@perfectgym.com",
    "billing@glofox.com",
    "ceo@abcfitness.com",
    "x@gymmaster.com",
    "uk@xplor.com",
    "hi@xplortechnologies.com",
    "info@clubright.co.uk",
    "support@wellnessliving.com",
    "ceo@mywellness.com",
    "anyone@technogym.com",
])
def test_is_competitor_email_known_competitors(email):
    from utils.competitor_blocklist import is_competitor_email
    assert is_competitor_email(email), f"{email} should be blocked"


def test_is_competitor_email_subdomain_walk():
    """Sub-domains of a blocked apex must also be blocked — a
    competitor spinning up ``newsletter.orbit4.com`` and registering
    against it shouldn't slip through."""
    from utils.competitor_blocklist import is_competitor_email
    assert is_competitor_email("test@newsletter.orbit4.com")
    assert is_competitor_email("nested@uk.team.orbit4.com")


def test_is_competitor_email_case_insensitive_and_whitespace():
    from utils.competitor_blocklist import is_competitor_email
    assert is_competitor_email("  CEO@ORBIT4.COM  ")
    assert is_competitor_email("Anyone@MindBody.io")


def test_is_competitor_email_clean_emails_pass_through():
    """Real-customer addresses must NOT be flagged. The matcher is
    suffix-aware, not prefix-aware — ``orbit4-fans.com`` is not
    Orbit 4."""
    from utils.competitor_blocklist import is_competitor_email
    assert not is_competitor_email("jane@my-real-gym.com")
    assert not is_competitor_email("ceo@orbit4-fans.com")        # prefix
    assert not is_competitor_email("billing@gymaxisai.com")      # us!
    assert not is_competitor_email("anyone@trainerize-clone.io")  # prefix


def test_is_competitor_email_malformed_inputs_dont_crash():
    """Empty / missing @ / weird input must return False, never raise."""
    from utils.competitor_blocklist import is_competitor_email
    assert not is_competitor_email("")
    assert not is_competitor_email("just-text")


def test_competitor_block_reason_present_for_blocked_only():
    from utils.competitor_blocklist import competitor_block_reason
    assert "sales@gymaxisai.com" in (competitor_block_reason("ceo@orbit4.com") or "")
    assert competitor_block_reason("jane@my-real-gym.com") is None


def test_blocked_domains_snapshot_contains_user_named():
    """The Master Admin status panel reads ``blocked_domains()`` —
    make sure the two CEO-named entries are visible."""
    from utils.competitor_blocklist import blocked_domains
    snap = blocked_domains()
    assert "orbit4.com" in snap
    assert "servicesport.co.uk" in snap
    # Sorted output — important so the panel renders deterministically.
    assert snap == sorted(snap)


# ══════════════════ 2 · /auth/register integration ═══════════════════


def _build_trial_payload(email: str):
    """Minimal valid UserRegister payload that triggers the trial path."""
    from models.schemas import UserRegister
    return UserRegister(
        email=email,
        password="ValidPassword!2026",
        full_name="Test Operator",
        company_name="Test Gym",
        phone="+447700900000",
        is_trial=True,
        trial_duration_days=3,
        cf_turnstile_response="bypass-token",
    )


def _patched_auth_module():
    """Patch the auth route module so the test never touches the
    real DB / Turnstile / Resend."""
    from routes import auth as route
    fake_db = MagicMock()
    fake_db.users.find_one = AsyncMock(return_value=None)
    fake_db.users.insert_one = AsyncMock()
    fake_db.organizations.find_one = AsyncMock(return_value={"id": "org-x", "name": "Test Gym"})
    return route, fake_db


def _fake_request(ip: str = "1.2.3.4"):
    req = MagicMock()
    req.client = MagicMock(host=ip)
    req.headers = {}
    return req


def test_register_blocks_trial_signup_from_competitor_domain():
    route, fake_db = _patched_auth_module()
    payload = _build_trial_payload(f"ceo+{uuid.uuid4().hex[:6]}@orbit4.com")
    fake_resp = MagicMock()

    async def go():
        with patch.object(route, "db", fake_db), \
             patch("utils.captcha.verify_captcha", AsyncMock(return_value=None)), \
             patch("utils.security.rate_limit", lambda *_a, **_kw: None):
            return await route.register(payload, _fake_request(), fake_resp)

    with pytest.raises(HTTPException) as exc:
        _run(go())
    assert exc.value.status_code == 400
    assert "sales@gymaxisai.com" in exc.value.detail
    # CRITICAL: we must NOT have inserted a user row for a blocked
    # signup. A future iter could reuse the email for legitimate
    # outreach (sales conversation) and we don't want a phantom row
    # to collide.
    fake_db.users.insert_one.assert_not_called()


def test_register_blocks_servicesport_subdomain():
    route, fake_db = _patched_auth_module()
    payload = _build_trial_payload("ops@uk.servicesport.co.uk")
    fake_resp = MagicMock()

    async def go():
        with patch.object(route, "db", fake_db), \
             patch("utils.captcha.verify_captcha", AsyncMock(return_value=None)), \
             patch("utils.security.rate_limit", lambda *_a, **_kw: None):
            return await route.register(payload, _fake_request(), fake_resp)

    with pytest.raises(HTTPException) as exc:
        _run(go())
    assert exc.value.status_code == 400


def test_register_allows_non_trial_signup_from_competitor_domain():
    """If a CRM admin invites a competitor employee as a contact —
    that's a *non-trial* registration. The blocklist must NOT fire
    on the non-trial path."""
    route, fake_db = _patched_auth_module()
    from models.schemas import UserRegister
    payload = UserRegister(
        email="invited@orbit4.com",
        password="ValidPassword!2026",
        full_name="Invited Contact",
        company_name="Orbit 4",
        is_trial=False,  # KEY — non-trial path
    )
    fake_resp = MagicMock()

    async def go():
        with patch.object(route, "db", fake_db), \
             patch.object(route, "_resolve_org_and_role",
                          AsyncMock(return_value=("org-x", "owner"))), \
             patch.object(route, "hash_password", lambda _p: "hashed"), \
             patch.object(route, "validate_password_strength", lambda _p: None), \
             patch.object(route, "sanitise_string", lambda s: s), \
             patch.object(route, "send_welcome_email", AsyncMock(return_value=None)), \
             patch("utils.security.rate_limit", lambda *_a, **_kw: None), \
             patch("utils.lifecycle_emails.send_welcome_now", AsyncMock(return_value=None)):
            return await route.register(payload, _fake_request(), fake_resp)

    out = _run(go())
    assert out.get("token") or out.get("user")
    fake_db.users.insert_one.assert_awaited_once()


def test_register_allows_clean_email_for_trial():
    route, fake_db = _patched_auth_module()
    payload = _build_trial_payload("clean@my-real-gym.com")
    fake_resp = MagicMock()

    async def go():
        with patch.object(route, "db", fake_db), \
             patch.object(route, "_resolve_org_and_role",
                          AsyncMock(return_value=("org-x", "owner"))), \
             patch.object(route, "hash_password", lambda _p: "hashed"), \
             patch.object(route, "validate_password_strength", lambda _p: None), \
             patch.object(route, "sanitise_string", lambda s: s), \
             patch.object(route, "send_welcome_email", AsyncMock(return_value=None)), \
             patch("utils.captcha.verify_captcha", AsyncMock(return_value=None)), \
             patch("utils.security.rate_limit", lambda *_a, **_kw: None), \
             patch("utils.lifecycle_emails.send_welcome_now", AsyncMock(return_value=None)), \
             patch("utils.email.send_trial_signup_notification", AsyncMock(return_value=None)):
            return await route.register(payload, _fake_request(), fake_resp)

    out = _run(go())
    assert out.get("token") or out.get("user")
    fake_db.users.insert_one.assert_awaited_once()
