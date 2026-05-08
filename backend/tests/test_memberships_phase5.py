"""End-to-end tests for Memberships Phase 5 — AI Insights layer.

Coverage:
  - GET /memberships/ai/demand-forecast    (deterministic, no LLM)
  - GET /memberships/ai/underperformers     (deterministic, no LLM)
  - GET /memberships/ai/pricing-recommendations  (LLM — schema check)
  - GET /memberships/ai/class-suggestions   (LLM — schema check)

Auth: operator JWT (lee.somers@pulsefitness.com). Anonymous calls 401/403.

Run with:  cd /app/backend && python -m pytest tests/test_memberships_phase5.py -v
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE_URL.rstrip('/')}/api"

OPERATOR = {
    "email": "lee.somers@pulsefitness.com",
    "password": "TempPass123!",
}


@pytest.fixture(scope="module")
def operator_token() -> str:
    r = requests.post(f"{API}/auth/login", json=OPERATOR, timeout=30)
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def hdr(operator_token: str) -> dict:
    return {"Authorization": f"Bearer {operator_token}"}


# ───────────────── 1. Demand forecast ─────────────────


def test_demand_forecast_unauthenticated_blocked():
    r = requests.get(f"{API}/memberships/ai/demand-forecast", timeout=30)
    assert r.status_code in (401, 403)


def test_demand_forecast_default_params(hdr):
    r = requests.get(f"{API}/memberships/ai/demand-forecast",
                     headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows" in body and isinstance(body["rows"], list)
    assert "count" in body
    assert "summary" in body
    assert {"demand_high_count", "demand_low_count",
            "high_confidence_count"} <= set(body["summary"].keys())
    # Each row, when present, has the predicted shape
    for row in body["rows"][:5]:
        assert "occurrence_id" in row
        assert "predicted_fill_pct" in row
        assert "current_fill_pct" in row
        assert row["confidence"] in ("high", "medium")


def test_demand_forecast_clamps_window(hdr):
    # weeks_back=1 should be rejected (ge=2)
    r = requests.get(f"{API}/memberships/ai/demand-forecast?weeks_back=1",
                     headers=hdr, timeout=30)
    assert r.status_code == 422
    # weeks_ahead=99 rejected (le=8)
    r = requests.get(f"{API}/memberships/ai/demand-forecast?weeks_ahead=99",
                     headers=hdr, timeout=30)
    assert r.status_code == 422


def test_demand_forecast_custom_params(hdr):
    r = requests.get(
        f"{API}/memberships/ai/demand-forecast?weeks_back=4&weeks_ahead=1",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 200
    p = r.json()["params"]
    assert p["weeks_back"] == 4 and p["weeks_ahead"] == 1


# ───────────────── 2. Underperformers ─────────────────


def test_underperformers_unauthenticated_blocked():
    r = requests.get(f"{API}/memberships/ai/underperformers", timeout=30)
    assert r.status_code in (401, 403)


def test_underperformers_default_params(hdr):
    r = requests.get(f"{API}/memberships/ai/underperformers",
                     headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows" in body and isinstance(body["rows"], list)
    assert "count" in body
    assert "params" in body
    p = body["params"]
    assert p["weeks"] == 4 and p["fill_threshold_pct"] == 50
    for row in body["rows"][:5]:
        assert "template_id" in row and "name" in row
        assert "avg_fill_pct" in row
        assert row["avg_fill_pct"] <= 50  # threshold default


def test_underperformers_custom_threshold(hdr):
    r = requests.get(
        f"{API}/memberships/ai/underperformers?weeks=2&fill_threshold_pct=40&min_occurrences=2",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["params"]["fill_threshold_pct"] == 40
    for row in body["rows"][:5]:
        assert row["avg_fill_pct"] <= 40


def test_underperformers_validates_bounds(hdr):
    # weeks=1 → 422 (ge=2)
    r = requests.get(f"{API}/memberships/ai/underperformers?weeks=1",
                     headers=hdr, timeout=30)
    assert r.status_code == 422
    # fill_threshold_pct=99 → 422 (le=90)
    r = requests.get(
        f"{API}/memberships/ai/underperformers?fill_threshold_pct=99",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 422


# ───────────────── 3. Pricing recommendations (LLM) ─────────────────


def test_pricing_recs_unauthenticated_blocked():
    r = requests.get(f"{API}/memberships/ai/pricing-recommendations",
                     timeout=30)
    assert r.status_code in (401, 403)


def test_pricing_recs_returns_strict_schema(hdr):
    """LLM call — accept either a 200 with valid schema, or a 503 if the
    LLM key is unavailable in the test environment. Both are healthy."""
    r = requests.get(f"{API}/memberships/ai/pricing-recommendations",
                     headers=hdr, timeout=120)
    if r.status_code == 503:
        # LLM unavailable — surface the reason, but don't fail the suite
        return
    assert r.status_code == 200, r.text
    body = r.json()
    assert "recommendations" in body and isinstance(body["recommendations"], list)
    # When org has plans, every rec should match schema
    for rec in body["recommendations"]:
        assert "plan_id" in rec
        assert "current_pence" in rec and isinstance(rec["current_pence"], int)
        assert "suggested_pence" in rec and isinstance(rec["suggested_pence"], int)
        assert rec["direction"] in ("raise", "hold", "lower")
        assert rec["confidence"] in ("high", "medium", "low")
    if "org_signals" in body:
        assert "fill_pct" in body["org_signals"]
        assert "waitlist_ratio_pct" in body["org_signals"]


# ───────────────── 4. New-class suggestions (LLM) ─────────────────


def test_class_suggestions_unauthenticated_blocked():
    r = requests.get(f"{API}/memberships/ai/class-suggestions", timeout=30)
    assert r.status_code in (401, 403)


def test_class_suggestions_returns_schema(hdr):
    r = requests.get(f"{API}/memberships/ai/class-suggestions",
                     headers=hdr, timeout=120)
    if r.status_code == 503:
        return  # LLM unavailable — acceptable in test envs
    assert r.status_code == 200, r.text
    body = r.json()
    assert "suggestions" in body and isinstance(body["suggestions"], list)
    for s in body["suggestions"]:
        assert "name" in s and isinstance(s["name"], str)
        assert s["confidence"] in ("high", "medium", "low")
