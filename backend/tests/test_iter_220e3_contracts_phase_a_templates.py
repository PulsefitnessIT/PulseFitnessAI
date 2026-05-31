"""Iter 220e3 — CRM → Contracts: Templates + structured cover schema.

Phase A of the operator's "make CRM → Contracts feel premium" brief.

Validates:

* Canonical catalog GET returns inclusion groups / exclusion items /
  consumable presets / response-time bands matching the spec.
* Tenants can override LABELS but slugs remain immutable.
* First call to ``/contract-templates`` seeds Silver / Gold / Platinum
  / Custom for the org with sensible defaults.
* Template CRUD round-trip (create, list, update, delete).
* Applying a template to a draft contract overlays the structured
  cover fields without clobbering customer / site / dates.
* Existing ``crm_contracts._build_contract_doc`` carries the new
  fields when supplied on POST (additive, no migration needed).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _stub_db():
    fdb = MagicMock()
    # crm2_contract_templates ─ in-memory store
    templates_store: list[dict] = []

    def _t_find(query, projection=None):
        rows = [
            {k: v for k, v in t.items() if k != "_id"}
            for t in templates_store
            if all(t.get(k) == v for k, v in query.items())
        ]
        cur = MagicMock()
        cur.sort = MagicMock(return_value=cur)
        cur.to_list = AsyncMock(return_value=rows)
        return cur

    fdb.crm2_contract_templates.find = MagicMock(side_effect=_t_find)
    fdb.crm2_contract_templates.find_one = AsyncMock(
        side_effect=lambda q, p=None: next(
            ({k: v for k, v in t.items() if k != "_id"}
             for t in templates_store
             if all(t.get(k) == v for k, v in q.items())), None,
        ),
    )

    async def _t_insert(doc):
        templates_store.append(doc)
        return MagicMock(inserted_id="x")

    fdb.crm2_contract_templates.insert_one = AsyncMock(side_effect=_t_insert)

    async def _t_update(q, upd):
        for t in templates_store:
            if all(t.get(k) == v for k, v in q.items()):
                t.update(upd.get("$set", {}))
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    fdb.crm2_contract_templates.update_one = AsyncMock(side_effect=_t_update)

    async def _t_delete(q):
        for i, t in enumerate(templates_store):
            if all(t.get(k) == v for k, v in q.items()):
                templates_store.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    fdb.crm2_contract_templates.delete_one = AsyncMock(side_effect=_t_delete)

    # crm2_contract_catalog
    catalog_doc: dict = {}
    fdb.crm2_contract_catalog.find_one = AsyncMock(
        side_effect=lambda q, p=None: catalog_doc if catalog_doc and
        catalog_doc.get("organization_id") == q.get("organization_id") else None,
    )

    async def _cat_update(q, upd, upsert=False):
        catalog_doc.clear()
        catalog_doc.update(upd.get("$set", {}))
        return MagicMock()

    fdb.crm2_contract_catalog.update_one = AsyncMock(side_effect=_cat_update)

    # crm2_contracts — store for apply-template test
    contracts_store: list[dict] = []
    fdb.crm2_contracts.find_one = AsyncMock(
        side_effect=lambda q, p=None: next(
            ({k: v for k, v in c.items() if k != "_id"}
             for c in contracts_store
             if all(c.get(k) == v for k, v in q.items())), None,
        ),
    )

    async def _c_update(q, upd):
        for c in contracts_store:
            if all(c.get(k) == v for k, v in q.items()):
                c.update(upd.get("$set", {}))
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    fdb.crm2_contracts.update_one = AsyncMock(side_effect=_c_update)
    fdb.crm2_contracts.insert_one = AsyncMock(
        side_effect=lambda d: contracts_store.append(d) or MagicMock(),
    )
    return fdb, templates_store, contracts_store


USER = {"id": "u-1", "organization_id": "org-1", "full_name": "Sam Coord"}


# ── 1 · Catalog ──────────────────────────────────────────────────


def test_catalog_returns_all_four_inclusion_groups():
    from routes.crm_contract_templates import get_contract_catalog
    fdb, _, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb):
        out = _run(get_contract_catalog(user=USER))
    keys = {g["key"] for g in out["inclusion_groups"]}
    assert keys == {"technical_support", "online_support", "maintenance", "extras"}


def test_catalog_includes_treadmill_belts_and_beds():
    from routes.crm_contract_templates import get_contract_catalog
    fdb, _, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb):
        out = _run(get_contract_catalog(user=USER))
    maint = next(g for g in out["inclusion_groups"] if g["key"] == "maintenance")
    item_keys = {i["key"] for i in maint["items"]}
    # Spec mandates fitness-industry specifics.
    assert {"treadmill_belts", "treadmill_beds", "upholstery"} <= item_keys


def test_catalog_response_time_bands_match_spec():
    from routes.crm_contract_templates import get_contract_catalog
    fdb, _, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb):
        out = _run(get_contract_catalog(user=USER))
    bands = {b["key"] for b in out["response_time_bands"]}
    assert bands == {"emergency", "urgent", "standard",
                     "remote_support", "parts_quotation", "first_attendance"}


def test_catalog_label_overrides_relabel_without_renumbering():
    from routes.crm_contract_templates import get_contract_catalog, update_catalog_labels
    fdb, _, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb):
        _run(update_catalog_labels(
            {"label_overrides": {"emergency": "Crisis", "callout": "Site visit"}},
            user=USER,
        ))
        out = _run(get_contract_catalog(user=USER))
    bands = {b["key"]: b["label"] for b in out["response_time_bands"]}
    assert bands["emergency"] == "Crisis"
    # Slug unchanged so contract docs still reference the same key.
    items = {i["key"]: i["label"]
             for g in out["inclusion_groups"] for i in g["items"]}
    assert items["callout"] == "Site visit"


# ── 2 · Template seeding & CRUD ──────────────────────────────────


def test_first_list_seeds_silver_gold_platinum_custom():
    from routes.crm_contract_templates import list_contract_templates
    fdb, templates_store, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb):
        out = _run(list_contract_templates(user=USER))
    slugs = {t["tier_slug"] for t in out["templates"]}
    assert {"silver", "gold", "platinum", "custom"} <= slugs
    assert all(t.get("is_system_default") for t in out["templates"])
    # Persisted so the next call doesn't re-seed.
    assert len(templates_store) == 4


def test_platinum_template_includes_all_premium_inclusions():
    from routes.crm_contract_templates import list_contract_templates
    fdb, _, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb):
        out = _run(list_contract_templates(user=USER))
    plat = next(t for t in out["templates"] if t["tier_slug"] == "platinum")
    maint = set(plat["inclusions"]["maintenance"])
    # The Platinum tier must cover the high-value spec items.
    assert {"treadmill_beds", "treadmill_belts", "upholstery",
            "asset_condition_report", "capex_recommendation"} <= maint
    assert plat["response_times"]["emergency"]["hours"] == 2


def test_create_bespoke_template_round_trip():
    from routes.crm_contract_templates import (
        create_contract_template, list_contract_templates,
    )
    fdb, _, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb), \
         patch("routes.crm_contract_templates.record_audit", AsyncMock()):
        # Seed defaults first.
        _run(list_contract_templates(user=USER))
        new = _run(create_contract_template({
            "name": "Labour Only",
            "tier_slug": "custom",
            "blurb": "Engineers only — parts billed separately",
            "inclusions": {
                "maintenance": ["callout", "labour"],
                "technical_support": ["technical_support"],
            },
            "exclusions": ["wear_tear_parts", "consumables_excl"],
        }, user=USER))
    assert new["name"] == "Labour Only"
    assert new["tier_slug"] == "custom"
    assert new["is_system_default"] is False
    assert "labour" in new["inclusions"]["maintenance"]


def test_system_default_template_cannot_be_deleted():
    from routes.crm_contract_templates import (
        list_contract_templates, delete_contract_template,
    )
    import pytest as _pytest
    from fastapi import HTTPException
    fdb, _, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb), \
         patch("routes.crm_contract_templates.record_audit", AsyncMock()):
        out = _run(list_contract_templates(user=USER))
        silver = next(t for t in out["templates"] if t["tier_slug"] == "silver")
        with _pytest.raises(HTTPException) as exc:
            _run(delete_contract_template(silver["id"], user=USER))
        assert exc.value.status_code == 400
        assert "rename" in exc.value.detail.lower()


def test_renaming_system_default_template_keeps_slug():
    from routes.crm_contract_templates import (
        list_contract_templates, update_contract_template,
    )
    fdb, _, _ = _stub_db()
    with patch("routes.crm_contract_templates.db", fdb), \
         patch("routes.crm_contract_templates.record_audit", AsyncMock()):
        out = _run(list_contract_templates(user=USER))
        silver = next(t for t in out["templates"] if t["tier_slug"] == "silver")
        # Operator wants to rebrand Silver → "Basic" — slug must stay.
        _run(update_contract_template(
            silver["id"], {"name": "Basic", "tier_slug": "BOGUS"}, user=USER,
        ))
        refreshed = _run(list_contract_templates(user=USER))
        basic = next(t for t in refreshed["templates"] if t["id"] == silver["id"])
        assert basic["name"] == "Basic"
        assert basic["tier_slug"] == "silver"  # immutable


# ── 3 · Apply template to draft contract ─────────────────────────


def test_apply_template_overlays_cover_fields_only():
    from routes.crm_contract_templates import (
        list_contract_templates, apply_template_to_contract,
    )
    fdb, _, contracts_store = _stub_db()
    contracts_store.append({
        "id": "ctr-1", "organization_id": "org-1",
        "status": "draft", "company_id": "co-1",
        "company_name": "Pulse Fitness", "start_date": "2026-01-01",
        "end_date": "2027-01-01", "tier": "silver",
    })
    with patch("routes.crm_contract_templates.db", fdb), \
         patch("routes.crm_contract_templates.record_audit", AsyncMock()):
        templates = _run(list_contract_templates(user=USER))
        gold = next(t for t in templates["templates"] if t["tier_slug"] == "gold")
        result = _run(apply_template_to_contract(gold["id"], "ctr-1", user=USER))
    assert result["applied"] == "Gold"
    updated = next(c for c in contracts_store if c["id"] == "ctr-1")
    # Cover fields overlaid.
    assert updated["tier"] == "gold"
    assert "maintenance" in updated["inclusions"]
    assert updated["response_times"]["emergency"]["hours"] == 4
    # Customer / site / dates untouched.
    assert updated["company_name"] == "Pulse Fitness"
    assert updated["start_date"] == "2026-01-01"


def test_apply_template_refuses_on_signed_contract():
    from routes.crm_contract_templates import (
        list_contract_templates, apply_template_to_contract,
    )
    import pytest as _pytest
    from fastapi import HTTPException
    fdb, _, contracts_store = _stub_db()
    contracts_store.append({
        "id": "ctr-signed", "organization_id": "org-1",
        "status": "active", "company_name": "Acme",
    })
    with patch("routes.crm_contract_templates.db", fdb), \
         patch("routes.crm_contract_templates.record_audit", AsyncMock()):
        templates = _run(list_contract_templates(user=USER))
        gold = next(t for t in templates["templates"] if t["tier_slug"] == "gold")
        with _pytest.raises(HTTPException) as exc:
            _run(apply_template_to_contract(gold["id"], "ctr-signed", user=USER))
    assert exc.value.status_code == 400


# ── 4 · Contract doc carries new fields ─────────────────────────


def test_build_contract_doc_accepts_structured_cover_fields():
    from routes.crm_contracts import _build_contract_doc
    payload = {
        "title": "Pulse Annual Cover", "tier": "gold",
        "company_id": "co-1", "company_name": "Pulse",
        "billing_contact_id": "ct-bill", "assigned_engineer_id": "eng-9",
        "renewal_date": "2027-10-01",
        "contract_length_months": 12,
        "inclusions": {"maintenance": ["callout", "labour"]},
        "exclusions_structured": ["misuse", "vandalism"],
        "consumables": [{"name": "Belt lubricant", "included": True, "charge": 0}],
        "response_times": {"emergency": {"hours": 4, "unit": "hours"}},
        "pricing": {"annual_value": 12000, "vat_percent": 20, "margin_percent": 35},
        "terms_md": "## Cover terms\n…",
        "template_id": "tpl-1",
    }
    doc = _build_contract_doc(payload, USER)
    assert doc["billing_contact_id"] == "ct-bill"
    assert doc["assigned_engineer_id"] == "eng-9"
    assert doc["renewal_date"] == "2027-10-01"
    assert doc["contract_length_months"] == 12
    assert doc["inclusions"]["maintenance"] == ["callout", "labour"]
    assert doc["exclusions_structured"] == ["misuse", "vandalism"]
    assert doc["consumables"][0]["name"] == "Belt lubricant"
    assert doc["response_times"]["emergency"]["hours"] == 4
    assert doc["pricing"]["margin_percent"] == 35
    assert doc["template_id"] == "tpl-1"
    assert "Cover terms" in doc["terms_md"]
    # Existing legacy fields remain.
    assert doc["status"] == "draft"
    assert doc["contract_number"].startswith("CTR-")
