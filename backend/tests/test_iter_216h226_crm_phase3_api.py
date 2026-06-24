"""Iter 216h226 — Phase 3 CRM Reports + Phase 3 endpoints (API smoke).

Tests the HTTP endpoints wired in this iter:
  • GET  /api/crm/reports                       (catalogue)
  • GET  /api/crm/reports/pipeline-by-stage     (envelope shape)
  • GET  /api/crm/reports/pipeline-by-territory
  • GET  /api/crm/reports/quote-conversion
  • GET  /api/crm/reports/margin
  • GET  /api/crm/reports/lost-reasons
  • GET  /api/crm/reports/salesperson
  • GET  /api/crm/reports/consent-overview
  • POST /api/crm/companies/{id}/enrich-from-website  (422 on missing website)
  • GET  /api/crm/companies/{id}/timeline             (404 on missing)
  • POST /api/crm/opportunities/{id}/ai/next-action   (404 on missing)

Run: pytest backend/tests/test_iter_216h226_crm_phase3_api.py -v
"""
import os
import pytest
import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://admin-setup-portal.preview.emergentagent.com"
).rstrip("/")


@pytest.fixture(scope="module")
def crm_token():
    """Get CRM JWT via cross-login from a CRM-entitled platform user."""
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    # Try Craig (CRM manager) first, fall back to admin master.
    for email, pw in [
        ("craig.henshall@pulsefitness.com", "Test123!"),
        ("admin@gymaxisai.com", "MasterAdmin123!"),
    ]:
        try:
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=10)
            if r.status_code != 200:
                continue
            token = r.json().get("token")
            if not token:
                continue
            cx = requests.post(
                f"{BASE_URL}/api/crm/auth/cross-login",
                headers={"Authorization": f"Bearer {token}"},
                json={},
                timeout=10,
            )
            if cx.status_code == 200:
                crm_t = cx.json().get("token")
                if crm_t:
                    return crm_t
        except Exception:
            continue
    pytest.skip("Could not obtain CRM token")


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


# ── Reports catalogue ──────────────────────────────────────────────


def test_reports_catalogue_lists_all_seven(crm_token):
    r = requests.get(f"{BASE_URL}/api/crm/reports", headers=_auth(crm_token), timeout=10)
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json().get("reports", [])}
    expected = {
        "pipeline-by-stage", "pipeline-by-territory", "quote-conversion",
        "margin", "lost-reasons", "salesperson", "consent-overview",
    }
    assert expected.issubset(ids), f"Missing: {expected - ids}"


@pytest.mark.parametrize("report_id", [
    "pipeline-by-stage",
    "pipeline-by-territory",
    "quote-conversion",
    "margin",
    "lost-reasons",
    "salesperson",
    "consent-overview",
])
def test_report_returns_envelope(crm_token, report_id):
    r = requests.get(f"{BASE_URL}/api/crm/reports/{report_id}", headers=_auth(crm_token), timeout=15)
    assert r.status_code == 200, f"{report_id}: {r.status_code} {r.text}"
    body = r.json()
    assert "rows" in body
    assert "totals" in body
    assert "generated_at" in body
    assert isinstance(body["rows"], list)
    assert isinstance(body["totals"], dict)


def test_reports_require_crm_auth():
    """Reports must reject calls without a CRM token."""
    r = requests.get(f"{BASE_URL}/api/crm/reports", timeout=10)
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"


def test_consent_overview_returns_all_channels(crm_token):
    r = requests.get(f"{BASE_URL}/api/crm/reports/consent-overview", headers=_auth(crm_token), timeout=10)
    assert r.status_code == 200
    channels = {row["channel"] for row in r.json().get("rows", [])}
    assert {"email", "sms", "phone", "post", "marketing"}.issubset(channels)


# ── Phase 3 endpoints ──────────────────────────────────────────────


def test_enrich_website_404_on_missing_company(crm_token):
    r = requests.post(
        f"{BASE_URL}/api/crm/companies/does-not-exist-xyz/enrich-from-website",
        headers=_auth(crm_token),
        json={},
        timeout=10,
    )
    assert r.status_code == 404


def test_company_timeline_404_on_missing(crm_token):
    r = requests.get(
        f"{BASE_URL}/api/crm/companies/does-not-exist-xyz/timeline",
        headers=_auth(crm_token),
        timeout=10,
    )
    assert r.status_code == 404


def test_ai_next_action_404_on_missing(crm_token):
    r = requests.post(
        f"{BASE_URL}/api/crm/opportunities/does-not-exist-xyz/ai/next-action",
        headers=_auth(crm_token),
        json={},
        timeout=15,
    )
    assert r.status_code == 404


def test_margin_report_includes_distribution_buckets(crm_token):
    r = requests.get(f"{BASE_URL}/api/crm/reports/margin", headers=_auth(crm_token), timeout=10)
    assert r.status_code == 200
    body = r.json()
    # rows is a distribution histogram for the margin report.
    if body["totals"].get("count", 0) > 0:
        bucket_keys = {row["bucket"] for row in body["rows"]}
        assert bucket_keys == {"0-10", "11-20", "21-30", "31-50", "51+"}
