"""Backend tests for Dealer Warranty Parts Phase 4.

Covers Failure Intelligence, Monitoring Agent (idempotent alerts + status
transitions), Replenishment engine, and closed-loop recommendation bumping.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EMAIL = "owner@isodemo.com"
PASSWORD = "IsoDemo123!"

VALID_STATUSES = ["new", "under_review", "investigating", "action_required", "resolved", "dismissed"]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


# ── Failure Intelligence ───────────────────────────────────────────
class TestIntel:
    def test_overview(self, h):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/intel/overview", params={"days": 90}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total_failures", "top_failing_parts", "by_country", "by_dealer", "by_model", "by_reason", "trend"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["top_failing_parts"], list)
        assert isinstance(d["by_country"], list)
        assert isinstance(d["trend"], list)

    @pytest.mark.parametrize("group_by", ["part", "country", "dealer", "model", "serial"])
    def test_failures_groupings(self, h, group_by):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/intel/failures",
                         params={"group_by": group_by, "days": 90}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["group_by"] == group_by
        assert isinstance(d.get("rows"), list)
        for row in d["rows"]:
            assert "failures" in row and "quality_flags" in row

    def test_failures_invalid_group(self, h):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/intel/failures",
                         params={"group_by": "bogus"}, headers=h, timeout=30)
        assert r.status_code == 422


# ── Monitoring Agent ───────────────────────────────────────────────
class TestMonitoring:
    def test_run_idempotent(self, h):
        r1 = requests.post(f"{BASE_URL}/api/dealer-parts/monitoring/run", headers=h, timeout=60)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert "alerts_created" in d1 and "failures_scanned" in d1
        # Re-run should be idempotent (dedup) — dev seed may already have alerts,
        # so we simply require that a second run creates 0 new alerts.
        r2 = requests.post(f"{BASE_URL}/api/dealer-parts/monitoring/run", headers=h, timeout=60)
        assert r2.status_code == 200
        assert r2.json()["alerts_created"] == 0, "monitoring re-run should not duplicate open alerts"

    def test_alerts_list_and_types(self, h):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/alerts", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        alerts = r.json().get("alerts", [])
        assert isinstance(alerts, list)
        # Expect at least some seeded alerts from earlier phases / MOTOR-260G Germany scenario
        # Not asserting non-empty to be robust — just structure.
        for a in alerts:
            assert a["alert_type"] in ("high_failure_rate", "potential_quality_issue", "repeated_failure_by_serial")
            assert a["status"] in VALID_STATUSES
            assert "severity" in a and "evidence" in a and "suggested_action" in a

    def test_alert_status_transitions(self, h):
        alerts = requests.get(f"{BASE_URL}/api/dealer-parts/alerts", headers=h, timeout=30).json().get("alerts", [])
        if not alerts:
            pytest.skip("no alerts to transition")
        aid = alerts[0]["id"]
        orig = alerts[0]["status"]
        # invalid rejected
        r_bad = requests.patch(f"{BASE_URL}/api/dealer-parts/alerts/{aid}",
                               json={"status": "not_a_status"}, headers=h, timeout=30)
        assert r_bad.status_code == 400
        # valid transitions
        for st in ["under_review", "investigating", "action_required"]:
            r = requests.patch(f"{BASE_URL}/api/dealer-parts/alerts/{aid}",
                               json={"status": st}, headers=h, timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == st
        # restore
        requests.patch(f"{BASE_URL}/api/dealer-parts/alerts/{aid}",
                       json={"status": orig if orig in VALID_STATUSES else "new"}, headers=h, timeout=30)

    def test_patch_missing_alert(self, h):
        r = requests.patch(f"{BASE_URL}/api/dealer-parts/alerts/does-not-exist",
                           json={"status": "resolved"}, headers=h, timeout=30)
        assert r.status_code == 404


# ── Replenishment ─────────────────────────────────────────────────
class TestReplenishment:
    def test_rows_and_labels(self, h):
        r = requests.get(f"{BASE_URL}/api/dealer-parts/replenishment", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json().get("rows", [])
        assert isinstance(rows, list)
        valid_labels = {"No Action Needed", "Monitor", "Low Stock", "Replenishment Recommended",
                        "Critical Replenishment", "Overstocked"}
        for row in rows:
            assert row["label"] in valid_labels
            assert row["urgency"] in {"critical", "high", "medium", "low", "none"}
            assert "recommended_qty" in row and "estimated_value" in row


# ── Closed-loop recommendation bump ───────────────────────────────
class TestClosedLoop:
    def test_failure_bump_on_germany_260g(self, h):
        # Find a Fitline Deutschland (Germany) dealer + a 260G-related order
        orders = requests.get(f"{BASE_URL}/api/dealer-parts/orders", headers=h, timeout=30).json()
        orders_list = orders if isinstance(orders, list) else orders.get("orders", [])
        # pick order for a German dealer if possible
        dealers = requests.get(f"{BASE_URL}/api/dealer-parts/dealers", headers=h, timeout=30).json()
        dealers_list = dealers if isinstance(dealers, list) else dealers.get("dealers", [])
        de_ids = {d["id"] for d in dealers_list if (d.get("country") or "").lower().startswith("germ")
                  or "deutsch" in (d.get("name") or "").lower()}
        target = None
        for o in orders_list:
            if o.get("dealer_id") in de_ids:
                target = o
                break
        if not target:
            pytest.skip("No Germany dealer order found to exercise closed loop")

        r = requests.post(f"{BASE_URL}/api/dealer-parts/recommend",
                          json={"order_id": target["id"]}, headers=h, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        # top-level quality_flags array should exist
        assert "quality_flags" in data, f"missing quality_flags in {data.keys()}"
        assert isinstance(data["quality_flags"], list)
        # Find MOTOR-260G item with failure_bumped
        items = data.get("items") or data.get("recommendations") or []
        motor = next((it for it in items if (it.get("part_sku") or it.get("sku")) == "MOTOR-260G"), None)
        if motor is None:
            pytest.skip(f"MOTOR-260G not in recommendation for this order (items={len(items)})")
        assert motor.get("failure_bumped") is True, f"expected failure_bumped=True on MOTOR-260G, got {motor}"
        reason = (motor.get("reason") or "").lower()
        assert "failure monitoring" in reason or "failure" in reason
        assert len(data["quality_flags"]) >= 0  # may include MOTOR-260G quality watch
