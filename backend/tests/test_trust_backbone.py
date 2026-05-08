"""Tests for the Trust Backbone (Layer 1)."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"
MASTER_EMAIL = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PWD = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
PULSE_EMAIL = "lee.somers@pulsefitness.com"
PULSE_PWD = "TempPass123!"


from tests.conftest import rate_limit_bypass_headers


def _login(email, pwd):
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": pwd},
        headers=rate_limit_bypass_headers(),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["token"]


@pytest.fixture(scope="module")
def master_token():
    return _login(MASTER_EMAIL, MASTER_PWD)


@pytest.fixture(scope="module")
def master_headers(master_token):
    return {"Authorization": f"Bearer {master_token}"}


def test_overview_requires_master_admin():
    pulse_token = _login(PULSE_EMAIL, PULSE_PWD)
    r = requests.get(f"{API}/master-admin/trust/overview",
                     headers={"Authorization": f"Bearer {pulse_token}"}, timeout=10)
    assert r.status_code == 403, f"Pulse Pro user must get 403, got {r.status_code}"


def test_overview_shape(master_headers):
    r = requests.get(f"{API}/master-admin/trust/overview", headers=master_headers, timeout=10)
    assert r.status_code == 200
    d = r.json()
    for k in ("summary", "reliability", "integrations", "open_events", "self_heal_log", "generated_at"):
        assert k in d, f"missing key: {k}"
    for k in ("open", "acknowledged", "resolved_24h", "critical_open", "high_open"):
        assert k in d["summary"]
    assert d["reliability"]["reliability_pct"] >= 0
    assert d["reliability"]["reliability_pct"] <= 100
    assert isinstance(d["integrations"], list)
    assert len(d["integrations"]) >= 3


def test_seed_demo_creates_events(master_headers):
    r = requests.post(f"{API}/master-admin/trust/events/seed-demo", headers=master_headers, timeout=10)
    assert r.status_code == 200
    assert r.json().get("seeded", 0) >= 1

    # list endpoint surfaces them
    r = requests.get(f"{API}/master-admin/trust/events?limit=50", headers=master_headers, timeout=10)
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) >= 1
    # must have the core keys
    ev = events[0]
    for k in ("id", "type", "severity", "state", "created_at", "summary"):
        assert k in ev


def test_ack_and_resolve_flow(master_headers):
    # seed — idempotent
    requests.post(f"{API}/master-admin/trust/events/seed-demo", headers=master_headers, timeout=10)
    # pick the newest open event
    r = requests.get(f"{API}/master-admin/trust/events?state=open&limit=1",
                     headers=master_headers, timeout=10)
    events = r.json()["events"]
    if not events:
        pytest.skip("no open events to test ack/resolve flow")
    eid = events[0]["id"]

    # ack
    r = requests.post(f"{API}/master-admin/trust/events/{eid}/ack",
                      headers=master_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["state"] == "acknowledged"

    # ack again — now in acknowledged state, must 404 (only matches "open")
    r = requests.post(f"{API}/master-admin/trust/events/{eid}/ack",
                      headers=master_headers, timeout=10)
    assert r.status_code == 404

    # resolve
    r = requests.post(f"{API}/master-admin/trust/events/{eid}/resolve",
                      json={"note": "pytest"}, headers=master_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["state"] == "resolved"

    # resolve again — already resolved, must 404
    r = requests.post(f"{API}/master-admin/trust/events/{eid}/resolve",
                      json={"note": "x"}, headers=master_headers, timeout=10)
    assert r.status_code == 404


def test_list_filters(master_headers):
    # Make sure demo events exist
    requests.post(f"{API}/master-admin/trust/events/seed-demo", headers=master_headers, timeout=10)
    r = requests.get(f"{API}/master-admin/trust/events?severity=low&limit=20",
                     headers=master_headers, timeout=10)
    assert r.status_code == 200
    for ev in r.json()["events"]:
        assert ev["severity"] == "low"


def test_unknown_event_ack_404(master_headers):
    r = requests.post(f"{API}/master-admin/trust/events/{uuid.uuid4()}/ack",
                      headers=master_headers, timeout=10)
    assert r.status_code == 404


def test_diagnose_unknown_event_404(master_headers):
    r = requests.post(f"{API}/master-admin/trust/events/{uuid.uuid4()}/diagnose",
                      headers=master_headers, timeout=10)
    assert r.status_code == 404


def test_diagnose_requires_master_admin():
    pulse_token = _login(PULSE_EMAIL, PULSE_PWD)
    # Use a random id — we only care about the 403 gate, not 404
    r = requests.post(f"{API}/master-admin/trust/events/{uuid.uuid4()}/diagnose",
                      headers={"Authorization": f"Bearer {pulse_token}"}, timeout=10)
    assert r.status_code == 403


def test_dedupe_key_increments_occurrences(master_headers):
    """Calling record_trust_event twice with the same dedupe_key must result
    in one doc with occurrences=2, not two separate docs."""
    # Trigger via the seed endpoint twice — demo events use stable dedupe keys
    requests.post(f"{API}/master-admin/trust/events/seed-demo", headers=master_headers, timeout=10)
    requests.post(f"{API}/master-admin/trust/events/seed-demo", headers=master_headers, timeout=10)
    r = requests.get(f"{API}/master-admin/trust/events?limit=50", headers=master_headers, timeout=10)
    events = r.json()["events"]
    # At least one of the demo events must now have occurrences >= 2
    demo_events = [e for e in events if (e.get("dedupe_key") or "").startswith("demo.")]
    assert any(e.get("occurrences", 1) >= 2 for e in demo_events), \
        f"Expected dedupe to fold duplicates but occurrences were {[e.get('occurrences') for e in demo_events]}"
