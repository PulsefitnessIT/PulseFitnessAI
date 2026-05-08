"""End-to-end tests for Memberships Phase 1 — promo codes, trials,
courses, packs with expiry, and bundles.

These tests hit the public API surface (so they exercise auth, validation,
Stripe coupon provisioning, etc.) using the Phase-1 operator account.

Run with:  cd /app/backend && python -m pytest tests/test_memberships_phase1.py -v
"""
import os
import time

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # In CI the backend is reachable over the preview URL; if running on the
    # box itself fall back to localhost.
    BASE_URL = "http://localhost:8001"

API = f"{BASE_URL.rstrip('/')}/api"

OPERATOR = {
    "email": "lee.somers@pulsefitness.com",
    "password": "TempPass123!",
}


def _login(creds: dict) -> str:
    r = requests.post(f"{API}/auth/login", json=creds, timeout=10)
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["token"]


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ───────────────────────── Promo codes ─────────────────────────


def test_promo_create_validate_archive_flow():
    token = _login(OPERATOR)
    h = _hdr(token)
    suffix = str(int(time.time()))[-6:]
    code = f"PYTEST{suffix}"

    # 1. List baseline
    r = requests.get(f"{API}/memberships/promo-codes", headers=h, timeout=10)
    assert r.status_code == 200
    initial = r.json().get("count", 0)

    # 2. Create with missing discount → 400
    r = requests.post(f"{API}/memberships/promo-codes", headers=h,
                      json={"code": code, "name": "Bad"}, timeout=10)
    assert r.status_code == 400, r.text

    # 3. Create both percent and amount → 400
    r = requests.post(f"{API}/memberships/promo-codes", headers=h,
                      json={"code": code, "name": "Bad",
                            "percent_off": 10, "amount_off_pence": 500},
                      timeout=10)
    assert r.status_code == 400, r.text

    # 4. Valid create — Stripe will provision the coupon + promo
    r = requests.post(f"{API}/memberships/promo-codes", headers=h,
                      json={"code": code, "name": "Pytest 25% off",
                            "percent_off": 25, "duration": "once"},
                      timeout=20)
    assert r.status_code == 200, r.text
    promo = r.json()["promo_code"]
    assert promo["code"] == code
    assert promo["stripe_coupon_id"]
    assert promo["stripe_promotion_code_id"]
    promo_id = promo["id"]

    # 5. Duplicate code in same org → 409
    r = requests.post(f"{API}/memberships/promo-codes", headers=h,
                      json={"code": code, "name": "Dup", "percent_off": 10},
                      timeout=15)
    assert r.status_code == 409, r.text

    # 6. List shows it
    r = requests.get(f"{API}/memberships/promo-codes", headers=h, timeout=10)
    assert r.status_code == 200
    assert r.json()["count"] == initial + 1

    # 7. Validate against bogus plan_id → 404
    r = requests.post(f"{API}/memberships/promo-codes/validate", headers=h,
                      json={"code": code, "plan_id": "no-such-plan"}, timeout=10)
    assert r.status_code == 404, r.text

    # 8. Validate with bogus code → 400
    r = requests.post(f"{API}/memberships/promo-codes/validate", headers=h,
                      json={"code": "DOESNOTEXIST", "plan_id": "x"}, timeout=10)
    assert r.status_code == 400, r.text

    # 9. Redemptions endpoint returns empty list (we haven't redeemed)
    r = requests.get(f"{API}/memberships/promo-codes/{promo_id}/redemptions",
                     headers=h, timeout=10)
    assert r.status_code == 200
    assert r.json()["count"] == 0

    # 10. Patch a non-Stripe-locked field
    r = requests.patch(f"{API}/memberships/promo-codes/{promo_id}", headers=h,
                       json={"name": "Pytest renamed"}, timeout=10)
    assert r.status_code == 200

    # 11. Archive — Stripe-side deactivate + DB flag flip
    r = requests.delete(f"{API}/memberships/promo-codes/{promo_id}",
                        headers=h, timeout=15)
    assert r.status_code == 200

    # 12. List excludes archived by default
    r = requests.get(f"{API}/memberships/promo-codes", headers=h, timeout=10)
    assert all(p["id"] != promo_id for p in r.json().get("promo_codes", []))

    # 13. include_archived=true now shows it
    r = requests.get(
        f"{API}/memberships/promo-codes?include_archived=true",
        headers=h, timeout=10,
    )
    assert any(p["id"] == promo_id for p in r.json().get("promo_codes", []))


def test_promo_unauthenticated_blocked():
    """All promo-code endpoints must require auth — no anonymous access."""
    r = requests.get(f"{API}/memberships/promo-codes", timeout=10)
    assert r.status_code in (401, 403)
    r = requests.post(f"{API}/memberships/promo-codes", json={}, timeout=10)
    assert r.status_code in (401, 403)
    r = requests.post(f"{API}/memberships/promo-codes/validate",
                      json={"code": "X", "plan_id": "Y"}, timeout=10)
    assert r.status_code in (401, 403)
