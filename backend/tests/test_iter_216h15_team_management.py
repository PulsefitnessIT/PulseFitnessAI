"""
Iter 216h15 — Owner-side team management:
  • Auto-create real Head Office site when org has sites but no HQ.
  • Rename "All sites" → "All Operations Sites" (frontend-only label).
  • POST /account/team/invite supports delivery=reset_link.
  • POST /account/team/invite accepts allowed_site_ids.
  • PATCH /account/team/{id}/site-access (owner pins teammate to sites).
  • POST /account/team/{id}/send-reset-link (owner emails reset link).
  • GET /account/team surfaces password_reset_sent_at/by audit trail.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pymongo import MongoClient

from utils.auth import create_token  # noqa: E402

API_URL = os.environ.get("REACT_APP_BACKEND_URL_TEST") or os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
)
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def make_headers():
    def _make(user_id):
        return {"Authorization": f"Bearer {create_token(user_id)}"}
    return _make


@pytest.fixture
def org_with_owner(db):
    """Owner + org + 2 sites (none flagged HQ) — mimics Pulse Fitness."""
    org_id = f"test-h15-org-{uuid.uuid4().hex[:8]}"
    owner_id = f"test-h15-owner-{uuid.uuid4().hex[:8]}"
    site_ids = [f"test-h15-site-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    db.organizations.insert_one({"id": org_id, "name": "Pulse Test H15"})
    db.users.insert_one({
        "id": owner_id, "email": f"h15-owner-{uuid.uuid4().hex[:6]}@example.com",
        "organization_id": org_id, "role": "owner", "full_name": "Owner H15",
        "password": "x", "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.sites.insert_many([
        {"id": site_ids[0], "organization_id": org_id, "name": "iGym Carshalton", "is_head_office": False, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": site_ids[1], "organization_id": org_id, "name": "iGym Congleton", "is_head_office": False, "created_at": datetime.now(timezone.utc).isoformat()},
    ])
    yield org_id, owner_id, site_ids
    # Cleanup
    db.users.delete_many({"organization_id": org_id})
    db.sites.delete_many({"organization_id": org_id})
    db.organizations.delete_one({"id": org_id})
    db.password_reset_tokens.delete_many({"issued_by": {"$regex": "h15-owner"}})


# ── Auto-create real Head Office ──────────────────────────────────

def test_get_sites_auto_creates_real_head_office(org_with_owner, make_headers, db):
    org_id, owner_id, _ = org_with_owner
    r = httpx.get(f"{API_URL}/api/sites", headers=make_headers(owner_id), timeout=30)
    assert r.status_code == 200
    sites = r.json()["sites"]
    # Should now be 3 — the 2 originals plus an auto-created real HQ
    assert len(sites) == 3
    # HQ should be FIRST in the list
    assert sites[0]["is_head_office"] is True
    assert sites[0]["name"].endswith(" Head Office")
    # NOT synthetic — a real `db.sites` row
    assert not sites[0]["id"].startswith("hq:")
    assert "is_synthetic" not in sites[0] or sites[0].get("is_synthetic") is None
    # Persisted in db.sites
    persisted = db.sites.find_one({"id": sites[0]["id"]})
    assert persisted is not None
    assert persisted["auto_created"] is True


def test_get_sites_does_not_double_create_hq(org_with_owner, make_headers, db):
    """Second call must not create a SECOND HQ — auto-create is idempotent."""
    org_id, owner_id, _ = org_with_owner
    httpx.get(f"{API_URL}/api/sites", headers=make_headers(owner_id), timeout=30)
    httpx.get(f"{API_URL}/api/sites", headers=make_headers(owner_id), timeout=30)
    hq_count = db.sites.count_documents({"organization_id": org_id, "is_head_office": True})
    assert hq_count == 1


# ── Invite — delivery=reset_link path ─────────────────────────────

def test_invite_with_reset_link_delivery_returns_invite_url(org_with_owner, make_headers, db):
    org_id, owner_id, _ = org_with_owner
    email = f"h15-staff-rl-{uuid.uuid4().hex[:6]}@example.com"
    r = httpx.post(
        f"{API_URL}/api/account/team/invite",
        headers=make_headers(owner_id),
        json={"email": email, "full_name": "Reset Link Staff", "role": "staff",
              "delivery": "reset_link"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["delivery"] == "reset_link"
    assert "invite_url" in data and data["invite_url"].startswith("http")
    assert "/reset-password?token=" in data["invite_url"]
    assert "temp_password" not in data  # MUST NOT leak the seed password
    # Audit trail stamped
    target = db.users.find_one({"email": email})
    assert target["password_reset_sent_at"]
    assert target["password_reset_sent_by"]


def test_invite_with_temp_password_delivery_returns_temp(org_with_owner, make_headers):
    """Legacy temp-password path still works (default fallback)."""
    org_id, owner_id, _ = org_with_owner
    email = f"h15-staff-temp-{uuid.uuid4().hex[:6]}@example.com"
    r = httpx.post(
        f"{API_URL}/api/account/team/invite",
        headers=make_headers(owner_id),
        json={"email": email, "full_name": "Temp Pwd Staff", "role": "staff",
              "delivery": "temp_password"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["delivery"] == "temp_password"
    assert data["temp_password"].startswith("Welcome")
    assert "invite_url" not in data


def test_invite_pins_allowed_site_ids(org_with_owner, make_headers, db):
    """Invite form's allowed_site_ids is persisted on the user doc."""
    org_id, owner_id, site_ids = org_with_owner
    email = f"h15-staff-pin-{uuid.uuid4().hex[:6]}@example.com"
    r = httpx.post(
        f"{API_URL}/api/account/team/invite",
        headers=make_headers(owner_id),
        json={"email": email, "full_name": "Pinned Staff", "role": "staff",
              "delivery": "reset_link", "allowed_site_ids": [site_ids[0]]},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["allowed_site_ids"] == [site_ids[0]]
    target = db.users.find_one({"email": email})
    assert target["allowed_site_ids"] == [site_ids[0]]


# ── PATCH /account/team/{id}/site-access ──────────────────────────

@pytest.fixture
def seeded_staff(org_with_owner, db):
    org_id, owner_id, site_ids = org_with_owner
    staff_id = f"test-h15-staff-{uuid.uuid4().hex[:8]}"
    db.users.insert_one({
        "id": staff_id, "email": f"staff-{uuid.uuid4().hex[:6]}@example.com",
        "organization_id": org_id, "role": "staff",
        "full_name": "Test Staff", "password": "x",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield staff_id


def test_owner_can_pin_staff_to_subset_of_sites(org_with_owner, seeded_staff, make_headers, db):
    org_id, owner_id, site_ids = org_with_owner
    r = httpx.patch(
        f"{API_URL}/api/account/team/{seeded_staff}/site-access",
        headers=make_headers(owner_id),
        json={"allowed_site_ids": [site_ids[0]]},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["allowed_site_ids"] == [site_ids[0]]
    target = db.users.find_one({"id": seeded_staff})
    assert target["site_access_updated_by"]


def test_pin_to_empty_list_means_full_access(org_with_owner, seeded_staff, make_headers, db):
    org_id, owner_id, _ = org_with_owner
    # First pin to a site
    httpx.patch(
        f"{API_URL}/api/account/team/{seeded_staff}/site-access",
        headers=make_headers(owner_id),
        json={"allowed_site_ids": ["some-site-id"]},
        timeout=15,
    )
    # Then clear
    r = httpx.patch(
        f"{API_URL}/api/account/team/{seeded_staff}/site-access",
        headers=make_headers(owner_id),
        json={"allowed_site_ids": []},
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["allowed_site_ids"] == []


def test_pin_rejects_sites_outside_org(org_with_owner, seeded_staff, make_headers, db):
    """Site ids from other tenants must be silently filtered out."""
    org_id, owner_id, _ = org_with_owner
    foreign_site_id = "definitely-not-ours-id"
    r = httpx.patch(
        f"{API_URL}/api/account/team/{seeded_staff}/site-access",
        headers=make_headers(owner_id),
        json={"allowed_site_ids": [foreign_site_id]},
        timeout=15,
    )
    assert r.status_code == 200
    # Filtered out
    assert r.json()["allowed_site_ids"] == []


def test_pin_rejects_owner_role(org_with_owner, make_headers):
    """Owners always see every site — must reject attempts to pin them."""
    org_id, owner_id, site_ids = org_with_owner
    r = httpx.patch(
        f"{API_URL}/api/account/team/{owner_id}/site-access",
        headers=make_headers(owner_id),
        json={"allowed_site_ids": [site_ids[0]]},
        timeout=15,
    )
    assert r.status_code == 403


# ── POST /account/team/{id}/send-reset-link ───────────────────────

def test_send_reset_link_to_existing_teammate(org_with_owner, seeded_staff, make_headers, db):
    org_id, owner_id, _ = org_with_owner
    r = httpx.post(
        f"{API_URL}/api/account/team/{seeded_staff}/send-reset-link",
        headers=make_headers(owner_id), timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["invite_url"].startswith("http")
    assert "/reset-password?token=" in data["invite_url"]
    assert data["sent_by"]
    # Audit fields stamped
    target = db.users.find_one({"id": seeded_staff})
    assert target["password_reset_sent_at"]
    assert target["password_reset_sent_by"]
    # Token actually persisted
    tok = data["invite_url"].rsplit("token=", 1)[1]
    pt = db.password_reset_tokens.find_one({"token": tok})
    assert pt is not None
    assert pt["kind"] == "invite"
    assert pt["user_id"] == seeded_staff


def test_send_reset_link_404_for_unknown_user(org_with_owner, make_headers):
    org_id, owner_id, _ = org_with_owner
    r = httpx.post(
        f"{API_URL}/api/account/team/does-not-exist/send-reset-link",
        headers=make_headers(owner_id), timeout=15,
    )
    assert r.status_code == 404


def test_send_reset_link_rejects_owner_target(org_with_owner, make_headers, db):
    """Two owners in the same org — owner-A cannot reset owner-B."""
    org_id, owner_id, _ = org_with_owner
    other_owner_id = f"test-h15-owner2-{uuid.uuid4().hex[:8]}"
    db.users.insert_one({
        "id": other_owner_id, "email": f"owner2-{uuid.uuid4().hex[:6]}@example.com",
        "organization_id": org_id, "role": "owner",
        "password": "x", "created_at": datetime.now(timezone.utc).isoformat(),
    })
    r = httpx.post(
        f"{API_URL}/api/account/team/{other_owner_id}/send-reset-link",
        headers=make_headers(owner_id), timeout=15,
    )
    assert r.status_code == 403


def test_team_list_surfaces_reset_audit_trail(org_with_owner, seeded_staff, make_headers, db):
    org_id, owner_id, _ = org_with_owner
    # Trigger a reset
    httpx.post(
        f"{API_URL}/api/account/team/{seeded_staff}/send-reset-link",
        headers=make_headers(owner_id), timeout=15,
    )
    # Re-fetch the team list
    r = httpx.get(f"{API_URL}/api/account/team", headers=make_headers(owner_id), timeout=15)
    members = r.json()["members"]
    target = next(m for m in members if m["id"] == seeded_staff)
    assert target.get("password_reset_sent_at")
    assert target.get("password_reset_sent_by")
