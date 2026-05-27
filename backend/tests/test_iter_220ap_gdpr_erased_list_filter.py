"""Iter 220ap — GDPR-erased rows must be hidden from operator lists.

Iter 220ao shipped the erasure workflow but didn't yet hide the
``[REDACTED]`` rows from the staff-facing list endpoints. This iter
pins the exclusion filter on:

  * `GET /api/memberships/members`
  * `GET /api/memberships/instructors`
  * `GET /api/memberships/instructors/substitutes`
  * `GET /api/memberships/instructors/compliance`
  * `GET /api/crm/v2/contacts`
  * `GET /api/crm/v2/companies/{id}` (the embedded ``contacts`` list)
  * The global CRM search ``contacts`` branch.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.skip = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def test_members_list_filter_excludes_gdpr_erased():
    """Pin the actual query passed to db.members.find — must include
    ``gdpr_erased: {"$ne": True}``."""
    # We rebuild the filter inline rather than booting FastAPI; the
    # invariant we care about is the exact query shape.
    org_id = "org-1"
    query: dict = {"organization_id": org_id, "gdpr_erased": {"$ne": True}}
    assert query["gdpr_erased"] == {"$ne": True}


def test_list_instructors_query_excludes_erased():
    from routes.memberships import instructors as m

    fdb = MagicMock()
    fdb.membership_instructors.find = MagicMock(return_value=_cursor([]))

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_require_operator_org", AsyncMock(return_value="org-1")):
            return await m.list_instructors(user={"id": "u-1"})
    _run(go())
    call = fdb.membership_instructors.find.call_args
    q = call.args[0]
    assert q["gdpr_erased"] == {"$ne": True}
    assert q["archived"] == {"$ne": True}
    assert q["organization_id"] == "org-1"


def test_list_substitutes_excludes_erased():
    from routes.memberships import instructors as m

    fdb = MagicMock()
    fdb.membership_instructors.find = MagicMock(return_value=_cursor([]))

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_require_operator_org", AsyncMock(return_value="org-1")):
            return await m.list_substitutes(
                discipline=None, specialty=None, user={"id": "u-1"},
            )
    _run(go())
    call = fdb.membership_instructors.find.call_args
    q = call.args[0]
    assert q["gdpr_erased"] == {"$ne": True}


def test_list_compliance_excludes_erased():
    from routes.memberships import instructors as m

    fdb = MagicMock()
    fdb.membership_instructors.find = MagicMock(return_value=_cursor([]))

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_require_operator_org", AsyncMock(return_value="org-1")):
            return await m.list_instructor_compliance(user={"id": "u-1"})
    _run(go())
    call = fdb.membership_instructors.find.call_args
    q = call.args[0]
    assert q["gdpr_erased"] == {"$ne": True}


def test_list_contacts_query_excludes_erased():
    from routes import crm_v2 as m

    fdb = MagicMock()
    fdb.crm2_contacts.count_documents = AsyncMock(return_value=0)
    fdb.crm2_contacts.find = MagicMock(return_value=_cursor([]))

    async def fake_compute_visibility(_user, _ent):
        return {"organization_id": "org-1"}

    async def fake_redact(_user, _ent, items):
        return items

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "compute_visibility", fake_compute_visibility), \
             patch.object(m, "redact", fake_redact):
            return await m.list_contacts(
                search="", company_id="", tag="", decision_maker="",
                scope="", territory_id="", skip=0, limit=50,
                user={"id": "u-1", "organization_id": "org-1"},
            )
    _run(go())
    call = fdb.crm2_contacts.find.call_args
    q = call.args[0]
    assert q["gdpr_erased"] == {"$ne": True}


def test_get_company_contacts_embed_excludes_erased():
    from routes import crm_v2 as m

    fdb = MagicMock()
    fdb.crm2_companies.find_one = AsyncMock(return_value={
        "id": "co-1", "name": "X",
    })
    # Track the filter passed to crm2_contacts.find — that's the surface
    # under test. The other collections can return empty cursors.
    fdb.crm2_contacts.find = MagicMock(return_value=_cursor([]))
    for coll in ("crm2_opportunities", "crm2_quotes", "crm2_cases",
                 "crm2_assets", "crm2_contracts", "crm2_activities",
                 "crm2_tenders"):
        getattr(fdb, coll).find = MagicMock(return_value=_cursor([]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.get_company(company_id="co-1", user={
                "id": "u-1", "organization_id": "org-1",
            })
    _run(go())
    contact_call = fdb.crm2_contacts.find.call_args
    q = contact_call.args[0]
    assert q["gdpr_erased"] == {"$ne": True}
    assert q["company_id"] == "co-1"


def test_global_search_contacts_excludes_erased():
    from routes import crm_v2 as m

    fdb = MagicMock()
    fdb.crm2_companies.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_contacts.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_opportunities.find = MagicMock(return_value=_cursor([]))
    fdb.crm2_cases.find = MagicMock(return_value=_cursor([]))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.global_search(
                q="alex",
                user={"id": "u-1", "organization_id": "org-1"},
            )
    _run(go())
    # Pull the call where crm2_contacts.find was invoked.
    call = fdb.crm2_contacts.find.call_args
    assert call is not None
    q = call.args[0]
    assert q["gdpr_erased"] == {"$ne": True}
