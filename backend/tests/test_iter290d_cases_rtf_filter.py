"""Iter 290d — Service Desk dashboard card interactivity.

The "Return to Fix" performance tile deep-links to the Cases queue with a
new ``rtf=1`` filter. Verifies the filter is accepted, composes with search
(``$and`` vs the search ``$or``), and only returns open RTF jobs.
"""
import requests

from tests.conftest import API_BASE_URL

PAUSED = {"paused_parts", "awaiting_parts", "paused_customer"}
TERMINAL = {"closed", "invoiced", "cancelled", "rejected"}


def _token():
    r = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        json={"email": "desk@pulsefitness.com", "password": "DeskAgent123!"}, timeout=20,
    )
    return r.json().get("token") if r.status_code == 200 else None


def test_rtf_filter_accepted_and_composes():
    token = _token()
    if not token:
        import pytest
        pytest.skip("desk agent not seeded")
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API_BASE_URL}/api/svc/cases?rtf=1", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    assert isinstance(r.json().get("cases"), list)
    # rtf + search must not 500 (they compose via $and / $or)
    r2 = requests.get(f"{API_BASE_URL}/api/svc/cases?rtf=1&search=zzz", headers=h, timeout=30)
    assert r2.status_code == 200, r2.text


def test_rtf_results_are_open_repeat_visit_jobs():
    token = _token()
    if not token:
        import pytest
        pytest.skip("desk agent not seeded")
    h = {"Authorization": f"Bearer {token}"}
    cases = requests.get(f"{API_BASE_URL}/api/svc/cases?rtf=1", headers=h, timeout=30).json()["cases"]
    for c in cases:
        assert c.get("status") not in TERMINAL, f"RTF must be open, got {c.get('status')}"
        # a returned case is RTF either by flag or by being parked for parts
        assert c.get("return_to_fix") or c.get("status") in PAUSED
