"""Iter 290f — "SLA at risk" alignment + mutual exclusivity.

"At risk" must mean *due soon but not yet breached* (a future resolution
target within SLA_RISK_WINDOW_HOURS), and must reconcile across the desk
performance tile, the Cases KPI strip and the /svc/cases?sla=at_risk
drill-down. It must never overlap with "breached".
"""
import requests

from tests.conftest import API_BASE_URL


def _token():
    r = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        json={"email": "desk@pulsefitness.com", "password": "DeskAgent123!"}, timeout=20,
    )
    return r.json().get("token") if r.status_code == 200 else None


def test_sla_buckets_reconcile_and_are_exclusive():
    token = _token()
    if not token:
        import pytest
        pytest.skip("desk agent not seeded")
    h = {"Authorization": f"Bearer {token}"}

    perf = requests.get(f"{API_BASE_URL}/api/service-desk/performance", headers=h, timeout=30).json()
    kpi = requests.get(f"{API_BASE_URL}/api/svc/desk/summary", headers=h, timeout=30).json()["kpis"]
    at_risk_drill = requests.get(f"{API_BASE_URL}/api/svc/cases?sla=at_risk&limit=1", headers=h, timeout=30).json().get("total")
    breached_drill = requests.get(f"{API_BASE_URL}/api/svc/cases?sla=breached&limit=1", headers=h, timeout=30).json().get("total")

    # dashboard tile == cases KPI for both buckets
    assert perf["sla_at_risk"] == kpi["sla_at_risk"], (perf["sla_at_risk"], kpi["sla_at_risk"])
    assert perf["sla_breached"] == kpi["sla_breached"], (perf["sla_breached"], kpi["sla_breached"])

    # and == the drill-down list totals
    if at_risk_drill is not None:
        assert perf["sla_at_risk"] == at_risk_drill, (perf["sla_at_risk"], at_risk_drill)
    if breached_drill is not None:
        assert perf["sla_breached"] == breached_drill, (perf["sla_breached"], breached_drill)


def test_at_risk_and_breached_do_not_overlap():
    token = _token()
    if not token:
        import pytest
        pytest.skip("desk agent not seeded")
    h = {"Authorization": f"Bearer {token}"}
    at_risk = requests.get(f"{API_BASE_URL}/api/svc/cases?sla=at_risk&limit=500", headers=h, timeout=30).json().get("cases", [])
    breached = requests.get(f"{API_BASE_URL}/api/svc/cases?sla=breached&limit=500", headers=h, timeout=30).json().get("cases", [])
    a = {c["id"] for c in at_risk}
    b = {c["id"] for c in breached}
    assert a.isdisjoint(b), f"a case cannot be both at-risk and breached: {a & b}"
