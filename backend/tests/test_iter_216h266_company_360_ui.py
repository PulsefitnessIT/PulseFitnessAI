"""Iter 216h266 — Company 360° deep UI audit.

Customer feedback (P2): "I didn't seem to be able to log a case
and have it appear against the company record. Being able to see
all related activities, cases, contacts, opportunities, and
quotes in one place is essential."

Audit found:
* Backend `/companies/{id}` already returns activities, cases,
  opportunities, contacts, assets, quotes, contracts (inline).
* Frontend UI exposed Quotes + Add quote affordance, but:
  - NO "Log a case" button on the Cases tab
  - NO "Add deal" button on the Opportunities tab
  - NO `activities` section tab (data loaded but never rendered)
  - Rows had no `data-testid` so smoke tests couldn't click them

This iter fills those gaps. Backend was already complete; the
work is entirely on the company drawer in CRMCompanies.js.
"""
from __future__ import annotations

import pathlib
import re


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. New section tab: Activities ─────────────────────────────────


def test_company_drawer_exposes_activities_tab():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text())
    # tab in the section list
    assert "id: 'activities'" in src
    assert "company-activities-section" in src
    # iterates company.activities[]
    assert "company.activities" in src
    assert "company-activity-row-" in src


# ─── 2. Log a case from the company drawer ──────────────────────────


def test_company_drawer_has_log_case_button():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text())
    assert 'data-testid="company-add-case-btn"' in src
    assert 'data-testid="company-add-case-dialog"' in src
    assert 'data-testid="company-add-case-subject"' in src
    assert 'data-testid="company-add-case-severity"' in src
    assert 'data-testid="company-add-case-submit"' in src
    # POST hits /crm/v2/cases with company_id in the body
    assert "/crm/v2/cases" in src
    assert "company_id: companyId" in src


def test_case_rows_have_testid():
    """User repro: 'log a case and have it appear against the
    company record' — assert each row gets a stable test-id."""
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text())
    assert "company-case-row-" in src


# ─── 3. Add deal from the company drawer ────────────────────────────


def test_company_drawer_has_add_deal_button():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text())
    assert 'data-testid="company-add-deal-btn"' in src
    assert 'data-testid="company-add-deal-dialog"' in src
    assert 'data-testid="company-add-deal-title"' in src
    assert 'data-testid="company-add-deal-stage"' in src
    assert 'data-testid="company-add-deal-submit"' in src
    assert "/crm/v2/opportunities" in src


def test_deal_stage_options_match_pipeline_stages():
    """The Stage select on the company drawer must use the same
    canonical stage ids the backend pipeline uses, otherwise the
    quote-create auto-progression won't recognise them."""
    src = pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text()
    for stage in ("lead", "qualified", "discovery", "solution",
                  "proposal", "negotiation"):
        assert f'value="{stage}"' in src, f"missing {stage} stage option"


def test_deal_rows_have_testid():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCompanies.js"
    ).read_text())
    assert "company-deal-row-" in src


# ─── 4. Backend already supports company_id on cases & opps ─────────


def test_backend_case_create_accepts_company_id():
    src = pathlib.Path("/app/backend/routes/crm_v2.py").read_text()
    create_case_block = src.split("@router.post(\"/cases\")")[1].split("@router")[0]
    assert "company_id" in create_case_block, \
        "create_case must persist company_id from the request body"


def test_backend_opportunity_create_accepts_company_id():
    src = pathlib.Path("/app/backend/routes/crm_v2.py").read_text()
    # opportunity create lives in a route — search for it
    assert "@router.post(\"/opportunities\")" in src
    opp_block = src.split("@router.post(\"/opportunities\")")[1].split("@router")[0]
    assert "company_id" in opp_block
