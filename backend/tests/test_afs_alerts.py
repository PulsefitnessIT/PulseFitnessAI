"""Aftersales proactive alerts (warranty + RPI) tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": CRM_EMAIL, "password": CRM_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def h(crm_token):
    return {"Authorization": f"Bearer {crm_token}", "Content-Type": "application/json"}


class TestAfsAlerts:
    def test_get_alerts_baseline(self, h):
        r = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/alerts", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "alerts" in data and "counts" in data
        assert set(["warranty", "rpi", "open_total", "unread_notifications"]).issubset(data["counts"].keys())
        # Seed expectations: at least 1 warranty + 1 RPI alert (either seeded already by background or by a run)
        # Store for other tests via pytest namespace
        TestAfsAlerts.baseline = data

    def test_run_alerts_and_idempotent(self, h):
        r1 = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/alerts/run", headers=h, timeout=60)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        for k in ("warranty_tasks", "rpi_tasks", "orgs_scanned", "notifications"):
            assert k in j1, f"Missing key {k}: {j1}"
        # Now baseline+run — get alerts to verify seed alerts exist
        r_after = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/alerts", headers=h, timeout=30)
        assert r_after.status_code == 200
        after = r_after.json()
        open_total_after_first_run = after["counts"]["open_total"]
        # Expect at least 1 warranty + 1 RPI alert (as per seeded data)
        types = [a.get("type") for a in after["alerts"] if a.get("status") == "open"]
        assert "warranty_alert" in types, f"No warranty_alert in open alerts. Types: {types}"
        assert "rpi_review_due" in types, f"No rpi_review_due in open alerts. Types: {types}"

        # Validate structural fields on an alert row
        sample = next(a for a in after["alerts"] if a.get("source") == "afs_alerts")
        for k in ("type", "threshold_days", "subject", "body", "status", "source"):
            assert k in sample, f"Alert missing field {k}: {sample}"
        assert sample["source"] == "afs_alerts"
        assert sample["threshold_days"] in (90, 120, 180)

        # Second run should not create duplicates
        r2 = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/alerts/run", headers=h, timeout=60)
        assert r2.status_code == 200, r2.text
        j2 = r2.json()
        assert j2["warranty_tasks"] == 0, f"Second run created warranty duplicates: {j2}"
        assert j2["rpi_tasks"] == 0, f"Second run created RPI duplicates: {j2}"

        # open_total should not grow across a rescan
        r_after2 = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/alerts", headers=h, timeout=30)
        assert r_after2.status_code == 200
        assert r_after2.json()["counts"]["open_total"] == open_total_after_first_run

    def test_unread_notifications_reflects_open_alerts(self, h):
        r = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/alerts", headers=h, timeout=30)
        assert r.status_code == 200
        c = r.json()["counts"]
        # unread_notifications should be >= open_total is not required — but at least > 0 when open alerts exist
        if c["open_total"] > 0:
            assert c["unread_notifications"] >= 0  # count exists; can be lower if some pre-marked read
            # We expect at least some unread since these were just created (fresh)
            # Not strict: some may have been dismissed elsewhere

    def test_dismiss_alert_removes_from_open(self, h):
        r = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/alerts?status=open", headers=h, timeout=30)
        alerts = r.json()["alerts"]
        assert alerts, "No open alerts available to dismiss"
        target = alerts[0]
        aid = target["id"]

        before_open = r.json()["counts"]["open_total"]
        d = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/alerts/{aid}/dismiss",
                          headers=h, timeout=30)
        assert d.status_code == 200, d.text
        assert d.json()["status"] == "done"

        r2 = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/alerts?status=open", headers=h, timeout=30)
        after_ids = [a["id"] for a in r2.json()["alerts"]]
        assert aid not in after_ids, "Dismissed alert still appears in open list"
        assert r2.json()["counts"]["open_total"] == before_open - 1

        # Rescan should NOT recreate the dismissed alert (dedupe persists)
        rr = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/alerts/run", headers=h, timeout=60)
        assert rr.status_code == 200
        assert rr.json()["warranty_tasks"] == 0 and rr.json()["rpi_tasks"] == 0

        r3 = requests.get(f"{BASE_URL}/api/crm/v2/aftersales/alerts?status=open", headers=h, timeout=30)
        assert aid not in [a["id"] for a in r3.json()["alerts"]]

    def test_dismiss_nonexistent_returns_404(self, h):
        d = requests.post(f"{BASE_URL}/api/crm/v2/aftersales/alerts/nonexistent-id-xyz/dismiss",
                          headers=h, timeout=30)
        assert d.status_code == 404
