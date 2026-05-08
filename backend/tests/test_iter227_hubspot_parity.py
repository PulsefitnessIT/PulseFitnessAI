"""Iter 227 — HubSpot Parity Audit backend tests."""
from __future__ import annotations

import os

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
def admin_headers() -> dict:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture(scope="module")
def operator_headers() -> dict:
    return {"Authorization": f"Bearer {_login('lee.somers@pulsefitness.com', 'TempPass123!')}"}


def test_parity_requires_master_admin(operator_headers):
    r = requests.get(f"{API_BASE}/master-admin/hubspot-parity", headers=operator_headers, timeout=10)
    assert r.status_code == 403


def test_parity_shape_and_summary(admin_headers):
    r = requests.get(f"{API_BASE}/master-admin/hubspot-parity", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "summary" in body
    assert "features" in body
    s = body["summary"]
    for k in ("last_audited", "hubspot_baseline", "total_features", "counts", "coverage_pct"):
        assert k in s
    # At least 60 curated features — the matrix is meant to be meaty.
    assert s["total_features"] >= 60
    # Coverage should be a sensible percentage.
    assert 0 <= s["coverage_pct"] <= 100
    # Sum of counts matches total.
    counts = s["counts"]
    assert sum(counts.values()) == s["total_features"]


def test_parity_feature_row_shape(admin_headers):
    r = requests.get(f"{API_BASE}/master-admin/hubspot-parity", headers=admin_headers, timeout=15)
    features = r.json()["features"]
    required_keys = {"id", "category", "feature", "hubspot_tier",
                     "our_status", "our_implementation", "gap_notes", "priority"}
    for f in features:
        missing = required_keys - f.keys()
        assert not missing, f"feature {f.get('id')} missing keys: {missing}"
        assert f["our_status"] in ("shipped", "partial", "missing", "not_planned")


def test_parity_ids_unique(admin_headers):
    r = requests.get(f"{API_BASE}/master-admin/hubspot-parity", headers=admin_headers, timeout=15)
    features = r.json()["features"]
    ids = [f["id"] for f in features]
    assert len(ids) == len(set(ids)), "duplicate feature ids"


def test_parity_known_shipped_features_present(admin_headers):
    """Sanity — Contacts, Quotes, Email Marketing, Lead Scoring should be marked shipped."""
    r = requests.get(f"{API_BASE}/master-admin/hubspot-parity", headers=admin_headers, timeout=15)
    by_id = {f["id"]: f for f in r.json()["features"]}
    for fid in ("crm-contacts", "crm-quotes", "mkt-email-marketing", "mkt-lead-scoring", "ops-mfa"):
        assert fid in by_id, f"missing feature id: {fid}"
        assert by_id[fid]["our_status"] == "shipped", f"{fid} should be shipped"


def test_parity_covers_both_hubs(admin_headers):
    """Audit must span CRM Core + Marketing categories at minimum."""
    r = requests.get(f"{API_BASE}/master-admin/hubspot-parity", headers=admin_headers, timeout=15)
    cats = {f["category"] for f in r.json()["features"]}
    assert "CRM Core" in cats
    assert any(c.startswith("Marketing") for c in cats), f"missing Marketing categories: {cats}"
