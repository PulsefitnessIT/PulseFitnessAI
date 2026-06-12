"""Iter 262 — Service Desk mobile audit: interactive KPI drill-downs.

User report (production): "Audit the service desk and ensure that it is fully
mobile optimised. Every card/modal/option/text. Cards are interactive where
possible navigating to the correct information."

Backend: GET /api/svc/cases gained two drill-down params wired to the desk
dashboard KPI cards:
  • assigned=unassigned → only cases with no engineer
  • sla=at_risk | breached → SLA-window filtering

Frontend (source pins): dashboard stat cards navigate to tabs, cases KPI
cards drill into the filtered queue, tables scroll horizontally on mobile.
"""

import requests

from tests.conftest import _test_backend_url

BASE_URL = _test_backend_url()


def _desk() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "desk@pulsefitness.com", "password": "DeskAgent123!"},
               timeout=20)
    assert r.status_code == 200, r.text
    return s


def test_cases_unassigned_filter():
    s = _desk()
    r = s.get(f"{BASE_URL}/api/svc/cases",
              params={"status": "open", "assigned": "unassigned", "limit": 50},
              timeout=30)
    assert r.status_code == 200, r.text
    cases = r.json().get("cases", [])
    for c in cases:
        assert not c.get("assigned_engineer_id"), (
            f"{c.get('reference')} has an engineer but was returned by assigned=unassigned"
        )


def test_cases_sla_breached_filter():
    s = _desk()
    r = s.get(f"{BASE_URL}/api/svc/cases",
              params={"status": "open", "sla": "breached", "limit": 50}, timeout=30)
    assert r.status_code == 200, r.text
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    for c in r.json().get("cases", []):
        assert c.get("sla_resolve_at"), c.get("reference")
        assert c["sla_resolve_at"] < now_iso, (
            f"{c.get('reference')} sla_resolve_at {c['sla_resolve_at']} is not breached"
        )


def test_cases_sla_at_risk_filter():
    s = _desk()
    r = s.get(f"{BASE_URL}/api/svc/cases",
              params={"status": "open", "sla": "at_risk", "limit": 50}, timeout=30)
    assert r.status_code == 200, r.text
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    lo, hi = now.isoformat(), (now + timedelta(hours=2)).isoformat()
    for c in r.json().get("cases", []):
        assert lo <= c["sla_resolve_at"] < hi, (
            f"{c.get('reference')} outside the 2h at-risk window: {c['sla_resolve_at']}"
        )


def test_frontend_mobile_audit_pins():
    base = "/app/frontend/src/pages"

    # Dashboard stat cards navigate to tabs (2-up on mobile).
    summary = open(f"{base}/ServiceDesk/DeskSummary.js", encoding="utf-8").read()
    assert "grid-cols-2 lg:grid-cols-4" in summary
    assert "onNavigate" in summary and "desk-stat-recent-activity" in summary

    shell = open(f"{base}/ServiceDeskPage.js", encoding="utf-8").read()
    assert shell.count("onNavigate={(t) => { setTab(t); setSelectedOrgId(null); }}") >= 3

    # Cases KPI cards drill into the filtered queue.
    cases = open(f"{base}/ServiceOps/ServiceDeskPage.js", encoding="utf-8").read()
    assert "drillTo({ assigned: 'unassigned' })" in cases
    assert "drillTo({ sla: 'breached' })" in cases
    assert 'data-testid="case-queue-section"' in cases
    assert 'data-testid="filter-quick-clear"' in cases

    # Wide tables scroll instead of clipping on mobile.
    css = open(f"{base}/ServiceOps/_serviceops.css", encoding="utf-8").read()
    assert "overflow-x: auto" in css.split(".svc-table-wrap")[1].split("}")[0]

    parts = open(f"{base}/ServiceOps/PartsInventoryPage.js", encoding="utf-8").read()
    assert "overflow-hidden" not in parts.split("catalogue-add-row")[1].split("<table")[0]
    assert "grid-cols-2 sm:grid-cols-12" in parts

    detail = open(f"{base}/ServiceDesk/DeskCustomerDetail.js", encoding="utf-8").read()
    assert "grid-cols-2 md:grid-cols-4" in detail
    assert 'id="desk-section-sites"' in detail
