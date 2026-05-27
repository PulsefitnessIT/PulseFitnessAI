"""Iter 220aa — Embeddable Widget (Log-a-Fault / Get-a-Quote).

Pins all the moving parts of the iframe widget engine:

  * Public config endpoint returns owner identity + reviews badge data.
  * Public submit creates a ``svc_job_requests`` row for engineer
    widgets, and a ``crm2_contacts`` lead for organization widgets.
  * Honeypot field silently discards bot submissions (returns 200, no
    DB write).
  * Per-IP, per-token rate limit kicks in after 5 submissions / hour.
  * Owner CRUD: list / create / patch / soft-revoke.
  * Revoked token → public endpoints 404.
  * Auth gating on owner endpoints.
"""
from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone
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


def _embed(**overrides) -> dict:
    base = {
        "id": "wid-1",
        "token": "tok-abc123",
        "owner_type": "partner_engineer",
        "owner_id": "partner-1",
        "label": "Log a fault",
        "redirect_url": None,
        "show_reviews_badge": True,
        "is_active": True,
        "submission_count": 0,
        "last_submission_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def _partner(**overrides) -> dict:
    base = {
        "id": "partner-1",
        "user_id": "user-1",
        "status": "approved",
        "full_name": "Sarah Patel",
        "company_name": "Patel Engineering",
        "level": "gold",
        "profile_photo_url": None,
        "public_slug": "sarah-patel-aaaa",
        "organization_id": "org-engineer-1",
    }
    base.update(overrides)
    return base


# ─── Public config ────────────────────────────────────────────

def test_public_config_returns_engineer_with_review_badge():
    from routes import widget_embed

    embed = _embed()
    partner = _partner()
    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=embed)
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_reviews.find = MagicMock(
        return_value=_make_cursor([{"rating": 5}, {"rating": 5}, {"rating": 4}]),
    )

    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.public_widget_config("tok-abc123"))

    assert out["owner_type"] == "partner_engineer"
    assert out["kind"] == "log_fault"
    assert out["owner"]["name"] == "Sarah Patel"
    assert out["owner"]["public_slug"] == "sarah-patel-aaaa"
    assert out["summary"]["count"] == 3
    assert out["summary"]["average"] == round((5 + 5 + 4) / 3, 2)


def test_public_config_skips_review_query_when_badge_disabled():
    from routes import widget_embed

    embed = _embed(show_reviews_badge=False)
    partner = _partner()
    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=embed)
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.partner_reviews.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.public_widget_config("tok-abc123"))

    fake_db.partner_reviews.find.assert_not_called()
    assert out["summary"]["count"] == 0


def test_public_config_404_when_token_unknown():
    from fastapi import HTTPException
    from routes import widget_embed

    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=None)
    with patch.object(widget_embed, "db", fake_db):
        try:
            _run(widget_embed.public_widget_config("tok-bad"))
            raised = False
        except HTTPException as exc:
            raised = exc.status_code == 404
    assert raised


def test_public_config_404_when_partner_no_longer_approved():
    from fastapi import HTTPException
    from routes import widget_embed

    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=_embed())
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    with patch.object(widget_embed, "db", fake_db):
        try:
            _run(widget_embed.public_widget_config("tok-abc123"))
            raised = False
        except HTTPException as exc:
            raised = exc.status_code == 404
    assert raised


def test_public_config_organization_owner():
    from routes import widget_embed

    embed = _embed(owner_type="organization", owner_id="org-pulse")
    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=embed)
    fake_db.organizations.find_one = AsyncMock(return_value={
        "id": "org-pulse", "name": "Pulse Fitness", "logo_url": "https://x/logo.png",
    })

    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.public_widget_config("tok-abc123"))

    assert out["owner_type"] == "organization"
    assert out["kind"] == "get_quote"
    assert out["owner"]["name"] == "Pulse Fitness"
    assert out["owner"]["logo_url"] == "https://x/logo.png"


# ─── Public submit → engineer inbox ─────────────────────────────

class _FakeRequest:
    def __init__(self, ip="1.2.3.4"):
        self.headers = {"x-forwarded-for": ip}

        class _C:
            host = "0.0.0.0"
        self.client = _C()


def test_public_submit_creates_svc_job_request_for_engineer():
    from routes import widget_embed

    embed = _embed()
    partner = _partner()
    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=embed)
    fake_db.widget_submission_log.count_documents = AsyncMock(return_value=0)
    fake_db.widget_submission_log.insert_one = AsyncMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.svc_job_requests.insert_one = AsyncMock()
    fake_db.widget_embeds.update_one = AsyncMock()

    payload = widget_embed.WidgetSubmitPayload(
        customer_name="Lee Somers",
        customer_email="lee@example.com",
        customer_phone="07900111222",
        site_name="CrossFit Soho",
        site_postcode="W1F 0AB",
        title="Treadmill #4 down",
        description="Belt slipping under load and clicking near the motor.",
        urgency="high",
    )

    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.public_widget_submit(
            "tok-abc123", payload, _FakeRequest(),
        ))

    assert out["ok"] is True
    fake_db.svc_job_requests.insert_one.assert_awaited_once()
    inserted = fake_db.svc_job_requests.insert_one.await_args.args[0]
    assert inserted["engineer_id"] == "partner-1"
    assert inserted["intake_channel"] == "embed_widget"
    assert inserted["priority"] == "high"
    assert inserted["title"] == "Treadmill #4 down"
    # Submission counter incremented.
    fake_db.widget_embeds.update_one.assert_awaited_once()


def test_public_submit_creates_crm_lead_for_organization():
    from routes import widget_embed

    embed = _embed(owner_type="organization", owner_id="org-pulse")
    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=embed)
    fake_db.widget_submission_log.count_documents = AsyncMock(return_value=0)
    fake_db.widget_submission_log.insert_one = AsyncMock()
    fake_db.crm2_contacts.insert_one = AsyncMock()
    fake_db.widget_embeds.update_one = AsyncMock()

    payload = widget_embed.WidgetSubmitPayload(
        customer_name="Alex Lake",
        customer_email="alex@studio.example",
        description="We're a new studio in Manchester planning to open in Q3.",
    )

    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.public_widget_submit(
            "tok-abc123", payload, _FakeRequest(),
        ))

    assert out["ok"] is True
    fake_db.crm2_contacts.insert_one.assert_awaited_once()
    inserted = fake_db.crm2_contacts.insert_one.await_args.args[0]
    assert inserted["organization_id"] == "org-pulse"
    assert inserted["lifecycle"] == "lead"
    assert inserted["source"] == "embed_widget"
    assert inserted["first_name"] == "Alex"
    assert inserted["last_name"] == "Lake"
    assert inserted["email"] == "alex@studio.example"


# ─── Honeypot + rate limit ─────────────────────────────────────

def test_public_submit_honeypot_discards_silently():
    from routes import widget_embed

    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=_embed())
    fake_db.svc_job_requests.insert_one = AsyncMock()
    fake_db.crm2_contacts.insert_one = AsyncMock()

    payload = widget_embed.WidgetSubmitPayload(
        customer_name="Bot",
        customer_email="bot@spam.example",
        description="cheap meds",
        website="https://spammy-link.example",
    )

    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.public_widget_submit(
            "tok-abc123", payload, _FakeRequest(),
        ))

    assert out["ok"] is True  # Silent success → no signal to the bot.
    fake_db.svc_job_requests.insert_one.assert_not_called()
    fake_db.crm2_contacts.insert_one.assert_not_called()


def test_public_submit_rate_limited_after_five_per_hour():
    from fastapi import HTTPException
    from routes import widget_embed

    fake_db = MagicMock()
    fake_db.widget_embeds.find_one = AsyncMock(return_value=_embed())
    # 5 prior submissions in the last hour from this IP/token.
    fake_db.widget_submission_log.count_documents = AsyncMock(return_value=5)

    payload = widget_embed.WidgetSubmitPayload(
        customer_name="Lee", customer_email="lee@example.com",
        description="Another one",
    )
    with patch.object(widget_embed, "db", fake_db):
        try:
            _run(widget_embed.public_widget_submit(
                "tok-abc123", payload, _FakeRequest(),
            ))
            raised = False
        except HTTPException as exc:
            raised = exc.status_code == 429
    assert raised


def test_public_submit_404_when_token_revoked():
    from fastapi import HTTPException
    from routes import widget_embed

    fake_db = MagicMock()
    # Revoked → find_one filter ``is_active: True`` yields None.
    fake_db.widget_embeds.find_one = AsyncMock(return_value=None)

    payload = widget_embed.WidgetSubmitPayload(
        customer_name="Lee", customer_email="lee@example.com",
        description="x",
    )
    with patch.object(widget_embed, "db", fake_db):
        try:
            _run(widget_embed.public_widget_submit(
                "tok-revoked", payload, _FakeRequest(),
            ))
            raised = False
        except HTTPException as exc:
            raised = exc.status_code == 404
    assert raised


# ─── Owner-side CRUD ───────────────────────────────────────────

def test_create_embed_partner_engineer_path():
    from routes import widget_embed

    user = {"id": "user-1"}
    partner = _partner()
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.widget_embeds.insert_one = AsyncMock()

    payload = widget_embed.WidgetCreatePayload(owner_type="partner_engineer")
    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.create_embed(payload, user))

    assert out["owner_type"] == "partner_engineer"
    assert out["owner_id"] == "partner-1"
    assert out["is_active"] is True
    assert len(out["token"]) >= 12  # token_urlsafe(12) ≥ 16 chars
    fake_db.widget_embeds.insert_one.assert_awaited_once()


def test_create_embed_org_path_when_user_has_org():
    from routes import widget_embed

    user = {"id": "user-1", "organization_id": "org-pulse",
            "company_name": "Pulse"}
    fake_db = MagicMock()
    # No partner record — resolver flips to organization.
    fake_db.partner_engineers.find_one = AsyncMock(return_value=None)
    fake_db.widget_embeds.insert_one = AsyncMock()

    payload = widget_embed.WidgetCreatePayload(owner_type="organization")
    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.create_embed(payload, user))

    assert out["owner_type"] == "organization"
    assert out["owner_id"] == "org-pulse"


def test_list_my_embeds_returns_only_my_rows():
    from routes import widget_embed

    user = {"id": "user-1"}
    partner = _partner()
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    fake_db.widget_embeds.find = MagicMock(
        return_value=_make_cursor([_embed(), _embed(id="wid-2", token="tok-2")]),
    )

    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.list_my_embeds(user))

    assert len(out["embeds"]) == 2
    args, _ = fake_db.widget_embeds.find.call_args
    assert args[0]["owner_type"] == "partner_engineer"
    assert args[0]["owner_id"] == "partner-1"


def test_revoke_embed_soft_deactivates():
    from routes import widget_embed

    user = {"id": "user-1"}
    partner = _partner()
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    update_res = MagicMock()
    update_res.matched_count = 1
    fake_db.widget_embeds.update_one = AsyncMock(return_value=update_res)

    with patch.object(widget_embed, "db", fake_db):
        out = _run(widget_embed.revoke_embed("wid-1", user))

    assert out["ok"] is True
    _, kwargs = fake_db.widget_embeds.update_one.call_args
    # The actual update should set is_active=False (positional args)
    args = fake_db.widget_embeds.update_one.call_args.args
    assert args[1]["$set"]["is_active"] is False


def test_revoke_embed_404_when_not_my_widget():
    from fastapi import HTTPException
    from routes import widget_embed

    user = {"id": "user-1"}
    partner = _partner()
    fake_db = MagicMock()
    fake_db.partner_engineers.find_one = AsyncMock(return_value=partner)
    update_res = MagicMock()
    update_res.matched_count = 0
    fake_db.widget_embeds.update_one = AsyncMock(return_value=update_res)

    with patch.object(widget_embed, "db", fake_db):
        try:
            _run(widget_embed.revoke_embed("wid-not-mine", user))
            raised = False
        except HTTPException as exc:
            raised = exc.status_code == 404
    assert raised


# ─── Live API smoke ─────────────────────────────────────────────

def test_public_config_endpoint_404_unknown_token_live():
    r = requests.get(
        f"{BASE}/api/widget/embed/{secrets.token_urlsafe(8)}",
        timeout=10,
    )
    assert r.status_code == 404


def test_owner_routes_require_auth_live():
    r = requests.get(f"{BASE}/api/widget/my-embeds", timeout=10)
    assert r.status_code in (401, 403)


def test_widget_embed_integration_create_submit_revoke_live(pulse_pro_token):
    """Full happy-path round trip via the live API.

    1. Create a widget (organization-owned).
    2. Read the public config.
    3. Submit a lead via the public endpoint.
    4. Revoke the widget.
    5. Verify subsequent public reads 404.
    """
    if not pulse_pro_token:
        return

    # 1) create
    r = requests.post(
        f"{BASE}/api/widget/embeds",
        json={"owner_type": "organization", "label": "Get a quote"},
        headers={"Authorization": f"Bearer {pulse_pro_token}"},
        timeout=10,
    )
    if r.status_code != 200:
        # Pulse Pro user might be a partner_engineer — try that flavour.
        r = requests.post(
            f"{BASE}/api/widget/embeds",
            json={"owner_type": "partner_engineer", "label": "Log a fault"},
            headers={"Authorization": f"Bearer {pulse_pro_token}"},
            timeout=10,
        )
    assert r.status_code == 200, r.text
    created = r.json()
    token = created["token"]
    embed_id = created["id"]

    # 2) public config
    cfg = requests.get(f"{BASE}/api/widget/embed/{token}", timeout=10)
    assert cfg.status_code == 200, cfg.text
    assert cfg.json()["owner"]["name"]

    # 3) public submit
    submit = requests.post(
        f"{BASE}/api/widget/embed/{token}/submit",
        json={
            "customer_name": "Live Test Customer",
            "customer_email": "live.test@example.com",
            "description": "Verifying the embed widget round-trip.",
            "urgency": "normal",
        }, timeout=10,
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["ok"] is True

    # 4) revoke
    rev = requests.delete(
        f"{BASE}/api/widget/embeds/{embed_id}",
        headers={"Authorization": f"Bearer {pulse_pro_token}"},
        timeout=10,
    )
    assert rev.status_code == 200, rev.text

    # 5) post-revoke 404
    cfg2 = requests.get(f"{BASE}/api/widget/embed/{token}", timeout=10)
    assert cfg2.status_code == 404
