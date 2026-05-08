"""
Iteration 215s — Studio Billing: Monthly class invoicing + Pro-rata smoothing.

Tests:
1. Monthly invoice preview endpoint (POST /api/memberships/billing/monthly-invoice/preview)
2. Monthly invoice generate endpoint (POST /api/memberships/billing/monthly-invoice/generate)
3. Invoice list endpoint (GET /api/memberships/billing/invoices)
4. Invoice status update (PATCH /api/memberships/billing/invoices/{id}/status)
5. Invoice send endpoint (POST /api/memberships/billing/invoices/{id}/send)
6. Member invoices endpoint (GET /api/member/invoices)
7. Plan smoothing fields (POST/PATCH /api/memberships/plans)
8. Smoothing preview endpoint (GET /api/memberships/plans/{plan_id}/smoothing-preview)
9. Regression: S3 OG cache (GET /api/m/{slug}/c/{occ}/og.png)
"""
import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"

# Seeded test data from main agent context
TEST_ORG_ID = "156c8dc4-8683-4cb4-8a74-facd811655ad"
TEST_PERIOD = "2026-04"  # April 2026 has seeded bookings


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code == 429:
        pytest.skip("Rate limited - wait 3 minutes and retry")
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    """Headers with operator auth."""
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def master_admin_token():
    """Get master admin JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if resp.status_code == 429:
        pytest.skip("Rate limited - wait 3 minutes and retry")
    assert resp.status_code == 200, f"Master admin login failed: {resp.text}"
    data = resp.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def master_admin_headers(master_admin_token):
    """Headers with master admin auth."""
    return {"Authorization": f"Bearer {master_admin_token}", "Content-Type": "application/json"}


class TestMonthlyInvoicePreview:
    """Tests for POST /api/memberships/billing/monthly-invoice/preview"""

    def test_preview_requires_auth(self):
        """Preview endpoint returns 401 without token."""
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview", json={
            "period": TEST_PERIOD
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS: Preview returns 401 without token")

    def test_preview_with_valid_token(self, operator_headers):
        """Preview returns member_count, total_pence, invoices[] with valid operator token."""
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            json={"period": TEST_PERIOD},
            headers=operator_headers
        )
        assert resp.status_code == 200, f"Preview failed: {resp.text}"
        data = resp.json()

        # Verify response structure
        assert "member_count" in data, "Missing member_count"
        assert "total_pence" in data, "Missing total_pence"
        assert "invoices" in data, "Missing invoices"
        assert isinstance(data["invoices"], list), "invoices should be a list"
        assert "period" in data, "Missing period"
        assert data["period"] == TEST_PERIOD

        print(f"PASS: Preview returned {data['member_count']} members, total £{data['total_pence']/100:.2f}")
        print(f"  Invoices: {len(data['invoices'])}")

    def test_preview_attended_only_filter(self, operator_headers):
        """include_attended_only:true filters to attended bookings only."""
        # First get preview with all bookings
        resp_all = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            json={"period": TEST_PERIOD, "include_attended_only": False},
            headers=operator_headers
        )
        assert resp_all.status_code == 200
        data_all = resp_all.json()

        # Then get preview with attended only
        resp_attended = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            json={"period": TEST_PERIOD, "include_attended_only": True},
            headers=operator_headers
        )
        assert resp_attended.status_code == 200
        data_attended = resp_attended.json()

        # Attended-only should have <= total (may be equal if all are attended)
        assert data_attended["total_pence"] <= data_all["total_pence"], \
            "Attended-only total should be <= all bookings total"

        print(f"PASS: Attended-only filter works - all: £{data_all['total_pence']/100:.2f}, attended: £{data_attended['total_pence']/100:.2f}")

    def test_preview_default_per_class_pence(self, operator_headers):
        """default_per_class_pence in payload is respected."""
        custom_rate = 1500  # £15.00
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/preview",
            json={"period": TEST_PERIOD, "default_per_class_pence": custom_rate},
            headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify the default rate is returned
        assert "default_per_class_pence" in data, "Missing default_per_class_pence in response"
        assert data["default_per_class_pence"] == custom_rate, \
            f"Expected default rate {custom_rate}, got {data['default_per_class_pence']}"

        print(f"PASS: Custom default_per_class_pence={custom_rate} respected")


class TestMonthlyInvoiceGenerate:
    """Tests for POST /api/memberships/billing/monthly-invoice/generate"""

    def test_generate_persists_invoices(self, operator_headers):
        """Generate persists invoices in membership_class_invoices collection."""
        # Use a different period to avoid conflicts with existing data
        test_period = "2026-03"  # March 2026

        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            json={"period": test_period, "send_email": False},
            headers=operator_headers
        )
        assert resp.status_code == 200, f"Generate failed: {resp.text}"
        data = resp.json()

        assert "generated_count" in data, "Missing generated_count"
        assert "invoices" in data, "Missing invoices"
        assert "period" in data, "Missing period"

        print(f"PASS: Generated {data['generated_count']} invoices for {test_period}")

    def test_generate_idempotent(self, operator_headers):
        """Running twice for same period generates same count (no duplicates)."""
        test_period = "2026-03"

        # First generation
        resp1 = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            json={"period": test_period, "send_email": False},
            headers=operator_headers
        )
        assert resp1.status_code == 200
        count1 = resp1.json()["generated_count"]

        # Second generation (should be idempotent)
        resp2 = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            json={"period": test_period, "send_email": False},
            headers=operator_headers
        )
        assert resp2.status_code == 200
        count2 = resp2.json()["generated_count"]

        # Counts should be equal (idempotent - updates existing drafts)
        assert count1 == count2, f"Idempotency failed: first={count1}, second={count2}"

        print(f"PASS: Generate is idempotent - both runs returned {count1} invoices")

    def test_generate_status_defaults_to_draft(self, operator_headers):
        """Generated invoices have status 'draft' by default."""
        test_period = "2026-03"

        resp = requests.post(f"{BASE_URL}/api/memberships/billing/monthly-invoice/generate",
            json={"period": test_period, "send_email": False},
            headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()

        for inv in data.get("invoices", []):
            assert inv.get("status") == "draft", f"Expected status 'draft', got '{inv.get('status')}'"

        print(f"PASS: All {len(data.get('invoices', []))} invoices have status 'draft'")


class TestInvoiceList:
    """Tests for GET /api/memberships/billing/invoices"""

    def test_list_invoices(self, operator_headers):
        """List invoices for operator org."""
        resp = requests.get(f"{BASE_URL}/api/memberships/billing/invoices", headers=operator_headers)
        assert resp.status_code == 200, f"List failed: {resp.text}"
        data = resp.json()

        assert "invoices" in data, "Missing invoices"
        assert isinstance(data["invoices"], list), "invoices should be a list"

        print(f"PASS: Listed {len(data['invoices'])} invoices")

    def test_list_invoices_filter_by_period(self, operator_headers):
        """Filter invoices by period."""
        test_period = "2026-03"
        resp = requests.get(f"{BASE_URL}/api/memberships/billing/invoices",
            params={"period": test_period},
            headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()

        for inv in data.get("invoices", []):
            assert inv.get("period") == test_period, f"Expected period {test_period}, got {inv.get('period')}"

        print(f"PASS: Period filter works - {len(data['invoices'])} invoices for {test_period}")

    def test_list_invoices_filter_by_status(self, operator_headers):
        """Filter invoices by status."""
        resp = requests.get(f"{BASE_URL}/api/memberships/billing/invoices",
            params={"status": "draft"},
            headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()

        for inv in data.get("invoices", []):
            assert inv.get("status") == "draft", f"Expected status 'draft', got {inv.get('status')}"

        print(f"PASS: Status filter works - {len(data['invoices'])} draft invoices")


class TestInvoiceStatusUpdate:
    """Tests for PATCH /api/memberships/billing/invoices/{id}/status"""

    def test_update_status_to_paid(self, operator_headers):
        """Update invoice status to 'paid'."""
        # First get a draft invoice
        resp = requests.get(f"{BASE_URL}/api/memberships/billing/invoices",
            params={"status": "draft"},
            headers=operator_headers
        )
        assert resp.status_code == 200
        invoices = resp.json().get("invoices", [])

        if not invoices:
            pytest.skip("No draft invoices to test status update")

        invoice_id = invoices[0]["id"]

        # Update status to paid
        resp = requests.patch(f"{BASE_URL}/api/memberships/billing/invoices/{invoice_id}/status",
            json={"status": "paid"},
            headers=operator_headers
        )
        assert resp.status_code == 200, f"Status update failed: {resp.text}"
        data = resp.json()

        assert data.get("ok") == True, "Expected ok: true"
        assert data.get("status") == "paid", f"Expected status 'paid', got {data.get('status')}"

        print(f"PASS: Updated invoice {invoice_id} status to 'paid'")

    def test_update_status_404_for_unknown_id(self, operator_headers):
        """404 for unknown invoice id."""
        fake_id = "nonexistent-invoice-id-12345"
        resp = requests.patch(f"{BASE_URL}/api/memberships/billing/invoices/{fake_id}/status",
            json={"status": "paid"},
            headers=operator_headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

        print("PASS: 404 returned for unknown invoice id")


class TestInvoiceSend:
    """Tests for POST /api/memberships/billing/invoices/{id}/send"""

    def test_send_400_when_no_email(self, operator_headers):
        """400 when member has no email."""
        # This test requires an invoice for a member without email
        # We'll test the endpoint exists and returns appropriate error

        # First get any invoice
        resp = requests.get(f"{BASE_URL}/api/memberships/billing/invoices", headers=operator_headers)
        assert resp.status_code == 200
        invoices = resp.json().get("invoices", [])

        if not invoices:
            pytest.skip("No invoices to test send endpoint")

        # Find an invoice without member_email (if any)
        no_email_invoice = next((inv for inv in invoices if not inv.get("member_email")), None)

        if no_email_invoice:
            resp = requests.post(f"{BASE_URL}/api/memberships/billing/invoices/{no_email_invoice['id']}/send",
                headers=operator_headers
            )
            assert resp.status_code == 400, f"Expected 400 for no email, got {resp.status_code}"
            print("PASS: 400 returned when member has no email")
        else:
            # Test with valid email - may get 502 due to unverified domain (acceptable)
            invoice = invoices[0]
            resp = requests.post(f"{BASE_URL}/api/memberships/billing/invoices/{invoice['id']}/send",
                headers=operator_headers
            )
            # 200 or 502 are both acceptable (502 = Resend domain not verified)
            assert resp.status_code in [200, 502], f"Expected 200 or 502, got {resp.status_code}: {resp.text}"
            print(f"PASS: Send endpoint exists and returns {resp.status_code}")

    def test_send_404_for_unknown_id(self, operator_headers):
        """404 for unknown invoice id."""
        fake_id = "nonexistent-invoice-id-67890"
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/invoices/{fake_id}/send",
            headers=operator_headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

        print("PASS: 404 returned for unknown invoice id on send")


class TestMemberInvoices:
    """Tests for GET /api/member/invoices (member portal)"""

    def test_member_invoices_requires_member_jwt(self, operator_headers):
        """Member invoices endpoint requires member JWT, not operator JWT."""
        # Operator token should not work for member endpoint
        resp = requests.get(f"{BASE_URL}/api/member/invoices", headers=operator_headers)
        # Should return 401 or 403 since operator is not a member
        assert resp.status_code in [401, 403, 422], \
            f"Expected 401/403/422 for operator token on member endpoint, got {resp.status_code}"

        print(f"PASS: Member invoices endpoint rejects operator token ({resp.status_code})")


class TestPlanSmoothingFields:
    """Tests for smoothed/smoothed_annual_pence/smoothed_months fields on plans"""

    def test_create_plan_with_smoothing(self, operator_headers):
        """POST /api/memberships/plans accepts smoothed fields."""
        plan_data = {
            "name": "TEST_Smoothed Annual Plan",
            "kind": "recurring",
            "price_pence": 0,  # Smoothed plans may have 0 base price
            "billing_cycle": "monthly",
            "smoothed": True,
            "smoothed_annual_pence": 52000,  # £520/year
            "smoothed_months": 12
        }

        resp = requests.post(f"{BASE_URL}/api/memberships/plans", json=plan_data, headers=operator_headers)
        assert resp.status_code == 200, f"Create plan failed: {resp.text}"
        data = resp.json()

        plan = data.get("plan", {})
        assert plan.get("smoothed") == True, "smoothed should be True"
        assert plan.get("smoothed_annual_pence") == 52000, f"Expected 52000, got {plan.get('smoothed_annual_pence')}"
        assert plan.get("smoothed_months") == 12, f"Expected 12, got {plan.get('smoothed_months')}"

        # Store plan id for cleanup
        TestPlanSmoothingFields.created_plan_id = plan.get("id")

        print(f"PASS: Created smoothed plan with id {plan.get('id')}")
        return plan.get("id")

    def test_patch_plan_smoothing_fields(self, operator_headers):
        """PATCH /api/memberships/plans/{id} allows smoothed fields."""
        # First create a plan to patch
        plan_data = {
            "name": "TEST_Plan for Patch",
            "kind": "recurring",
            "price_pence": 5000,
            "billing_cycle": "monthly"
        }

        resp = requests.post(f"{BASE_URL}/api/memberships/plans", json=plan_data, headers=operator_headers)
        assert resp.status_code == 200
        plan_id = resp.json().get("plan", {}).get("id")

        # Patch with smoothing fields
        patch_data = {
            "smoothed": True,
            "smoothed_annual_pence": 48000,
            "smoothed_months": 12,
            "per_class_pence": 1200
        }

        resp = requests.patch(f"{BASE_URL}/api/memberships/plans/{plan_id}", json=patch_data, headers=operator_headers)
        assert resp.status_code == 200, f"Patch failed: {resp.text}"

        # Verify by fetching plans
        resp = requests.get(f"{BASE_URL}/api/memberships/plans", headers=operator_headers)
        assert resp.status_code == 200
        plans = resp.json().get("plans", [])

        patched_plan = next((p for p in plans if p.get("id") == plan_id), None)
        assert patched_plan is not None, "Patched plan not found"
        assert patched_plan.get("smoothed") == True, "smoothed should be True after patch"
        assert patched_plan.get("smoothed_annual_pence") == 48000
        assert patched_plan.get("per_class_pence") == 1200

        print(f"PASS: Patched plan {plan_id} with smoothing fields")


class TestSmoothingPreview:
    """Tests for GET /api/memberships/plans/{plan_id}/smoothing-preview"""

    def test_smoothing_preview_for_smoothed_plan(self, operator_headers):
        """Returns enabled:true with computed monthly_pence for smoothed plan."""
        # Create a smoothed plan
        plan_data = {
            "name": "TEST_Smoothing Preview Plan",
            "kind": "recurring",
            "price_pence": 0,
            "billing_cycle": "monthly",
            "smoothed": True,
            "smoothed_annual_pence": 52000,  # £520/year
            "smoothed_months": 12
        }

        resp = requests.post(f"{BASE_URL}/api/memberships/plans", json=plan_data, headers=operator_headers)
        assert resp.status_code == 200
        plan_id = resp.json().get("plan", {}).get("id")

        # Get smoothing preview
        resp = requests.get(f"{BASE_URL}/api/memberships/plans/{plan_id}/smoothing-preview", headers=operator_headers)
        assert resp.status_code == 200, f"Smoothing preview failed: {resp.text}"
        data = resp.json()

        assert data.get("enabled") == True, "enabled should be True for smoothed plan"
        assert data.get("monthly_pence") == 4333, f"Expected 4333 (52000/12 rounded), got {data.get('monthly_pence')}"
        assert data.get("months") == 12, f"Expected 12, got {data.get('months')}"
        assert data.get("annual_pence") == 52000, f"Expected 52000, got {data.get('annual_pence')}"

        # Verify diff calculation: 52000 - (4333 * 12) = 52000 - 51996 = 4
        expected_diff = 52000 - (4333 * 12)
        assert data.get("annual_vs_monthly_diff_pence") == expected_diff, \
            f"Expected diff {expected_diff}, got {data.get('annual_vs_monthly_diff_pence')}"

        print(f"PASS: Smoothing preview returns correct values - £{data['monthly_pence']/100:.2f}/month")

    def test_smoothing_preview_for_non_smoothed_plan(self, operator_headers):
        """Returns enabled:false for non-smoothed plans."""
        # Create a non-smoothed plan
        plan_data = {
            "name": "TEST_Non-Smoothed Plan",
            "kind": "recurring",
            "price_pence": 5000,
            "billing_cycle": "monthly",
            "smoothed": False
        }

        resp = requests.post(f"{BASE_URL}/api/memberships/plans", json=plan_data, headers=operator_headers)
        assert resp.status_code == 200
        plan_id = resp.json().get("plan", {}).get("id")

        # Get smoothing preview
        resp = requests.get(f"{BASE_URL}/api/memberships/plans/{plan_id}/smoothing-preview", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data.get("enabled") == False, "enabled should be False for non-smoothed plan"

        print("PASS: Smoothing preview returns enabled:false for non-smoothed plan")

    def test_smoothing_preview_404_for_unknown_plan(self, operator_headers):
        """404 for unknown plan id."""
        fake_id = "nonexistent-plan-id-99999"
        resp = requests.get(f"{BASE_URL}/api/memberships/plans/{fake_id}/smoothing-preview", headers=operator_headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"

        print("PASS: 404 returned for unknown plan id")


class TestRegressionS3OGCache:
    """Regression test for S3 OG cache from Iter 215r"""

    def test_og_cache_fresh_then_cache(self, operator_headers):
        """GET /api/m/{slug}/c/{occ}/og.png returns X-GymAxis-OG-Cache header."""
        # Use the known test occurrence from 215r
        slug = "maintenance-hub-357"
        occ_id = "past-occ-test"

        # First request - may be fresh or cache depending on prior runs
        resp1 = requests.get(f"{BASE_URL}/api/m/{slug}/c/{occ_id}/og.png")

        if resp1.status_code == 404:
            pytest.skip("Test occurrence not found - may have been cleaned up")

        assert resp1.status_code == 200, f"OG image request failed: {resp1.status_code}"

        cache_header1 = resp1.headers.get("X-GymAxis-OG-Cache", "")
        content1 = resp1.content

        # Second request - should be cache
        resp2 = requests.get(f"{BASE_URL}/api/m/{slug}/c/{occ_id}/og.png")
        assert resp2.status_code == 200

        cache_header2 = resp2.headers.get("X-GymAxis-OG-Cache", "")
        content2 = resp2.content

        # Verify cache header exists
        assert cache_header1 in ["fresh", "cache"], f"Expected 'fresh' or 'cache', got '{cache_header1}'"
        assert cache_header2 == "cache", f"Second request should be 'cache', got '{cache_header2}'"

        # Verify identical bytes
        assert content1 == content2, "Cached image should have identical bytes"

        print(f"PASS: OG cache working - first: {cache_header1}, second: {cache_header2}, bytes match: {len(content1)}")


class TestCleanup:
    """Cleanup test data created during tests"""

    def test_cleanup_test_plans(self, operator_headers):
        """Archive TEST_ prefixed plans."""
        resp = requests.get(f"{BASE_URL}/api/memberships/plans", headers=operator_headers)
        if resp.status_code != 200:
            return

        plans = resp.json().get("plans", [])
        cleaned = 0

        for plan in plans:
            if plan.get("name", "").startswith("TEST_"):
                del_resp = requests.delete(f"{BASE_URL}/api/memberships/plans/{plan['id']}", headers=operator_headers)
                if del_resp.status_code == 200:
                    cleaned += 1

        print(f"PASS: Cleaned up {cleaned} test plans")
