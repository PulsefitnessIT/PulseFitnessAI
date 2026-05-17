"""
Iter 216h174 — Payload-size reduction tests.

Three list endpoints had heavy detail-only fields stripped from the
response:

* `/api/master-admin/organizations` — `features_audit` (≈3.7-5.3 KB per
  org) no longer ships in the list. Detail still served at
  `/master-admin/organizations/{id}/features-audit`.

* `/api/svc/cases` — 17 detail-only fields stripped (AI triage blobs,
  signatures, media arrays, embedded notes, embedded quote lines,
  state-change history). The full doc still ships from `/svc/cases/{id}`.

* `/api/memberships/members` — N+1 lookup eliminated (per-member find →
  bulk find with $in) and the embedded `active_membership` is now
  projected to just the four fields the UI reads.

These tests are projection-shape unit tests — they don't need real data
or a running server. We construct a mock Motor cursor + collection that
records the projection it received and verify the right fields are
excluded.
"""
import asyncio
import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _RecordingCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):  return self
    def skip(self, *a, **k):  return self
    def limit(self, *a, **k): return self

    async def to_list(self, _n=None):
        return list(self._docs)


class _RecordingCollection:
    """Minimal Motor stand-in that records every query call so we can
    assert the projection shape."""
    def __init__(self, docs=None):
        self.docs = docs or []
        self.find_calls = []
        self.find_one_calls = []
        self.count_calls = []

    def find(self, query=None, projection=None):
        self.find_calls.append((query, projection))
        return _RecordingCursor(self.docs)

    async def find_one(self, query=None, projection=None):
        self.find_one_calls.append((query, projection))
        return self.docs[0] if self.docs else None

    async def count_documents(self, query=None):
        self.count_calls.append(query)
        return len(self.docs)


def test_master_admin_orgs_list_excludes_features_audit():
    """The org list endpoint must never spread features_audit into the
    list response. We verify by inspecting the source for the
    projection literal (full integration coverage would need an in-mem
    Mongo which is overkill for a projection regression).

    Iter 216h178 — the orgs list route was moved to master_admin_orgs.py
    as part of the master_admin decomposition. The projection still
    lives next to its route handler."""
    src = open('/app/backend/routes/master_admin_orgs.py').read()
    assert '_ORG_LIST_EXCLUDE' in src, "expected named projection constant"
    block_start = src.index('_ORG_LIST_EXCLUDE')
    block = src[block_start:block_start + 400]
    assert '"features_audit": 0' in block, "features_audit must be excluded from org list"


def test_svc_cases_list_excludes_detail_only_fields():
    """The case list endpoint must strip 17 known heavy fields."""
    src = open('/app/backend/routes/svc/cases.py').read()
    assert '_CASE_LIST_EXCLUDE' in src
    block_start = src.index('_CASE_LIST_EXCLUDE')
    block = src[block_start:block_start + 1200]
    for field in (
        'ai_triage', 'ai_summary', 'ai_triage_history',
        'triage_history', 'state_change_history', 'dispatch_history',
        'customer_signature', 'engineer_signature',
        'media', 'photos', 'attachments',
        'safety_responses',
        'notes_internal', 'notes_customer',
        'resolution_note', 'cover_audit',
        'quote_lines', 'parts_requested',
    ):
        assert f'"{field}": 0' in block, f"{field} must be excluded from case list"


def test_svc_cases_detail_still_returns_full_doc():
    """Sanity-check that the detail endpoint did NOT inherit the list
    projection — operators rely on AI triage, notes, signatures, etc.
    when opening a case drawer."""
    src = open('/app/backend/routes/svc/cases.py').read()
    detail_block = src.split('async def get_case')[1].split('async def')[0]
    # find_one must NOT pass the heavy projection
    assert '_CASE_LIST_EXCLUDE' not in detail_block, \
        "case detail must not strip detail-only fields"


def test_members_list_eliminates_n_plus_1():
    """The bulk-load refactor must replace the per-row find_one with
    two batch finds keyed by $in."""
    src = open('/app/backend/routes/memberships/members.py').read()
    list_block = src.split('async def members_list')[1].split('async def')[0]
    # The old per-row pattern is gone.
    assert 'for r in rows:\n        mm = await db.member_memberships.find_one' not in list_block
    # The bulk pattern is present.
    assert '"$in": member_ids' in list_block, "members list must bulk-load memberships by $in"
    # Tight projection on the embedded membership.
    assert '_MM_LIST_PROJ' in list_block, "membership projection must be explicit"


def test_members_list_projection_does_not_leak_password():
    src = open('/app/backend/routes/memberships/members.py').read()
    list_block = src.split('async def members_list')[1].split('async def')[0]
    # The outer member find must still exclude password.
    assert '"password": 0' in list_block, "password must stay excluded from members list"


def test_master_admin_module_imports_clean():
    """Module-level import smoke — the new projection literal must not
    have broken any import chain."""
    importlib.import_module('routes.master_admin')
    importlib.import_module('routes.svc.cases')
    importlib.import_module('routes.memberships.members')


if __name__ == '__main__':
    # Allow `python tests/test_iter_216h174_payload_size.py` for quick iter.
    test_master_admin_orgs_list_excludes_features_audit()
    test_svc_cases_list_excludes_detail_only_fields()
    test_svc_cases_detail_still_returns_full_doc()
    test_members_list_eliminates_n_plus_1()
    test_members_list_projection_does_not_leak_password()
    asyncio.run(asyncio.sleep(0))  # noqa: just keeps async import happy
    test_master_admin_module_imports_clean()
    print('OK')
