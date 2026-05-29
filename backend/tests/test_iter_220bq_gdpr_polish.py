"""Iter 220bq — GDPR Article 17 right-to-erasure polish.

Locks in the four polish items added in Iter 220bq:

  1. Fail-closed audit trail (``audit_required("gdpr_erasure_audit", …)``)
     fires on create, execute, cancel.
  2. Pre-scrub PII snapshot persisted on the request row so the
     organisation keeps an auditable "what was erased" record.
  3. Cancellation reason is accepted and persisted.
  4. ``auto_execute_due_requests`` sweeps every ``pending`` request
     whose ``execute_after`` has elapsed (UK ICO 1-month deadline).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.skip = MagicMock(return_value=cur)
    cur.limit = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


class _FakeDb:
    """Same lazy collection mock as the existing 220ao tests."""

    def __init__(self):
        self._cols: dict[str, MagicMock] = {}

    def _col(self, name: str) -> MagicMock:
        if name not in self._cols:
            c = MagicMock()
            c.insert_one = AsyncMock()
            c.update_one = AsyncMock()
            c.find_one = AsyncMock(return_value=None)
            c.count_documents = AsyncMock(return_value=0)
            c.find = MagicMock(return_value=_cursor([]))
            self._cols[name] = c
        return self._cols[name]

    def __getitem__(self, name):
        return self._col(name)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._col(name)


_ADMIN = {"id": "u-admin", "is_master_admin": True, "email": "admin@x",
          "organization_id": "org-1"}


# ══════════════ 1 · fail-closed audit trail ═══════════════════════


def test_create_request_writes_audit_event():
    from routes import gdpr_erasure as m
    fdb = _FakeDb()
    fdb["members"].find_one = AsyncMock(return_value={
        "id": "mem-1", "first_name": "Alex", "last_name": "Carter",
        "email": "alex@example.com",
    })
    audit = AsyncMock()

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", audit):
            await m.create_request(
                m.CreateRequestPayload(subject_type="member",
                                        subject_id="mem-1", reason="DSR"),
                user=_ADMIN,
            )
    _run(go())
    audit.assert_awaited_once()
    coll, doc = audit.call_args.args
    assert coll == "gdpr_erasure_audit"
    assert doc["event"] == "request_created"
    assert doc["subject_id"] == "mem-1"
    assert doc["requested_by"] == "u-admin"
    assert doc["reason"] == "DSR"


def test_execute_writes_audit_event_with_summary_keys():
    from routes import gdpr_erasure as m

    pending_req = {
        "id": "req-1", "status": "pending",
        "subject_type": "member", "subject_id": "mem-1",
        "subject_label": "Alex Carter",
        "execute_after": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value=pending_req)
    fdb["members"].find_one = AsyncMock(return_value={
        "id": "mem-1", "first_name": "Alex", "last_name": "Carter",
        "email": "alex@example.com", "phone": "07700900123",
    })
    audit = AsyncMock()

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", audit):
            return await m.execute_request("req-1",
                                            m.ExecutePayload(force=False),
                                            user=_ADMIN)
    out = _run(go())
    assert out["status"] == "executed"
    audit.assert_awaited_once()
    coll, doc = audit.call_args.args
    assert coll == "gdpr_erasure_audit"
    assert doc["event"] == "request_executed"
    # The summary keys should include the fields actually scrubbed.
    assert "email" in doc["scrub_summary_keys"]
    assert "first_name" in doc["scrub_summary_keys"]
    # 4 fields had PII: first_name, last_name, email, phone → snapshot=4.
    assert doc["snapshot_field_count"] == 4
    assert doc["forced"] is False


def test_cancel_writes_audit_event_with_reason():
    from routes import gdpr_erasure as m
    pending_req = {
        "id": "req-1", "status": "pending",
        "subject_type": "member", "subject_id": "mem-1",
        "subject_label": "Alex Carter",
    }
    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value=pending_req)
    audit = AsyncMock()

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", audit):
            await m.cancel_request("req-1",
                                    payload=m.CancelPayload(reason="Subject withdrew request"),
                                    user=_ADMIN)
    _run(go())
    audit.assert_awaited_once()
    coll, doc = audit.call_args.args
    assert coll == "gdpr_erasure_audit"
    assert doc["event"] == "request_cancelled"
    assert doc["cancellation_reason"] == "Subject withdrew request"


# ══════════════ 2 · pre-scrub PII snapshot persisted ══════════════


def test_execute_persists_pre_scrub_snapshot_on_request_row():
    """The full pre-scrub PII payload must land in
    ``gdpr_erasure_requests.pre_scrub_snapshot`` so the org keeps an
    audit-grade record of exactly what was erased — even though the
    canonical row has lost the data."""
    from routes import gdpr_erasure as m
    pending_req = {
        "id": "req-1", "status": "pending",
        "subject_type": "crm_contact", "subject_id": "c-1",
        "subject_label": "Beth Khan",
        "execute_after": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    subject = {
        "id": "c-1", "first_name": "Beth", "last_name": "Khan",
        "email": "beth@khan.co.uk", "phone": "07700900111",
        "city": "London", "postcode": "EC1A 1AA",
        "notes": "Discussed renewal options",
    }
    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value=pending_req)
    fdb["crm2_contacts"].find_one = AsyncMock(return_value=subject)

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", AsyncMock()):
            return await m.execute_request("req-1",
                                            m.ExecutePayload(force=True),
                                            user=_ADMIN)
    _run(go())

    # Verify the request row got updated with the snapshot.
    update_call = fdb.gdpr_erasure_requests.update_one.call_args_list[-1]
    set_doc = update_call.args[1]["$set"]
    snap = set_doc["pre_scrub_snapshot"]
    assert snap["first_name"] == "Beth"
    assert snap["email"] == "beth@khan.co.uk"
    assert snap["phone"] == "07700900111"
    assert snap["notes"] == "Discussed renewal options"
    # Empty-value fields must NOT pollute the snapshot.
    assert "linkedin_url" not in snap


# ══════════════ 3 · cancellation reason persisted ═════════════════


def test_cancel_persists_reason_on_request_row():
    from routes import gdpr_erasure as m
    pending_req = {
        "id": "req-1", "status": "pending",
        "subject_type": "member", "subject_id": "mem-1",
    }
    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value=pending_req)

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", AsyncMock()):
            await m.cancel_request(
                "req-1",
                payload=m.CancelPayload(reason="Member withdrew after dialog"),
                user=_ADMIN,
            )
    _run(go())
    set_doc = fdb.gdpr_erasure_requests.update_one.call_args.args[1]["$set"]
    assert set_doc["cancellation_reason"] == "Member withdrew after dialog"
    assert set_doc["status"] == "cancelled"


def test_cancel_without_reason_defaults_to_empty_string():
    """Backward compatibility — the panel may not send a reason."""
    from routes import gdpr_erasure as m
    pending_req = {
        "id": "req-1", "status": "pending",
        "subject_type": "member", "subject_id": "mem-1",
    }
    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value=pending_req)

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", AsyncMock()):
            # No payload — default body.
            await m.cancel_request("req-1", payload=None, user=_ADMIN)
    _run(go())
    set_doc = fdb.gdpr_erasure_requests.update_one.call_args.args[1]["$set"]
    assert set_doc["cancellation_reason"] == ""


# ══════════════ 4 · auto-execute scheduler ════════════════════════


def test_auto_execute_sweeps_overdue_pending_requests():
    """ICO requires erasure within ONE month. Any pending request past
    its ``execute_after`` must be auto-executed by the scheduler — no
    operator click required."""
    from routes import gdpr_erasure as m
    overdue_a = {
        "id": "req-a", "status": "pending",
        "subject_type": "member", "subject_id": "mem-a",
        "subject_label": "Alice",
        "execute_after": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
    }
    overdue_b = {
        "id": "req-b", "status": "pending",
        "subject_type": "crm_contact", "subject_id": "c-b",
        "subject_label": "Bob",
        "execute_after": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }
    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find = MagicMock(return_value=_cursor([overdue_a, overdue_b]))

    # Subjects exist so the scrub path runs.
    fdb["members"].find_one = AsyncMock(return_value={
        "id": "mem-a", "first_name": "Alice", "email": "alice@x",
    })
    fdb["crm2_contacts"].find_one = AsyncMock(return_value={
        "id": "c-b", "first_name": "Bob", "email": "bob@y",
    })

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", AsyncMock()):
            return await m.auto_execute_due_requests()
    out = _run(go())
    assert out["executed"] == 2
    assert out["errors"] == 0
    # Members.update_one and crm2_contacts.update_one both called once
    # to perform the scrub.
    fdb["members"].update_one.assert_awaited_once()
    fdb["crm2_contacts"].update_one.assert_awaited_once()


def test_auto_execute_is_noop_when_nothing_due():
    from routes import gdpr_erasure as m
    fdb = _FakeDb()
    # find returns empty list — no due rows.
    fdb.gdpr_erasure_requests.find = MagicMock(return_value=_cursor([]))

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", AsyncMock()):
            return await m.auto_execute_due_requests()
    out = _run(go())
    assert out == {"executed": 0, "errors": 0}


def test_auto_execute_skips_still_pending_in_window():
    """A pending row whose ``execute_after`` is in the FUTURE must NOT
    be touched. The find() query already filters on ``execute_after``
    but we still want defence-in-depth on the executor."""
    from routes import gdpr_erasure as m
    future_row = {
        "id": "req-future", "status": "pending",
        "subject_type": "member", "subject_id": "mem-x",
        "subject_label": "Future Alex",
        # Cooling-off window still open.
        "execute_after": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
    }
    fdb = _FakeDb()
    # Pretend the query returned this row anyway (defensive test).
    fdb.gdpr_erasure_requests.find = MagicMock(return_value=_cursor([future_row]))

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", AsyncMock()):
            return await m.auto_execute_due_requests()
    out = _run(go())
    # The executor should refuse via the cooling-off check (no force)
    # and count it under errors, never as executed.
    assert out["executed"] == 0
    assert out["errors"] == 1


def test_auto_execute_records_executed_by_system_label():
    """Auto-executed requests should be visibly tagged as such on the
    request row + audit log (``executed_by="system:auto"``)."""
    from routes import gdpr_erasure as m
    overdue = {
        "id": "req-a", "status": "pending",
        "subject_type": "member", "subject_id": "mem-a",
        "subject_label": "Alice",
        "execute_after": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find = MagicMock(return_value=_cursor([overdue]))
    fdb["members"].find_one = AsyncMock(return_value={
        "id": "mem-a", "first_name": "Alice", "email": "alice@x",
    })
    audit = AsyncMock()

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "audit_required", audit):
            await m.auto_execute_due_requests()
    _run(go())
    # Inspect the request-row update.
    set_doc = fdb.gdpr_erasure_requests.update_one.call_args.args[1]["$set"]
    assert set_doc["executed_by"] == "system:auto"
    assert set_doc["status"] == "executed"
    # And the audit row.
    coll, doc = audit.call_args.args
    assert coll == "gdpr_erasure_audit"
    assert doc["executed_by"] == "system:auto"


def test_run_now_endpoint_is_master_admin_only():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m
    non_admin = {"id": "u-2", "is_master_admin": False}

    async def go():
        with pytest.raises(HTTPException) as exc:
            await m.auto_execute_run_now(user=non_admin)
        assert exc.value.status_code == 403
    _run(go())


def test_server_wires_gdpr_auto_executor_on_startup():
    """The startup hook in server.py must register the auto-executor
    background task so deployments pick it up automatically."""
    import pathlib
    server_src = (pathlib.Path(__file__).resolve().parents[1] / "server.py").read_text()
    assert "run_gdpr_erasure_auto_executor" in server_src, (
        "server.py startup hook must import and start the GDPR auto-executor."
    )
    assert "GDPR_ERASURE_AUTOEXEC" in server_src, (
        "Auto-executor cadence must be env-driven via "
        "GDPR_ERASURE_AUTOEXEC_INTERVAL_MIN."
    )
