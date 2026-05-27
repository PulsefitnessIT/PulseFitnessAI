"""Iter 220z — Engineer "Share your wall" endpoint.

Pins:
  * Approved partner → returns ``public_slug`` + full ``public_url`` +
    summary stats + a ready-to-share LinkedIn caption.
  * Slug is minted on first call AND persisted (idempotent).
  * 404 when the caller has no partner record (haven't applied).
  * 403 when the partner application is still pending/rejected.
  * 401 when the caller is not authenticated.
  * Share text varies based on review count — neutral copy under 3
    reviews, star-count brag when ≥3.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import requests

from tests.conftest import _test_backend_url

BASE = _test_backend_url()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _approved_partner(**overrides) -> dict:
    base = {
        "id": "partner-1",
        "user_id": "user-1",
        "status": "approved",
        "full_name": "Sarah Patel",
        "company_name": "Patel Engineering Services",
        "level": "gold",
        "public_slug": "sarah-patel-aaaa",
    }
    base.update(overrides)
    return base


# ─── Happy path ──────────────────────────────────────────────────

def test_my_public_wall_returns_slug_url_and_stats():
    from routes import partners

    partner = _approved_partner()
    reviews = [{"rating": 5}, {"rating": 5}, {"rating": 4}, {"rating": 5}]
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_engineers.update_one = AsyncMock()
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor(reviews))

    user = {"id": "user-1"}
    with patch.object(partners, "db", fake_db), \
         patch.object(partners, "_get_partner_by_user",
                      AsyncMock(return_value=partner)), \
         patch.dict(os.environ, {"FRONTEND_URL": "https://app.gymaxis.ai"}, clear=False):
        out = _run(partners.my_public_wall(user))

    assert out["public_slug"] == "sarah-patel-aaaa"
    assert out["public_url"] == \
        "https://app.gymaxis.ai/engineers/sarah-patel-aaaa/reviews"
    assert out["summary"]["count"] == 4
    assert out["summary"]["average"] == 4.75
    # ≥3 reviews ⇒ brag copy
    assert "4 ★ reviews" in out["share_text"]
    assert "4.8/5" in out["share_text"]


def test_my_public_wall_share_text_falls_back_when_under_three_reviews():
    from routes import partners

    partner = _approved_partner()
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_engineers.update_one = AsyncMock()
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor([{"rating": 5}]))

    user = {"id": "user-1"}
    with patch.object(partners, "db", fake_db), \
         patch.object(partners, "_get_partner_by_user",
                      AsyncMock(return_value=partner)):
        out = _run(partners.my_public_wall(user))
    assert "verified GymAxis Partner Engineer" in out["share_text"]


def test_my_public_wall_mints_slug_when_missing():
    from routes import partners

    partner = _approved_partner(public_slug=None)
    fake_db = MagicMock()
    # Slug collision check inside _ensure_partner_public_slug → None.
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    fake_db.partner_engineers.update_one = AsyncMock()
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor([]))

    user = {"id": "user-1"}
    with patch.object(partners, "db", fake_db), \
         patch.object(partners, "_get_partner_by_user",
                      AsyncMock(return_value=partner)):
        out = _run(partners.my_public_wall(user))

    assert out["public_slug"].startswith("sarah-patel-")
    # update_one fired to persist the mint
    assert fake_db.partner_engineers.update_one.call_count >= 1


# ─── Gating ─────────────────────────────────────────────────────

def test_my_public_wall_404_when_not_a_partner():
    from fastapi import HTTPException
    from routes import partners

    user = {"id": "user-1"}
    with patch.object(partners, "_get_partner_by_user",
                      AsyncMock(return_value=None)):
        try:
            _run(partners.my_public_wall(user))
            raised = False
        except HTTPException as exc:
            raised = True
            assert exc.status_code == 404
    assert raised


def test_my_public_wall_403_when_pending():
    from fastapi import HTTPException
    from routes import partners

    partner = _approved_partner(status="pending", public_slug=None)
    user = {"id": "user-1"}
    with patch.object(partners, "_get_partner_by_user",
                      AsyncMock(return_value=partner)):
        try:
            _run(partners.my_public_wall(user))
            raised = False
        except HTTPException as exc:
            raised = True
            assert exc.status_code == 403
    assert raised


def test_my_public_wall_403_when_rejected():
    from fastapi import HTTPException
    from routes import partners

    partner = _approved_partner(status="rejected", public_slug=None)
    user = {"id": "user-1"}
    with patch.object(partners, "_get_partner_by_user",
                      AsyncMock(return_value=partner)):
        try:
            _run(partners.my_public_wall(user))
            raised = False
        except HTTPException as exc:
            raised = True
            assert exc.status_code == 403
    assert raised


# ─── Live API smoke ─────────────────────────────────────────────

def test_my_public_wall_endpoint_rejects_anonymous_live():
    """No Authorization header → 401/403, NEVER 200."""
    r = requests.get(f"{BASE}/api/partners/me/public-wall", timeout=10)
    assert r.status_code in (401, 403), r.status_code


def test_my_public_wall_endpoint_returns_404_for_non_partner_live():
    """A logged-in master admin who isn't a partner → 404."""
    from tests.conftest import MASTER_ADMIN_EMAIL, MASTER_ADMIN_PASSWORD
    auth = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
        timeout=10,
    )
    if auth.status_code != 200:
        return
    token = auth.json().get("token")
    if not token:
        return  # MFA path — skip
    r = requests.get(
        f"{BASE}/api/partners/me/public-wall",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert r.status_code in (404, 403), r.status_code
