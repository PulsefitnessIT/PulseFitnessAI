"""
Marketing Suite Phase 1 — Backend API Tests (Iteration 186)

Tests for:
- Entitlement endpoint
- Audiences (AI suggest, preview, CRUD)
- Campaigns (templates, instantiate, CRUD, send)
- Creative Studio (generate)
- Journeys (CRUD)
- Insights
- Performance dashboard
- Social status
- AI Assistant
- Conversion attribution
- Master Admin (plans, analytics, subscriptions)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
PULSE_PRO_EMAIL = "lee.somers@pulsefitness.com"
PULSE_PRO_PASSWORD = "TempPass123!"
MASTER_ADMIN_EMAIL = "admin@gymaxisai.com"
MASTER_ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def pulse_pro_token():
    """Get auth token for Pulse Pro user (lee.somers)"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": PULSE_PRO_EMAIL,
        "password": PULSE_PRO_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Could not login as Pulse Pro user: {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def master_admin_token():
    """Get auth token for Master Admin"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MASTER_ADMIN_EMAIL,
        "password": MASTER_ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Could not login as Master Admin: {response.text}")
    return response.json().get("token")


@pytest.fixture
def pulse_headers(pulse_pro_token):
    return {"Authorization": f"Bearer {pulse_pro_token}", "Content-Type": "application/json"}


@pytest.fixture
def admin_headers(master_admin_token):
    return {"Authorization": f"Bearer {master_admin_token}", "Content-Type": "application/json"}


class TestMarketingEntitlement:
    """Test /api/marketing/me/entitlement endpoint"""

    def test_entitlement_returns_plan_and_features(self, pulse_headers):
        """Entitlement endpoint returns plan info with features and limits"""
        response = requests.get(f"{BASE_URL}/api/marketing/me/entitlement", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "subscription" in data
        assert "plan" in data
        assert "features" in data
        assert "limits" in data

        # Verify plan structure
        plan = data["plan"]
        assert "name" in plan
        assert "monthly_price_gbp" in plan

        # Verify features structure
        features = data["features"]
        assert "audiences" in features
        assert "campaigns" in features

        print(f"✓ Entitlement: Plan={plan['name']}, Status={data['subscription'].get('status')}")


class TestMarketingInsights:
    """Test /api/marketing/insights endpoint"""

    def test_insights_returns_tiles(self, pulse_headers):
        """Insights endpoint returns opportunity tiles"""
        response = requests.get(f"{BASE_URL}/api/marketing/insights", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "insights" in data
        insights = data["insights"]
        assert isinstance(insights, list)

        # Should have at least the welcome tile if no other insights
        if len(insights) > 0:
            insight = insights[0]
            assert "id" in insight
            assert "title" in insight
            assert "body" in insight
            assert "cta" in insight
            print(f"✓ Insights: {len(insights)} tiles returned, first: {insight['title'][:50]}")
        else:
            print("✓ Insights: Empty list (healthy engagement)")


class TestMarketingAudiences:
    """Test Audiences endpoints"""

    def test_ai_suggest_audience(self, pulse_headers):
        """AI suggest returns rule-tree from plain English description"""
        response = requests.post(
            f"{BASE_URL}/api/marketing/audiences/ai-suggest",
            json={"description": "high-spending members at risk of churning"},
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "rules" in data
        assert "estimated_size" in data

        rules = data["rules"]
        assert "op" in rules
        assert "conditions" in rules
        assert isinstance(rules["conditions"], list)

        print(f"✓ AI Suggest: {len(rules['conditions'])} conditions, estimated size: {data['estimated_size']}")

    def test_preview_audience(self, pulse_headers):
        """Preview audience returns count and sample"""
        rules = {
            "op": "and",
            "conditions": [
                {"field": "lifetime_value_gbp", "op": ">=", "value": 100}
            ]
        }
        response = requests.post(
            f"{BASE_URL}/api/marketing/audiences/preview",
            json={"rules": rules},
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "estimated_size" in data
        assert "sample_contacts" in data

        print(f"✓ Preview: {data['estimated_size']} contacts match")

    def test_create_and_list_audience(self, pulse_headers):
        """Create audience and verify it appears in list"""
        # Create
        create_response = requests.post(
            f"{BASE_URL}/api/marketing/audiences",
            json={
                "name": "TEST_High_Value_Members",
                "rules": {"op": "and", "conditions": [{"field": "lifetime_value_gbp", "op": ">=", "value": 500}]},
                "tags": ["test", "iteration186"]
            },
            headers=pulse_headers
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"

        created = create_response.json()["audience"]
        assert created["name"] == "TEST_High_Value_Members"
        assert "id" in created

        # List and verify
        list_response = requests.get(f"{BASE_URL}/api/marketing/audiences", headers=pulse_headers)
        assert list_response.status_code == 200

        audiences = list_response.json()["audiences"]
        found = any(a["id"] == created["id"] for a in audiences)
        assert found, "Created audience not found in list"

        print(f"✓ Audience CRUD: Created '{created['name']}' with {created.get('estimated_size', 0)} contacts")


class TestMarketingCampaigns:
    """Test Campaigns endpoints"""

    def test_list_templates(self, pulse_headers):
        """Templates endpoint returns 6 quick-start templates"""
        response = requests.get(f"{BASE_URL}/api/marketing/templates", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "templates" in data
        templates = data["templates"]
        assert len(templates) == 6, f"Expected 6 templates, got {len(templates)}"

        # Verify expected template IDs
        template_ids = [t["id"] for t in templates]
        expected = ["welcome_new_member", "winback", "class_promo", "pt_upsell", "failed_payment_recovery", "referral_push"]
        for tid in expected:
            assert tid in template_ids, f"Missing template: {tid}"

        print(f"✓ Templates: {len(templates)} templates returned: {', '.join(template_ids)}")

    def test_instantiate_winback_template(self, pulse_headers):
        """Instantiate winback template creates draft audience + campaign"""
        response = requests.post(
            f"{BASE_URL}/api/marketing/templates/winback/instantiate",
            json={},
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "audience_id" in data
        assert "campaign_id" in data
        assert "subject" in data

        print(f"✓ Instantiate: Created campaign {data['campaign_id'][:8]}... with audience size {data.get('audience_size', 0)}")

    def test_list_campaigns(self, pulse_headers):
        """List campaigns returns campaign list"""
        response = requests.get(f"{BASE_URL}/api/marketing/campaigns", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "campaigns" in data
        campaigns = data["campaigns"]

        # Should have at least the winback campaign from previous test
        if len(campaigns) > 0:
            campaign = campaigns[0]
            assert "id" in campaign
            assert "name" in campaign
            assert "status" in campaign
            assert "metrics" in campaign
            print(f"✓ Campaigns: {len(campaigns)} campaigns, first: {campaign['name']} ({campaign['status']})")
        else:
            print("✓ Campaigns: Empty list")

    def test_create_campaign(self, pulse_headers):
        """Create a campaign from scratch"""
        # First get an audience
        audiences_resp = requests.get(f"{BASE_URL}/api/marketing/audiences", headers=pulse_headers)
        audiences = audiences_resp.json().get("audiences", [])
        audience_id = audiences[0]["id"] if audiences else None

        response = requests.post(
            f"{BASE_URL}/api/marketing/campaigns",
            json={
                "name": "TEST_Manual_Campaign",
                "channel": "email",
                "audience_id": audience_id,
                "content": {
                    "subject": "Test Subject",
                    "body_html": "<h1>Hello {{first_name}}</h1><p>Test email</p>"
                }
            },
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "campaign" in data
        campaign = data["campaign"]
        assert campaign["name"] == "TEST_Manual_Campaign"
        assert campaign["status"] == "draft"

        print(f"✓ Create Campaign: {campaign['name']} ({campaign['id'][:8]}...)")


class TestMarketingCreativeStudio:
    """Test Creative Studio endpoints"""

    def test_generate_creative(self, pulse_headers):
        """Generate creative returns variants (or fallback SVG)"""
        response = requests.post(
            f"{BASE_URL}/api/marketing/creative/generate",
            json={
                "prompt": "High-energy spin class promotion",
                "type": "social_post",
                "n": 1
            },
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "asset" in data
        asset = data["asset"]
        assert "variants" in asset
        assert len(asset["variants"]) >= 1

        variant = asset["variants"][0]
        assert "url" in variant
        assert "model" in variant

        print(f"✓ Creative: Generated {len(asset['variants'])} variant(s), model: {variant['model']}")

    def test_list_creative_assets(self, pulse_headers):
        """List creative assets returns gallery"""
        response = requests.get(f"{BASE_URL}/api/marketing/creative", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "assets" in data

        print(f"✓ Creative Gallery: {len(data['assets'])} assets")


class TestMarketingJourneys:
    """Test Journeys endpoints"""

    def test_create_journey(self, pulse_headers):
        """Create a journey with nodes"""
        response = requests.post(
            f"{BASE_URL}/api/marketing/journeys",
            json={
                "name": "TEST_Welcome_Journey",
                "trigger": {"event": "member_signed_up"},
                "nodes": [
                    {"id": "n1", "type": "wait", "duration_h": 24},
                    {"id": "n2", "type": "send_email", "template": "welcome"}
                ],
                "edges": [
                    {"from": "trigger", "to": "n1"},
                    {"from": "n1", "to": "n2"}
                ],
                "status": "draft"
            },
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "journey" in data
        journey = data["journey"]
        assert journey["name"] == "TEST_Welcome_Journey"
        assert len(journey["nodes"]) == 2

        print(f"✓ Journey: Created '{journey['name']}' with {len(journey['nodes'])} nodes")

    def test_list_journeys(self, pulse_headers):
        """List journeys returns journey list"""
        response = requests.get(f"{BASE_URL}/api/marketing/journeys", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "journeys" in data

        print(f"✓ Journeys: {len(data['journeys'])} journeys")


class TestMarketingPerformance:
    """Test Performance dashboard endpoints"""

    def test_dashboard_v2(self, pulse_headers):
        """Dashboard v2 returns 8+ KPI tiles"""
        response = requests.get(f"{BASE_URL}/api/marketing/dashboard/v2", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()

        # Verify expected KPIs
        expected_keys = [
            "campaigns_30d", "messages_sent_30d", "opens_30d", "clicks_30d",
            "conversions_30d", "revenue_attributed_gbp", "open_rate_pct",
            "click_rate_pct", "audiences_total", "journeys_active"
        ]
        for key in expected_keys:
            assert key in data, f"Missing KPI: {key}"

        print(f"✓ Dashboard v2: {data['campaigns_30d']} campaigns, {data['messages_sent_30d']} messages, £{data['revenue_attributed_gbp']} attributed")


class TestMarketingSocial:
    """Test Social Media endpoints"""

    def test_social_status(self, pulse_headers):
        """Social status returns platform configuration state"""
        response = requests.get(f"{BASE_URL}/api/marketing/social/status", headers=pulse_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "platform_configured" in data
        assert "accounts" in data
        assert "missing_env_vars" in data

        # META_APP_ID/SECRET not set, so should show not configured
        if not data["platform_configured"]:
            assert "META_APP_ID" in data["missing_env_vars"] or "META_APP_SECRET" in data["missing_env_vars"]
            print(f"✓ Social Status: Not configured (missing: {', '.join(data['missing_env_vars'])})")
        else:
            print(f"✓ Social Status: Configured, {len(data['accounts'])} accounts connected")


class TestMarketingAIAssistant:
    """Test AI Assistant endpoint"""

    def test_assistant_ask_campaigns(self, pulse_headers):
        """AI Assistant returns suggestions for campaigns tab"""
        response = requests.post(
            f"{BASE_URL}/api/marketing/assistant/ask",
            json={"page": "campaigns", "question": ""},
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "suggestions" in data
        suggestions = data["suggestions"]
        assert isinstance(suggestions, list)
        assert len(suggestions) <= 3

        if suggestions:
            s = suggestions[0]
            assert "id" in s
            assert "label" in s
            assert "body" in s
            print(f"✓ AI Assistant (campaigns): {len(suggestions)} suggestions, first: {s['label'][:40]}")
        else:
            print("✓ AI Assistant (campaigns): No suggestions")

    def test_assistant_ask_audiences(self, pulse_headers):
        """AI Assistant returns suggestions for audiences tab"""
        response = requests.post(
            f"{BASE_URL}/api/marketing/assistant/ask",
            json={"page": "audiences", "question": ""},
            headers=pulse_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "suggestions" in data
        print(f"✓ AI Assistant (audiences): {len(data['suggestions'])} suggestions")


class TestMarketingConversionAttribution:
    """Test conversion attribution endpoint"""

    def test_track_conversion_no_recent_message(self, pulse_headers):
        """Track conversion returns not attributed when no recent message"""
        response = requests.post(
            f"{BASE_URL}/api/marketing/track/conversion",
            json={
                "contact_id": "nonexistent-contact-id",
                "kind": "booking",
                "revenue_gbp": 50
            },
            headers=pulse_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "attributed" in data
        # Should not be attributed since no recent message engagement
        assert data["attributed"] == False

        print("✓ Conversion Attribution: Not attributed (no recent engagement)")


class TestMasterAdminMarketing:
    """Test Master Admin Marketing Suite endpoints"""

    def test_admin_list_plans(self, admin_headers):
        """Admin can list marketing plans"""
        response = requests.get(f"{BASE_URL}/api/master-admin/marketing/plans", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "plans" in data
        plans = data["plans"]
        assert len(plans) == 3, f"Expected 3 plans, got {len(plans)}"

        plan_ids = [p["id"] for p in plans]
        assert "basic" in plan_ids
        assert "pro" in plan_ids
        assert "enterprise" in plan_ids

        # Verify pricing
        basic = next(p for p in plans if p["id"] == "basic")
        pro = next(p for p in plans if p["id"] == "pro")
        enterprise = next(p for p in plans if p["id"] == "enterprise")

        assert basic["monthly_price_gbp"] == 49
        assert pro["monthly_price_gbp"] == 149
        assert enterprise["monthly_price_gbp"] == 399

        print(f"✓ Admin Plans: Basic £{basic['monthly_price_gbp']}, Pro £{pro['monthly_price_gbp']}, Enterprise £{enterprise['monthly_price_gbp']}")

    def test_admin_marketing_analytics(self, admin_headers):
        """Admin can view marketing analytics"""
        response = requests.get(f"{BASE_URL}/api/master-admin/marketing/analytics", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "mrr_gbp" in data
        assert "total_subscriptions" in data
        assert "emails_30d" in data
        assert "by_plan" in data

        print(f"✓ Admin Analytics: MRR £{data['mrr_gbp']}, {data['total_subscriptions']} subs, {data['emails_30d']} emails (30d)")

    def test_admin_list_subscriptions(self, admin_headers):
        """Admin can list marketing subscriptions"""
        response = requests.get(f"{BASE_URL}/api/master-admin/marketing/subscriptions", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "subscriptions" in data

        print(f"✓ Admin Subscriptions: {len(data['subscriptions'])} subscriptions")


class TestEquipmentImagesAdmin:
    """Test Equipment Images Admin endpoints"""

    def test_equipment_images_status(self, admin_headers):
        """Admin can view equipment images backfill status"""
        response = requests.get(f"{BASE_URL}/api/master-admin/equipment-images/status", headers=admin_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert "totals" in data

        totals = data["totals"]
        assert "total_equipment" in totals
        assert "with_user_photo" in totals
        assert "with_auto_image" in totals
        assert "missing_image" in totals

        print(f"✓ Equipment Images Status: {totals['total_equipment']} total, {totals['missing_image']} missing")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
