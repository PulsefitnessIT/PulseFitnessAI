"""Tests for staff onboarding pack email settings (Jan 2026)."""
import os, time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mod-only-deploy.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "owner@isodemo.com", "password": "IsoDemo123!"},
        timeout=30,
    )
    if r.status_code == 429:
        time.sleep(40)
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "owner@isodemo.com", "password": "IsoDemo123!"},
            timeout=30,
        )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_get_settings(headers):
    r = requests.get(f"{BASE_URL}/api/staff-onboarding/settings", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "email_pack_on_activation" in data
    assert isinstance(data["email_pack_on_activation"], bool)
    assert "pack_recipient_emails" in data
    assert isinstance(data["pack_recipient_emails"], list)


def test_put_settings_filters_invalid_emails(headers):
    payload = {
        "email_pack_on_activation": True,
        "pack_recipient_emails": ["hr@pulsefitness.ai", "payroll@pulsefitness.ai", "not-an-email"],
    }
    r = requests.put(
        f"{BASE_URL}/api/staff-onboarding/settings",
        headers=headers,
        json=payload,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["email_pack_on_activation"] is True
    emails = data["pack_recipient_emails"]
    assert "not-an-email" not in emails
    assert "hr@pulsefitness.ai" in emails
    assert "payroll@pulsefitness.ai" in emails
    assert len(emails) == 2

    # Persistence: GET again
    r2 = requests.get(f"{BASE_URL}/api/staff-onboarding/settings", headers=headers, timeout=30)
    assert r2.status_code == 200
    d2 = r2.json()
    assert set(d2["pack_recipient_emails"]) == {"hr@pulsefitness.ai", "payroll@pulsefitness.ai"}
    assert d2["email_pack_on_activation"] is True


def test_put_settings_toggle_off_and_on(headers):
    # Toggle off
    r = requests.put(
        f"{BASE_URL}/api/staff-onboarding/settings",
        headers=headers,
        json={"email_pack_on_activation": False},
        timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["email_pack_on_activation"] is False

    # Toggle back on
    r = requests.put(
        f"{BASE_URL}/api/staff-onboarding/settings",
        headers=headers,
        json={"email_pack_on_activation": True},
        timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["email_pack_on_activation"] is True
