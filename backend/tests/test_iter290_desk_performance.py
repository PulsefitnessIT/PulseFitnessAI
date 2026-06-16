"""Iter 290 — Service Desk team-performance KPIs endpoint.

`GET /api/service-desk/performance` powers the redesigned dashboard
(FTF/RTF, SLA health, throughput, engineer leaderboard). Verifies the
endpoint authorises a desk agent and returns the full, well-typed shape.
"""
import requests

from tests.conftest import API_BASE_URL

DESK_EMAIL = "desk@pulsefitness.com"
DESK_PASSWORD = "DeskAgent123!"


def _desk_token():
    r = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        json={"email": DESK_EMAIL, "password": DESK_PASSWORD}, timeout=20,
    )
    if r.status_code != 200:
        return None
    return r.json().get("token")


def test_performance_requires_auth():
    r = requests.get(f"{API_BASE_URL}/api/service-desk/performance", timeout=20)
    assert r.status_code in (401, 403), r.status_code


def test_performance_shape_and_types():
    token = _desk_token()
    if not token:
        import pytest
        pytest.skip("desk agent account not seeded in this environment")
    r = requests.get(
        f"{API_BASE_URL}/api/service-desk/performance",
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    int_keys = [
        "open_cases", "rtf_open", "unassigned", "sla_breached", "sla_at_risk",
        "closed_7d", "ftf_count", "total_closed_30d", "active_engineers", "window_days",
    ]
    for k in int_keys:
        assert isinstance(d.get(k), int), f"{k} should be int, got {d.get(k)!r}"
    assert 0 <= d["ftf_rate"] <= 100
    assert 0 <= d["ftf_rate_prev"] <= 100
    assert isinstance(d["ftf_trend"], int)
    assert isinstance(d["avg_resolution_hours"], (int, float))
    assert isinstance(d["leaderboard"], list)
    # FTF can never exceed the jobs actually closed in the window
    assert d["ftf_count"] <= d["total_closed_30d"]
    for row in d["leaderboard"]:
        assert {"engineer_id", "name", "closed", "ftf", "ftf_rate", "photo_url"} <= set(row)
        assert 0 <= row["ftf_rate"] <= 100
        assert row["ftf"] <= row["closed"]
        assert row["name"], "leaderboard rows must carry a resolved engineer name"
