"""Iter 216h261 — Engineer Lite CRM auto-suggest banner.

User follow-up (Feb 21, 2026):
"Add an auto-suggest banner on the Quote/Invoice builders that
recognises a new email/phone and prompts 'Save this customer to your
Lite CRM?' with one-click confirmation."

Backend additions:
  • GET /api/svc/engineer/customers/lookup?email=&phone= — lightweight
    probe used by the builders to decide whether to nudge. Returns
    {found: bool, customer?: {...}} based on org-scoped match on
    email OR phone.

Frontend:
  • QuoteBuilder + InvoiceBuilder CustomerPickers watch the current
    name/email/phone state and call /lookup with 600ms debounce.
  • When `found === false` and the engineer has typed a name + at
    least one contact field, an inline blue banner appears with
    Save / Dismiss buttons.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Backend ────────────────────────────────────────────────────────


def test_lookup_route_registered():
    from routes.svc.engineer_customers import router
    paths = {r.path for r in router.routes}
    assert "/svc/engineer/customers/lookup" in paths


def test_lookup_returns_not_found_when_blank():
    from routes.svc.engineer_customers import lookup_customer
    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(return_value=None)
    with patch("routes.svc.engineer_customers.db", fake_db):
        res = _run(lookup_customer(user={"id": "u-1", "organization_id": "org-1"},
                                    email=None, phone=None))
    assert res == {"found": False}


def test_lookup_returns_not_found_when_no_match():
    from routes.svc.engineer_customers import lookup_customer
    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(return_value=None)
    with patch("routes.svc.engineer_customers.db", fake_db):
        res = _run(lookup_customer(user={"id": "u-1", "organization_id": "org-1"},
                                    email="newperson@nowhere.com", phone=None))
    assert res == {"found": False}


def test_lookup_returns_match_with_customer_payload():
    from routes.svc.engineer_customers import lookup_customer
    existing = {
        "id": "cust-1", "organization_id": "org-1",
        "name": "Acme Returning Customer", "email": "match@example.com",
        "phone": None,
    }
    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(return_value=existing)
    with patch("routes.svc.engineer_customers.db", fake_db):
        res = _run(lookup_customer(user={"id": "u-1", "organization_id": "org-1"},
                                    email="MATCH@Example.com", phone=None))
    assert res["found"] is True
    assert res["customer"]["id"] == "cust-1"
    assert res["customer"]["name"] == "Acme Returning Customer"


def test_lookup_matches_by_phone_alone():
    from routes.svc.engineer_customers import lookup_customer
    existing = {
        "id": "cust-2", "organization_id": "org-1",
        "name": "Phone Only", "email": None, "phone": "+447700900111",
    }
    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(return_value=existing)
    with patch("routes.svc.engineer_customers.db", fake_db):
        res = _run(lookup_customer(user={"id": "u-1", "organization_id": "org-1"},
                                    email=None, phone="+44 7700 900111"))
    # _find_duplicate gets called with the normalised phone — assert call args
    args, _ = fake_db.svc_engineer_customers.find_one.call_args
    query = args[0]
    assert "$or" in query
    phone_clauses = [c for c in query["$or"] if "phone" in c]
    assert phone_clauses and phone_clauses[0]["phone"] == "+447700900111"
    assert res["found"] is True


# ─── Frontend wiring ────────────────────────────────────────────────


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


def test_quote_builder_passes_customer_prop_to_picker():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerQuoteBuilder.js"
    ).read_text())
    assert "customer={{" in src or "customer={ {" in src
    assert "/svc/engineer/customers/lookup" in src
    assert 'data-testid="qb-customer-suggest"' in src
    assert 'data-testid="qb-customer-suggest-save"' in src
    assert 'data-testid="qb-customer-suggest-dismiss"' in src


def test_invoice_builder_has_suggest_banner():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerInvoiceBuilder.js"
    ).read_text())
    assert "/svc/engineer/customers/lookup" in src
    assert 'data-testid="ib-customer-suggest"' in src
    assert 'data-testid="ib-customer-suggest-save"' in src
    assert 'data-testid="ib-customer-suggest-dismiss"' in src
