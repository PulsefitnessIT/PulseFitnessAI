"""Iter 217 — The Pulse Score endpoint.

Pins the contract of `/api/pulse-score/me`:

  * Auth required (401 without token).
  * Returns the canonical shape:
      { score, band, scope, components, generated_at }
  * `score` is an int 0-100.
  * `band` is one of {poor, fair, good, excellent} and matches
    the documented thresholds.
  * `components` includes all 5 sub-scores with their weights and
    the per-component detail blob (no `_id` ever leaks).
  * Weights sum to 1.0 (otherwise the composite math is wrong).
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://maintenance-hub-357.preview.emergentagent.com",
)
COMPONENT_KEYS = {
    "fault_freshness",
    "self_fix_rate",
    "audit_coverage",
    "warranty_health",
    "sla_adherence",
}


def _login(email: str, password: str) -> str:
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
        )
        r.raise_for_status()
        return r.json()["token"]


# ── 401 without auth ────────────────────────────────────────────


def test_pulse_score_requires_auth() -> None:
    with httpx.Client(timeout=15.0) as c:
        r = c.get(f"{BASE}/api/pulse-score/me")
    assert r.status_code in (401, 403), f"expected unauth, got {r.status_code}"


# ── Happy path ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    token = _login("jack.ottey@thirdspace.london", "Test123!")
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/pulse-score/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200, r.text
    return r.json()


def test_score_is_int_0_to_100(payload: dict[str, Any]) -> None:
    s = payload["score"]
    assert isinstance(s, int)
    assert 0 <= s <= 100


def test_band_matches_thresholds(payload: dict[str, Any]) -> None:
    s, band = payload["score"], payload["band"]
    if s >= 85:
        assert band == "excellent"
    elif s >= 70:
        assert band == "good"
    elif s >= 50:
        assert band == "fair"
    else:
        assert band == "poor"


def test_all_five_components_returned(payload: dict[str, Any]) -> None:
    components = payload["components"]
    assert set(components.keys()) == COMPONENT_KEYS
    for k, comp in components.items():
        assert isinstance(comp["score"], int)
        assert 0 <= comp["score"] <= 100
        assert isinstance(comp["weight"], (int, float))
        assert "detail" in comp


def test_weights_sum_to_one(payload: dict[str, Any]) -> None:
    total = sum(c["weight"] for c in payload["components"].values())
    assert abs(total - 1.0) < 0.001, f"weights summed to {total}, expected 1.0"


def test_no_mongo_id_leakage(payload: dict[str, Any]) -> None:
    """Defence-in-depth — pin that no Mongo `_id` ever escapes through
    the components' detail blobs."""
    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            assert "_id" not in obj
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
    _walk(payload)


def test_scope_block_present(payload: dict[str, Any]) -> None:
    scope = payload["scope"]
    assert "organization_id" in scope
    assert scope["organization_id"]
    # site_id may be None for org-level rollups
    assert "site_id" in scope
