"""Iter 220ao — GDPR Article 17 right-to-erasure workflow.

Pins the master-admin-only PII anonymisation workflow for the three
PII-bearing subject types (member, instructor, crm_contact):

  * Preview endpoint surfaces the scrub plan (current PII → planned
    post-scrub value) WITHOUT touching the DB.
  * Create-request stamps a 30-day cooling-off window and 409s on
    duplicate pending requests for the same subject.
  * Execute refuses to fire before ``execute_after`` unless ``force``
    is True; performs in-place PII anonymisation (names → ``[REDACTED]``,
    email → ``erased+{sha8}@gdpr.local``, phone/dob/address → None);
    stamps ``gdpr_erased=True`` so the record is excluded from future
    marketing batches.
  * Cancel resets a pending request to ``cancelled``.
  * Master-admin-only on every endpoint.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
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


class _FakeDb:
    """MagicMock that returns a per-collection mock on ``db[name]``
    *and* on ``db.<name>`` (the GDPR module uses both styles)."""

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


_ADMIN = {"id": "u-1", "is_master_admin": True, "email": "admin@x", "organization_id": "org-1"}
_OPER = {"id": "u-2", "is_master_admin": False, "email": "op@x", "organization_id": "org-1"}


# ── Auth gating ────────────────────────────────────────────────────

def test_preview_requires_master_admin():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    async def go():
        with patch.object(m, "db", _FakeDb()):
            try:
                await m.preview_erasure(
                    m.PreviewPayload(subject_type="member", subject_id="x"),
                    user=_OPER,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 403


def test_execute_requires_master_admin():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    async def go():
        with patch.object(m, "db", _FakeDb()):
            try:
                await m.execute_request(
                    request_id="r-1",
                    payload=m.ExecutePayload(force=True),
                    user=_OPER,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 403


# ── Preview ───────────────────────────────────────────────────────

def test_preview_returns_scrub_plan_for_member():
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    fdb["members"].find_one = AsyncMock(return_value={
        "id": "mem-1", "first_name": "Alex", "last_name": "Carter",
        "email": "alex@example.com", "phone": "07123 456789",
        "dob": "1990-01-01", "postcode": "SW1A 1AA",
    })

    async def go():
        with patch.object(m, "db", fdb):
            return await m.preview_erasure(
                m.PreviewPayload(subject_type="member", subject_id="mem-1"),
                user=_ADMIN,
            )
    out = _run(go())
    assert out["label"] == "Alex Carter"
    assert out["already_erased"] is False
    assert out["plan"]["first_name"]["after"] == "[REDACTED]"
    assert out["plan"]["last_name"]["after"] == "[REDACTED]"
    assert out["plan"]["email"]["after"].startswith("erased+")
    assert out["plan"]["email"]["after"].endswith("@gdpr.local")
    assert out["plan"]["phone"]["after"] is None
    assert out["plan"]["dob"]["after"] is None
    assert out["plan"]["postcode"]["after"] is None
    # Retained-fields whitelist surfaced for operator transparency.
    assert "member_number" in out["retains"]


def test_preview_rejects_unknown_subject_type():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    async def go():
        with patch.object(m, "db", _FakeDb()):
            try:
                await m.preview_erasure(
                    m.PreviewPayload(subject_type="vampire", subject_id="x"),
                    user=_ADMIN,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 400


def test_preview_404_when_subject_missing():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    fdb = _FakeDb()  # all find_ones return None.

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.preview_erasure(
                    m.PreviewPayload(subject_type="crm_contact", subject_id="x"),
                    user=_ADMIN,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 404


# ── Create request ────────────────────────────────────────────────

def test_create_request_stamps_30_day_cooling_off():
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    fdb["members"].find_one = AsyncMock(return_value={
        "id": "mem-1", "first_name": "Alex", "last_name": "Carter",
        "email": "alex@example.com",
    })
    # No prior pending request.
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.create_request(
                m.CreateRequestPayload(
                    subject_type="member", subject_id="mem-1",
                    reason="member emailed asking for full deletion",
                ),
                user=_ADMIN,
            )
    out = _run(go())
    assert out["status"] == "pending"
    assert out["subject_label"] == "Alex Carter"
    assert out["requested_by"] == "u-1"
    # execute_after is ~30d in the future.
    eft = datetime.fromisoformat(out["execute_after"])
    delta = eft - datetime.fromisoformat(out["requested_at"])
    assert 29 <= delta.days <= 31
    fdb.gdpr_erasure_requests.insert_one.assert_awaited_once()


def test_create_request_409_on_existing_pending():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    fdb["members"].find_one = AsyncMock(return_value={"id": "mem-1"})
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value={
        "id": "req-existing", "status": "pending",
    })

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.create_request(
                    m.CreateRequestPayload(
                        subject_type="member", subject_id="mem-1",
                    ),
                    user=_ADMIN,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 409
    fdb.gdpr_erasure_requests.insert_one.assert_not_called()


def test_create_request_rejects_already_erased_subject():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    fdb["members"].find_one = AsyncMock(return_value={
        "id": "mem-1", "gdpr_erased": True,
    })

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.create_request(
                    m.CreateRequestPayload(
                        subject_type="member", subject_id="mem-1",
                    ),
                    user=_ADMIN,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 400


# ── Execute ────────────────────────────────────────────────────────

def test_execute_blocked_before_cooling_off_unless_forced():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    future = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value={
        "id": "req-1", "subject_type": "member", "subject_id": "mem-1",
        "status": "pending", "execute_after": future,
    })

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.execute_request(
                    request_id="req-1",
                    payload=m.ExecutePayload(force=False),
                    user=_ADMIN,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 400
    # The subject row must NOT have been touched.
    fdb["members"].update_one.assert_not_called()


def test_execute_force_bypasses_cooling_window_and_anonymises_pii():
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    future = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value={
        "id": "req-1", "subject_type": "member", "subject_id": "mem-1",
        "status": "pending", "execute_after": future,
    })
    fdb["members"].find_one = AsyncMock(return_value={
        "id": "mem-1", "first_name": "Alex", "last_name": "Carter",
        "email": "alex@example.com", "phone": "07123",
        "postcode": "SW1A", "dob": "1990-01-01",
    })

    async def go():
        with patch.object(m, "db", fdb):
            return await m.execute_request(
                request_id="req-1",
                payload=m.ExecutePayload(force=True),
                user=_ADMIN,
            )
    out = _run(go())
    assert out["status"] == "executed"
    # The subject row was updated with the anonymised set.
    fdb["members"].update_one.assert_awaited_once()
    update_arg = fdb["members"].update_one.await_args.args[1]["$set"]
    assert update_arg["gdpr_erased"] is True
    assert update_arg["first_name"] == "[REDACTED]"
    assert update_arg["last_name"] == "[REDACTED]"
    assert update_arg["email"].startswith("erased+") and update_arg["email"].endswith("@gdpr.local")
    assert update_arg["phone"] is None
    assert update_arg["postcode"] is None
    assert update_arg["dob"] is None
    # The request row got status=executed.
    fdb.gdpr_erasure_requests.update_one.assert_awaited_once()
    req_update = fdb.gdpr_erasure_requests.update_one.await_args.args[1]["$set"]
    assert req_update["status"] == "executed"
    assert req_update["forced"] is True


def test_execute_after_cooling_off_window_does_not_need_force():
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value={
        "id": "req-1", "subject_type": "instructor", "subject_id": "ins-1",
        "status": "pending", "execute_after": past,
    })
    fdb["membership_instructors"].find_one = AsyncMock(return_value={
        "id": "ins-1", "name": "Jordan Lee", "email": "jordan@x.com",
    })

    async def go():
        with patch.object(m, "db", fdb):
            return await m.execute_request(
                request_id="req-1",
                payload=m.ExecutePayload(force=False),
                user=_ADMIN,
            )
    out = _run(go())
    assert out["status"] == "executed"
    fdb["membership_instructors"].update_one.assert_awaited_once()


def test_execute_idempotent_when_subject_already_deleted():
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value={
        "id": "req-1", "subject_type": "crm_contact", "subject_id": "c-1",
        "status": "pending", "execute_after": past,
    })
    # No subject row anymore — we still mark the request executed.
    fdb["crm2_contacts"].find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.execute_request(
                request_id="req-1",
                payload=m.ExecutePayload(force=False),
                user=_ADMIN,
            )
    out = _run(go())
    assert out["status"] == "executed"
    assert "not found" in out["scrub_summary"]["note"].lower()
    fdb.gdpr_erasure_requests.update_one.assert_awaited_once()


def test_execute_refuses_when_status_not_pending():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value={
        "id": "req-1", "status": "executed",
    })

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.execute_request(
                    request_id="req-1",
                    payload=m.ExecutePayload(force=True),
                    user=_ADMIN,
                )
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 400


# ── Cancel ────────────────────────────────────────────────────────

def test_cancel_pending_request():
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value={
        "id": "req-1", "status": "pending",
    })

    async def go():
        with patch.object(m, "db", fdb):
            return await m.cancel_request(request_id="req-1", user=_ADMIN)
    out = _run(go())
    assert out["status"] == "cancelled"
    fdb.gdpr_erasure_requests.update_one.assert_awaited_once()
    set_arg = fdb.gdpr_erasure_requests.update_one.await_args.args[1]["$set"]
    assert set_arg["status"] == "cancelled"
    assert set_arg["cancelled_by"] == "u-1"


def test_cancel_refuses_non_pending():
    from fastapi import HTTPException
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    fdb.gdpr_erasure_requests.find_one = AsyncMock(return_value={
        "id": "req-1", "status": "executed",
    })

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.cancel_request(request_id="req-1", user=_ADMIN)
                return None
            except HTTPException as exc:
                return exc.status_code
    assert _run(go()) == 400


# ── List ──────────────────────────────────────────────────────────

def test_list_requests_with_status_filter():
    from routes import gdpr_erasure as m

    fdb = _FakeDb()
    rows = [
        {"id": "r1", "status": "pending"},
        {"id": "r2", "status": "pending"},
    ]
    fdb.gdpr_erasure_requests.count_documents = AsyncMock(return_value=2)
    fdb.gdpr_erasure_requests.find = MagicMock(return_value=_cursor(rows))

    async def go():
        with patch.object(m, "db", fdb):
            return await m.list_requests(
                status="pending", subject_type=None,
                skip=0, limit=10, user=_ADMIN,
            )
    out = _run(go())
    assert out["total"] == 2
    assert [r["id"] for r in out["requests"]] == ["r1", "r2"]
    # The find query had the status filter applied.
    call = fdb.gdpr_erasure_requests.find.call_args
    assert call.args[0] == {"status": "pending"}
