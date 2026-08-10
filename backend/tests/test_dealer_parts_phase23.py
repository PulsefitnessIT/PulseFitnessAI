"""Dealer Parts Phase 2 & 3 backend tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-eng-booking.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

STAFF_EMAIL = "owner@isodemo.com"
STAFF_PASS = "IsoDemo123!"
DEALER_EMAIL = "portal2@fitline.test"
DEALER_PASS = "DealerDemo123!"
FITLINE_DEALER_ID = "5e7fc632-eab1-4d6a-ad54-42d96b459f5c"
MATCHED_REF = "305H-ZZY"


def _login(email, pw, retries=3):
    last = None
    for i in range(retries):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
        if r.status_code == 200:
            return r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")
        last = r
        if r.status_code == 429:
            time.sleep(40)
        else:
            time.sleep(2)
    raise RuntimeError(f"Login failed {email}: {last.status_code} {last.text[:200]}")


@pytest.fixture(scope="session")
def staff_token():
    return _login(STAFF_EMAIL, STAFF_PASS)


@pytest.fixture(scope="session")
def dealer_token():
    time.sleep(2)
    return _login(DEALER_EMAIL, DEALER_PASS)


@pytest.fixture(scope="session")
def staff_headers(staff_token):
    return {"Authorization": f"Bearer {staff_token}"}


@pytest.fixture(scope="session")
def dealer_headers(dealer_token):
    return {"Authorization": f"Bearer {dealer_token}"}


# ─── PHASE 2 — machine matching ────────────────────────────────────
class TestMatchMachine:
    def test_exact_ref(self, staff_headers):
        r = requests.get(f"{API}/dealer-parts/data/match-machine", params={"q": MATCHED_REF}, headers=staff_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["match"] is not None
        assert j["match"]["top_level_ref"] == MATCHED_REF
        assert j["match"]["method"] == "exact_ref"
        assert "alternatives" in j and isinstance(j["alternatives"], list)

    def test_garbage(self, staff_headers):
        r = requests.get(f"{API}/dealer-parts/data/match-machine", params={"q": "ZZZ-NOPE-000"}, headers=staff_headers)
        assert r.status_code == 200
        j = r.json()
        assert j["match"] is None
        assert "alternatives" in j


# ─── PHASE 2 — recommend ───────────────────────────────────────────
class TestRecommend:
    def test_happy_path(self, staff_headers):
        body = {"dealer_id": FITLINE_DEALER_ID, "order_value": 50000,
                "lines": [{"machine_ref": MATCHED_REF, "quantity": 3}]}
        r = requests.post(f"{API}/dealer-parts/data/recommend", json=body, headers=staff_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["allowance"] == 1250, f"allowance {j['allowance']}"
        assert j["over_allowance"] is False
        assert j["total_value"] > 0
        assert "id" in j
        pack = j["pack"]
        assert len(pack) == 1
        grp = pack[0]
        assert grp["machine_ref"] == MATCHED_REF
        items = grp["items"]
        # ~21 items expected
        assert 15 <= len(items) <= 30, f"items count {len(items)}"
        it = items[0]
        for f in ("part_sku", "priority", "recommended_qty", "original_qty",
                  "already_held", "unit_value", "value", "trend", "reason", "status"):
            assert f in it, f"missing field {f}"
        # fleet scaling: original_qty should reflect fleet_factor=3
        # base priorities >0; scaled = base*3, so at least one item original_qty >=3
        assert any(i["original_qty"] >= 3 for i in items)
        # store run id for follow-up
        pytest.rec_run_id = j["id"]

    def test_over_allowance(self, staff_headers):
        body = {"dealer_id": FITLINE_DEALER_ID, "order_value": 1000,
                "lines": [{"machine_ref": MATCHED_REF, "quantity": 3}]}
        r = requests.post(f"{API}/dealer-parts/data/recommend", json=body, headers=staff_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["allowance"] == 25.0
        assert j["over_allowance"] is True
        assert j["allowance_remaining"] < 0

    def test_unmatched_line(self, staff_headers):
        body = {"dealer_id": FITLINE_DEALER_ID, "order_value": 10000,
                "lines": [{"machine_ref": "NONEXIST-999", "quantity": 1},
                          {"machine_ref": MATCHED_REF, "quantity": 1}]}
        r = requests.post(f"{API}/dealer-parts/data/recommend", json=body, headers=staff_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert any(u["input_ref"] == "NONEXIST-999" for u in j["unmatched_lines"])
        # machine_lines has matched:false for that ref
        bad = [m for m in j["machine_lines"] if m["input_ref"] == "NONEXIST-999"]
        assert bad and bad[0]["matched"] is False
        # no pack entry for NONEXIST-999
        assert not any(p["machine_ref"] == "NONEXIST-999" for p in j["pack"])

    def test_duplicate_prevention_informational(self, staff_headers):
        """Duplicate prevention: check duplicates_avoided field exists; informational if 0."""
        body = {"dealer_id": FITLINE_DEALER_ID, "order_value": 50000,
                "lines": [{"machine_ref": MATCHED_REF, "quantity": 3}]}
        r = requests.post(f"{API}/dealer-parts/data/recommend", json=body, headers=staff_headers)
        j = r.json()
        assert "duplicates_avoided" in j
        # If any item has already_held>0 and status==duplicate_avoided or reduced qty, ensure counter increments
        for grp in j["pack"]:
            for it in grp["items"]:
                if it["already_held"] > 0 and it["recommended_qty"] < it["original_qty"]:
                    assert j["duplicates_avoided"] >= 1
                    return
        # No overlap: informational
        assert j["duplicates_avoided"] >= 0

    def test_missing_dealer_id(self, staff_headers):
        r = requests.post(f"{API}/dealer-parts/data/recommend", json={"order_value": 100, "lines": []}, headers=staff_headers)
        assert r.status_code == 400


# ─── PHASE 3 — monitoring ──────────────────────────────────────────
class TestMonitoring:
    def test_monitoring(self, staff_headers):
        r = requests.get(f"{API}/dealer-parts/data/monitoring", headers=staff_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        ins = j["insights"]
        for k in ("bom_missing_high_usage", "bom_never_used", "increasing_usage", "new_failure_trend", "sent_never_used"):
            assert k in ins
            assert "top" in ins[k] and isinstance(ins[k]["top"], list)
            assert "count" in ins[k]
        assert "value" in ins["sent_never_used"]
        assert "totals" in j
        for k in ("analysis_parts", "bom_components", "matched_bom_components"):
            assert k in j["totals"]
        # sanity: expected magnitudes
        assert ins["bom_missing_high_usage"]["count"] > 0
        assert ins["bom_never_used"]["count"] > 0


# ─── PHASE 3 — reports CSV ─────────────────────────────────────────
class TestReports:
    @pytest.mark.parametrize("report", ["most-used-since-2022", "parts-used-vs-bom-match",
                                         "unmatched-high-usage", "bom-no-usage"])
    def test_report_ok(self, staff_headers, report):
        r = requests.get(f"{API}/dealer-parts/data/reports/{report}.csv", headers=staff_headers)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        # has header row
        first_line = r.text.splitlines()[0] if r.text else ""
        assert "," in first_line and len(first_line) > 0

    def test_most_used_by_machine_missing_ref(self, staff_headers):
        r = requests.get(f"{API}/dealer-parts/data/reports/most-used-by-machine.csv", headers=staff_headers)
        assert r.status_code == 400

    def test_most_used_by_machine_ok(self, staff_headers):
        r = requests.get(f"{API}/dealer-parts/data/reports/most-used-by-machine.csv",
                         params={"top_level_ref": MATCHED_REF}, headers=staff_headers)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")

    def test_unknown_report(self, staff_headers):
        r = requests.get(f"{API}/dealer-parts/data/reports/not-a-report.csv", headers=staff_headers)
        assert r.status_code == 404


# ─── RBAC — dealer_user 403 ────────────────────────────────────────
class TestRBAC:
    def test_dealer_match_machine_blocked(self, dealer_headers):
        r = requests.get(f"{API}/dealer-parts/data/match-machine", params={"q": MATCHED_REF}, headers=dealer_headers)
        assert r.status_code == 403, f"got {r.status_code}"

    def test_dealer_recommend_blocked(self, dealer_headers):
        r = requests.post(f"{API}/dealer-parts/data/recommend",
                          json={"dealer_id": FITLINE_DEALER_ID, "order_value": 100, "lines": []},
                          headers=dealer_headers)
        assert r.status_code == 403

    def test_dealer_monitoring_blocked(self, dealer_headers):
        r = requests.get(f"{API}/dealer-parts/data/monitoring", headers=dealer_headers)
        assert r.status_code == 403

    def test_dealer_reports_blocked(self, dealer_headers):
        r = requests.get(f"{API}/dealer-parts/data/reports/most-used-since-2022.csv", headers=dealer_headers)
        assert r.status_code == 403
