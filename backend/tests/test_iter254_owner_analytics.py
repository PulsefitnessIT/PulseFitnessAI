"""Iter 254 — Owner Analytics dashboard (Service Desk › Insights › Analytics).

GET /api/svc/analytics/owner?from&to returns org-scoped:
- headline (cases, avg response/resolve hours, SLA rates)
- sla_by_priority (p1–p4, normalised from mixed-case live data)
- engineers (utilisation vs 8h-weekday capacity)
- revenue (engineer invoices + deduped invoiced quotes, avg per job)
- trend (weekly created/closed/SLA %)

Tenant isolation: a self-serve provider only sees their own org's numbers.
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()

MASTER_ADMIN = ("admin@gymaxisai.com", "MasterAdmin123!")
PROVIDER = ("sp.fe.1781277405@example.com", "Str0ngPass!23")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_requires_auth():
    r = requests.get(f"{BASE_URL}/api/svc/analytics/owner", timeout=20)
    assert r.status_code in (401, 403)


def test_rejects_inverted_range():
    h = _login(*MASTER_ADMIN)
    r = requests.get(f"{BASE_URL}/api/svc/analytics/owner",
                     params={"from": "2026-07-01", "to": "2026-06-01"}, headers=h, timeout=20)
    assert r.status_code == 400


def test_owner_analytics_shape_and_data():
    h = _login(*MASTER_ADMIN)
    r = requests.get(f"{BASE_URL}/api/svc/analytics/owner",
                     params={"from": "2026-03-14T00:00:00+00:00", "to": "2026-06-12T23:59:59+00:00"},
                     headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for key in ("headline", "sla_by_priority", "engineers", "revenue", "trend"):
        assert key in d
    hl = d["headline"]
    for k in ("cases_created", "cases_closed", "open_cases", "avg_response_h",
              "avg_resolve_h", "sla_response_rate", "sla_resolve_rate"):
        assert k in hl
    # Hub org has real history — these must be non-trivial.
    assert hl["cases_created"] > 0
    assert d["revenue"]["total"] >= 0
    assert set(d["sla_by_priority"].keys()) == {"p1", "p2", "p3", "p4"}
    # Mixed-case live priorities ('P2', 'medium') must be normalised into buckets.
    bucketed = sum(b["resolve_total"] + b["response_total"] for b in d["sla_by_priority"].values())
    assert bucketed > 0
    assert len(d["trend"]) >= 12  # ~13 weeks in a 90-day window
    for w in d["trend"]:
        assert {"week", "created", "closed", "sla_pct"} <= set(w.keys())
    for e in d["engineers"]:
        assert 0.0 <= e["utilisation_pct"] <= 1.0
        assert e["capacity_h"] > 0


def test_provider_is_tenant_scoped():
    h = _login(*PROVIDER)
    r = requests.get(f"{BASE_URL}/api/svc/analytics/owner", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    # Fresh provider org: must NOT see the hub org's 684 cases.
    assert d["headline"]["cases_created"] < 50
    assert d["revenue"]["total"] == 0
    names = [e["name"] for e in d["engineers"]]
    assert "Master Admin" not in names
