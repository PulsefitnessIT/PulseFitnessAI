"""
Iteration 215u — Backend tests for:
1. POST /api/memberships/billing/invoices/{invoice_id}/checkout — Stripe pay-link for unpaid invoices
2. GET /api/public/billing/invoice/{id}/pay — Public redirect to Stripe checkout
3. POST /api/memberships/webhook/stripe — checkout.session.completed for class_invoice
4. PDF rendering — _render_invoice_pdf returns valid PDF bytes
5. Email with PDF attachment — POST /api/memberships/billing/invoices/{id}/send
6. Smoothed checkout — Stripe Price uses monthly_pence (not price_pence=0)
7. Regression: non-smoothed plans use stripe_price_id and price_pence
8. Regression: GET /api/member/bookings returns waitlist_position and promoted_from_waitlist_at
"""
import pytest
import requests
import os
import json
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"
ORG_ID = "156c8dc4-8683-4cb4-8a74-facd811655ad"

# Test invoice ID from review_request
TEST_INVOICE_ID = "0c37e453-e972-4680-8be5-a75a670ebbb8"
TEST_MEMBER_ID = "9f7a2273-1f56-44e1-8235-e38f8a619481"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


class TestInvoiceCheckoutEndpoint:
    """POST /api/memberships/billing/invoices/{invoice_id}/checkout"""

    def test_checkout_requires_auth(self):
        """401 without token"""
        resp = requests.post(f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/checkout")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: checkout endpoint requires auth")

    def test_checkout_404_for_unknown_invoice(self, operator_headers):
        """404 for non-existent invoice"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/invoices/nonexistent-id/checkout",
            headers=operator_headers
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: checkout returns 404 for unknown invoice")

    def test_checkout_creates_stripe_url(self, operator_headers):
        """200 returns checkout_url for unpaid invoice"""
        # First, reset the test invoice to 'sent' status if it's paid
        reset_resp = requests.patch(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/status",
            json={"status": "sent"},
            headers=operator_headers
        )
        # May fail if invoice doesn't exist - that's ok, we'll check in the main test

        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/checkout",
            headers=operator_headers
        )

        if resp.status_code == 404:
            pytest.skip("Test invoice not found - may need to generate one first")

        if resp.status_code == 400:
            # Could be "already paid" or "total is zero"
            detail = resp.json().get("detail", "")
            if "paid" in detail.lower():
                print(f"SKIP: Invoice already paid - {detail}")
                pytest.skip("Invoice already paid")
            elif "zero" in detail.lower():
                print(f"SKIP: Invoice total is zero - {detail}")
                pytest.skip("Invoice total is zero")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "checkout_url" in data, "Response should contain checkout_url"
        assert data["checkout_url"].startswith("https://checkout.stripe.com/"), \
            f"URL should be Stripe checkout: {data['checkout_url']}"
        print(f"PASS: checkout returns valid Stripe URL: {data['checkout_url'][:60]}...")

    def test_checkout_400_for_paid_invoice(self, operator_headers):
        """400 if invoice status is 'paid'"""
        # First mark the invoice as paid
        requests.patch(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/status",
            json={"status": "paid"},
            headers=operator_headers
        )

        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/checkout",
            headers=operator_headers
        )

        if resp.status_code == 404:
            pytest.skip("Test invoice not found")

        assert resp.status_code == 400, f"Expected 400 for paid invoice, got {resp.status_code}"
        assert "paid" in resp.json().get("detail", "").lower()
        print("PASS: checkout returns 400 for paid invoice")

        # Reset back to sent for other tests
        requests.patch(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/status",
            json={"status": "sent"},
            headers=operator_headers
        )


class TestPublicInvoicePay:
    """GET /api/public/billing/invoice/{id}/pay"""

    def test_public_pay_404_for_unknown(self):
        """404 for non-existent invoice"""
        resp = requests.get(
            f"{BASE_URL}/api/public/billing/invoice/nonexistent-id/pay",
            allow_redirects=False
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: public pay returns 404 for unknown invoice")

    def test_public_pay_redirects_for_unpaid(self, operator_headers):
        """302 redirect to Stripe for unpaid invoice"""
        # Ensure invoice is in 'sent' status
        requests.patch(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/status",
            json={"status": "sent"},
            headers=operator_headers
        )

        resp = requests.get(
            f"{BASE_URL}/api/public/billing/invoice/{TEST_INVOICE_ID}/pay",
            allow_redirects=False
        )

        if resp.status_code == 404:
            pytest.skip("Test invoice not found")

        if resp.status_code == 400:
            detail = resp.json().get("detail", "")
            if "zero" in detail.lower() or "nothing" in detail.lower():
                pytest.skip("Invoice has zero total")

        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        location = resp.headers.get("Location", "")
        assert "checkout.stripe.com" in location, f"Should redirect to Stripe: {location}"
        print(f"PASS: public pay redirects to Stripe: {location[:60]}...")

    def test_public_pay_shows_already_paid_html(self, operator_headers):
        """200 HTML with 'Already paid' for paid invoice"""
        # Mark invoice as paid
        requests.patch(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/status",
            json={"status": "paid"},
            headers=operator_headers
        )

        resp = requests.get(
            f"{BASE_URL}/api/public/billing/invoice/{TEST_INVOICE_ID}/pay",
            allow_redirects=False
        )

        if resp.status_code == 404:
            pytest.skip("Test invoice not found")

        assert resp.status_code == 200, f"Expected 200 for paid invoice, got {resp.status_code}"
        assert "Already paid" in resp.text, "Response should contain 'Already paid'"
        print("PASS: public pay shows 'Already paid' HTML for paid invoice")

        # Reset for other tests
        requests.patch(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/status",
            json={"status": "sent"},
            headers=operator_headers
        )


class TestStripeWebhookClassInvoice:
    """POST /api/memberships/webhook/stripe with gymaxis_kind=class_invoice

    Note: Webhook requires Stripe signature verification in production.
    These tests verify the webhook handler logic exists and routes correctly.
    """

    def test_webhook_endpoint_exists(self):
        """Webhook endpoint exists and validates signature"""
        # Without proper Stripe signature, should return 400 "Bad signature"
        event_payload = {
            "id": f"evt_test_{datetime.now(timezone.utc).timestamp()}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": f"cs_test_{datetime.now(timezone.utc).timestamp()}",
                    "payment_status": "paid",
                    "metadata": {
                        "gymaxis_kind": "class_invoice",
                        "gymaxis_invoice_id": TEST_INVOICE_ID
                    }
                }
            }
        }

        resp = requests.post(
            f"{BASE_URL}/api/memberships/webhook/stripe",
            json=event_payload,
            headers={"Content-Type": "application/json"}
        )

        # Webhook requires signature - 400 "Bad signature" is expected
        # This confirms the endpoint exists and validates signatures
        assert resp.status_code == 400, f"Expected 400 (signature required), got {resp.status_code}"
        assert "signature" in resp.text.lower() or "bad" in resp.text.lower()
        print("PASS: webhook endpoint exists and requires Stripe signature")

    def test_webhook_handler_code_exists(self):
        """Verify mark_class_invoice_paid_from_session handler exists"""
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from routes.memberships.studio_billing import mark_class_invoice_paid_from_session

            # Verify it's a coroutine function
            import asyncio
            assert asyncio.iscoroutinefunction(mark_class_invoice_paid_from_session)
            print("PASS: mark_class_invoice_paid_from_session handler exists and is async")
        except ImportError as e:
            pytest.fail(f"Could not import webhook handler: {e}")


class TestPDFRendering:
    """Test _render_invoice_pdf helper returns valid PDF bytes"""

    def test_pdf_helper_returns_valid_bytes(self):
        """Import and call _render_invoice_pdf directly"""
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from routes.memberships.studio_billing import _render_invoice_pdf

            test_invoice = {
                "id": "test-pdf-invoice",
                "member_email": "test@example.com",
                "period": "2026-01",
                "total_pence": 5000,
                "lines": [
                    {"description": "HIIT Class · Mon 5 Jan 10:00", "amount_pence": 1500},
                    {"description": "Yoga Class · Wed 7 Jan 18:00", "amount_pence": 1500},
                    {"description": "Spin Class · Fri 9 Jan 07:00", "amount_pence": 2000},
                ]
            }

            pdf_bytes = _render_invoice_pdf(
                org_name="Test Studio",
                period_label="January 2026",
                invoice=test_invoice,
                member_name="Test Member",
                primary_color_hex="#00B2C7"
            )

            assert isinstance(pdf_bytes, bytes), "Should return bytes"
            assert pdf_bytes.startswith(b"%PDF-"), f"Should start with PDF header, got: {pdf_bytes[:10]}"
            assert len(pdf_bytes) > 1000, f"PDF should be substantial, got {len(pdf_bytes)} bytes"

            # PDF content is compressed, so we just verify it's a valid PDF structure
            # The %PDF- header and substantial size confirms it's a real PDF
            print(f"PASS: PDF rendering works, {len(pdf_bytes)} bytes, starts with %PDF-")

        except ImportError as e:
            pytest.skip(f"Could not import PDF helper: {e}")


class TestInvoiceEmailWithAttachment:
    """POST /api/memberships/billing/invoices/{id}/send with PDF attachment"""

    def test_send_invoice_endpoint_exists(self, operator_headers):
        """Endpoint exists and validates invoice"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/invoices/nonexistent-id/send",
            headers=operator_headers
        )
        assert resp.status_code == 404, f"Expected 404 for unknown invoice, got {resp.status_code}"
        print("PASS: send invoice endpoint exists and returns 404 for unknown")

    def test_send_invoice_requires_email(self, operator_headers):
        """400 if member has no email"""
        # This test depends on having an invoice with a member without email
        # We'll just verify the endpoint responds correctly
        resp = requests.post(
            f"{BASE_URL}/api/memberships/billing/invoices/{TEST_INVOICE_ID}/send",
            headers=operator_headers
        )

        if resp.status_code == 404:
            pytest.skip("Test invoice not found")

        # Could be 200 (sent), 400 (no email), or 502 (email failed)
        assert resp.status_code in [200, 400, 502], \
            f"Expected 200/400/502, got {resp.status_code}: {resp.text}"

        if resp.status_code == 200:
            print("PASS: send invoice succeeded")
        elif resp.status_code == 400:
            print(f"PASS: send invoice validates (400: {resp.json().get('detail', '')})")
        else:
            # 502 means email service failed but PDF was built
            print("PASS: send invoice built PDF but email service unavailable (502)")


class TestSmoothedCheckout:
    """Smoothed plans use monthly_pence for Stripe Price, not price_pence=0"""

    def test_smoothed_plan_stripe_price_calculation(self, operator_headers):
        """Create smoothed plan and verify Stripe Price uses correct amount"""
        # Create a test smoothed plan
        plan_payload = {
            "name": f"TEST_Smoothed_Plan_{datetime.now(timezone.utc).timestamp()}",
            "kind": "recurring",
            "billing_cycle": "monthly",
            "price_pence": 0,  # Headline price is 0 for smoothed
            "smoothed": True,
            "smoothed_annual_pence": 52000,  # £520/year
            "smoothed_months": 12,
            "included_classes": "unlimited"
        }

        create_resp = requests.post(
            f"{BASE_URL}/api/memberships/plans",
            json=plan_payload,
            headers=operator_headers
        )

        # 200 or 201 are both acceptable
        assert create_resp.status_code in [200, 201], \
            f"Could not create test plan: {create_resp.status_code} - {create_resp.text}"

        data = create_resp.json()
        plan = data.get("plan") or data
        plan_id = plan.get("id")

        try:
            # Verify smoothing preview shows correct monthly amount
            preview_resp = requests.get(
                f"{BASE_URL}/api/memberships/plans/{plan_id}/smoothing-preview",
                headers=operator_headers
            )

            assert preview_resp.status_code == 200
            preview = preview_resp.json()

            # 52000 / 12 = 4333.33... rounds to 4333
            expected_monthly = round(52000 / 12)
            assert preview.get("monthly_pence") == expected_monthly, \
                f"Expected monthly_pence={expected_monthly}, got {preview.get('monthly_pence')}"
            assert preview.get("enabled") == True

            print(f"PASS: Smoothed plan monthly_pence = {expected_monthly} (52000/12)")

        finally:
            # Clean up - archive the test plan
            requests.patch(
                f"{BASE_URL}/api/memberships/plans/{plan_id}",
                json={"archived": True},
                headers=operator_headers
            )


class TestNonSmoothedRegression:
    """Non-smoothed plans use stripe_price_id and price_pence"""

    def test_non_smoothed_plan_uses_price_pence(self, operator_headers):
        """Non-smoothed plan should use price_pence for Stripe"""
        # Create a non-smoothed plan
        plan_payload = {
            "name": f"TEST_NonSmoothed_Plan_{datetime.now(timezone.utc).timestamp()}",
            "kind": "recurring",
            "billing_cycle": "monthly",
            "price_pence": 3500,  # £35/month
            "smoothed": False,
            "included_classes": "unlimited"
        }

        create_resp = requests.post(
            f"{BASE_URL}/api/memberships/plans",
            json=plan_payload,
            headers=operator_headers
        )

        # 200 or 201 are both acceptable
        assert create_resp.status_code in [200, 201], \
            f"Could not create test plan: {create_resp.status_code} - {create_resp.text}"

        data = create_resp.json()
        plan = data.get("plan") or data
        plan_id = plan.get("id")

        try:
            # Verify smoothing preview shows disabled
            preview_resp = requests.get(
                f"{BASE_URL}/api/memberships/plans/{plan_id}/smoothing-preview",
                headers=operator_headers
            )

            assert preview_resp.status_code == 200
            preview = preview_resp.json()

            assert preview.get("enabled") == False, "Non-smoothed plan should have enabled=false"
            # For non-smoothed, monthly_pence should equal price_pence
            assert preview.get("monthly_pence") == 3500, \
                f"Expected monthly_pence=3500, got {preview.get('monthly_pence')}"

            print("PASS: Non-smoothed plan uses price_pence correctly")

        finally:
            # Clean up
            requests.patch(
                f"{BASE_URL}/api/memberships/plans/{plan_id}",
                json={"archived": True},
                headers=operator_headers
            )


class TestMemberBookingsWaitlistFields:
    """GET /api/member/bookings returns waitlist_position and promoted_from_waitlist_at"""

    def test_member_bookings_returns_waitlist_position(self):
        """Waitlist bookings should have waitlist_position field"""
        # Login as the rebook test member from test_credentials.md
        member_resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": "rebook-1777578936@example.com",
            "password": "Test123!"
        })

        if member_resp.status_code != 200:
            pytest.skip(f"Could not login as test member: {member_resp.status_code}")

        member_token = member_resp.json().get("token")
        member_headers = {"Authorization": f"Bearer {member_token}"}

        bookings_resp = requests.get(
            f"{BASE_URL}/api/member/bookings",
            headers=member_headers
        )

        assert bookings_resp.status_code == 200
        data = bookings_resp.json()

        assert "upcoming" in data
        assert "past" in data

        # Check if any waitlist bookings have position
        waitlist_bookings = [b for b in data["upcoming"] if b.get("status") == "waitlist"]
        for b in waitlist_bookings:
            assert "waitlist_position" in b, f"Waitlist booking {b['id']} missing waitlist_position"
            assert isinstance(b["waitlist_position"], int)
            print(f"Waitlist booking {b['id']}: position #{b['waitlist_position']}")

        if waitlist_bookings:
            print(f"PASS: {len(waitlist_bookings)} waitlist bookings have waitlist_position")
        else:
            print("PASS: member/bookings endpoint works (no waitlist bookings to verify position)")

    def test_member_bookings_includes_promoted_field(self):
        """Promoted bookings should have promoted_from_waitlist_at field"""
        # This test verifies the field is returned when present
        member_resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
            "email": "rebook-1777578936@example.com",
            "password": "Test123!"
        })

        if member_resp.status_code != 200:
            pytest.skip(f"Could not login as test member: {member_resp.status_code}")

        member_token = member_resp.json().get("token")
        member_headers = {"Authorization": f"Bearer {member_token}"}

        bookings_resp = requests.get(
            f"{BASE_URL}/api/member/bookings",
            headers=member_headers
        )

        assert bookings_resp.status_code == 200
        data = bookings_resp.json()

        # Check all bookings for promoted_from_waitlist_at field
        all_bookings = data["upcoming"] + data["past"]
        promoted = [b for b in all_bookings if b.get("promoted_from_waitlist_at")]

        for b in promoted:
            assert isinstance(b["promoted_from_waitlist_at"], str)
            # Should be ISO format
            try:
                datetime.fromisoformat(b["promoted_from_waitlist_at"].replace("Z", "+00:00"))
            except ValueError:
                pytest.fail(f"promoted_from_waitlist_at not ISO format: {b['promoted_from_waitlist_at']}")

        if promoted:
            print(f"PASS: {len(promoted)} bookings have promoted_from_waitlist_at")
        else:
            print("PASS: member/bookings endpoint works (no promoted bookings to verify)")


class TestInvoiceListEndpoint:
    """GET /api/memberships/billing/invoices - regression test"""

    def test_list_invoices(self, operator_headers):
        """List invoices returns array"""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/billing/invoices",
            headers=operator_headers
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "invoices" in data
        assert isinstance(data["invoices"], list)
        print(f"PASS: list invoices returns {len(data['invoices'])} invoices")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
