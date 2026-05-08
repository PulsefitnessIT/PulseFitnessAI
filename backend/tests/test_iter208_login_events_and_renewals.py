"""Login events + auto-renewal regression tests (iteration 208)."""
import requests
from conftest import _test_backend_url, rate_limit_bypass_headers


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


def test_login_events_list(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/login-events?limit=20", headers=_h(master_admin_token_session), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "events" in body and isinstance(body["events"], list)
    assert "trust_events" in body
    assert "stats" in body
    # Master admin is logging in for these tests, so we should always see at
    # least one successful login row.
    assert any(e.get("action") == "login" for e in body["events"])


def test_login_events_summary(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/login-events/summary", headers=_h(master_admin_token_session), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_hours"] == 24
    for k in ("success", "failure", "brute_force_signals"):
        assert isinstance(body[k], int)


def test_login_events_filters_by_email(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/master-admin/login-events?email=admin@gymaxisai.com&limit=20",
        headers=_h(master_admin_token_session), timeout=10,
    )
    assert r.status_code == 200
    for ev in r.json()["events"]:
        # Filter is case/space-normalised on the server.
        assert (ev.get("user_email") or "").lower() == "admin@gymaxisai.com"


def test_login_events_requires_master_admin(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/master-admin/login-events", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403


def test_run_renewals_is_safe_to_call(master_admin_token_session):
    base = _test_backend_url()
    r = requests.post(f"{base}/api/master-admin/billing/run-renewals", headers=_h(master_admin_token_session), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("processed", "invoices_created", "skipped", "errors"):
        assert k in body
    assert isinstance(body["errors"], list)


def test_run_renewals_requires_master_admin(pulse_pro_token):
    base = _test_backend_url()
    r = requests.post(f"{base}/api/master-admin/billing/run-renewals", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403
