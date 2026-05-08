"""Iter 225 — Master Admin DB Viewer backend tests."""
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


# ──────── Auth ────────

def test_db_viewer_requires_master_admin(operator_headers):
    """Operator (non-master) gets 403 on every DB viewer endpoint."""
    for path in (
        "/master-admin/db/collections",
        "/master-admin/db/collections/users",
        "/master-admin/db/collections/users/export?format=json&confirm=true",
    ):
        r = requests.get(f"{API_BASE}{path}", headers=operator_headers, timeout=10)
        assert r.status_code == 403, f"{path} should 403 for non-master, got {r.status_code}: {r.text[:200]}"


def test_db_viewer_unauth_rejected():
    r = requests.get(f"{API_BASE}/master-admin/db/collections", timeout=10)
    assert r.status_code in (401, 403)


# ──────── List collections ────────

def test_list_collections_returns_sorted_with_counts(admin_headers):
    r = requests.get(f"{API_BASE}/master-admin/db/collections", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "collections" in body
    assert body["count"] == len(body["collections"])
    names = [c["name"] for c in body["collections"]]
    assert names == sorted(names), "collection list must be alphabetically sorted"
    # Sanity — a few core collections must exist.
    for required in ("users", "equipment", "issues"):
        assert required in names, f"missing core collection: {required}"
    # System collections are deny-listed.
    for forbidden in ("system.indexes", "system.users"):
        assert forbidden not in names


# ──────── Browse + redact ────────

def test_browse_users_redacts_password_field(admin_headers):
    r = requests.get(
        f"{API_BASE}/master-admin/db/collections/users?q=lee.somers&page_size=1",
        headers=admin_headers, timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    doc = body["docs"][0]
    # `password` field should be redacted.
    assert doc.get("password") == "[REDACTED]"
    # Non-sensitive fields should pass through.
    assert doc.get("email") == "lee.somers@pulsefitness.com"
    # Redacted-keys list is exposed for UI hint.
    assert "password" in body["redacted_keys"]


def test_browse_pagination(admin_headers):
    r = requests.get(
        f"{API_BASE}/master-admin/db/collections/users?page=1&page_size=5",
        headers=admin_headers, timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert len(body["docs"]) <= 5
    assert body["pages"] >= 1


def test_browse_invalid_collection_403(admin_headers):
    """Querying a system collection is blocked at API level."""
    r = requests.get(
        f"{API_BASE}/master-admin/db/collections/system.indexes",
        headers=admin_headers, timeout=10,
    )
    assert r.status_code == 403


# ──────── Export ────────

def test_export_requires_confirm_true(admin_headers):
    r = requests.get(
        f"{API_BASE}/master-admin/db/collections/users/export?format=json",
        headers=admin_headers, timeout=10,
    )
    assert r.status_code == 400
    assert "confirm" in r.text.lower()


def test_export_json_streams_ndjson(admin_headers):
    r = requests.get(
        f"{API_BASE}/master-admin/db/collections/users/export?format=json&confirm=true&q=lee.somers",
        headers=admin_headers, timeout=20,
    )
    assert r.status_code == 200
    assert "x-export-count" in {k.lower() for k in r.headers}
    assert r.headers["content-type"].startswith("application/x-ndjson")
    # Each line must be parseable JSON, password redacted.
    import json as _json
    lines = [l for l in r.text.strip().split("\n") if l]
    assert len(lines) >= 1
    parsed = _json.loads(lines[0])
    assert parsed.get("password") == "[REDACTED]"


def test_export_csv_has_headers_and_rows(admin_headers):
    r = requests.get(
        f"{API_BASE}/master-admin/db/collections/users/export?format=csv&confirm=true&q=lee.somers",
        headers=admin_headers, timeout=20,
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    # CSV header row should mention `email` somewhere.
    assert "email" in body.split("\n", 1)[0]
    # And include the redacted token in any password column.
    assert "[REDACTED]" in body
