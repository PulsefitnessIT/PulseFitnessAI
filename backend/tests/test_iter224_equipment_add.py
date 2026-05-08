"""Iter 224 — Equipment Add overhaul backend tests.

Covers:
 - GET /api/equipment/manufacturers returns the curated brand list with
   stable display names + domains.
 - The list contains the post-meeting UK additions (Origin, Watson, Hoist,
   Indigo, Physical Company, Wattbike, Eleiko).
 - Display overrides handle awkward casing (BH Fitness, Concept2, StairMaster).
 - The list is alphabetically sorted.
 - Aliases collapse to one entry per domain (Matrix Fitness only appears once).
 - POST /api/equipment accepts manufacturer + SLA + date fields and
   round-trips them via GET /api/equipment.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

API_BASE = os.environ.get("API_BASE") or (
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=", 1)[1].split("\n", 1)[0].strip()
    + "/api"
)

# ---------- shared helpers ----------

def _login(email: str, password: str) -> str:
    headers = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only-2026"}
    r = requests.post(f"{API_BASE}/auth/login", json={"email": email, "password": password}, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def operator_token() -> str:
    return _login("lee.somers@pulsefitness.com", "TempPass123!")


# ---------- /equipment/manufacturers ----------

def test_manufacturers_endpoint_public_and_returns_curated_list():
    """Endpoint is unauthenticated (frontend dropdown is shown pre-org-load)."""
    r = requests.get(f"{API_BASE}/equipment/manufacturers", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "manufacturers" in body
    assert "count" in body
    assert body["count"] == len(body["manufacturers"])
    # Sanity floor — we ship at least 40 brands.
    assert body["count"] >= 40, f"expected >=40 brands, got {body['count']}"


def test_manufacturers_includes_post_meeting_uk_additions():
    r = requests.get(f"{API_BASE}/equipment/manufacturers", timeout=10)
    names = {m["name"] for m in r.json()["manufacturers"]}
    expected = {
        "Origin Fitness", "Watson Gym Equipment", "Hoist Fitness",
        "Indigo Fitness", "Physical Company", "Wattbike", "Eleiko",
        "Pulse Fitness", "Life Fitness", "Technogym", "Matrix Fitness",
    }
    missing = expected - names
    assert not missing, f"missing curated brands: {missing}"


def test_manufacturers_display_overrides_applied():
    r = requests.get(f"{API_BASE}/equipment/manufacturers", timeout=10)
    names = {m["name"] for m in r.json()["manufacturers"]}
    # These would render incorrectly under naive title-case.
    assert "BH Fitness" in names, "expected 'BH Fitness' (not 'Bh Fitness')"
    assert "Concept2" in names, "expected 'Concept2' (no space)"
    assert "StairMaster" in names, "expected 'StairMaster' camel-case"
    assert "Force USA" in names, "expected 'Force USA'"


def test_manufacturers_alphabetically_sorted():
    r = requests.get(f"{API_BASE}/equipment/manufacturers", timeout=10)
    names = [m["name"] for m in r.json()["manufacturers"]]
    assert names == sorted(names, key=str.lower), "manufacturers not alpha-sorted"


def test_manufacturers_aliases_collapse_to_one_per_domain():
    r = requests.get(f"{API_BASE}/equipment/manufacturers", timeout=10)
    items = r.json()["manufacturers"]
    domains = [m["domain"] for m in items]
    assert len(domains) == len(set(domains)), "duplicate domains — aliases not collapsed"
    # Matrix Fitness has both 'matrix' and 'matrix fitness' aliases. Should appear once.
    matrix_rows = [m for m in items if m["domain"] == "matrixfitness.com"]
    assert len(matrix_rows) == 1
    assert matrix_rows[0]["name"] == "Matrix Fitness"


# ---------- POST /api/equipment with new fields ----------

def test_create_equipment_with_curated_manufacturer_and_sla(operator_token):
    """Round-trip — create equipment with all iter 224 fields set."""
    headers = {"Authorization": f"Bearer {operator_token}"}
    nonce = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Iter224 Test Bike {nonce}",
        "equipment_type": "Spin Bike",
        "manufacturer": "Wattbike",
        "model": "Atom",
        "serial_number": f"WB-{nonce}",
        "location": "Studio A",
        "purchase_date": "2025-09-01",
        "warranty_expiry": "2027-09-01",
        "sla_response_time": "48h",
        "sla_contract_ref": f"CTR-{nonce}",
        "sla_expiry": "2026-09-01",
        "notes": "iter 224 happy-path test",
    }
    r = requests.post(f"{API_BASE}/equipment", json=payload, headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["manufacturer"] == "Wattbike"
    assert created["sla_response_time"] == "48h"
    assert created["sla_expiry"] == "2026-09-01"
    eq_id = created["id"]

    # Read back via GET.
    g = requests.get(f"{API_BASE}/equipment/{eq_id}", headers=headers, timeout=10)
    assert g.status_code == 200
    fetched = g.json()
    for k in ("manufacturer", "sla_response_time", "sla_contract_ref", "sla_expiry",
              "purchase_date", "warranty_expiry"):
        assert fetched[k] == payload[k], f"mismatch on {k}: {fetched[k]} vs {payload[k]}"

    # Cleanup so re-runs stay clean.
    requests.delete(f"{API_BASE}/equipment/{eq_id}", headers=headers, timeout=10)


def test_create_equipment_other_manufacturer_freetext_persists(operator_token):
    """A custom (non-curated) manufacturer string is stored verbatim."""
    headers = {"Authorization": f"Bearer {operator_token}"}
    nonce = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Iter224 Custom Brand {nonce}",
        "equipment_type": "Cable Machine",
        "manufacturer": "Bespoke Iron Works Ltd",
        "sla_response_time": "Next business day",
    }
    r = requests.post(f"{API_BASE}/equipment", json=payload, headers=headers, timeout=15)
    assert r.status_code == 200
    created = r.json()
    assert created["manufacturer"] == "Bespoke Iron Works Ltd"
    assert created["sla_response_time"] == "Next business day"
    requests.delete(f"{API_BASE}/equipment/{created['id']}", headers=headers, timeout=10)
