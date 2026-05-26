"""Iter 216h259 — Engineer Lite CRM + UI polish.

User feedback (Feb 21, 2026):
* "Engineer app — ensure there are back buttons on every page"
* "Support button doesn't work? Move to top nav…"
* "Merge card stats with analytics — remove the Card Stats button"
* "Engineers to have a Lite CRM so they can save customer details
  and avoid retyping"

Backend changes:
* New collection `svc_engineer_customers` (org-wide shared list).
* New router `routes/svc/engineer_customers.py` with GET/POST/PATCH/
  DELETE + /search + a `touch_last_job(...)` helper.
* `engineer_quotes.create_quote` + `engineer_invoices.create_invoice`
  now best-effort-stamp `last_job_at` on the matching customer row.

Frontend changes:
* `EngineerHomeV2`: Support → top nav as icon button. Card Stats
  QuickAction removed. New "My customers" QuickAction.
* New page `EngineerCustomers.js` at `/svc/engineer/customers`.
* `EngineerQuoteBuilder` + `EngineerInvoiceBuilder` get a customer
  autocomplete + "Save" button that pushes the current details into
  the Lite CRM.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── 1. Backend: customer model + helpers ───────────────────────────


def test_customer_models_present():
    from routes.svc.engineer_customers import CustomerIn, CustomerPatch
    assert "name" in CustomerIn.model_fields
    assert "email" in CustomerIn.model_fields
    assert "phone" in CustomerIn.model_fields
    assert "site_name" in CustomerIn.model_fields
    assert "site_address" in CustomerIn.model_fields
    assert "notes" in CustomerIn.model_fields
    assert "equipment_list" in CustomerIn.model_fields
    # patch is fully optional
    p = CustomerPatch(name="Acme")
    assert p.name == "Acme"


def test_norm_email_and_phone_strip_and_lower():
    from routes.svc.engineer_customers import _norm_email, _norm_phone
    assert _norm_email("  Hello@World.Com ") == "hello@world.com"
    assert _norm_email("") is None
    assert _norm_phone("+44 (0) 7700 900 123") == "+4407700900123"
    assert _norm_phone("") is None


def test_to_doc_produces_clean_payload():
    from routes.svc.engineer_customers import CustomerIn, _to_doc
    payload = CustomerIn(
        name="  Acme Gym  ", email="MAIL@x.uk", phone="+44 1234",
        site_name="HQ", site_address="12 Lane", notes="VIP",
        equipment_list=["", "Rower #1", "  ", "Treadmill"],
    )
    doc = _to_doc(payload, org_id="org-1", user_id="user-1")
    assert doc["name"] == "Acme Gym"
    assert doc["email"] == "mail@x.uk"
    assert doc["phone"] == "+441234"
    assert doc["organization_id"] == "org-1"
    assert doc["created_by_id"] == "user-1"
    assert doc["equipment_list"] == ["Rower #1", "Treadmill"]
    assert doc["last_job_at"] is None
    assert "id" in doc and "created_at" in doc and "updated_at" in doc


# ─── 2. Backend: route surface ──────────────────────────────────────


def test_router_exposes_crud_paths():
    from routes.svc.engineer_customers import router
    paths = {r.path for r in router.routes}
    assert "/svc/engineer/customers" in paths
    assert "/svc/engineer/customers/search" in paths
    assert "/svc/engineer/customers/{customer_id}" in paths


def test_router_registered_in_features():
    src = pathlib.Path("/app/backend/route_registry/features.py").read_text()
    assert "svc_engineer_customers_router" in src
    assert "from routes.svc.engineer_customers" in src


def test_server_wires_ensure_indexes():
    src = pathlib.Path("/app/backend/server.py").read_text()
    assert "ensure_engineer_customer_indexes" in src
    assert "from routes.svc.engineer_customers import ensure_indexes" in src


# ─── 3. Backend: create dedupes on email or phone ───────────────────


def test_create_customer_dedupes_on_email():
    """Posting the same email twice merges instead of creating a duplicate."""
    from routes.svc.engineer_customers import create_customer, CustomerIn

    user = {"id": "u-1", "organization_id": "org-1"}
    payload1 = CustomerIn(name="Acme Original", email="contact@acme.uk")
    payload2 = CustomerIn(name="Acme Updated",  email="contact@acme.uk", phone="+441234")

    inserted = []
    existing_row = None

    async def fake_insert(doc):
        nonlocal existing_row
        existing_row = {**doc}
        inserted.append(doc)
        return MagicMock()

    async def fake_find_one(query, projection=None):
        # mimic find by email/phone OR
        if "$or" in query and existing_row:
            for clause in query["$or"]:
                for k, v in clause.items():
                    if existing_row.get(k) == v:
                        return {**existing_row}
            return None
        if existing_row and query.get("id") == existing_row.get("id"):
            return {**existing_row}
        return None

    async def fake_update_one(query, update):
        nonlocal existing_row
        if existing_row and query.get("id") == existing_row["id"]:
            existing_row.update(update["$set"])
        return MagicMock(matched_count=1)

    fake_db = MagicMock()
    fake_db.svc_engineer_customers.insert_one = AsyncMock(side_effect=fake_insert)
    fake_db.svc_engineer_customers.find_one = AsyncMock(side_effect=fake_find_one)
    fake_db.svc_engineer_customers.update_one = AsyncMock(side_effect=fake_update_one)

    with patch("routes.svc.engineer_customers.db", fake_db):
        first = _run(create_customer(payload1, user=user))
        assert first["merged"] is False
        assert first["customer"]["name"] == "Acme Original"

        second = _run(create_customer(payload2, user=user))
        # MUST be merge, not new insert
        assert second["merged"] is True
        assert second["customer"]["name"] == "Acme Updated"
        assert second["customer"]["phone"] == "+441234"
        assert len(inserted) == 1  # never inserted twice


def test_touch_last_job_updates_matching_row():
    from routes.svc.engineer_customers import touch_last_job

    existing = {"id": "cust-1", "organization_id": "org-1",
                "email": "j@example.com", "phone": "+441000"}

    captured = {}

    async def fake_find_one(query, projection=None):
        if "$or" in query:
            return existing
        return None

    async def fake_update_one(query, update):
        captured["update"] = update
        return MagicMock(matched_count=1)

    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(side_effect=fake_find_one)
    fake_db.svc_engineer_customers.update_one = AsyncMock(side_effect=fake_update_one)

    with patch("routes.svc.engineer_customers.db", fake_db):
        _run(touch_last_job("org-1", email="J@Example.com", phone=None))

    assert "update" in captured
    assert "last_job_at" in captured["update"]["$set"]


def test_touch_last_job_safe_with_missing_data():
    from routes.svc.engineer_customers import touch_last_job
    # Should NOT raise even when org_id missing or both contact fields None.
    _run(touch_last_job("", email=None, phone=None))
    _run(touch_last_job("org", email=None, phone=None))


# ─── 4. Frontend wiring sanity ──────────────────────────────────────


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


def test_card_stats_quickaction_removed():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js"
    ).read_text())
    assert 'testid="qa-card-analytics"' not in src
    assert "Card stats" not in src


def test_support_moved_to_top_nav():
    """Iter 220m — Support row was relocated AGAIN, from EngineerHomeV2
    header into the EngineerAccountSettings drawer's Help section. The
    invariants we care about (Support reachable, routes to /support)
    are unchanged — only the home file is.
    """
    home_src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js"
    ).read_text())
    # Still removed from the QuickActions grid (the original h259 invariant)
    assert 'testid="qa-support"' not in home_src
    # Lives in the hamburger drawer now — Help section with a navigate('/support')
    settings_src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerAccountSettings.js"
    ).read_text())
    assert 'testid="engineer-settings-support-row"' in settings_src
    assert "navigate('/support')" in settings_src


def test_customers_quickaction_present():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js"
    ).read_text())
    assert 'testid="qa-customers"' in src
    assert "/svc/engineer/customers" in src


def test_customers_route_registered():
    src = pathlib.Path("/app/frontend/src/routes/AppRoutes.js").read_text()
    assert "/svc/engineer/customers" in src
    assert "ServiceOpsEngineerCustomers" in src


def test_engineer_customers_page_exists():
    p = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerCustomers.js"
    )
    assert p.exists()
    src = p.read_text()
    assert 'data-testid="customers-back"' in src
    assert 'data-testid="customers-new-btn"' in src
    assert 'data-testid="customers-search"' in src
    assert 'data-testid="customer-form-save"' in src
    assert "/api/svc/engineer/customers" in src or "/svc/engineer/customers" in src


def test_quote_builder_has_customer_picker():
    src = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerQuoteBuilder.js"
    ).read_text()
    assert "function CustomerPicker" in src
    assert 'data-testid="qb-customer-picker"' in src
    assert "/svc/engineer/customers/search" in src
    assert 'data-testid="qb-customer-save"' in src


def test_invoice_builder_has_customer_picker():
    src = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerInvoiceBuilder.js"
    ).read_text()
    assert "function CustomerPicker" in src
    assert 'data-testid="ib-customer-picker"' in src
    assert "/svc/engineer/customers/search" in src


# ─── 5. Quote/invoice creators call touch_last_job ──────────────────


def test_quote_creator_touches_last_job():
    src = pathlib.Path(
        "/app/backend/routes/svc/engineer_quotes.py"
    ).read_text()
    assert "touch_last_job" in src
    assert "from routes.svc.engineer_customers import touch_last_job" in src


def test_invoice_creator_touches_last_job():
    src = pathlib.Path(
        "/app/backend/routes/svc/engineer_invoices.py"
    ).read_text()
    assert "touch_last_job" in src
