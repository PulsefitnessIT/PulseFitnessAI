"""Iter 216h192 — regression coverage for the 4 production fixes
reported by Lee on 18 May 2026 against gymaxisai.com:

1. Password-reset URL uses brand-aware ``app_url_for_org`` so production
   emails point at gymaxisai.com / pulsefitness.ai rather than the
   preview URL (which was the cause of "Invalid Reset Link").
2. Marketing entitlement heals stale ``trial`` subs for paid platform
   plans so the misleading "Free trial" pill disappears.
3. brand_urls defaults switched to the apex production domains.

These are pure unit tests against the helpers — no FastAPI client needed.
"""
from __future__ import annotations

import asyncio
import os
import re
from unittest.mock import AsyncMock, patch

from utils.brand_urls import app_url_for, app_url_for_org


def test_brand_urls_default_to_apex_domains() -> None:
    """Production defaults must hit gymaxisai.com / pulsefitness.ai apex."""
    # Clear env overrides so we hit the defaults.
    for k in ("BRAND_URL_GYMAXIS", "BRAND_URL_PULSE", "FRONTEND_URL"):
        os.environ.pop(k, None)

    assert app_url_for("gymaxis") == "https://gymaxisai.com"
    assert app_url_for("full") == "https://gymaxisai.com"
    assert app_url_for("lite") == "https://gymaxisai.com"
    assert app_url_for(None) == "https://gymaxisai.com"
    assert app_url_for("pulse") == "https://pulsefitness.ai"
    assert app_url_for("pulse_pro") == "https://pulsefitness.ai"


def test_brand_urls_env_overrides_still_win() -> None:
    """Per-brand overrides keep priority over the new apex defaults."""
    os.environ["BRAND_URL_GYMAXIS"] = "https://staging.gymaxisai.com"
    os.environ["BRAND_URL_PULSE"] = "https://staging.pulsefitness.ai"
    try:
        assert app_url_for("gymaxis") == "https://staging.gymaxisai.com"
        assert app_url_for("pulse_pro") == "https://staging.pulsefitness.ai"
    finally:
        os.environ.pop("BRAND_URL_GYMAXIS", None)
        os.environ.pop("BRAND_URL_PULSE", None)


def test_app_url_for_org_handles_missing_org() -> None:
    """``None`` org should fall back to the GymAxis default."""
    for k in ("BRAND_URL_GYMAXIS", "BRAND_URL_PULSE", "FRONTEND_URL"):
        os.environ.pop(k, None)
    assert app_url_for_org(None) == "https://gymaxisai.com"
    assert app_url_for_org({}) == "https://gymaxisai.com"
    assert app_url_for_org({"account_type": "pulse_pro"}) == "https://pulsefitness.ai"


def test_reset_password_link_uses_brand_url() -> None:
    """The reset URL embedded in the email must use the brand-aware host."""
    for k in ("BRAND_URL_GYMAXIS", "BRAND_URL_PULSE", "FRONTEND_URL"):
        os.environ.pop(k, None)

    org = {"account_type": "pulse_pro"}
    base = app_url_for_org(org)
    reset_url = f"{base}/reset-password?token=ABC"
    assert re.match(r"^https://pulsefitness\.ai/reset-password\?token=", reset_url)

    org = {"account_type": "full"}
    base = app_url_for_org(org)
    reset_url = f"{base}/reset-password?token=XYZ"
    assert re.match(r"^https://gymaxisai\.com/reset-password\?token=", reset_url)


def test_marketing_sub_heals_trial_for_paid_platform_plan() -> None:
    """An existing ``trial`` marketing sub on a Pulse Pro org must be
    healed to ``active`` when the entitlement is next requested."""
    from routes.marketing import helpers as mh
    from unittest.mock import MagicMock

    org_id = "org-pulse-pro-1"
    existing_sub = {
        "organization_id": org_id, "plan_id": "pro",
        "status": "trial",
        "trial_ends_at": "2026-01-01T00:00:00+00:00",
        "usage_this_period": {},
    }
    org_doc = {"id": org_id, "account_type": "pulse_pro"}

    update_calls = []

    fake_subs = MagicMock()
    fake_subs.find_one = AsyncMock(return_value=dict(existing_sub))
    async def _update(query, update):
        update_calls.append((query, update))
    fake_subs.update_one = AsyncMock(side_effect=_update)

    fake_orgs = MagicMock()
    fake_orgs.find_one = AsyncMock(return_value=org_doc)

    fake_db = MagicMock()
    fake_db.marketing_subscriptions = fake_subs
    fake_db.organizations = fake_orgs

    with patch.object(mh, "db", fake_db):
        sub = asyncio.get_event_loop().run_until_complete(mh._get_org_subscription(org_id))

    assert sub["status"] == "active"
    assert sub["comp_seats"] is True
    assert sub["trial_ends_at"] is None
    assert update_calls, "expected an update_one call to persist the heal"
    set_clause = update_calls[0][1]["$set"]
    assert set_clause["status"] == "active"
    assert set_clause["healed_reason"] == "bundled_with_platform_plan"


def test_marketing_sub_keeps_trial_for_free_orgs() -> None:
    """Orgs without a paid platform plan must still see status=trial."""
    from routes.marketing import helpers as mh
    from unittest.mock import MagicMock

    org_id = "org-free-1"
    existing_sub = {
        "organization_id": org_id, "plan_id": "pro",
        "status": "trial",
        "trial_ends_at": "2099-01-01T00:00:00+00:00",
    }
    org_doc = {"id": org_id, "account_type": "free"}

    fake_subs = MagicMock()
    fake_subs.find_one = AsyncMock(return_value=dict(existing_sub))
    async def _update(*_a, **_k):
        raise AssertionError("free orgs must NOT be healed")
    fake_subs.update_one = AsyncMock(side_effect=_update)

    fake_orgs = MagicMock()
    fake_orgs.find_one = AsyncMock(return_value=org_doc)

    fake_db = MagicMock()
    fake_db.marketing_subscriptions = fake_subs
    fake_db.organizations = fake_orgs

    with patch.object(mh, "db", fake_db):
        sub = asyncio.get_event_loop().run_until_complete(mh._get_org_subscription(org_id))

    assert sub["status"] == "trial"
