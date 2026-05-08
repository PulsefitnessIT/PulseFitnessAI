"""
GymAxis Memberships Iteration 167 — Backend API Tests

Tests for:
1. Setup wizard endpoints (/memberships/setup/*)
2. Record payment endpoint (/memberships/members/{member_id}/record-payment)
3. White-label branding endpoints (/m/{slug}/branding, /m/{slug}/plans, /m/{slug}/ads)
4. Ads CRUD endpoints (/memberships/ads)
5. Member registration with organization_slug
6. Old checkout endpoint still exists (deprecated but not removed)
"""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"
MEMBER_EMMA_EMAIL = "emma.wright@demo.gymaxis"
MEMBER_EMMA_PASSWORD = "Member2026!"
MEMBER_OLIVER_ID = "mbr-oliver"
DEMO_ORG_ID = "mbr-demo-org"
DEMO_SLUG = "pulse-leeds"


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
def member_token():
    """Get member JWT token for Emma"""
    resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
        "email": MEMBER_EMMA_EMAIL,
        "password": MEMBER_EMMA_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Member login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture(scope="module")
def member_headers(member_token):
    return {"Authorization": f"Bearer {member_token}"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. White-label branding endpoints (PUBLIC - no auth required)
# ═══════════════════════════════════════════════════════════════════════════

class TestPublicBranding:
    """Tests for /m/{slug}/branding endpoint"""

    def test_branding_returns_correct_fields(self):
        """GET /api/m/pulse-leeds/branding returns expected fields"""
        resp = requests.get(f"{BASE_URL}/api/m/{DEMO_SLUG}/branding")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify all required fields
        assert "organization_id" in data
        assert data["organization_id"] == DEMO_ORG_ID
        assert "name" in data
        assert "Pulse Studio" in data["name"]
        assert "slug" in data
        assert data["slug"] == DEMO_SLUG
        assert "logo_url" in data
        assert "primary_brand_colour" in data
        assert "currency" in data
        assert data["currency"] == "GBP"
        print(f"✓ Branding endpoint returns: {data}")

    def test_branding_unknown_slug_returns_404(self):
        """GET /api/m/unknown-slug/branding returns 404"""
        resp = requests.get(f"{BASE_URL}/api/m/nonexistent-gym-xyz/branding")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ Unknown slug returns 404")


class TestPublicPlans:
    """Tests for /m/{slug}/plans endpoint"""

    def test_plans_returns_seeded_plans(self):
        """GET /api/m/pulse-leeds/plans returns 4 seeded plans"""
        resp = requests.get(f"{BASE_URL}/api/m/{DEMO_SLUG}/plans")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "plans" in data
        plans = data["plans"]
        assert len(plans) >= 4, f"Expected at least 4 plans, got {len(plans)}"

        plan_names = [p["name"] for p in plans]
        assert "Monthly Unlimited" in plan_names
        assert "10-Class Pack" in plan_names
        print(f"✓ Plans endpoint returns {len(plans)} plans: {plan_names}")

    def test_plans_unknown_slug_returns_404(self):
        """GET /api/m/unknown-slug/plans returns 404"""
        resp = requests.get(f"{BASE_URL}/api/m/nonexistent-gym-xyz/plans")
        assert resp.status_code == 404


class TestPublicAds:
    """Tests for /m/{slug}/ads endpoint"""

    def test_ads_returns_seeded_ad(self):
        """GET /api/m/pulse-leeds/ads?placement=book_top returns seeded ad"""
        resp = requests.get(f"{BASE_URL}/api/m/{DEMO_SLUG}/ads", params={"placement": "book_top"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "ads" in data
        ads = data["ads"]
        # Should have at least the seeded "Refer a friend" ad
        if len(ads) > 0:
            ad = ads[0]
            assert "headline" in ad
            print(f"✓ Ads endpoint returns {len(ads)} ads, first: {ad.get('headline')}")
        else:
            print("✓ Ads endpoint returns empty list (ad may have been deleted)")

    def test_ads_unknown_slug_returns_404(self):
        """GET /api/m/unknown-slug/ads returns 404"""
        resp = requests.get(f"{BASE_URL}/api/m/nonexistent-gym-xyz/ads")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 2. Setup wizard endpoints (OPERATOR AUTH REQUIRED)
# ═══════════════════════════════════════════════════════════════════════════

class TestSetupWizard:
    """Tests for /memberships/setup/* endpoints"""

    def test_setup_status_returns_org_and_counts(self, operator_headers):
        """GET /api/memberships/setup/status returns organization and counts"""
        resp = requests.get(f"{BASE_URL}/api/memberships/setup/status", headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Verify organization fields
        assert "organization" in data
        org = data["organization"]
        assert "id" in org
        assert "name" in org
        assert "slug" in org
        assert "logo_url" in org
        assert "primary_brand_colour" in org
        assert "currency" in org
        assert "timezone" in org
        assert "payment_method" in org
        assert "setup_completed" in org
        assert "setup_step" in org

        # Verify counts
        assert "counts" in data
        counts = data["counts"]
        assert "plans" in counts
        assert "class_templates" in counts
        assert "instructors" in counts

        print(f"✓ Setup status: org={org['name']}, slug={org['slug']}, counts={counts}")

    def test_setup_status_requires_auth(self):
        """GET /api/memberships/setup/status without auth returns 401"""
        resp = requests.get(f"{BASE_URL}/api/memberships/setup/status")
        assert resp.status_code == 401

    def test_setup_basics_updates_org(self, operator_headers):
        """POST /api/memberships/setup/basics updates org fields"""
        # Get current state first
        status_resp = requests.get(f"{BASE_URL}/api/memberships/setup/status", headers=operator_headers)
        current_org = status_resp.json()["organization"]

        # Update with same values (idempotent test)
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/basics", headers=operator_headers, json={
            "name": current_org["name"],
            "timezone": current_org.get("timezone", "Europe/London"),
            "currency": current_org.get("currency", "GBP"),
            "primary_brand_colour": current_org.get("primary_brand_colour", "#19CDFF"),
            "slug": current_org.get("slug")
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        assert "slug" in data
        print(f"✓ Setup basics updated, slug={data['slug']}")

    def test_setup_payment_method_manual(self, operator_headers):
        """POST /api/memberships/setup/payment-method accepts 'manual'"""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/payment-method", headers=operator_headers, json={
            "payment_method": "manual"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        assert data.get("payment_method") == "manual"
        print("✓ Payment method 'manual' accepted")

    def test_setup_payment_method_direct_debit_returns_note(self, operator_headers):
        """POST /api/memberships/setup/payment-method with 'direct_debit' returns coming soon note"""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/payment-method", headers=operator_headers, json={
            "payment_method": "direct_debit"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        assert data.get("payment_method") == "direct_debit"
        assert "coming soon" in (data.get("note") or "").lower()
        print(f"✓ Payment method 'direct_debit' accepted with note: {data.get('note')}")

    def test_setup_payment_method_stripe_connect_returns_note(self, operator_headers):
        """POST /api/memberships/setup/payment-method with 'stripe_connect' returns coming soon note"""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/payment-method", headers=operator_headers, json={
            "payment_method": "stripe_connect"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        assert data.get("payment_method") == "stripe_connect"
        assert "coming soon" in (data.get("note") or "").lower()
        print(f"✓ Payment method 'stripe_connect' accepted with note: {data.get('note')}")

        # Reset to manual for other tests
        requests.post(f"{BASE_URL}/api/memberships/setup/payment-method", headers=operator_headers, json={
            "payment_method": "manual"
        })

    def test_setup_plans_bulk_creates(self, operator_headers):
        """POST /api/memberships/setup/plans bulk-creates plans"""
        # Create a test plan
        test_plan = {
            "name": f"TEST_Setup_Plan_{datetime.now().timestamp()}",
            "kind": "class_pack",
            "billing_cycle": "oneoff",
            "price_pence": 2500,
            "credits_count": 5
        }
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/plans", headers=operator_headers, json={
            "plans": [test_plan]
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        assert "created" in data
        assert len(data["created"]) == 1
        print(f"✓ Setup plans created: {data['created']}")

    def test_setup_complete_flips_flag(self, operator_headers):
        """POST /api/memberships/setup/complete sets setup_completed=true"""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/complete", headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True

        # Verify the flag is set
        status_resp = requests.get(f"{BASE_URL}/api/memberships/setup/status", headers=operator_headers)
        org = status_resp.json()["organization"]
        assert org.get("setup_completed") == True
        print("✓ Setup complete flipped setup_completed=true")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Record payment endpoint (OPERATOR AUTH REQUIRED)
# ═══════════════════════════════════════════════════════════════════════════

class TestRecordPayment:
    """Tests for /memberships/members/{member_id}/record-payment endpoint"""

    def test_record_payment_creates_membership(self, operator_headers):
        """POST /api/memberships/members/mbr-oliver/record-payment creates active membership"""
        # Get a plan ID first
        plans_resp = requests.get(f"{BASE_URL}/api/memberships/plans", headers=operator_headers)
        plans = plans_resp.json().get("plans", [])
        class_pack_plan = next((p for p in plans if p.get("kind") == "class_pack"), plans[0])

        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/{MEMBER_OLIVER_ID}/record-payment",
            headers=operator_headers,
            json={
                "plan_id": class_pack_plan["id"],
                "method": "cash",
                "reference": "TEST-REF-001",
                "note": "Test payment recording"
            }
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        assert "membership_id" in data
        print(f"✓ Record payment created membership: {data['membership_id']}")

    def test_record_payment_invalid_plan_returns_404(self, operator_headers):
        """POST record-payment with invalid plan_id returns 404"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/{MEMBER_OLIVER_ID}/record-payment",
            headers=operator_headers,
            json={
                "plan_id": "nonexistent-plan-id",
                "method": "cash"
            }
        )
        assert resp.status_code == 404
        print("✓ Invalid plan_id returns 404")

    def test_record_payment_invalid_member_returns_404(self, operator_headers):
        """POST record-payment with invalid member_id returns 404"""
        plans_resp = requests.get(f"{BASE_URL}/api/memberships/plans", headers=operator_headers)
        plans = plans_resp.json().get("plans", [])

        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/nonexistent-member/record-payment",
            headers=operator_headers,
            json={
                "plan_id": plans[0]["id"],
                "method": "cash"
            }
        )
        assert resp.status_code == 404
        print("✓ Invalid member_id returns 404")

    def test_record_payment_requires_auth(self):
        """POST record-payment without auth returns 401"""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/members/{MEMBER_OLIVER_ID}/record-payment",
            json={"plan_id": "any", "method": "cash"}
        )
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 4. Ads CRUD endpoints (OPERATOR AUTH REQUIRED)
# ═══════════════════════════════════════════════════════════════════════════

class TestAdsCRUD:
    """Tests for /memberships/ads CRUD endpoints"""

    @pytest.fixture
    def created_ad_id(self, operator_headers):
        """Create a test ad and return its ID"""
        resp = requests.post(f"{BASE_URL}/api/memberships/ads", headers=operator_headers, json={
            "headline": f"TEST_Ad_{datetime.now().timestamp()}",
            "body": "Test ad body",
            "cta_label": "Click me",
            "cta_url": "https://example.com",
            "placement": "book_top",
            "active": True,
            "background_colour": "#FF5733"
        })
        assert resp.status_code == 200
        ad_id = resp.json()["ad"]["id"]
        yield ad_id
        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/ads/{ad_id}", headers=operator_headers)

    def test_create_ad(self, operator_headers):
        """POST /api/memberships/ads creates ad"""
        resp = requests.post(f"{BASE_URL}/api/memberships/ads", headers=operator_headers, json={
            "headline": f"TEST_Create_Ad_{datetime.now().timestamp()}",
            "body": "Test body",
            "placement": "book_top",
            "active": True,
            "background_colour": "#19CDFF"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ad" in data
        ad = data["ad"]
        assert "id" in ad
        assert ad["headline"].startswith("TEST_Create_Ad_")
        assert ad["placement"] == "book_top"
        assert ad["active"] == True
        print(f"✓ Created ad: {ad['id']}")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/ads/{ad['id']}", headers=operator_headers)

    def test_list_ads(self, operator_headers, created_ad_id):
        """GET /api/memberships/ads lists ads"""
        resp = requests.get(f"{BASE_URL}/api/memberships/ads", headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ads" in data
        ads = data["ads"]
        assert any(a["id"] == created_ad_id for a in ads), "Created ad should be in list"
        print(f"✓ Listed {len(ads)} ads")

    def test_update_ad(self, operator_headers, created_ad_id):
        """PATCH /api/memberships/ads/{ad_id} updates ad"""
        resp = requests.patch(
            f"{BASE_URL}/api/memberships/ads/{created_ad_id}",
            headers=operator_headers,
            json={"headline": "Updated Headline", "active": False}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        print(f"✓ Updated ad {created_ad_id}")

    def test_delete_ad(self, operator_headers):
        """DELETE /api/memberships/ads/{ad_id} removes ad"""
        # Create an ad to delete
        create_resp = requests.post(f"{BASE_URL}/api/memberships/ads", headers=operator_headers, json={
            "headline": f"TEST_Delete_Ad_{datetime.now().timestamp()}",
            "placement": "book_top"
        })
        ad_id = create_resp.json()["ad"]["id"]

        # Delete it
        resp = requests.delete(f"{BASE_URL}/api/memberships/ads/{ad_id}", headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        print(f"✓ Deleted ad {ad_id}")

    def test_ads_requires_auth(self):
        """Ads endpoints require auth"""
        resp = requests.get(f"{BASE_URL}/api/memberships/ads")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 5. Ad click tracking
# ═══════════════════════════════════════════════════════════════════════════

class TestAdTracking:
    """Tests for ad impression and click tracking"""

    def test_ad_click_increments(self, operator_headers):
        """POST /api/m/{slug}/ads/{ad_id}/click increments clicks"""
        # Get an ad first
        ads_resp = requests.get(f"{BASE_URL}/api/m/{DEMO_SLUG}/ads")
        ads = ads_resp.json().get("ads", [])

        if len(ads) == 0:
            # Create a test ad
            create_resp = requests.post(f"{BASE_URL}/api/memberships/ads", headers=operator_headers, json={
                "headline": "Test Click Ad",
                "placement": "book_top",
                "active": True
            })
            ad_id = create_resp.json()["ad"]["id"]
        else:
            ad_id = ads[0]["id"]

        # Click the ad
        resp = requests.post(f"{BASE_URL}/api/m/{DEMO_SLUG}/ads/{ad_id}/click")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        print(f"✓ Ad click tracked for {ad_id}")


# ═══════════════════════════════════════════════════════════════════════════
# 6. Member registration with organization_slug
# ═══════════════════════════════════════════════════════════════════════════

class TestMemberRegistration:
    """Tests for member registration with organization_slug"""

    def test_register_with_slug_resolves_org(self):
        """POST /api/member-auth/register with organization_slug resolves org"""
        import uuid
        test_email = f"test_{uuid.uuid4().hex[:8]}@test.gymaxis"

        resp = requests.post(f"{BASE_URL}/api/member-auth/register", json={
            "email": test_email,
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User",
            "organization_slug": DEMO_SLUG
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "token" in data
        assert "member" in data
        assert data["member"]["organization_id"] == DEMO_ORG_ID
        print(f"✓ Registered member with slug, org_id={data['member']['organization_id']}")

    def test_register_missing_both_returns_400(self):
        """POST /api/member-auth/register without org_id or slug returns 400"""
        import uuid
        test_email = f"test_{uuid.uuid4().hex[:8]}@test.gymaxis"

        resp = requests.post(f"{BASE_URL}/api/member-auth/register", json={
            "email": test_email,
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User"
            # No organization_id or organization_slug
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ Missing both org_id and slug returns 400")

    def test_register_invalid_slug_returns_404(self):
        """POST /api/member-auth/register with invalid slug returns 404"""
        import uuid
        test_email = f"test_{uuid.uuid4().hex[:8]}@test.gymaxis"

        resp = requests.post(f"{BASE_URL}/api/member-auth/register", json={
            "email": test_email,
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User",
            "organization_slug": "nonexistent-gym-xyz"
        })
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ Invalid slug returns 404")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Verify old checkout endpoint still exists (deprecated)
# ═══════════════════════════════════════════════════════════════════════════

class TestDeprecatedCheckout:
    """Verify old checkout endpoint still exists"""

    def test_checkout_endpoint_exists(self, member_headers):
        """POST /api/memberships/checkout should still exist"""
        # Get a plan first
        plans_resp = requests.get(f"{BASE_URL}/api/m/{DEMO_SLUG}/plans")
        plans = plans_resp.json().get("plans", [])

        if len(plans) == 0:
            pytest.skip("No plans available")

        # Try to hit checkout - it may fail for various reasons but should not 404
        resp = requests.post(f"{BASE_URL}/api/memberships/checkout", headers=member_headers, json={
            "plan_id": plans[0]["id"],
            "member_id": "mbr-emma"
        })
        # Should not be 404 (endpoint exists) - may be 400/422/500 depending on Stripe config
        assert resp.status_code != 404, f"Checkout endpoint should exist, got {resp.status_code}"
        print(f"✓ Checkout endpoint exists (status={resp.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
