"""Iter 217 — unified Gym Health Score endpoint.

Pins the merged contract of `/api/gym-health-score` after the
previously-duplicate "Pulse Score" route was folded into it.

Key invariants:

  * Endpoint still requires auth (401 otherwise).
  * Response carries the canonical 7-metric breakdown.
  * Every metric's `max` is positive; the sum of all `max` values
    is exactly 100 (otherwise the composite math is wrong).
  * The two h217-new metrics — `fault_freshness` and `sla_adherence`
    — are present.
  * `score`, `rating`, `color` returned at the top level.
  * No Mongo `_id` leaks anywhere in the payload.
  * The dead `/api/pulse-score/me` route is gone.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://staffing-ops-preview.preview.emergentagent.com",
)

EXPECTED_BREAKDOWN_KEYS = {
    "fault_management",
    "fault_freshness",   # NEW in iter 217
    "self_fix_rate",
    "audit_coverage",
    "warranty_health",
    "sla_adherence",     # NEW in iter 217
    "ai_knowledge",
}


def _login(email: str, password: str) -> str:
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()["token"]


# ── 401 without auth ────────────────────────────────────────────


def test_gym_health_score_requires_auth() -> None:
    with httpx.Client(timeout=15.0) as c:
        r = c.get(f"{BASE}/api/gym-health-score")
    assert r.status_code in (401, 403), f"expected unauth, got {r.status_code}"


# ── Dead route confirmed gone ──────────────────────────────────


def test_old_pulse_score_route_is_gone() -> None:
    """h217 merged the duplicate route. /api/pulse-score/me must 404."""
    token = _login("jack.ottey@thirdspace.london", "Test123!")
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/pulse-score/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 404, f"expected 404, got {r.status_code}"


# ── Happy path ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    token = _login("jack.ottey@thirdspace.london", "Test123!")
    with httpx.Client(timeout=15.0) as c:
        r = c.get(
            f"{BASE}/api/gym-health-score",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200, r.text
    return r.json()


def test_score_is_int_0_to_100(payload: dict[str, Any]) -> None:
    s = payload["score"]
    assert isinstance(s, int)
    assert 0 <= s <= 100


def test_all_seven_breakdown_keys_present(payload: dict[str, Any]) -> None:
    if payload.get("not_ready"):
        pytest.skip("tenant in not-ready state — breakdown not returned")
    assert set(payload["breakdown"].keys()) == EXPECTED_BREAKDOWN_KEYS


def test_breakdown_maxes_sum_to_100(payload: dict[str, Any]) -> None:
    if payload.get("not_ready"):
        pytest.skip("tenant in not-ready state — breakdown not returned")
    total = sum(v["max"] for v in payload["breakdown"].values())
    assert total == 100, f"breakdown maxes summed to {total}, expected 100"


def test_each_metric_score_within_its_max(payload: dict[str, Any]) -> None:
    if payload.get("not_ready"):
        pytest.skip("tenant in not-ready state — breakdown not returned")
    for key, comp in payload["breakdown"].items():
        assert isinstance(comp["score"], int), f"{key}: score not int"
        assert 0 <= comp["score"] <= comp["max"], (
            f"{key}: score {comp['score']} out of 0..{comp['max']}"
        )
        assert isinstance(comp.get("detail"), str)


def test_h217_new_metrics_present(payload: dict[str, Any]) -> None:
    """Pin the two iter-217-new metrics explicitly so neither can
    silently regress out of the breakdown."""
    if payload.get("not_ready"):
        pytest.skip("tenant in not-ready state")
    assert "fault_freshness" in payload["breakdown"]
    assert "sla_adherence" in payload["breakdown"]
    assert payload["breakdown"]["fault_freshness"]["max"] == 10
    assert payload["breakdown"]["sla_adherence"]["max"] == 15


def test_rating_band_thresholds(payload: dict[str, Any]) -> None:
    if payload.get("not_ready"):
        pytest.skip("not-ready state")
    s, band = payload["score"], payload["rating"]
    if s >= 80:
        assert band == "Excellent"
    elif s >= 60:
        assert band == "Good"
    elif s >= 40:
        assert band == "Fair"
    elif s >= 20:
        assert band == "Needs Attention"
    else:
        assert band == "Critical"


def test_no_mongo_id_leakage(payload: dict[str, Any]) -> None:
    """Defence-in-depth — pin that no Mongo `_id` escapes anywhere."""
    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            assert "_id" not in obj
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
    _walk(payload)
