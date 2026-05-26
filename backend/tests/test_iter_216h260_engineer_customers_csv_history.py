"""Iter 216h260 — Engineer Lite CRM history + CSV import/template.

User follow-up (Feb 21, 2026):
"Continue potential enhancement — Also allow engineers to import
customers via .csv file. They need to download template, single
and bulk import."

Backend additions:
  • GET  /api/svc/engineer/customers/template.csv  — downloadable template
  • POST /api/svc/engineer/customers/import-csv    — bulk import (idempotent)
  • GET  /api/svc/engineer/customers/{id}          — now also returns
        `recent_quotes` + `recent_invoices` (max 5 each), matched on
        the customer's email/phone within the same org.

Frontend:
  • Customers page gets Download Template + Import CSV buttons.
  • Expanded customer row fetches the detail endpoint and renders
    the recent quotes/invoices inline with clickable links.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Backend: surface ───────────────────────────────────────────────


def test_router_exposes_template_and_import_paths():
    from routes.svc.engineer_customers import router
    paths = {r.path for r in router.routes}
    assert "/svc/engineer/customers/template.csv" in paths
    assert "/svc/engineer/customers/import-csv" in paths


# ─── Backend: template content ──────────────────────────────────────


def test_template_csv_returns_canonical_header():
    from routes.svc.engineer_customers import template_csv

    resp = _run(template_csv(_user={"id": "u-1", "organization_id": "org-1"}))
    assert resp.media_type.startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "").lower()
    body = resp.body.decode("utf-8")
    first = body.splitlines()[0]
    for col in ("name", "email", "phone", "site_name", "site_address", "notes", "equipment_list"):
        assert col in first, f"missing column {col} in template header"
    # second line is the example row
    assert len(body.splitlines()) >= 2


# ─── Backend: history endpoint shape ────────────────────────────────


def test_get_customer_now_includes_history_keys():
    from routes.svc.engineer_customers import get_customer

    customer_doc = {
        "id": "c-1", "organization_id": "org-1",
        "name": "Acme", "email": "x@acme.uk", "phone": "+44",
    }

    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(return_value=customer_doc)

    # Cursor-style helpers returning empty
    def empty_cursor():
        cur = MagicMock()
        cur.sort = MagicMock(return_value=cur)
        cur.limit = MagicMock(return_value=cur)
        cur.to_list = AsyncMock(return_value=[])
        return cur

    fake_db.svc_engineer_quotes.find = MagicMock(return_value=empty_cursor())
    fake_db.svc_engineer_invoices.find = MagicMock(return_value=empty_cursor())

    with patch("routes.svc.engineer_customers.db", fake_db):
        result = _run(get_customer("c-1", user={"id": "u-1", "organization_id": "org-1"}))

    assert "recent_quotes" in result and result["recent_quotes"] == []
    assert "recent_invoices" in result and result["recent_invoices"] == []


def test_get_customer_returns_matching_quotes_and_invoices():
    from routes.svc.engineer_customers import get_customer

    quotes = [{"id": "q-1", "quote_number": "Q-001", "status": "sent", "total": 500.0,
               "created_at": "2026-02-21T00:00:00+00:00"}]
    invoices = [{"id": "i-1", "invoice_number": "INV-001", "status": "paid", "total": 600.0,
                 "created_at": "2026-02-21T00:00:00+00:00"}]

    def cursor_with(data):
        cur = MagicMock()
        cur.sort = MagicMock(return_value=cur)
        cur.limit = MagicMock(return_value=cur)
        cur.to_list = AsyncMock(return_value=data)
        return cur

    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(return_value={
        "id": "c-1", "organization_id": "org-1", "name": "Acme",
        "email": "x@acme.uk", "phone": None,
    })
    fake_db.svc_engineer_quotes.find = MagicMock(return_value=cursor_with(quotes))
    fake_db.svc_engineer_invoices.find = MagicMock(return_value=cursor_with(invoices))

    with patch("routes.svc.engineer_customers.db", fake_db):
        result = _run(get_customer("c-1", user={"id": "u-1", "organization_id": "org-1"}))

    assert result["recent_quotes"] == quotes
    assert result["recent_invoices"] == invoices


def test_get_customer_handles_history_failures_gracefully():
    """If the quote/invoice query blows up the customer payload still returns."""
    from routes.svc.engineer_customers import get_customer

    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(return_value={
        "id": "c-1", "organization_id": "org-1", "name": "Acme",
        "email": "x@acme.uk", "phone": None,
    })

    def boom_cursor():
        cur = MagicMock()
        cur.sort = MagicMock(side_effect=RuntimeError("kaboom"))
        return cur

    fake_db.svc_engineer_quotes.find = MagicMock(return_value=boom_cursor())
    fake_db.svc_engineer_invoices.find = MagicMock(return_value=boom_cursor())

    with patch("routes.svc.engineer_customers.db", fake_db):
        result = _run(get_customer("c-1", user={"id": "u-1", "organization_id": "org-1"}))

    assert result["recent_quotes"] == []
    assert result["recent_invoices"] == []


def test_recent_quotes_short_circuits_without_contact():
    from routes.svc.engineer_customers import _recent_quotes
    out = _run(_recent_quotes("org-1", email=None, phone=None))
    assert out == []


# ─── Backend: CSV import ────────────────────────────────────────────


def _fake_upload(content: bytes, filename="customers.csv"):
    upload = MagicMock()
    upload.filename = filename
    upload.read = AsyncMock(return_value=content)
    return upload


def test_import_csv_creates_and_merges_idempotently():
    from routes.svc.engineer_customers import import_csv

    csv_bytes = (
        b"name,email,phone,site_name,equipment_list\n"
        b"Acme One,one@example.com,+447001,HQ One,Treadmill | Bike\n"
        b"Acme Two,two@example.com,+447002,HQ Two,Rower\n"
        b"Acme One Dup,one@example.com,+447099,HQ One,Treadmill\n"
        b"  ,no-name@example.com,,,\n"
    )
    upload = _fake_upload(csv_bytes)

    existing: dict[str, dict] = {}

    async def fake_find_one(query, projection=None):
        if "$or" in query:
            for clause in query["$or"]:
                for row in existing.values():
                    for k, v in clause.items():
                        if row.get(k) == v:
                            return row
        return None

    async def fake_insert(doc):
        existing[doc["id"]] = {**doc}
        return MagicMock()

    async def fake_update(query, update):
        if "id" in query:
            for row in existing.values():
                if row["id"] == query["id"]:
                    row.update(update["$set"])
        return MagicMock(matched_count=1)

    fake_db = MagicMock()
    fake_db.svc_engineer_customers.find_one = AsyncMock(side_effect=fake_find_one)
    fake_db.svc_engineer_customers.insert_one = AsyncMock(side_effect=fake_insert)
    fake_db.svc_engineer_customers.update_one = AsyncMock(side_effect=fake_update)

    with patch("routes.svc.engineer_customers.db", fake_db):
        result = _run(import_csv(file=upload, user={"id": "u-1", "organization_id": "org-1"}))

    assert result["imported"] == 2
    assert result["merged"] == 1
    assert len(result["skipped"]) == 1
    # equipment list split on '|'
    inserted_rows = list(existing.values())
    assert any("Treadmill" in (r.get("equipment_list") or []) for r in inserted_rows)


def test_import_csv_rejects_missing_name_column():
    from routes.svc.engineer_customers import import_csv
    from fastapi import HTTPException

    upload = _fake_upload(b"email,phone\nfoo@bar,1234\n")

    fake_db = MagicMock()
    with patch("routes.svc.engineer_customers.db", fake_db):
        try:
            _run(import_csv(file=upload, user={"id": "u-1", "organization_id": "org-1"}))
        except HTTPException as e:
            assert e.status_code == 400
            assert "name" in e.detail.lower()
        else:
            raise AssertionError("expected HTTPException for missing name column")


def test_import_csv_rejects_empty_file():
    from routes.svc.engineer_customers import import_csv
    from fastapi import HTTPException
    upload = _fake_upload(b"")
    try:
        _run(import_csv(file=upload, user={"id": "u-1", "organization_id": "org-1"}))
    except HTTPException as e:
        assert e.status_code == 400
    else:
        raise AssertionError("expected HTTPException for empty CSV")


# ─── Frontend wiring sanity ─────────────────────────────────────────


def _strip_js(src: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    s = re.sub(r"//.*", "", s)
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.DOTALL)
    return s


def test_customers_page_has_csv_buttons():
    """Iter 220m — the CSV import / template-download flow moved from the
    EngineerCustomers page into the EngineerAccountSettings hamburger
    drawer (cleaner home screen, consolidated settings UX). Assert on
    the drawer + assert the API contracts the buttons hit are still
    the same. Both backend routes haven't moved."""
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerAccountSettings.js"
    ).read_text())
    assert 'testid="engineer-settings-template-row"' in src
    assert 'testid="engineer-settings-import-row"' in src
    assert "/svc/engineer/customers/template.csv" in src
    assert "/svc/engineer/customers/import-csv" in src


def test_customers_page_renders_history_inline():
    src = _strip_js(pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerCustomers.js"
    ).read_text())
    assert "recent_quotes" in src
    assert "recent_invoices" in src
    assert "customer-history" in src
    assert "customer-quote-" in src
    assert "customer-invoice-" in src
