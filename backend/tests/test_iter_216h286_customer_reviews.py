"""Iter 216h286 — Customer review submission flow (Gap 8).

Closes Gap 8 from the BA audit: the marketing landing page promised a
star-rating system that the platform didn't have. Now any gym contact
can submit a review on a partner engineer via a public endpoint.

Endpoints exercised:
  * POST /partners/{id}/reviews            — public submission
  * GET  /partners/{id}/reviews            — public list (approved only)
  * GET  /partners/me/reviews              — engineer's own view
  * POST /partners/me/reviews/{id}/respond — engineer response
  * POST /master-admin/partners/{id}/reviews/{rid}/moderate — admin approve/reject

Pins:
  * Validation on rating (1–5), name, body
  * Low-rating + keyword heuristic routes to pending; high-star
    "clean" reviews auto-approve
  * 24h cooldown per (partner, reviewer_email)
  * IP hash + reviewer_email + ip never leak in public list
  * Engineer respond endpoint requires ownership
  * Admin moderate flips status + audit-logs
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin():
    return {"id": "u-admin", "is_master_admin": True, "role": "owner"}


def _user():
    return {"id": "u-jane", "organization_id": "org-1"}


def _make_cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _request(ip: str = "1.2.3.4"):
    r = MagicMock()
    r.client.host = ip
    return r


# ── Moderation heuristic ──────────────────────────────────────────


def test_moderation_status_low_rating_pends():
    from routes.partners import _moderation_status
    assert _moderation_status(1, "ok") == "pending"
    assert _moderation_status(3, "ok") == "pending"
    assert _moderation_status(4, "great work") == "approved"
    assert _moderation_status(5, "amazing") == "approved"


def test_moderation_status_keyword_pends():
    from routes.partners import _moderation_status
    assert _moderation_status(5, "what a SCAM") == "pending"
    assert _moderation_status(5, "filed lawsuit against him") == "pending"


# ── Submit endpoint ───────────────────────────────────────────────


def test_submit_review_validates_rating():
    from routes.partners import submit_review
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "full_name": "Jane"})
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(submit_review("p1", body={"rating": 0, "reviewer_name": "X", "body": "y"}, request=_request()))
    assert "between 1 and 5" in str(exc.value.detail)


def test_submit_review_requires_name_and_body():
    from routes.partners import submit_review
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "full_name": "Jane"})
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(submit_review("p1", body={"rating": 5, "body": "y"}, request=_request()))
        assert "reviewer_name" in str(exc.value.detail)
        with pytest.raises(Exception) as exc2:
            _run(submit_review("p1", body={"rating": 5, "reviewer_name": "X"}, request=_request()))
        assert "review body" in str(exc2.value.detail)


def test_submit_review_high_star_auto_approves():
    from routes.partners import submit_review
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "full_name": "Jane"})
    fake_db.partner_reviews.find_one = AsyncMock(return_value=None)  # no dup
    captured = {}

    async def cap(doc):
        captured.update(doc)
    fake_db.partner_reviews.insert_one = AsyncMock(side_effect=cap)
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()):
        out = _run(submit_review(
            "p1",
            body={"rating": 5, "reviewer_name": "Tom", "reviewer_email": "tom@x", "body": "Engineer fixed the bike, brilliant"},
            request=_request(),
        ))
    assert out["status"] == "approved"
    assert captured["rating"] == 5
    assert captured["status"] == "approved"
    # Reviewer-email captured, IP hashed (not raw)
    assert captured["reviewer_email"] == "tom@x"
    assert "ip_hash" in captured
    assert captured["ip_hash"] != "1.2.3.4"


def test_submit_review_low_star_pends_for_moderation():
    from routes.partners import submit_review
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "full_name": "Jane"})
    fake_db.partner_reviews.find_one = AsyncMock(return_value=None)
    captured = {}
    fake_db.partner_reviews.insert_one = AsyncMock(side_effect=lambda d: captured.update(d))
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()):
        out = _run(submit_review(
            "p1",
            body={"rating": 2, "reviewer_name": "Tom", "body": "engineer ghosted me"},
            request=_request(),
        ))
    assert out["status"] == "pending"
    assert "team has reviewed" in out["message"]
    assert captured["status"] == "pending"


def test_submit_review_24h_cooldown_blocks_duplicate():
    from routes.partners import submit_review
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "full_name": "Jane"})
    fake_db.partner_reviews.find_one = AsyncMock(return_value={"id": "prev-review"})
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(submit_review(
                "p1",
                body={"rating": 5, "reviewer_name": "Tom", "reviewer_email": "tom@x", "body": "good"},
                request=_request(),
            ))
    assert exc.value.status_code == 429


def test_submit_review_partner_must_be_approved():
    from routes.partners import submit_review
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)  # find_one queries status:approved
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(submit_review("p1", body={"rating": 5, "reviewer_name": "X", "body": "y"}, request=_request()))
    assert exc.value.status_code == 404


# ── List endpoint (public + engineer-side) ────────────────────────


def test_public_list_excludes_sensitive_fields():
    from routes.partners import list_partner_reviews
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "full_name": "Jane Doe"})
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor([
        {"id": "r1", "rating": 5, "title": "Great", "body": "Top job", "reviewer_name": "Tom", "gym_name": "Bicep Hub", "created_at": "2026-02-21"},
        {"id": "r2", "rating": 4, "title": "Good", "body": "Fast", "reviewer_name": "Sue", "created_at": "2026-02-20"},
    ]))
    with patch("routes.partners.db", fake_db):
        out = _run(list_partner_reviews("p1"))
    # find() was called with a projection that drops reviewer_email + ip_hash.
    proj = fake_db.partner_reviews.find.call_args[0][1]
    assert proj.get("ip_hash") == 0
    assert proj.get("reviewer_email") == 0
    # Aggregate
    assert out["summary"]["count"] == 2
    assert out["summary"]["average"] == 4.5
    # Partner exposed minimally
    assert out["partner"]["first_name"] == "Jane"
    assert "full_name" not in out["partner"]


def test_engineer_list_includes_status_breakdown():
    from routes.partners import list_my_reviews
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "user_id": "u-jane"})
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor([
        {"id": "r1", "rating": 5, "status": "approved"},
        {"id": "r2", "rating": 4, "status": "approved"},
        {"id": "r3", "rating": 2, "status": "pending"},
    ]))
    with patch("routes.partners.db", fake_db):
        out = _run(list_my_reviews(user=_user()))
    assert out["summary"]["total"] == 3
    assert out["summary"]["approved"] == 2
    assert out["summary"]["pending"] == 1
    assert out["summary"]["average"] == 4.5


# ── Engineer response endpoint ────────────────────────────────────


def test_engineer_respond_requires_ownership():
    from routes.partners import respond_to_review
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "user_id": "u-jane"})
    fake_db.partner_reviews.find_one = AsyncMock(return_value=None)  # review not on this partner
    with patch("routes.partners.db", fake_db):
        with pytest.raises(Exception) as exc:
            _run(respond_to_review("r-not-mine", body={"response": "thanks"}, user=_user()))
    assert "not found" in str(exc.value.detail).lower()


def test_engineer_respond_persists_response_and_timestamp():
    from routes.partners import respond_to_review
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value={"id": "p1", "user_id": "u-jane"})
    fake_db.partner_reviews.find_one = AsyncMock(return_value={"id": "r1", "partner_id": "p1"})
    captured = {}
    fake_db.partner_reviews.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()):
        out = _run(respond_to_review("r1", body={"response": "Thanks for the feedback!"}, user=_user()))
    assert out["ok"] is True
    set_doc = captured["$set"]
    assert set_doc["engineer_response"] == "Thanks for the feedback!"
    assert set_doc["engineer_response_at"]


# ── Admin moderation endpoint ─────────────────────────────────────


def test_admin_moderate_approve_flips_status():
    from routes.partners import admin_moderate_review
    fake_db = MagicMock()
    fake_db.partner_reviews.find_one = AsyncMock(return_value={"id": "r1", "partner_id": "p1", "status": "pending"})
    captured = {}
    fake_db.partner_reviews.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()):
        out = _run(admin_moderate_review("p1", "r1", body={"decision": "approve"}, user=_admin()))
    assert out["status"] == "approved"
    assert captured["$set"]["status"] == "approved"
    assert captured["$set"]["moderated_by"] == "u-admin"


def test_admin_moderate_reject_carries_note():
    from routes.partners import admin_moderate_review
    fake_db = MagicMock()
    fake_db.partner_reviews.find_one = AsyncMock(return_value={"id": "r1", "partner_id": "p1"})
    captured = {}
    fake_db.partner_reviews.update_one = AsyncMock(side_effect=lambda _f, upd: captured.update(upd))
    with patch("routes.partners.db", fake_db), \
         patch("routes.partners._audit", AsyncMock()):
        _run(admin_moderate_review(
            "p1", "r1",
            body={"decision": "reject", "note": "Same user, second submission within minutes."},
            user=_admin(),
        ))
    assert captured["$set"]["status"] == "rejected"
    assert captured["$set"]["moderation_note"].startswith("Same user")


def test_admin_moderate_rejects_unknown_decision():
    from routes.partners import admin_moderate_review
    with pytest.raises(Exception) as exc:
        _run(admin_moderate_review("p1", "r1", body={"decision": "maybe"}, user=_admin()))
    assert "approve" in str(exc.value.detail) and "reject" in str(exc.value.detail)
