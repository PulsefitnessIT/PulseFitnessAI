"""Iter 216h240 — Integration field capture across all import surfaces.

Validates that the import surface and manual-add surfaces persist
every field required for the Sicon / Sage / Orbit 4 round-trip
documented in INTEGRATION_FIELD_MAPPING.md §19, §22, §23, §29, §31, §32.

Scope of this test:

1. ``EquipmentCreate`` Pydantic model accepts the new round-trip
   fields (`qr_code`, `manufacturing_date`, `deprecation_date`,
   `orbit4_asset_id`, `orbit4_product_id`, `sicon_equipment_id`).
2. ``routes/equipment.py`` PATCH allowed_fields includes the new
   set so operators can backfill them later.
3. ``routes/equipment.py`` CSV template + parser carry the new
   columns through to the inserted document.
4. ``routes/sites_import.py`` CSV template carries
   ``opening_hours``, ``access_notes``, ``default_engineer_email``.
5. ``routes/sites.py`` create_site persists the new Sicon-routing
   fields.
6. ``routes/crm_core.py`` ``create_company`` POST persists the Sage
   / Sicon refs and the new ``/companies/csv-template`` +
   ``/companies/import-csv`` endpoints are registered.
7. ``routes/crm_contracts.py`` default contract doc carries an
   ``orbit4_contract_id`` slot.
"""
from __future__ import annotations

import inspect


def test_equipment_create_accepts_integration_fields():
    from models.schemas import EquipmentCreate
    fields = set(EquipmentCreate.model_fields.keys())
    required = {
        "qr_code", "manufacturing_date", "deprecation_date",
        "orbit4_asset_id", "orbit4_product_id", "sicon_equipment_id",
    }
    missing = required - fields
    assert not missing, f"EquipmentCreate missing fields: {missing}"


def test_equipment_patch_allowed_fields_include_integration_refs():
    from routes import equipment as eq_mod
    src = inspect.getsource(eq_mod.update_equipment)
    for key in (
        "qr_code", "manufacturing_date", "deprecation_date",
        "orbit4_asset_id", "orbit4_product_id", "sicon_equipment_id",
    ):
        assert f'"{key}"' in src, f"PATCH allowed_fields missing {key}"


def test_equipment_csv_parser_emits_integration_fields():
    """A CSV row with the new headers must produce a doc carrying them."""
    from routes.equipment import _parse_csv_row, _CSV_FIELDS_SNAKE
    row = {
        "name": "Treadmill 1", "equipment_type": "Treadmill",
        "manufacturer": "Life Fitness", "model": "T5", "serial_number": "SN1",
        "qr_code": "GA-TM-001", "manufacturing_date": "2023-11-01",
        "deprecation_date": "2034-01-15", "orbit4_asset_id": "12345",
        "sicon_equipment_id": "SICON-EQ-001",
    }
    user = {"id": "u1", "organization_id": "o1"}
    doc = _parse_csv_row(row, _CSV_FIELDS_SNAKE, user)
    assert doc["qr_code"] == "GA-TM-001"
    assert doc["manufacturing_date"] == "2023-11-01"
    assert doc["deprecation_date"] == "2034-01-15"
    assert doc["orbit4_asset_id"] == "12345"
    assert doc["sicon_equipment_id"] == "SICON-EQ-001"


def test_sites_csv_template_carries_sicon_routing_headers():
    from routes.sites_import import _SITE_CSV_HEADERS
    for col in ("opening_hours", "access_notes", "default_engineer_email"):
        assert col in _SITE_CSV_HEADERS, f"sites CSV missing {col}"


def test_sites_create_persists_routing_fields():
    """create_site must shape the doc with the three new routing fields."""
    from routes import sites as sites_mod
    src = inspect.getsource(sites_mod.create_site)
    for key in ("opening_hours", "access_notes", "default_engineer_email"):
        assert f'"{key}"' in src, f"create_site missing persistence for {key}"


def test_sites_patch_accepts_routing_fields():
    from routes import sites as sites_mod
    src = inspect.getsource(sites_mod.update_site)
    for key in ("opening_hours", "access_notes", "default_engineer_email"):
        assert f'"{key}"' in src, f"update_site missing field {key}"


def test_crm_create_company_accepts_sage_sicon_refs():
    from routes import crm_core
    src = inspect.getsource(crm_core.create_company)
    for key in (
        "sage_customer_account_id", "sage_customer_reference",
        "sicon_company_id", "sicon_company_reference",
        "vat_registration", "currency", "nominal_default",
        "payment_terms_days", "credit_limit", "account_status",
    ):
        assert f'"{key}"' in src, f"create_company missing {key}"


def test_crm_companies_csv_template_and_import_routes_registered():
    from routes.crm_core import router
    paths = {r.path for r in router.routes}
    # Iter 216h240 — paths use the ``-`` separator (not ``/``) to avoid
    # FastAPI route-precedence collision with ``/companies/{company_id}``.
    assert "/crm/companies-csv-template" in paths
    assert "/crm/companies-import-csv" in paths


def test_crm_company_csv_parser_round_trips_natural_keys():
    from routes.crm_core import _parse_company_csv_row
    row = {
        "name": "Acme Fitness Ltd", "industry": "Health & Fitness",
        "sage_customer_account_id": "ACME001",
        "sage_customer_reference": "ACME-LDN",
        "sicon_company_id": "sicon-acme-1234",
        "sicon_company_reference": "SiconAcme",
        "vat_registration": "GB123456789", "currency": "GBP",
        "nominal_default": "4000", "payment_terms_days": "30",
        "credit_limit": "50000", "account_status": "active",
    }
    doc = _parse_company_csv_row(row, "u1", "o1")
    assert doc is not None
    assert doc["sage_customer_account_id"] == "ACME001"
    assert doc["sage_customer_reference"] == "ACME-LDN"
    assert doc["sicon_company_id"] == "sicon-acme-1234"
    assert doc["payment_terms_days"] == 30.0  # parsed to numeric
    assert doc["credit_limit"] == 50000.0
    assert doc["currency"] == "GBP"
    assert doc["account_status"] == "active"


def test_crm_contact_csv_parser_captures_sage_refs():
    from routes.crm_core import _parse_csv_row
    row = {
        "first_name": "Jane", "last_name": "Doe", "email": "jane@example.com",
        "sage_ref": "JANE001", "sage_id": "uuid-jane",
        "sage_customer_account_id": "ACME001",
    }
    doc = _parse_csv_row(row, "u1")
    assert doc is not None
    assert doc["sage_ref"] == "JANE001"
    assert doc["sage_id"] == "uuid-jane"
    assert doc["sage_customer_account_id"] == "ACME001"


def test_crm_contract_default_doc_carries_orbit4_id():
    from routes import crm_contracts
    src = inspect.getsource(crm_contracts._build_contract_doc)
    assert '"orbit4_contract_id"' in src, "contract default doc missing orbit4_contract_id"


def test_equipment_csv_template_string_includes_new_columns():
    """The downloadable CSV header MUST advertise the new round-trip columns."""
    from routes import equipment as eq_mod
    src = inspect.getsource(eq_mod.get_csv_template)
    for col in (
        "qr_code", "manufacturing_date", "deprecation_date",
        "orbit4_asset_id", "sicon_equipment_id",
    ):
        assert col in src, f"CSV template missing {col}"
