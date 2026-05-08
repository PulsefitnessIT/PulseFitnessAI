"""Iter 228 — Marketing Forms + Landing Pages tests."""
from __future__ import annotations

import os
import uuid

import pytest
import requests

API_BASE = os.environ.get("API_BASE") or (
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=", 1)[1].split("\n", 1)[0].strip() + "/api"
)


def _login(email: str, password: str) -> str:
    headers = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only-2026"}
    r = requests.post(f"{API_BASE}/auth/login", json={"email": email, "password": password}, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def operator_headers() -> dict:
    return {"Authorization": f"Bearer {_login('lee.somers@pulsefitness.com', 'TempPass123!')}"}


# ─────── Forms ───────

def test_form_crud_lifecycle(operator_headers):
    """Create → list → fetch → update → archive."""
    nonce = uuid.uuid4().hex[:6]
    payload = {
        "name": f"Iter228 Test Form {nonce}",
        "description": "Test description",
        "fields": [
            {"label": "Email", "field_type": "email", "required": True, "crm_property": "email"},
            {"label": "Note", "field_type": "textarea", "required": False, "crm_property": "notes"},
        ],
    }
    r = requests.post(f"{API_BASE}/marketing/forms", json=payload, headers=operator_headers, timeout=15)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["slug"].startswith("iter228-test-form")
    assert "lee.somers@pulsefitness.com" in created["notify_emails"]  # creator auto-added
    form_id = created["id"]

    # List should include this form.
    r = requests.get(f"{API_BASE}/marketing/forms", headers=operator_headers, timeout=10)
    assert r.status_code == 200
    assert any(f["id"] == form_id for f in r.json()["forms"])

    # Update
    update = dict(payload, name=f"Iter228 Test Form {nonce} v2", success_message="All good!")
    r = requests.put(f"{API_BASE}/marketing/forms/{form_id}", json=update, headers=operator_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["name"].endswith("v2")
    assert r.json()["success_message"] == "All good!"

    # Archive
    r = requests.delete(f"{API_BASE}/marketing/forms/{form_id}", headers=operator_headers, timeout=10)
    assert r.status_code == 200
    assert r.json().get("archived") is True

    # Archived forms drop out of the list.
    r = requests.get(f"{API_BASE}/marketing/forms", headers=operator_headers, timeout=10)
    assert all(f["id"] != form_id for f in r.json()["forms"])


def test_public_form_unauth_lookup_and_submit(operator_headers):
    """End-to-end public flow — UNAUTH lookup + UNAUTH submit creates a CRM contact."""
    nonce = uuid.uuid4().hex[:6]
    payload = {
        "name": f"Iter228 Public Submit {nonce}",
        "fields": [
            {"label": "Full name", "field_type": "text", "required": True, "crm_property": "first_name"},
            {"label": "Email", "field_type": "email", "required": True, "crm_property": "email"},
        ],
        "require_consent": True,
        "send_confirmation": False,
    }
    r = requests.post(f"{API_BASE}/marketing/forms", json=payload, headers=operator_headers, timeout=10)
    assert r.status_code == 200
    form = r.json()
    slug = form["slug"]

    # Public lookup — no auth header
    r = requests.get(f"{API_BASE}/marketing/forms/by-slug/{slug}", timeout=10)
    assert r.status_code == 200
    public = r.json()
    assert public["name"] == form["name"]
    assert "notify_emails" not in public  # private fields stripped
    fid_email = next(f["id"] for f in public["fields"] if f["field_type"] == "email")
    fid_name = next(f["id"] for f in public["fields"] if f["field_type"] == "text")

    # Reject submit without consent
    r = requests.post(
        f"{API_BASE}/marketing/forms/by-slug/{slug}/submit",
        json={"values": {fid_email: "iter228-test@example.com", fid_name: "Test"}, "consent": False},
        timeout=10,
    )
    assert r.status_code == 400

    # Reject submit missing required email
    r = requests.post(
        f"{API_BASE}/marketing/forms/by-slug/{slug}/submit",
        json={"values": {fid_name: "Test"}, "consent": True},
        timeout=10,
    )
    assert r.status_code == 400

    # Successful submit
    submit_email = f"iter228-{nonce}@example.com"
    r = requests.post(
        f"{API_BASE}/marketing/forms/by-slug/{slug}/submit",
        json={
            "values": {fid_email: submit_email, fid_name: "Test User"},
            "consent": True,
            "utm": {"utm_source": "test"},
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["submitted"] is True

    # Submission appears in operator's view.
    r = requests.get(f"{API_BASE}/marketing/forms/{form['id']}/submissions", headers=operator_headers, timeout=10)
    assert r.status_code == 200
    subs = r.json()["submissions"]
    assert len(subs) >= 1
    last = subs[0]
    assert last["values"][fid_email] == submit_email
    assert last["consent"] is True
    assert last.get("crm_contact_id"), "expected CRM contact to be auto-created"


def test_form_404_for_unknown_slug():
    r = requests.get(f"{API_BASE}/marketing/forms/by-slug/does-not-exist-{uuid.uuid4().hex[:6]}", timeout=10)
    assert r.status_code == 404


def test_form_requires_auth(operator_headers):
    """Authed CRUD endpoints reject unauth callers."""
    r = requests.get(f"{API_BASE}/marketing/forms", timeout=10)
    assert r.status_code in (401, 403)


# ─────── Landing Pages ───────

def test_page_crud_and_publish_flow(operator_headers):
    nonce = uuid.uuid4().hex[:6]
    payload = {
        "title": f"Iter228 Landing {nonce}",
        "subtitle": "Sign up today",
        "body_markdown": "Hello world.\n\nSecond paragraph.",
        "cta_label": "Book", "cta_url": "https://example.com",
    }
    r = requests.post(f"{API_BASE}/marketing/pages", json=payload, headers=operator_headers, timeout=10)
    assert r.status_code == 200
    page = r.json()
    assert page["status"] == "draft"
    assert page["slug"].startswith("iter228-landing")
    page_id = page["id"]

    # Drafts are NOT public.
    r = requests.get(f"{API_BASE}/marketing/pages/by-slug/{page['slug']}", timeout=10)
    assert r.status_code == 404

    # Publish.
    r = requests.put(f"{API_BASE}/marketing/pages/{page_id}", json={"status": "published"},
                     headers=operator_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "published"

    # Public lookup now returns the page.
    r = requests.get(f"{API_BASE}/marketing/pages/by-slug/{page['slug']}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == payload["title"]
    assert body["form"] is None  # No form attached.

    # Track a visit.
    r = requests.post(f"{API_BASE}/marketing/pages/by-slug/{page['slug']}/visit",
                      json={"utm": {"utm_source": "test"}, "user_agent": "pytest"}, timeout=10)
    assert r.status_code == 200

    # Archive.
    r = requests.delete(f"{API_BASE}/marketing/pages/{page_id}", headers=operator_headers, timeout=10)
    assert r.status_code == 200


def test_invalid_status_rejected(operator_headers):
    payload = {"title": "Iter228 status guard", "body_markdown": "x"}
    r = requests.post(f"{API_BASE}/marketing/pages", json=payload, headers=operator_headers, timeout=10)
    assert r.status_code == 200
    page_id = r.json()["id"]
    r = requests.put(f"{API_BASE}/marketing/pages/{page_id}", json={"status": "invalid_value"},
                     headers=operator_headers, timeout=10)
    assert r.status_code == 400
    requests.delete(f"{API_BASE}/marketing/pages/{page_id}", headers=operator_headers, timeout=10)
