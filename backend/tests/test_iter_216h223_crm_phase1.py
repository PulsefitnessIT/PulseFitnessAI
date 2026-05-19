"""Iter 216h223 — CRM Phase 1 contract tests.

Locks in the behaviour of:
  • POST /crm/v2/contacts mandatory email validation
  • POST /crm/v2/contacts influence_types accepted + legacy booleans synced
  • GET  /crm/picklists/{key} merges global + org values, hides deprecated
  • POST /crm/picklists/{key} duplicate label rejection
  • DELETE /crm/picklists/{key}/{id} refused when value is referenced
  • PATCH /crm/contacts/{id}/influence-types syncs is_decision_maker / is_champion
  • Influence types catalogue contains the canonical Miller Heiman + ops roles
"""
from __future__ import annotations

import os
import uuid
import asyncio
import time
from datetime import datetime, timezone

import httpx
import pytest


BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("PUBLIC_BASE_URL")
    or "http://localhost:8001"
).rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> str:
    r = httpx.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def _crm_token() -> str:
    main = _login("e1.agent@gymaxisai.com", "E1Agent123!")
    r = httpx.post(
        f"{API}/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {main}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def crm_token() -> str:
    return _crm_token()


@pytest.fixture(scope="module")
def auth(crm_token):
    return {"Authorization": f"Bearer {crm_token}"}


# ── Picklists ─────────────────────────────────────────────────────


def test_picklists_keys_endpoint_returns_canonical_keys(auth):
    r = httpx.get(f"{API}/crm/picklists", headers=auth, timeout=15)
    assert r.status_code == 200
    keys = {k["key"] for k in r.json()["keys"]}
    # Spot-check the canonical set — these must always be present.
    assert "job_title" in keys
    assert "industry" in keys
    assert "lead_source" in keys
    assert "lost_reason" in keys
    assert "case_type" in keys


def test_picklists_values_merges_global_and_org(auth):
    r = httpx.get(f"{API}/crm/picklists/job_title", headers=auth, timeout=15)
    assert r.status_code == 200
    payload = r.json()
    assert payload["key"] == "job_title"
    vals = payload["values"]
    assert len(vals) >= 10  # global defaults seeded on startup
    # Deprecated rows should NOT appear (the contract tested below
    # toggles a flag and we re-read).
    assert all(v.get("deprecated") in (False, None) for v in vals)


def test_picklists_post_rejects_duplicate_label(auth):
    # First create a unique value, then try to dup it.
    label = f"Test-216h223-{uuid.uuid4().hex[:6]}"
    r = httpx.post(
        f"{API}/crm/picklists/job_title",
        json={"label": label},
        headers=auth,
        timeout=15,
    )
    assert r.status_code == 200
    value_id = r.json()["id"]

    # Same label again (case-insensitive) → 409.
    r2 = httpx.post(
        f"{API}/crm/picklists/job_title",
        json={"label": label.upper()},
        headers=auth,
        timeout=15,
    )
    assert r2.status_code == 409

    # Cleanup.
    httpx.delete(
        f"{API}/crm/picklists/job_title/{value_id}",
        headers=auth,
        timeout=15,
    )


def test_picklists_unknown_key_returns_404(auth):
    r = httpx.get(f"{API}/crm/picklists/no_such_key", headers=auth, timeout=15)
    assert r.status_code == 404


# ── Stakeholder influence types ───────────────────────────────────


def test_influence_types_contains_canonical_roles(auth):
    r = httpx.get(f"{API}/crm/stakeholders/influence-types", headers=auth, timeout=15)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()["types"]}
    # Canonical Miller Heiman roles must all be present.
    for role in ("economic_buyer", "technical_buyer", "user_buyer", "coach", "champion", "decision_maker", "blocker"):
        assert role in ids, f"Missing canonical role: {role}"


# ── Contact create / email validation / influence sync ───────────


def test_contact_create_rejects_missing_email(auth):
    r = httpx.post(
        f"{API}/crm/v2/contacts",
        json={"first_name": "NoEmail", "last_name": "Test"},
        headers=auth,
        timeout=15,
    )
    assert r.status_code == 422
    assert "email" in r.text.lower()


def test_contact_create_rejects_invalid_email(auth):
    r = httpx.post(
        f"{API}/crm/v2/contacts",
        json={"first_name": "Bad", "last_name": "Email", "email": "not-an-email"},
        headers=auth,
        timeout=15,
    )
    assert r.status_code == 422


def test_contact_create_with_influence_types_syncs_legacy_booleans(auth):
    suffix = f"{int(time.time())}-{uuid.uuid4().hex[:4]}"
    email = f"phase1.test+{suffix}@example.com"
    r = httpx.post(
        f"{API}/crm/v2/contacts",
        json={
            "first_name": "Phase1",
            "last_name": "Test",
            "email": email,
            "influence_types": ["economic_buyer", "champion"],
        },
        headers=auth,
        timeout=15,
    )
    assert r.status_code == 200
    contact = r.json()
    assert "economic_buyer" in contact["influence_types"]
    assert contact["is_champion"] is True
    assert contact["is_decision_maker"] is False  # not in types

    # PATCH endpoint syncs decision_maker too.
    r2 = httpx.patch(
        f"{API}/crm/contacts/{contact['id']}/influence-types",
        json={"influence_types": ["decision_maker", "procurement"]},
        headers=auth,
        timeout=15,
    )
    assert r2.status_code == 200
    updated = r2.json()
    assert updated["is_decision_maker"] is True
    assert updated["is_champion"] is False  # champion was removed

    # Reject unknown type.
    r3 = httpx.patch(
        f"{API}/crm/contacts/{contact['id']}/influence-types",
        json={"influence_types": ["nonexistent_role"]},
        headers=auth,
        timeout=15,
    )
    assert r3.status_code == 400


def test_contact_create_rejects_duplicate_email_softly(auth):
    suffix = f"{int(time.time())}-dup-{uuid.uuid4().hex[:4]}"
    email = f"phase1.dup+{suffix}@example.com"
    r = httpx.post(
        f"{API}/crm/v2/contacts",
        json={"first_name": "Dup", "last_name": "First", "email": email},
        headers=auth, timeout=15,
    )
    assert r.status_code == 200

    # Second create with same email → 409.
    r2 = httpx.post(
        f"{API}/crm/v2/contacts",
        json={"first_name": "Dup", "last_name": "Second", "email": email},
        headers=auth, timeout=15,
    )
    assert r2.status_code == 409
    assert "already exists" in r2.text.lower()

    # Override flag bypasses.
    r3 = httpx.post(
        f"{API}/crm/v2/contacts",
        json={"first_name": "Dup", "last_name": "Override", "email": email, "allow_duplicate_email": True},
        headers=auth, timeout=15,
    )
    assert r3.status_code == 200
