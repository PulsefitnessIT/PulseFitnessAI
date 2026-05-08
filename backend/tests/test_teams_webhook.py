"""
Microsoft Teams webhook channel tests (P4, Feb 2026).
"""
import pytest
import requests
from fastapi import HTTPException

from tests.conftest import _test_backend_url, run_async as run

BASE = _test_backend_url()


# ─── URL validation ─────────────────────────────────────────────

def test_validate_webhook_accepts_workflows_url():
    from utils.teams_webhook import validate_webhook_url
    validate_webhook_url(
        "https://prod-01.westeurope.logic.azure.com/workflows/abc/triggers/manual/paths/invoke"
    )


def test_validate_webhook_accepts_legacy_connector():
    from utils.teams_webhook import validate_webhook_url
    validate_webhook_url(
        "https://contoso.webhook.office.com/webhookb2/abc@def/IncomingWebhook/xyz"
    )


def test_validate_webhook_rejects_http():
    from utils.teams_webhook import validate_webhook_url
    with pytest.raises(HTTPException) as exc:
        validate_webhook_url("http://webhook.office.com/abc")
    assert exc.value.status_code == 400


def test_validate_webhook_rejects_foreign_host():
    from utils.teams_webhook import validate_webhook_url
    with pytest.raises(HTTPException) as exc:
        validate_webhook_url("https://evil.example.com/abc")
    assert exc.value.status_code == 400


def test_validate_webhook_rejects_empty():
    from utils.teams_webhook import validate_webhook_url
    with pytest.raises(HTTPException):
        validate_webhook_url("")


# ─── Legacy detection ───────────────────────────────────────────

def test_is_legacy_webhook_classification():
    from utils.teams_webhook import _is_legacy_webhook
    assert _is_legacy_webhook("https://contoso.webhook.office.com/webhookb2/...") is True
    assert _is_legacy_webhook("https://prod-01.eastus.logic.azure.com/workflows/...") is False


# ─── Adaptive Card rendering ────────────────────────────────────

def test_render_adaptive_card_shape():
    from utils.teams_webhook import render_adaptive_card
    user = {"full_name": "Lee Somers", "email": "lee@example.com"}
    payload = {
        "summary": "3 items need attention",
        "items": [
            {"type": "nudge.ppm_overdue", "severity": "high",
             "customer_safe_message": "2 PPM tasks overdue"},
        ],
    }
    card = render_adaptive_card(user, payload, "weekly")
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    # First-name greeting present
    flat = str(card)
    assert "Lee" in flat
    assert "weekly digest" in flat
    assert "Planned maintenance overdue" in flat
    # Action.OpenUrl present
    assert any(a.get("type") == "Action.OpenUrl" for a in card.get("actions", []))


def test_wrap_for_transport_uses_attachments_envelope():
    from utils.teams_webhook import wrap_for_transport
    card = {"type": "AdaptiveCard", "version": "1.4"}
    env = wrap_for_transport(card, "https://prod-01.logic.azure.com/invoke")
    assert env["type"] == "message"
    assert env["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert env["attachments"][0]["content"] == card


# ─── Prefs persist Teams fields ─────────────────────────────────

def test_put_preferences_saves_teams_fields(pulse_pro_token):
    if not pulse_pro_token:
        return
    url = "https://prod-01.westeurope.logic.azure.com/workflows/abc/invoke"
    patch = {"teams_enabled": True, "teams_webhook_url": url}
    r = requests.put(
        f"{BASE}/api/digest/preferences",
        json=patch,
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["teams_enabled"] is True
    assert body["teams_webhook_url"] == url

    # Cleanup
    requests.put(
        f"{BASE}/api/digest/preferences",
        json={"teams_enabled": False, "teams_webhook_url": ""},
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )


def test_put_preferences_rejects_bad_teams_url(pulse_pro_token):
    if not pulse_pro_token:
        return
    r = requests.put(
        f"{BASE}/api/digest/preferences",
        json={"teams_webhook_url": "https://evil.example.com/hook"},
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    assert r.status_code == 400


def test_test_teams_requires_saved_url(pulse_pro_token):
    if not pulse_pro_token:
        return
    # Ensure no URL saved
    requests.put(
        f"{BASE}/api/digest/preferences",
        json={"teams_webhook_url": "", "teams_enabled": False},
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    r = requests.post(
        f"{BASE}/api/digest/test-teams",
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    assert r.status_code == 400
    assert "webhook" in r.json().get("detail", "").lower()


# ─── post_to_teams error handling ───────────────────────────────

def test_post_to_teams_returns_false_on_network_error():
    """post_to_teams must never raise — unreachable host returns False."""
    from utils.teams_webhook import post_to_teams
    ok = run(post_to_teams(
        "https://prod-01.westeurope.logic.azure.com/this-path-does-not-exist-xyz",
        {"type": "AdaptiveCard", "version": "1.4", "body": []},
    ))
    # Either the host returns 4xx/5xx or the connection 404s; either way False.
    assert ok is False


def test_post_to_teams_empty_url_returns_false():
    from utils.teams_webhook import post_to_teams
    assert run(post_to_teams("", {"type": "AdaptiveCard"})) is False
