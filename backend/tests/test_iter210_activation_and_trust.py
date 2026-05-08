"""Activation funnel + Trust page + Command palette regression (iter 210)."""
import requests
import os
import sys

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import _test_backend_url, rate_limit_bypass_headers


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def test_activation_funnel_returns_all_event_types(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/activation/funnel", headers=_h(master_admin_token_session), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["steps"], list)
    assert len(body["steps"]) >= 8  # 8 declared event_types
    # Each step has the required fields.
    for s in body["steps"]:
        for k in ("event_type", "label", "orgs", "pct"):
            assert k in s


def test_activation_funnel_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/activation/funnel", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403


def test_record_activation_event_idempotent(pulse_pro_token):
    base = _test_backend_url()
    payload = {"event_type": "first_member_added"}
    r1 = requests.post(f"{base}/api/activation/record", json=payload, headers=_h(pulse_pro_token), timeout=10)
    r2 = requests.post(f"{base}/api/activation/record", json=payload, headers=_h(pulse_pro_token), timeout=10)
    assert r1.status_code == 200 and r2.status_code == 200
    # Second call must not insert a duplicate.
    assert r2.json()["recorded"] is False


def test_record_activation_event_rejects_unknown(pulse_pro_token):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/activation/record",
        json={"event_type": "made_up_event"},
        headers=_h(pulse_pro_token), timeout=10,
    )
    assert r.status_code == 400


def test_record_activation_event_no_org_user_returns_no_op(master_admin_token_session):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/activation/record",
        json={"event_type": "first_login"},
        headers=_h(master_admin_token_session), timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    # Master admin has no organisation_id → endpoint returns recorded=False.
    assert body["recorded"] is False


def test_activation_per_org_endpoint(master_admin_token_session):
    """The per-org timeline endpoint should always return all 8 event types,
    each with `fired` true/false and `occurred_at` either iso or null."""
    base = _test_backend_url()
    # Pick any org id from the org list.
    orgs = requests.get(f"{base}/api/master-admin/organizations", headers=_h(master_admin_token_session), timeout=10).json()
    org_id = orgs.get("organizations", [{}])[0].get("id") if isinstance(orgs, dict) else None
    if not org_id:
        # Fallback to a known seeded id.
        org_id = "156c8dc4-8683-4cb4-8a74-facd811655ad"
    r = requests.get(f"{base}/api/master-admin/activation/org/{org_id}", headers=_h(master_admin_token_session), timeout=10)
    assert r.status_code == 200
    timeline = r.json()["timeline"]
    assert len(timeline) >= 8
    for row in timeline:
        assert "event_type" in row and "fired" in row
