"""Iter 233 — Master-admin KPI cards: numbers must match the lists they
represent, and the CRM analytics payload must feed every card.

Bugs fixed:
1. `/master-admin/stats` ignored the `brand` query param the frontend
   sends, so the "Organisations" KPI counted ALL orgs while the
   organisations list right below it was brand-filtered (4 vs 1 in prod).
2. `/master-admin/crm-analytics` returned `active_opportunities` but the
   "Active Deals" card read `overview.total_deals` → blank card.
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()


def _admin() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
               timeout=20)
    assert r.status_code == 200, r.text
    return s


def test_stats_brand_scoping_matches_orgs_list():
    s = _admin()
    for brand in ("pulse", "gymaxis"):
        stats = s.get(f"{BASE_URL}/api/master-admin/stats?brand={brand}", timeout=30).json()
        orgs = s.get(f"{BASE_URL}/api/master-admin/organizations?brand={brand}", timeout=30).json()
        org_rows = orgs.get("organizations", orgs if isinstance(orgs, list) else [])
        assert stats.get("total_organizations") == len(org_rows), (
            f"brand={brand}: stats card says {stats.get('total_organizations')} "
            f"orgs but the list shows {len(org_rows)} — the card must ride the "
            f"same brand scope as the list"
        )


def test_stats_unscoped_when_brand_all_or_missing():
    s = _admin()
    plain = s.get(f"{BASE_URL}/api/master-admin/stats", timeout=30).json()
    all_brand = s.get(f"{BASE_URL}/api/master-admin/stats?brand=all", timeout=30).json()
    assert plain.get("total_organizations") == all_brand.get("total_organizations")


def test_crm_analytics_overview_has_total_deals():
    s = _admin()
    d = s.get(f"{BASE_URL}/api/master-admin/crm-analytics", timeout=30).json()
    overview = d.get("overview") or {}
    assert "total_deals" in overview, (
        "overview.total_deals missing — the 'Active Deals' KPI card renders blank without it"
    )
    assert overview["total_deals"] == overview.get("active_opportunities"), (
        "total_deals must alias active_opportunities"
    )
    # The other KPI keys the cards read.
    for key in ("total_contacts", "total_companies", "pipeline_value"):
        assert key in overview, f"overview.{key} missing"
    pipeline = d.get("pipeline") or {}
    for key in ("win_rate", "won_deals", "lost_deals", "total_won_value"):
        assert key in pipeline, f"pipeline.{key} missing"


def test_memberships_overview_kpis_present():
    s = _admin()
    d = s.get(f"{BASE_URL}/api/master-admin/memberships/overview", timeout=30).json()
    kpis = d.get("kpis") or {}
    for key in ("total_organizations", "active_members", "total_mrr_pence",
                "bookings_30d", "churn_pct_30d", "occupancy_pct_7d", "no_shows_30d"):
        assert key in kpis, f"kpis.{key} missing — Memberships overview card would render blank"


def test_admin_crm_cards_deep_link_into_crm_workspace():
    """Source pin — every CRM KPI card must navigate to its CRM tab."""
    src = open("/app/frontend/src/pages/MasterAdmin/AdminCRMAnalytics.js", encoding="utf-8").read()
    assert "navigate('/crm?tab=contacts')" in src
    assert "navigate('/crm?tab=companies')" in src
    assert "navigate('/crm?tab=pipeline')" in src
    assert "overview.total_deals ?? overview.active_opportunities" in src


def test_memberships_overview_cards_navigate_tabs():
    """Source pin — Memberships overview cards switch to the matching tab."""
    src = open("/app/frontend/src/pages/MasterAdmin/AdminMemberships/OverviewTab.js", encoding="utf-8").read()
    assert "onNavTab?.('organisations')" in src
    assert "onNavTab?.('revenue')" in src
    assert "onNavTab?.('engagement')" in src
    host = open("/app/frontend/src/pages/MasterAdmin/AdminMemberships/AdminMemberships.js", encoding="utf-8").read()
    assert "onNavTab={setTab}" in host


def test_org_list_duplicated_filters_hidden_in_module_context():
    """Source pin — the Modules dropdown hides when the hosting tab already
    fixes the module (portalFilter) and the Platforms dropdown hides when
    account types are pinned (MoD)."""
    src = open("/app/frontend/src/pages/MasterAdmin/AdminOrganizations.js", encoding="utf-8").read()
    assert "{!portalFilter && !(Array.isArray(accountTypesIn) && accountTypesIn.length > 0) && (" in src
    assert src.count("!(Array.isArray(accountTypesIn) && accountTypesIn.length > 0) && (") >= 2
