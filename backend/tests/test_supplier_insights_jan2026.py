"""Backend tests for Supplier Insights (Pro/Full) + equipment supplier_id persistence.
Jan 2026 iteration."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api"
PRO = ("owner@isodemo.com", "IsoDemo123!")
LITE = ("lite.suptest@pulsedemo.test", "LiteSup123!")


def _login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def pro_token():
    return _login(*PRO)


@pytest.fixture(scope="module")
def lite_token():
    return _login(*LITE)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ── Supplier Insights endpoint ────────────────────────────────────
class TestSupplierInsights:
    def test_pro_insights_shape(self, pro_token):
        r = requests.get(f"{BASE}/suppliers/insights", headers=_h(pro_token), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("window_days") == 90
        assert "total_faults" in data
        assert isinstance(data.get("suppliers"), list)
        for row in data["suppliers"]:
            for k in ("supplier", "is_unassigned", "total_faults", "open_faults",
                      "resolved_faults", "avg_resolution_hours", "all_time_faults"):
                assert k in row, f"missing {k} in row: {row}"

    def test_pro_insights_sort_unassigned_last(self, pro_token):
        r = requests.get(f"{BASE}/suppliers/insights", headers=_h(pro_token), timeout=30)
        assert r.status_code == 200
        rows = r.json()["suppliers"]
        # Named suppliers sorted by total_faults desc, unassigned always last
        seen_unassigned = False
        for row in rows:
            if seen_unassigned:
                assert row["is_unassigned"], "Row after unassigned must also be unassigned (there should be only one)"
            if row["is_unassigned"]:
                seen_unassigned = True
        named = [r for r in rows if not r["is_unassigned"]]
        totals = [r["total_faults"] for r in named]
        assert totals == sorted(totals, reverse=True), "named suppliers must sort by total_faults desc"

    def test_lite_insights_403(self, lite_token):
        r = requests.get(f"{BASE}/suppliers/insights", headers=_h(lite_token), timeout=30)
        assert r.status_code == 403


# ── Equipment supplier_id persistence ────────────────────────────
class TestEquipmentSupplierId:
    def test_pro_create_persists_supplier_and_id(self, pro_token):
        # Get an existing supplier to attach
        rs = requests.get(f"{BASE}/suppliers", headers=_h(pro_token), timeout=30)
        assert rs.status_code == 200
        suppliers = rs.json()["suppliers"]
        assert suppliers, "Pro org should have at least the default supplier"
        # Prefer non-default if present, else use default
        target = next((s for s in suppliers if not s.get("is_default_pulse")), suppliers[0])
        payload = {
            "name": "TEST_SupplierInsights_Machine",
            "equipment_type": "Treadmill",
            "supplier": target["name"],
            "supplier_id": target["id"],
        }
        rc = requests.post(f"{BASE}/equipment", headers=_h(pro_token), json=payload, timeout=30)
        assert rc.status_code == 200, rc.text
        eq = rc.json()
        eq_id = eq["id"]
        try:
            assert eq.get("supplier") == target["name"]
            assert eq.get("supplier_id") == target["id"]
            # Verify persistence via GET
            rg = requests.get(f"{BASE}/equipment/{eq_id}", headers=_h(pro_token), timeout=30)
            assert rg.status_code == 200
            eq2 = rg.json()
            assert eq2.get("supplier") == target["name"]
            assert eq2.get("supplier_id") == target["id"]
        finally:
            requests.delete(f"{BASE}/equipment/{eq_id}", headers=_h(pro_token), timeout=30)

    def test_lite_create_defaults_to_pulse_fitness(self, lite_token):
        payload = {"name": "TEST_LiteAutoDefault", "equipment_type": "Bike"}
        rc = requests.post(f"{BASE}/equipment", headers=_h(lite_token), json=payload, timeout=30)
        assert rc.status_code == 200, rc.text
        eq = rc.json()
        eq_id = eq["id"]
        try:
            assert eq.get("supplier") == "Pulse Fitness", f"expected Pulse Fitness default, got {eq.get('supplier')}"
        finally:
            requests.delete(f"{BASE}/equipment/{eq_id}", headers=_h(lite_token), timeout=30)
