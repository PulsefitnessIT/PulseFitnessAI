"""Tests for utils.auth.apply_site_lock — Iter 216bl.

Guards the new server-side site-locking helper against regressions:
the equipment + issues endpoints rely on this clamping non-privileged
staff to their `users.allowed_site_ids`, while letting owners and
master-admins pass through unchanged.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from utils.auth import apply_site_lock


def _user(role: str = "staff", **kw):
    return {"id": "u-1", "organization_id": "org-1", "role": role, **kw}


# ─── unrestricted (legacy default) ───────────────────────────────────
def test_unrestricted_passthrough_with_site():
    out = apply_site_lock(_user(), "site-A", {"organization_id": "org-1"})
    # apply_site_lock applies the legacy site_id $or branch even for
    # unrestricted users, matching the pre-216bl behaviour exactly.
    assert "$or" in out
    assert {"site_id": "site-A"} in out["$or"]


def test_unrestricted_passthrough_without_site():
    out = apply_site_lock(_user(), None, {"organization_id": "org-1"})
    # No site filter at all — caller wants the full org.
    assert "$or" not in out
    assert out == {"organization_id": "org-1"}


# ─── owner / manager / master-admin always bypass ────────────────────
@pytest.mark.parametrize("role", ["owner", "manager", "master_admin", "master"])
def test_privileged_roles_ignore_allowed_site_ids(role):
    u = _user(role=role, allowed_site_ids=["site-A"])
    out = apply_site_lock(u, "site-Z", {"organization_id": "org-1"})
    # Privileged users see whatever they request — no 403, no narrowing.
    assert {"site_id": "site-Z"} in out["$or"]


def test_master_admin_flag_bypasses():
    u = _user(role="staff", is_master_admin=True, allowed_site_ids=["site-A"])
    out = apply_site_lock(u, None, {"organization_id": "org-1"})
    assert "$or" not in out


# ─── locked staff ─────────────────────────────────────────────────────
def test_locked_staff_no_site_clamps_to_allowed():
    u = _user(allowed_site_ids=["site-A", "site-B"])
    out = apply_site_lock(u, None, {"organization_id": "org-1"})
    or_branch = out["$or"]
    # site_id must be in the allowed set, OR null/missing/empty.
    assert {"site_id": {"$in": ["site-A", "site-B"]}} in or_branch
    assert {"site_id": {"$exists": False}} in or_branch


def test_locked_staff_requesting_allowed_site_passes():
    u = _user(allowed_site_ids=["site-A", "site-B"])
    out = apply_site_lock(u, "site-A", {"organization_id": "org-1"})
    assert {"site_id": {"$in": ["site-A"]}} in out["$or"]


def test_locked_staff_requesting_forbidden_site_403s():
    u = _user(allowed_site_ids=["site-A"])
    with pytest.raises(HTTPException) as exc:
        apply_site_lock(u, "site-Z", {"organization_id": "org-1"})
    assert exc.value.status_code == 403
    assert "access" in exc.value.detail.lower()


# ─── filter merging ─────────────────────────────────────────────────
def test_base_filter_keys_preserved():
    u = _user(allowed_site_ids=["site-A"])
    out = apply_site_lock(
        u, None, {"organization_id": "org-1", "status": "open"},
    )
    assert out["organization_id"] == "org-1"
    assert out["status"] == "open"
    assert "$or" in out
