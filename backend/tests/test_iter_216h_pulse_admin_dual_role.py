"""
Iter 216h — Pulse Master Admin dual-role contract.

Pulse Master Admins (cross-platform, ``organization_id=None``) can ALSO be
attached to one or more organisations via ``organization_memberships``.
When attached, they must surface in the org-users list as a virtual
per-org row, so the existing UI filtering by ``organization_id`` works
without changes.

These tests pin:
  1. PUT .../org-memberships persists the list (full replacement).
  2. GET /master-admin/pulse-admins returns the memberships + decorated names.
  3. GET /master-admin/users fans the admin out as a per-org row for each
     attached organisation — without losing the original cross-platform row.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MASTER_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PWD = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")


@pytest.fixture
def master_token():
    r = httpx.post(
        f"{API_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PWD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture
def headers(master_token):
    return {"Authorization": f"Bearer {master_token}"}


@pytest.fixture
def test_pulse_admin(headers):
    """Provision a fresh pulse admin, yield it, then revoke it."""
    email = f"pulse-dual-{uuid.uuid4().hex[:8]}@example.com"
    r = httpx.post(
        f"{API_URL}/api/master-admin/pulse-admins",
        json={"email": email, "full_name": "Iter216h Dual-Role Test"},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    admin = r.json()
    yield admin
    # Cleanup
    httpx.delete(
        f"{API_URL}/api/master-admin/pulse-admins/{admin['user_id']}",
        headers=headers, timeout=30,
    )


@pytest.fixture
def test_org_id(headers):
    """Use the first available Pulse-visible org as the attachment target."""
    r = httpx.get(
        f"{API_URL}/api/master-admin/organizations",
        headers=headers, timeout=30,
    )
    r.raise_for_status()
    orgs = r.json().get("organizations", [])
    assert orgs, "Need at least one org in the database to run this test."
    return orgs[0]["id"]


def test_set_org_memberships_persists_and_decorates(headers, test_pulse_admin, test_org_id):
    """PUT memberships → admin list returns the membership ids + names."""
    r = httpx.put(
        f"{API_URL}/api/master-admin/pulse-admins/{test_pulse_admin['user_id']}/org-memberships",
        json={"organization_ids": [test_org_id]},
        headers=headers, timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.json()["organization_ids"] == [test_org_id]

    listed = httpx.get(
        f"{API_URL}/api/master-admin/pulse-admins",
        headers=headers, timeout=30,
    ).json()["admins"]
    me = next((a for a in listed if a["id"] == test_pulse_admin["user_id"]), None)
    assert me, "Admin missing from /pulse-admins list"
    assert me["organization_memberships"] == [test_org_id]
    assert me["membership_org_names"]
    assert me["membership_org_names"][0]["id"] == test_org_id
    assert me["membership_org_names"][0].get("name")


def test_org_memberships_replace_semantics(headers, test_pulse_admin, test_org_id):
    """PUT with [] clears the list — full replacement, not append."""
    httpx.put(
        f"{API_URL}/api/master-admin/pulse-admins/{test_pulse_admin['user_id']}/org-memberships",
        json={"organization_ids": [test_org_id]},
        headers=headers, timeout=30,
    )
    r = httpx.put(
        f"{API_URL}/api/master-admin/pulse-admins/{test_pulse_admin['user_id']}/org-memberships",
        json={"organization_ids": []},
        headers=headers, timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["organization_ids"] == []


def test_attached_admin_surfaces_in_org_users_list(headers, test_pulse_admin, test_org_id):
    """The attached admin appears as a per-org virtual row in /master-admin/users."""
    httpx.put(
        f"{API_URL}/api/master-admin/pulse-admins/{test_pulse_admin['user_id']}/org-memberships",
        json={"organization_ids": [test_org_id]},
        headers=headers, timeout=30,
    )
    users = httpx.get(
        f"{API_URL}/api/master-admin/users",
        headers=headers, timeout=60,
    ).json()["users"]
    matching = [u for u in users if u.get("email") == test_pulse_admin["email"]]
    # Expect AT LEAST: cross-platform (org_id=None) row + per-org virtual row.
    org_ids = {u.get("organization_id") for u in matching}
    assert None in org_ids or "" in org_ids or any(u.get("organization_id") is None for u in matching), \
        "Cross-platform Pulse Admin row missing"
    assert test_org_id in org_ids, "Per-org virtual row missing"
    # The per-org row should be labelled as a Pulse Platform Admin.
    per_org_row = next(u for u in matching if u.get("organization_id") == test_org_id)
    assert per_org_row.get("display_role") == "Pulse Platform Admin"


def test_invalid_org_id_is_dropped_silently(headers, test_pulse_admin):
    """Non-existent org ids are filtered out — saving stays idempotent."""
    r = httpx.put(
        f"{API_URL}/api/master-admin/pulse-admins/{test_pulse_admin['user_id']}/org-memberships",
        json={"organization_ids": ["bogus-org-id-doesnt-exist"]},
        headers=headers, timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["organization_ids"] == []
