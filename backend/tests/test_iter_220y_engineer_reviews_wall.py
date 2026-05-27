"""Iter 220y — Public Wall of Reviews at /api/engineers/{slug}/reviews.

Pins:
  * Slug helper produces stable, hyphenated, name-derived strings.
  * ``_ensure_partner_public_slug`` is idempotent — second call returns
    the same slug it minted on the first call.
  * Endpoint resolves by ``public_slug`` (primary), partner ``id``
    (legacy share links), and an unambiguous name-based fallback.
  * Returns the 1★–5★ rating distribution alongside the existing
    summary stats.
  * Never leaks PII (``reviewer_email`` / ``ip_hash``) in the response.
  * Approved-status filter: only approved partners + approved reviews.
  * Engineer responses appear inline when present.
  * Unknown slug → 404.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import requests

from tests.conftest import _test_backend_url

BASE = _test_backend_url()


def _run(coro):
    """Drive ``coro`` on a fresh loop. Each test owns its own loop so
    motor lifecycle never bleeds across tests (Iter 220x pattern)."""
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
        "status": "approved",
        "full_name": "Sarah Patel",
        "company_name": "Patel Engineering Services",
        "level": "gold",
        "approved_at": "2026-01-15T10:00:00+00:00",
        "created_at": "2026-01-10T10:00:00+00:00",
        "availability": {"status": "available"},
    }
    base.update(overrides)
    return base


def _review(rating: int, **overrides) -> dict:
    base = {
        "id": f"rev-{uuid.uuid4().hex[:8]}",
        "partner_id": "partner-1",
        "status": "approved",
        "rating": rating,
        "title": "Quick and clean",
        "body": "Top job, would book again.",
        "reviewer_name": "Lee Somers",
        "gym_name": "CrossFit Soho",
        "reviewer_email": "lee@example.com",  # MUST NOT leak
        "ip_hash": "abc123",                  # MUST NOT leak
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# ─── Slug helper ─────────────────────────────────────────────────

def test_slugify_partner_name_basic():
    from routes.partners import _slugify_partner_name
    assert _slugify_partner_name("Sarah Patel") == "sarah-patel"
    assert _slugify_partner_name("  Jane O'Hara  ") == "jane-o-hara"
    assert _slugify_partner_name("Anne-Marie") == "anne-marie"


def test_slugify_partner_name_punctuation_and_emoji():
    from routes.partners import _slugify_partner_name
    assert _slugify_partner_name("João Silva 🔧") == "jo-o-silva"
    assert _slugify_partner_name("") == "engineer"
    assert _slugify_partner_name(None) == "engineer"


# ─── _ensure_partner_public_slug is idempotent ──────────────────

def test_ensure_partner_public_slug_returns_existing_when_set():
    from routes import partners

    partner = _approved_partner(public_slug="sarah-patel-aaaa")
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    fake_db.partner_engineers.update_one = AsyncMock()

    with patch.object(partners, "db", fake_db):
        slug = _run(partners._ensure_partner_public_slug(partner))
    assert slug == "sarah-patel-aaaa"
    # No collision check / update needed when the slug already exists.
    fake_db.partner_engineers.find_one.assert_not_called()
    fake_db.partner_engineers.update_one.assert_not_called()


def test_ensure_partner_public_slug_mints_when_missing():
    from routes import partners

    partner = _approved_partner()
    fake_db = MagicMock()
    # No collision on first candidate.
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    fake_db.partner_engineers.update_one = AsyncMock()

    with patch.object(partners, "db", fake_db):
        slug = _run(partners._ensure_partner_public_slug(partner))
    assert slug.startswith("sarah-patel-"), slug
    # 4-hex disambiguator (secrets.token_hex(2) → 4 chars).
    assert len(slug.split("-")[-1]) == 4
    fake_db.partner_engineers.update_one.assert_called_once()


def test_ensure_partner_public_slug_retries_on_collision():
    from routes import partners

    partner = _approved_partner()
    fake_db = MagicMock()
    # First candidate collides, second is free.
    fake_db.partner_engineers.find_one = AsyncMock(
        side_effect=[{"id": "other-partner"}, None],
    )
    fake_db.partner_engineers.update_one = AsyncMock()

    with patch.object(partners, "db", fake_db):
        slug = _run(partners._ensure_partner_public_slug(partner))
    assert slug.startswith("sarah-patel-")
    assert fake_db.partner_engineers.find_one.call_count == 2


# ─── Public Wall endpoint — happy path ─────────────────────────────

def test_public_wall_resolves_by_slug_and_returns_distribution():
    from routes import partners

    partner = _approved_partner(public_slug="sarah-patel-aaaa")
    reviews = [
        _review(5), _review(5), _review(5), _review(4), _review(3),
    ]
    fake_db = MagicMock()
    # First find_one call → resolves slug → partner. Second call (inside
    # _ensure_partner_public_slug) returns short-circuit because the
    # partner already has a public_slug.
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_engineers.update_one = AsyncMock()
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor(reviews))

    with patch.object(partners, "db", fake_db):
        out = _run(partners.public_engineer_reviews_wall("sarah-patel-aaaa", 50))

    assert out["partner"]["id"] == "partner-1"
    assert out["partner"]["public_slug"] == "sarah-patel-aaaa"
    assert out["partner"]["full_name"] == "Sarah Patel"
    assert out["partner"]["first_name"] == "Sarah"
    assert out["summary"]["count"] == 5
    assert out["summary"]["average"] == round((5 + 5 + 5 + 4 + 3) / 5, 2)
    assert out["distribution"] == {"1": 0, "2": 0, "3": 1, "4": 1, "5": 3}
    assert len(out["reviews"]) == 5
    # PII MUST NEVER leak in the public payload.
    for r in out["reviews"]:
        assert "reviewer_email" not in r
        assert "ip_hash" not in r


def test_public_wall_returns_zero_distribution_when_no_reviews():
    from routes import partners

    partner = _approved_partner(public_slug="quiet-engineer-bbbb")
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_engineers.update_one = AsyncMock()
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(partners, "db", fake_db):
        out = _run(partners.public_engineer_reviews_wall("quiet-engineer-bbbb", 50))

    assert out["summary"]["count"] == 0
    assert out["summary"]["average"] is None
    assert out["distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    assert out["reviews"] == []


def test_public_wall_engineer_response_is_passed_through():
    from routes import partners

    partner = _approved_partner(public_slug="responsive-cccc")
    with_response = _review(5, engineer_response="Thanks Lee, glad we got you back up!",
                             engineer_response_at="2026-02-01T09:00:00+00:00")
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_engineers.update_one = AsyncMock()
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor([with_response]))

    with patch.object(partners, "db", fake_db):
        out = _run(partners.public_engineer_reviews_wall("responsive-cccc", 50))

    assert out["reviews"][0]["engineer_response"] == \
        "Thanks Lee, glad we got you back up!"


# ─── Fallbacks ──────────────────────────────────────────────────

def test_public_wall_fallback_to_uuid_id_when_slug_unmapped():
    """Legacy share links use the partner UUID, not a slug."""
    from routes import partners

    partner = _approved_partner(id="abc-uuid-xyz")  # no public_slug
    fake_db = MagicMock()
    # 1) slug lookup → None. 2) UUID lookup → hit. 3+) slug-collision
    # checks inside _ensure_partner_public_slug → None.
    fake_db.partner_engineers.find_one = AsyncMock(
        side_effect=[None, partner, None, None, None, None, None, None, None, None],
    )
    fake_db.partner_engineers.update_one = AsyncMock()
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(partners, "db", fake_db):
        out = _run(partners.public_engineer_reviews_wall("abc-uuid-xyz", 50))

    assert out["partner"]["id"] == "abc-uuid-xyz"
    # A slug was minted during the resolve.
    assert out["partner"]["public_slug"].startswith("sarah-patel-")


def test_public_wall_404_on_unknown_slug():
    from fastapi import HTTPException
    from routes import partners

    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    fake_db.partner_engineers.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(partners, "db", fake_db):
        try:
            _run(partners.public_engineer_reviews_wall("does-not-exist", 50))
            raised = False
        except HTTPException as exc:
            raised = True
            assert exc.status_code == 404
    assert raised, "expected HTTPException(404)"


def test_public_wall_404_when_partner_not_approved():
    """Pending / rejected partners must NOT have a public wall."""
    from fastapi import HTTPException
    from routes import partners

    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    fake_db.partner_engineers.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(partners, "db", fake_db):
        try:
            _run(partners.public_engineer_reviews_wall("pending-engineer", 50))
            raised = False
        except HTTPException as exc:
            raised = True
            assert exc.status_code == 404
    assert raised


# ─── Live API smoke ─────────────────────────────────────────────

def test_public_wall_endpoint_returns_404_for_unknown_slug_live():
    r = requests.get(
        f"{BASE}/api/engineers/this-engineer-definitely-does-not-exist-xyz/reviews",
        timeout=10,
    )
    assert r.status_code == 404


def test_public_wall_endpoint_is_unauthenticated_live():
    """No Authorization header → still resolves (or 404s) without 401."""
    r = requests.get(
        f"{BASE}/api/engineers/another-unknown-slug-abc/reviews",
        timeout=10,
    )
    assert r.status_code in (200, 404), r.status_code
