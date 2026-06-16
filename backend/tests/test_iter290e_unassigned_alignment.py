"""Iter 290e — "Unassigned" count alignment.

The desk performance tile, the Cases-page KPI strip, and the
``/svc/cases?assigned=unassigned`` drill-down must all report the same
"unassigned open cases" number ("no engineer" = empty OR null/missing,
not just ``""``) so a desk agent never sees the count change when they
click through.
"""
import requests

from tests.conftest import API_BASE_URL


def _token():
    r = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        json={"email": "desk@pulsefitness.com", "password": "DeskAgent123!"}, timeout=20,
    )
    return r.json().get("token") if r.status_code == 200 else None


def test_unassigned_count_is_consistent_across_surfaces():
    token = _token()
    if not token:
        import pytest
        pytest.skip("desk agent not seeded")
    h = {"Authorization": f"Bearer {token}"}

    perf = requests.get(f"{API_BASE_URL}/api/service-desk/performance", headers=h, timeout=30).json()["unassigned"]
    kpi = requests.get(f"{API_BASE_URL}/api/svc/desk/summary", headers=h, timeout=30).json()["kpis"]["unassigned"]
    drill = requests.get(
        f"{API_BASE_URL}/api/svc/cases?assigned=unassigned&status=open&limit=1",
        headers=h, timeout=30,
    ).json().get("total")

    assert perf == kpi, f"dashboard tile ({perf}) must match Cases KPI ({kpi})"
    if drill is not None:
        assert perf == drill, f"dashboard tile ({perf}) must match drill-down list ({drill})"
