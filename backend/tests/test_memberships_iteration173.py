"""
Iteration 173 — Memberships: Referrals Analytics Leaderboard.

Tests:
  • GET /api/memberships/analytics/referrals — operator-only referral performance endpoint
    - Returns {kpis:{total, earned, pending, conversion_pct, credit_paid_gbp}, top_referrers:[...], trend:[...], range}
    - Scoped by organization_id
    - Supports from= and to= date params
    - Rejects member-token with 403
  • Demo seed creates ≥5 referrals for mbr-emma (3 earned, 2 pending) and 1 earned for mbr-sophia
  • Regression: All iteration-172 endpoints still pass
  • Member portal referral card still works for emma.wright@demo.gymaxis
  • ?ref= query param pre-populates registration form
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"
MEMBER_EMAIL = "emma.wright@demo.gymaxis"
MEMBER_PASSWORD = "Member2026!"
BRAG_SLUG = "pulse-leeds"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    """Headers with operator auth."""
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def member_token():
    """Get member JWT token for Emma."""
    resp = requests.post(f"{BASE_URL}/api/member-auth/login", json={
        "email": MEMBER_EMAIL,
        "password": MEMBER_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Member login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def member_headers(member_token):
    """Headers with member auth."""
    return {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}


class TestReferralsAnalyticsEndpoint:
    """GET /api/memberships/analytics/referrals — operator referral performance."""

    def test_referrals_returns_kpis(self, operator_headers):
        """Referrals endpoint returns KPIs: total, earned, pending, conversion_pct, credit_paid_gbp."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "kpis" in data, f"Missing kpis in response: {data.keys()}"
        kpis = data["kpis"]

        # Verify all required KPI fields
        assert "total" in kpis, f"Missing total in kpis: {kpis}"
        assert "earned" in kpis, f"Missing earned in kpis: {kpis}"
        assert "pending" in kpis, f"Missing pending in kpis: {kpis}"
        assert "conversion_pct" in kpis, f"Missing conversion_pct in kpis: {kpis}"
        assert "credit_paid_gbp" in kpis, f"Missing credit_paid_gbp in kpis: {kpis}"

        print(f"✓ Referrals KPIs: total={kpis['total']}, earned={kpis['earned']}, pending={kpis['pending']}, "
              f"conversion={kpis['conversion_pct']}%, credit=£{kpis['credit_paid_gbp']}")

    def test_referrals_returns_top_referrers(self, operator_headers):
        """Referrals endpoint returns top_referrers list with required fields."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "top_referrers" in data, f"Missing top_referrers in response: {data.keys()}"
        top_referrers = data["top_referrers"]

        # Should have at least Emma and Sophia from seed
        assert len(top_referrers) >= 2, f"Expected at least 2 top referrers, got {len(top_referrers)}"

        # Verify each referrer has required fields
        for referrer in top_referrers:
            assert "member_id" in referrer, f"Missing member_id in referrer: {referrer}"
            assert "name" in referrer, f"Missing name in referrer: {referrer}"
            assert "email" in referrer, f"Missing email in referrer: {referrer}"
            assert "referral_code" in referrer, f"Missing referral_code in referrer: {referrer}"
            assert "total" in referrer, f"Missing total in referrer: {referrer}"
            assert "earned" in referrer, f"Missing earned in referrer: {referrer}"
            assert "conversion_pct" in referrer, f"Missing conversion_pct in referrer: {referrer}"
            assert "credit_earned_gbp" in referrer, f"Missing credit_earned_gbp in referrer: {referrer}"

        print(f"✓ Top referrers: {len(top_referrers)} entries")
        for r in top_referrers[:3]:
            print(f"  - {r['name']}: {r['total']} referrals, {r['earned']} earned, {r['conversion_pct']}%")

    def test_referrals_returns_trend(self, operator_headers):
        """Referrals endpoint returns trend array with bucket, new, earned."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "trend" in data, f"Missing trend in response: {data.keys()}"
        trend = data["trend"]

        # Trend may be empty if no referrals in range
        if len(trend) > 0:
            for entry in trend:
                assert "bucket" in entry, f"Missing bucket in trend entry: {entry}"
                assert "new" in entry, f"Missing new in trend entry: {entry}"
                assert "earned" in entry, f"Missing earned in trend entry: {entry}"

            print(f"✓ Trend: {len(trend)} buckets")
            for t in trend[:3]:
                print(f"  - {t['bucket']}: {t['new']} new, {t['earned']} earned")
        else:
            print("✓ Trend: empty (no referrals in date range)")

    def test_referrals_returns_range(self, operator_headers):
        """Referrals endpoint returns range with from and to dates."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "range" in data, f"Missing range in response: {data.keys()}"
        range_data = data["range"]
        assert "from" in range_data, f"Missing from in range: {range_data}"
        assert "to" in range_data, f"Missing to in range: {range_data}"

        print(f"✓ Range: {range_data['from'][:10]} to {range_data['to'][:10]}")

    def test_referrals_supports_date_params(self, operator_headers):
        """Referrals endpoint supports from= and to= query params."""
        # Test with a narrow date range (far future - should return 0 referrals)
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/referrals?from=2030-01-01T00:00:00Z&to=2030-12-31T23:59:59Z",
            headers=operator_headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()

        # With far future dates, should have 0 referrals
        assert data["kpis"]["total"] == 0, f"Expected 0 referrals in far future, got {data['kpis']['total']}"
        assert len(data["top_referrers"]) == 0, "Expected 0 top referrers in far future"

        print("✓ Date params work: far future returns 0 referrals")

    def test_referrals_scoped_by_org(self, operator_headers):
        """Referrals endpoint only returns referrals for operator's organization."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()

        # All top referrers should be from the same org (mbr-demo-org)
        # We can't directly verify org_id, but we can check that Emma is present
        # since she's seeded for mbr-demo-org
        top_referrers = data["top_referrers"]
        emma_found = any(r.get("member_id") == "mbr-emma" or "emma" in r.get("name", "").lower()
                        for r in top_referrers)
        assert emma_found, f"Expected Emma in top referrers (org scoping): {[r['name'] for r in top_referrers]}"

        print("✓ Referrals scoped by org: Emma found in top referrers")

    def test_referrals_rejects_member_token(self, member_headers):
        """Referrals endpoint rejects member-token with 403."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=member_headers)
        assert resp.status_code == 403, f"Expected 403 for member token, got {resp.status_code}"
        print("✓ Member token rejected with 403")

    def test_referrals_requires_auth(self):
        """Referrals endpoint requires authentication."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals")
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
        print("✓ No auth returns 401")


class TestReferralsSeedData:
    """Verify demo seed creates expected referral data."""

    def test_emma_has_at_least_5_referrals(self, operator_headers):
        """Emma (mbr-emma) should have ≥5 referrals (3 earned, 2 pending)."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()

        top_referrers = data["top_referrers"]
        emma = next((r for r in top_referrers if r.get("member_id") == "mbr-emma" or
                    "emma" in r.get("name", "").lower()), None)

        assert emma is not None, f"Emma not found in top referrers: {[r['name'] for r in top_referrers]}"
        assert emma["total"] >= 5, f"Expected Emma to have ≥5 referrals, got {emma['total']}"
        assert emma["earned"] >= 3, f"Expected Emma to have ≥3 earned, got {emma['earned']}"

        print(f"✓ Emma: {emma['total']} total, {emma['earned']} earned, code={emma.get('referral_code')}")

    def test_sophia_has_at_least_1_earned(self, operator_headers):
        """Sophia (mbr-sophia) should have ≥1 earned referral."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()

        top_referrers = data["top_referrers"]
        sophia = next((r for r in top_referrers if r.get("member_id") == "mbr-sophia" or
                      "sophia" in r.get("name", "").lower()), None)

        assert sophia is not None, f"Sophia not found in top referrers: {[r['name'] for r in top_referrers]}"
        assert sophia["earned"] >= 1, f"Expected Sophia to have ≥1 earned, got {sophia['earned']}"

        print(f"✓ Sophia: {sophia['total']} total, {sophia['earned']} earned")

    def test_kpis_match_seed_expectations(self, operator_headers):
        """KPIs should reflect seeded data: ≥6 total, ≥4 earned, ≥2 pending."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/referrals", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        kpis = data["kpis"]

        # From seed: Emma has 5 (3 earned, 2 pending), Sophia has 1 earned, James has 1 earned
        # Total: 7, Earned: 5, Pending: 2
        assert kpis["total"] >= 6, f"Expected ≥6 total referrals, got {kpis['total']}"
        assert kpis["earned"] >= 4, f"Expected ≥4 earned referrals, got {kpis['earned']}"
        assert kpis["pending"] >= 2, f"Expected ≥2 pending referrals, got {kpis['pending']}"

        # Conversion should be reasonable (earned/total * 100)
        expected_conv = round(100.0 * kpis["earned"] / kpis["total"], 1) if kpis["total"] > 0 else 0
        assert abs(kpis["conversion_pct"] - expected_conv) < 1, \
            f"Conversion mismatch: expected ~{expected_conv}%, got {kpis['conversion_pct']}%"

        print(f"✓ KPIs match seed: total={kpis['total']}, earned={kpis['earned']}, pending={kpis['pending']}")


class TestMemberPortalReferralCard:
    """Member portal 'Your friend link' referral card still works."""

    def test_member_referrals_endpoint(self, member_headers):
        """GET /api/member/referrals returns referral data for Emma."""
        resp = requests.get(f"{BASE_URL}/api/member/referrals", headers=member_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Should have code, stats, referrals
        assert "code" in data, f"Missing code in response: {data.keys()}"
        assert "stats" in data, f"Missing stats in response: {data.keys()}"
        assert "referrals" in data, f"Missing referrals in response: {data.keys()}"

        # Emma's code should be EMMA-FIT7 (from seed)
        assert data["code"], "Referral code should not be empty"

        stats = data["stats"]
        assert "friends_joined" in stats, f"Missing friends_joined in stats: {stats}"
        assert "pending" in stats, f"Missing pending in stats: {stats}"
        assert "earned" in stats, f"Missing earned in stats: {stats}"
        assert "credit_earned_pence" in stats, f"Missing credit_earned_pence in stats: {stats}"

        print(f"✓ Member referrals: code={data['code']}, friends={stats['friends_joined']}, "
              f"earned={stats['earned']}, credit=£{stats['credit_earned_pence']/100:.2f}")


class TestRegressionIteration172:
    """Regression tests for iteration 172 endpoints."""

    def test_og_png(self):
        """OG image still works."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/og.png")
        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("Content-Type", "")

    def test_share_page(self):
        """Share page still works."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/share")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("Content-Type", "")

    def test_poster_formats(self):
        """Multi-format posters still work."""
        for fmt in ["square", "story", "a4"]:
            resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?format={fmt}")
            assert resp.status_code == 200, f"Poster format {fmt} failed"

    def test_poster_pdf(self):
        """PDF poster still works."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("Content-Type", "")

    def test_analytics_overview_with_forecast_bands(self, operator_headers):
        """Analytics overview with confidence bands still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/overview", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "revenue_forecast" in data

    def test_resend_launch_kit(self, operator_headers):
        """Resend launch kit still works."""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/resend-launch-kit",
                            json={}, headers=operator_headers)
        assert resp.status_code == 200

    def test_setup_complete(self, operator_headers):
        """Setup complete with launch_kit still works."""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/complete",
                            json={}, headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "launch_kit" in data

    def test_analytics_retention(self, operator_headers):
        """Analytics retention still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/retention", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "cohort_matrix" in data

    def test_analytics_classes(self, operator_headers):
        """Analytics classes still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/classes", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data

    def test_analytics_operations(self, operator_headers):
        """Analytics operations still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/operations", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data

    def test_members_by_kpi(self, operator_headers):
        """Members by KPI drill-down still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/members-by-kpi?kpi=active_members",
                           headers=operator_headers)
        assert resp.status_code == 200

    def test_at_risk_members(self, operator_headers):
        """At-risk members endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/at-risk", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "members" in data

    def test_crm_push(self, operator_headers):
        """CRM push still works (400 for empty member_ids)."""
        resp = requests.post(f"{BASE_URL}/api/memberships/analytics/crm-push",
                            json={"member_ids": [], "pipeline": "retention"},
                            headers=operator_headers)
        assert resp.status_code == 400  # Expected for empty member_ids

    def test_csv_export(self, operator_headers):
        """CSV export still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/export.csv?report=overview",
                           headers=operator_headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_pdf_export(self, operator_headers):
        """PDF export still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/export.pdf", headers=operator_headers)
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("Content-Type", "")

    def test_weekly_digest(self, operator_headers):
        """Weekly digest endpoint still works."""
        resp = requests.post(f"{BASE_URL}/api/memberships/analytics/send-weekly-digest",
                            json={}, headers=operator_headers)
        assert resp.status_code == 200

    def test_dashboard(self, operator_headers):
        """Dashboard still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/dashboard", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "active_members" in data

    def test_brag_page(self):
        """Brag page still works."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/brag")
        assert resp.status_code == 200
        data = resp.json()
        assert "organization" in data
        assert "stats" in data
