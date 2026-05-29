"""Iter 220bs — CRM evolution: strict picklists + Tender deep-linking.

Pins the four polish items added in Iter 220bs:

  1. `validate_picklist_value` is case-insensitive, returns canonical
     label, raises HTTPException(400) on mismatch in strict mode,
     and passes through empty values.
  2. `validate_picklist_fields` normalises payloads in-place using a
     `{payload_field: picklist_key}` map.
  3. New `tender_status` and `tender_outcome_reason` picklist keys
     exist with sensible defaults seeded.
  4. `tender_id` foreign key on quotes — create + update both enforce
     same-org ownership and reject cross-tenant links.
  5. `get_tender` hydrates linked quotes inline.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.skip = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


# ══════════════ 1 · validate_picklist_value semantics ═══════════════


def test_validate_picklist_passes_through_empty_values():
    from routes import crm_picklists as m
    async def go():
        assert await m.validate_picklist_value("job_title", None, "org-1") is None
        assert await m.validate_picklist_value("job_title", "", "org-1") is None
        assert await m.validate_picklist_value("job_title", "   ", "org-1") is None
    _run(go())


def test_validate_picklist_returns_canonical_label_case_insensitive():
    from routes import crm_picklists as m
    fake_rows = [
        {"label": "CEO"}, {"label": "Operations Director"},
        {"label": "Sales Manager"},
    ]
    fdb = MagicMock()
    fdb.crm_picklists.find = MagicMock(return_value=_cursor(fake_rows))
    async def go():
        with patch.object(m, "db", fdb):
            out = await m.validate_picklist_value(
                "job_title", "operations director", "org-1",
            )
            assert out == "Operations Director"  # canonical casing
            out2 = await m.validate_picklist_value(
                "job_title", "  ceo  ", "org-1",
            )
            assert out2 == "CEO"  # trimmed + matched
    _run(go())


def test_validate_picklist_strict_rejects_unknown_value_with_helpful_400():
    from routes import crm_picklists as m
    fdb = MagicMock()
    fdb.crm_picklists.find = MagicMock(return_value=_cursor([{"label": "CEO"}]))
    async def go():
        with patch.object(m, "db", fdb):
            with pytest.raises(HTTPException) as exc:
                await m.validate_picklist_value(
                    "job_title", "Supreme Overlord", "org-1",
                )
            assert exc.value.status_code == 400
            detail = exc.value.detail
            assert isinstance(detail, dict)
            assert detail["error"] == "invalid_picklist_value"
            assert detail["key"] == "job_title"
            assert detail["received"] == "Supreme Overlord"
            assert "CEO" in detail["valid_examples"]
            # The hint guides the operator to the picklist endpoint.
            assert "/api/crm/picklists/" in detail["hint"]
    _run(go())


def test_validate_picklist_non_strict_returns_none_on_miss():
    """For legacy importers that need to migrate gradually."""
    from routes import crm_picklists as m
    fdb = MagicMock()
    fdb.crm_picklists.find = MagicMock(return_value=_cursor([{"label": "CEO"}]))
    async def go():
        with patch.object(m, "db", fdb):
            out = await m.validate_picklist_value(
                "job_title", "Bogus Title", "org-1", strict=False,
            )
            assert out is None
    _run(go())


def test_validate_picklist_unknown_key_strict_raises():
    """An unsupported key with strict=True still raises — typos in the
    integration code should fail loudly."""
    from routes import crm_picklists as m
    fdb = MagicMock()
    fdb.crm_picklists.find = MagicMock(return_value=_cursor([]))
    async def go():
        with patch.object(m, "db", fdb):
            with pytest.raises(HTTPException) as exc:
                await m.validate_picklist_value(
                    "nonexistent_picklist_key", "anything", "org-1",
                )
            assert exc.value.status_code == 400
    _run(go())


# ══════════════ 2 · validate_picklist_fields normalises in-place ═══


def test_validate_picklist_fields_normalises_payload_in_place():
    from routes import crm_picklists as m
    fdb = MagicMock()
    # 2 keys → 2 separate `find()` results. We use a side_effect that
    # returns each cursor in turn based on the query.
    def _find(q, _proj):
        if q.get("key") == "lead_source":
            return _cursor([{"label": "LinkedIn"}, {"label": "Tender"}])
        if q.get("key") == "opportunity_type":
            return _cursor([{"label": "New Business"}])
        return _cursor([])
    fdb.crm_picklists.find = MagicMock(side_effect=_find)
    payload = {
        "title": "Big bid",
        "lead_source": "tender",          # lower-cased → normalise to "Tender"
        "opportunity_type": "new business",
        "value": 100000,
    }
    async def go():
        with patch.object(m, "db", fdb):
            await m.validate_picklist_fields(payload, {
                "lead_source": "lead_source",
                "opportunity_type": "opportunity_type",
            }, "org-1")
    _run(go())
    assert payload["lead_source"] == "Tender"
    assert payload["opportunity_type"] == "New Business"
    # Untouched fields stay as-is.
    assert payload["title"] == "Big bid"
    assert payload["value"] == 100000


def test_validate_picklist_fields_ignores_missing_keys():
    from routes import crm_picklists as m
    fdb = MagicMock()
    fdb.crm_picklists.find = MagicMock(return_value=_cursor([{"label": "CEO"}]))
    payload = {"title": "X"}  # no picklist fields set
    async def go():
        with patch.object(m, "db", fdb):
            await m.validate_picklist_fields(payload, {
                "job_title": "job_title",
            }, "org-1")
    _run(go())
    assert payload == {"title": "X"}


# ══════════════ 3 · new tender_status / tender_outcome_reason keys ══


def test_tender_picklist_keys_registered():
    from routes import crm_picklists as m
    assert "tender_status" in m.PICKLIST_KEYS
    assert "tender_outcome_reason" in m.PICKLIST_KEYS
    # Tender lifecycle defaults make sense for a real bid team.
    statuses = m.PICKLIST_KEYS["tender_status"]["defaults"]
    for label in ("Draft", "Submitted", "Awarded", "Lost"):
        assert label in statuses
    reasons = m.PICKLIST_KEYS["tender_outcome_reason"]["defaults"]
    assert any("price" in r.lower() for r in reasons)
    assert any("technical" in r.lower() for r in reasons)


# ══════════════ 4 · Quote ↔ Tender deep-link cross-tenant guard ═════


def test_quote_create_rejects_tender_from_another_org():
    from routes import crm_cpq as m
    fdb = MagicMock()
    # find_one for the OTHER org's tender returns None (org-scoped).
    fdb.crm2_tenders.find_one = AsyncMock(return_value=None)
    user = {"id": "u-1", "organization_id": "org-A"}

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_min_margin_threshold", AsyncMock(return_value=0)), \
             patch.object(m, "_hydrate_line_items", AsyncMock(return_value=[])), \
             patch.object(m, "log_audit", AsyncMock()):
            with pytest.raises(HTTPException) as exc:
                await m.create_quote(
                    data={"title": "X", "tender_id": "tender-from-org-B"},
                    user=user,
                )
            assert exc.value.status_code == 400
            assert "tender" in exc.value.detail.lower()
    _run(go())


def test_quote_create_accepts_tender_from_same_org():
    from routes import crm_cpq as m
    fdb = MagicMock()
    fdb.crm2_tenders.find_one = AsyncMock(return_value={"id": "tender-1", "title": "T"})
    fdb.crm_quotes.insert_one = AsyncMock()
    user = {"id": "u-1", "organization_id": "org-A"}

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_min_margin_threshold", AsyncMock(return_value=0)), \
             patch.object(m, "_hydrate_line_items", AsyncMock(return_value=[])), \
             patch.object(m, "log_audit", AsyncMock()):
            return await m.create_quote(
                data={"title": "Pricing for ITT", "tender_id": "tender-1"},
                user=user,
            )
    out = _run(go())
    assert out["tender_id"] == "tender-1"


def test_quote_update_rejects_repointing_to_another_orgs_tender():
    from routes import crm_cpq as m
    fdb = MagicMock()
    fdb.crm_quotes.find_one = AsyncMock(return_value={
        "id": "q-1", "organization_id": "org-A", "approval_status": "not_required",
    })
    fdb.crm2_tenders.find_one = AsyncMock(return_value=None)  # other-org tender
    user = {"id": "u-1", "organization_id": "org-A"}

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_min_margin_threshold", AsyncMock(return_value=0)), \
             patch.object(m, "log_audit", AsyncMock()):
            with pytest.raises(HTTPException) as exc:
                await m.update_quote(
                    quote_id="q-1",
                    data={"tender_id": "tender-from-org-B"},
                    user=user,
                )
            assert exc.value.status_code == 400
    _run(go())


def test_quote_update_allows_unlinking_tender():
    """Passing tender_id=None is allowed (unlink path)."""
    from routes import crm_cpq as m
    fdb = MagicMock()
    fdb.crm_quotes.find_one = AsyncMock(return_value={
        "id": "q-1", "organization_id": "org-A", "approval_status": "not_required",
    })
    fdb.crm_quotes.update_one = AsyncMock()
    user = {"id": "u-1", "organization_id": "org-A"}

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_min_margin_threshold", AsyncMock(return_value=0)), \
             patch.object(m, "log_audit", AsyncMock()):
            await m.update_quote(
                quote_id="q-1", data={"tender_id": None}, user=user,
            )
    _run(go())
    set_doc = fdb.crm_quotes.update_one.call_args.args[1]["$set"]
    assert set_doc["tender_id"] is None


# ══════════════ 5 · get_tender hydrates linked quotes ═══════════════


def test_get_tender_hydrates_linked_quotes():
    from routes import crm_v2 as m
    fdb = MagicMock()
    tender_doc = {
        "id": "t-1", "organization_id": "org-A", "title": "Big bid",
        "company_id": None, "opportunity_id": None,
    }
    fdb.crm2_tenders.find_one = AsyncMock(return_value=tender_doc)
    fdb.crm2_tender_questions.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_tender_docs.find = MagicMock(return_value=_cursor([]))
    quotes = [
        {"id": "q-1", "quote_number": "QT-001", "title": "Commercial reply",
         "status": "draft", "total": 50000, "currency": "GBP",
         "version": 1, "is_latest_version": True, "created_at": "2026-02-29T00:00:00Z"},
        {"id": "q-2", "quote_number": "QT-002", "title": "V2 — discount",
         "status": "sent", "total": 45000, "currency": "GBP",
         "version": 2, "is_latest_version": True, "created_at": "2026-02-29T01:00:00Z"},
    ]
    fdb.crm_quotes.find = MagicMock(return_value=_cursor(quotes))

    user = {"id": "u-1", "organization_id": "org-A"}

    async def go():
        with patch.object(m, "db", fdb):
            return await m.get_tender(tender_id="t-1", user=user)
    out = _run(go())
    assert "quotes" in out
    assert len(out["quotes"]) == 2
    assert out["quotes"][0]["quote_number"] == "QT-001"
    assert out["quotes"][1]["status"] == "sent"
    # find() was called with tender_id + org_id (cross-tenant safe).
    find_call = fdb.crm_quotes.find.call_args
    q = find_call.args[0]
    assert q["tender_id"] == "t-1"
    assert q["organization_id"] == "org-A"


# ══════════════ 6 · enforcement at CRUD boundaries ══════════════════


def test_create_opportunity_rejects_unknown_lead_source():
    """Smoke test that the enforcement is wired at the CRUD boundary."""
    from routes import crm_v2 as m
    # The picklist lookup returns no matching value.
    async def fake_validate(payload, _fields, _org_id, **_kw):
        raise HTTPException(400, "picklist failure")
    user = {"id": "u-1", "organization_id": "org-A"}

    async def go():
        with patch.object(m, "validate_picklist_fields", side_effect=fake_validate):
            with pytest.raises(HTTPException) as exc:
                await m.create_opportunity(
                    data={"title": "X", "lead_source": "wat"}, user=user,
                )
            assert exc.value.status_code == 400
    _run(go())


def test_create_contact_wires_picklist_enforcement():
    """Static assert — the create_contact source must call
    validate_picklist_fields before persisting."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "routes" / "crm_v2.py").read_text()
    # Find the create_contact function block.
    idx = src.find("async def create_contact(")
    assert idx > 0
    end = src.find("\nasync def ", idx + 1)
    block = src[idx:end] if end > 0 else src[idx:]
    assert "validate_picklist_fields" in block
    assert "job_title" in block and "department" in block


def test_create_tender_wires_picklist_enforcement():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "routes" / "crm_v2.py").read_text()
    idx = src.find("async def create_tender(")
    end = src.find("\nasync def ", idx + 1)
    block = src[idx:end]
    assert "validate_picklist_fields" in block
    assert "tender_status" in block
    assert "tender_outcome_reason" in block
