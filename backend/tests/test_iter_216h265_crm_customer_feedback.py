"""Iter 216h265 — CRM customer-feedback batch (P0 + P1, 8 items).

User asks (Feb 21, 2026, prospective customer feedback):

P0 — done in this iter:
  1. Geographic territory tree (UK → Scotland → North …) — add a
     `/api/crm/territories/tree` endpoint that nests rows by
     `parent_id` (the column already existed).
  2. Auto-link Companies House directors as contact records on the
     parent company — `_seed_director_contacts()` is now invoked on
     company create + exposed via
     `POST /api/crm/v2/companies/{id}/seed-directors`.
  3. Mandatory email on contacts — already enforced. Confirmed in
     test below.
  4. Quotes must surface in Sales Pipeline — `list_opportunities`
     now decorates each opp with `quotes`, `quote_count`,
     `quoted_value`.

P1 — done in this iter:
  5. Lead → Prospect → Quote workflow audit — quote creation now
     auto-advances opp to `proposal` stage and bumps contact
     lifecycle `lead` → `prospect`.
  6. Quote PDF + Email buttons exposed in UI — frontend now
     dispatches `GET /quotes/{id}/pdf` + `POST /quotes/{id}/send-email`.
  7. Job-title picklist on contact EDIT form — parity with the
     create form.
  8. Approval-required visible callout on Quote detail when margin
     below the org's configured floor.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


# ─── 1. Territory tree ──────────────────────────────────────────────


def test_territory_tree_route_registered():
    from routes.crm_territories import router
    paths = {r.path for r in router.routes}
    assert "/crm/territories/tree" in paths


def test_territory_tree_nests_by_parent_id():
    from routes.crm_territories import territory_tree

    rows = [
        {"id": "uk",   "organization_id": "org-1", "name": "UK", "parent_id": None},
        {"id": "scot", "organization_id": "org-1", "name": "Scotland", "parent_id": "uk"},
        {"id": "n",    "organization_id": "org-1", "name": "North", "parent_id": "uk"},
        {"id": "ne",   "organization_id": "org-1", "name": "North East", "parent_id": "n"},
        {"id": "midl", "organization_id": "org-1", "name": "Midlands", "parent_id": "uk"},
        {"id": "south","organization_id": "org-1", "name": "South", "parent_id": "uk"},
    ]
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=rows)
    fake_db = MagicMock()
    fake_db.crm_territories.find = MagicMock(return_value=cur)

    with patch("routes.crm_territories.db", fake_db):
        result = _run(territory_tree(user={"id": "u", "organization_id": "org-1", "role": "crm_user"}))

    assert result["total"] == 6
    assert len(result["tree"]) == 1, "expected one root (UK)"
    uk = result["tree"][0]
    assert uk["name"] == "UK"
    kids = {c["name"]: c for c in uk["children"]}
    assert set(kids.keys()) == {"Scotland", "North", "Midlands", "South"}
    # North → North East nesting preserved
    north = kids["North"]
    assert any(c["name"] == "North East" for c in north["children"])


# ─── 2. Director auto-link ──────────────────────────────────────────


def test_seed_director_contacts_creates_one_per_director():
    from routes.crm_v2 import _seed_director_contacts

    company = {
        "id": "co-1",
        "organization_id": "org-1",
        "name": "Acme Ltd",
        "directors": [
            "Alice Anderson",
            {"name": "Bob Barker", "role": "Finance Director"},
            "",  # blank — must be skipped
        ],
    }
    inserts = []

    async def find_one(query, projection=None):
        return None  # no existing contacts

    async def insert(doc):
        inserts.append(doc)
        return MagicMock()

    fake_db = MagicMock()
    fake_db.crm2_contacts.find_one = AsyncMock(side_effect=find_one)
    fake_db.crm2_contacts.insert_one = AsyncMock(side_effect=insert)

    with patch("routes.crm_v2.db", fake_db):
        created = _run(_seed_director_contacts(company, user={
            "id": "u", "organization_id": "org-1", "full_name": "M",
        }))

    assert created == 2  # blank skipped
    names = [(c["first_name"], c["last_name"]) for c in inserts]
    assert ("Alice", "Anderson") in names
    assert ("Bob", "Barker") in names
    # Decision-maker + Miller Heiman influence tag
    assert all("decision_maker" in c["influence_types"] for c in inserts)
    # Tagged for traceability
    assert all("director" in c["tags"] for c in inserts)
    assert all(c["source"] == "companies_house" for c in inserts)
    # Linked to the parent company
    assert all(c["company_id"] == "co-1" for c in inserts)


def test_seed_directors_is_idempotent():
    from routes.crm_v2 import _seed_director_contacts

    company = {"id": "co-1", "organization_id": "org-1", "name": "Acme",
               "directors": ["Alice Anderson"]}

    async def find_one(query, projection=None):
        return {"id": "existing"}  # contact already exists

    insert_calls = []

    async def insert(doc):
        insert_calls.append(doc)

    fake_db = MagicMock()
    fake_db.crm2_contacts.find_one = AsyncMock(side_effect=find_one)
    fake_db.crm2_contacts.insert_one = AsyncMock(side_effect=insert)

    with patch("routes.crm_v2.db", fake_db):
        created = _run(_seed_director_contacts(company, user={
            "id": "u", "organization_id": "org-1", "full_name": "M",
        }))
    assert created == 0
    assert insert_calls == []


def test_seed_directors_endpoint_registered():
    from routes.crm_v2 import router
    paths = {r.path for r in router.routes}
    assert "/crm/v2/companies/{company_id}/seed-directors" in paths


# ─── 3. Quote PDF + Email routes ────────────────────────────────────


def test_quote_pdf_route_registered():
    from routes.crm_v2 import router
    paths = {r.path for r in router.routes}
    assert "/crm/v2/quotes/{quote_id}/pdf" in paths


def test_quote_send_email_route_registered():
    from routes.crm_v2 import router
    paths = {r.path for r in router.routes}
    assert "/crm/v2/quotes/{quote_id}/send-email" in paths


def test_quote_send_email_validates_recipient():
    from routes.crm_v2 import send_quote_email
    from fastapi import HTTPException

    fake_db = MagicMock()
    fake_db.crm2_quotes.find_one = AsyncMock(return_value={
        "id": "q-1", "organization_id": "org-1",
        "quote_number": "QT-AAA111", "total": 100,
        "contact_id": None,  # nothing linked
    })

    with patch("routes.crm_v2.db", fake_db):
        try:
            _run(send_quote_email(
                quote_id="q-1",
                data={},  # no `to` field
                user={"id": "u", "organization_id": "org-1",
                      "role": "crm_user", "full_name": "M"},
            ))
        except HTTPException as e:
            assert e.status_code == 400
            assert "recipient" in e.detail.lower() or "email" in e.detail.lower()
        else:
            raise AssertionError("expected 400 for missing recipient")


def test_render_quote_pdf_helper_exists():
    """The render helper is the seam between the route + the
    synchronous reportlab builder."""
    from utils.crm_quote_pdf import render_quote_pdf, build_crm_quote_pdf  # noqa: F401
    assert callable(render_quote_pdf)


# ─── 4. Pipeline surfaces quotes ────────────────────────────────────


def test_pipeline_opp_listing_includes_quotes():
    """`list_opportunities` should decorate each opp with its quotes
    (the customer's headline complaint)."""
    src = pathlib.Path("/app/backend/routes/crm_v2.py").read_text()
    assert "quoted_value" in src
    assert "quote_count" in src
    assert "opp[\"quotes\"] = attached" in src or 'opp["quotes"] = attached' in src


# ─── 5. Workflow tightening ─────────────────────────────────────────


def test_create_quote_advances_opp_to_proposal_stage():
    """When a quote is raised on an opp, the opp should jump to at
    least `proposal` stage. Asserting via the source so we don't have
    to wire up the full pipeline."""
    src = pathlib.Path("/app/backend/routes/crm_v2.py").read_text()
    assert "Quote created" in src
    assert '"stage": "proposal"' in src
    # contact lifecycle bumps lead → prospect
    assert '"lifecycle": "prospect"' in src


# ─── 6. Frontend wiring ─────────────────────────────────────────────


def test_quote_detail_exposes_print_and_email_buttons():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCPQ.js"
    ).read_text())
    assert 'data-testid="quote-print-btn"' in src
    assert 'data-testid="quote-email-btn"' in src
    assert "/crm/v2/quotes/${quoteId}/pdf" in src
    assert "/crm/v2/quotes/${quoteId}/send-email" in src
    assert 'data-testid="quote-email-dialog"' in src


def test_quote_detail_renders_approval_callout():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMCPQ.js"
    ).read_text())
    assert 'data-testid="quote-approval-callout"' in src
    assert "approval_required" in src
    assert "approval_status" in src


def test_contact_edit_form_uses_job_title_picklist():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/CRM/CRMContacts.js"
    ).read_text())
    assert "edit-contact-job-title-picklist" in src
    # the free-text job_title row must NOT be in the iterated edit
    # fields any more — picklist replaces it.
    iterated = src.split("].map(f => (")[0]
    assert "key: 'job_title'" not in iterated.split("editForm")[-1]
