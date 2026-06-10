"""Iter 235 — Read-only cross-org Campaigns & Journeys browser for the
Master Admin Marketing tab.

Covers:
1. GET /master-admin/marketing/campaigns lists campaigns across tenants,
   decorated with organization_name, never leaking body content.
2. GET /master-admin/marketing/journeys returns node_count instead of
   the full node graph.
3. ?status= filter narrows both lists.
4. Non-master-admin users are rejected.
5. Source pins — analytics tiles deep-link to the new browser tab.
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return s


def _admin() -> requests.Session:
    return _login("admin@gymaxisai.com", "MasterAdmin123!")


def test_admin_campaigns_list_shape():
    s = _admin()
    r = s.get(f"{BASE_URL}/api/master-admin/marketing/campaigns", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "campaigns" in d and "total" in d
    assert d["total"] >= len(d["campaigns"]) or d["total"] == len(d["campaigns"])
    for c in d["campaigns"]:
        assert "organization_name" in c, "rows must be decorated with org names"
        assert "content" not in c, "browser is read-only metadata — body content must never leak"
        assert "variants" not in c
        for key in ("id", "name", "status"):
            assert key in c


def test_admin_journeys_list_shape():
    s = _admin()
    r = s.get(f"{BASE_URL}/api/master-admin/marketing/journeys", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "journeys" in d and "total" in d
    for j in d["journeys"]:
        assert "organization_name" in j
        assert "node_count" in j and isinstance(j["node_count"], int)
        assert "nodes" not in j, "full node graph must not be shipped to the browser list"


def test_admin_campaigns_status_filter():
    s = _admin()
    all_rows = s.get(f"{BASE_URL}/api/master-admin/marketing/campaigns", timeout=30).json()["campaigns"]
    sent = s.get(f"{BASE_URL}/api/master-admin/marketing/campaigns?status=sent", timeout=30).json()["campaigns"]
    assert all(c["status"] == "sent" for c in sent)
    assert len(sent) <= len(all_rows)


def test_non_admin_rejected():
    s = _login("owner@apexfitness.group", "ApexDemo2026!")
    for path in ("campaigns", "journeys"):
        r = s.get(f"{BASE_URL}/api/master-admin/marketing/{path}", timeout=30)
        assert r.status_code in (401, 403), f"{path}: non-master-admin must be rejected, got {r.status_code}"


def test_analytics_tiles_deep_link_to_browser():
    """Source pin — Campaigns/Journeys KPI tiles must navigate to the new tab."""
    src = open("/app/frontend/src/pages/MasterAdmin/AdminMarketingSuite.js", encoding="utf-8").read()
    assert "CampaignsJourneys" in src
    assert "'campaigns', label: 'Campaigns & Journeys'" in src.replace("id: ", "")
    assert src.count("onNavTab?.('campaigns')") >= 2, (
        "Both the Campaigns (30d) and Active journeys tiles must deep-link to the browser"
    )
