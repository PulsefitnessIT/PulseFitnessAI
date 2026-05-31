"""Iter 220ax — Wave 6 Security Hardening · Audit hygiene + 404/403.

Closes 4 risk-register findings:

  * F-20 — Audit-log decorator on exports (``@audit_export``).
  * F-28 — Impersonation audit row (``record_impersonation_event``).
  * F-29 — Engineer-app horizontal access (``assert_engineer_owns``).
  * F-33 — 404-vs-403 disambiguation (``not_found_unless_owned``).

Also smokes F-31 (/health minimal) and F-32 (500-handler scrub) — both
existing surfaces that we want regression-locked so a future refactor
can't accidentally re-expose stack traces or version info.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── F-20 · @audit_export decorator ────────────────────────────────


def test_audit_export_records_after_success():
    from utils import audit_log

    @audit_log.audit_export("tender.pitch.pdf", resource_kwarg="tender_id")
    async def _endpoint(tender_id, user):
        return {"streamed": True}

    captured = {}

    async def _fake_insert(doc):
        captured["doc"] = doc
        return MagicMock()

    mock_db = MagicMock()
    mock_db.export_events.insert_one = _fake_insert
    with patch.object(audit_log, "db", mock_db):
        result = _run(_endpoint(tender_id="t-1",
                                user={"id": "u1", "email": "x@y.com",
                                      "organization_id": "org-1"}))
    assert result == {"streamed": True}
    assert captured["doc"]["name"] == "tender.pitch.pdf"
    assert captured["doc"]["resource_id"] == "t-1"
    assert captured["doc"]["actor_id"] == "u1"
    assert captured["doc"]["actor_email"] == "x@y.com"
    assert captured["doc"]["organization_id"] == "org-1"


def test_audit_export_swallows_db_failure():
    from utils import audit_log

    @audit_log.audit_export("any.export")
    async def _endpoint(user):
        return {"ok": True}

    async def _boom(_doc):
        raise RuntimeError("mongo down")

    mock_db = MagicMock()
    mock_db.export_events.insert_one = _boom
    with patch.object(audit_log, "db", mock_db):
        # Must not raise — download must complete even if audit fails.
        result = _run(_endpoint(user={"id": "u1"}))
    assert result == {"ok": True}


def test_audit_export_with_response_body():
    """When the wrapped endpoint returns a ``StreamingResponse``-like
    object the decorator records the ``content-length`` header."""
    from utils import audit_log

    class _FakeResp:
        def __init__(self):
            self.headers = {"content-length": "12345"}
            self.body = None

    @audit_log.audit_export("any.export")
    async def _endpoint(user):
        return _FakeResp()

    captured = {}

    async def _fake_insert(doc):
        captured["doc"] = doc
        return MagicMock()

    mock_db = MagicMock()
    mock_db.export_events.insert_one = _fake_insert
    with patch.object(audit_log, "db", mock_db):
        _run(_endpoint(user={"id": "u1"}))
    assert captured["doc"]["response_bytes"] == 12345


# ── F-28 · record_impersonation_event ──────────────────────────────


def test_impersonation_event_persists_actor_target_token():
    from utils import audit_log

    captured = {}

    async def _fake_insert(doc):
        captured["doc"] = doc
        return MagicMock()

    mock_db = MagicMock()
    mock_db.impersonation_events.insert_one = _fake_insert
    with patch.object(audit_log, "db", mock_db):
        _run(audit_log.record_impersonation_event(
            actor={"id": "a1", "email": "admin@x.com", "role": "master_admin"},
            target_user_id="t1", target_email="t@y.com",
            target_organization_id="org-2", token_jti="jti-1",
            expires_at="2026-01-01T00:00:00+00:00",
            request=None, reason="manual_test",
        ))
    doc = captured["doc"]
    assert doc["actor_id"] == "a1"
    assert doc["actor_role"] == "master_admin"
    assert doc["target_user_id"] == "t1"
    assert doc["target_organization_id"] == "org-2"
    assert doc["token_jti"] == "jti-1"
    assert doc["reason"] == "manual_test"


def test_impersonation_event_handles_datetime_expires():
    from datetime import datetime, timezone
    from utils import audit_log

    captured = {}

    async def _fake_insert(doc):
        captured["doc"] = doc
        return MagicMock()

    exp = datetime(2026, 5, 28, tzinfo=timezone.utc)
    mock_db = MagicMock()
    mock_db.impersonation_events.insert_one = _fake_insert
    with patch.object(audit_log, "db", mock_db):
        _run(audit_log.record_impersonation_event(
            actor={"id": "a1"},
            target_user_id="t1", target_email=None,
            target_organization_id="org",
            token_jti="j", expires_at=exp,
        ))
    assert captured["doc"]["expires_at"] == exp.isoformat()


def test_impersonation_event_swallows_db_errors():
    from utils import audit_log

    async def _boom(_doc):
        raise RuntimeError("mongo down")

    mock_db = MagicMock()
    mock_db.impersonation_events.insert_one = _boom
    with patch.object(audit_log, "db", mock_db):
        # Must not raise — impersonation must succeed even if audit fails.
        _run(audit_log.record_impersonation_event(
            actor={"id": "a"}, target_user_id="t",
            target_email=None, target_organization_id=None,
            token_jti=None, expires_at=None,
        ))


# ── F-29 / F-33 · not_found_unless_owned ───────────────────────────


def test_not_found_unless_owned_returns_row_when_same_tenant():
    from utils.audit_log import not_found_unless_owned
    doc = {"id": "x", "organization_id": "org-1"}
    user = {"id": "u1", "organization_id": "org-1"}
    out = not_found_unless_owned(doc, user, label="Foo")
    assert out is doc


def test_not_found_unless_owned_raises_404_for_cross_tenant():
    from fastapi import HTTPException
    from utils.audit_log import not_found_unless_owned
    doc = {"id": "x", "organization_id": "org-2"}
    user = {"id": "u1", "organization_id": "org-1"}
    try:
        not_found_unless_owned(doc, user, label="Foo")
        raise AssertionError("expected HTTPException(404)")
    except HTTPException as exc:
        # Critical: NOT 403, NOT 401 — 404 to prevent enumeration.
        assert exc.status_code == 404
        assert "Foo" in exc.detail


def test_not_found_unless_owned_raises_404_for_missing_doc():
    from fastapi import HTTPException
    from utils.audit_log import not_found_unless_owned
    try:
        not_found_unless_owned(None, {"id": "u"}, label="Bar")
        raise AssertionError()
    except HTTPException as exc:
        assert exc.status_code == 404


def test_not_found_unless_owned_lets_master_admin_pass():
    from utils.audit_log import not_found_unless_owned
    doc = {"id": "x", "organization_id": "org-2"}
    out = not_found_unless_owned(
        doc, {"id": "a", "is_master_admin": True, "organization_id": "org-1"},
    )
    assert out is doc


def test_not_found_unless_owned_legacy_no_tenant_passes():
    """Legacy rows without a tenant key pass through (defence-in-depth
    must not break legitimate single-tenant ops during migration)."""
    from utils.audit_log import not_found_unless_owned
    doc = {"id": "x"}  # no organization_id
    out = not_found_unless_owned(doc, {"id": "u1", "organization_id": "org-1"})
    assert out is doc


def test_not_found_unless_owned_anonymous_caller_is_404():
    from fastapi import HTTPException
    from utils.audit_log import not_found_unless_owned
    try:
        not_found_unless_owned({"id": "x"}, None)
        raise AssertionError()
    except HTTPException as exc:
        assert exc.status_code == 404


# ── F-29 · assert_engineer_owns ────────────────────────────────────


def test_assert_engineer_owns_passes_when_same():
    from utils.audit_log import assert_engineer_owns
    # No raise.
    assert_engineer_owns("eng-1", "eng-1")


def test_assert_engineer_owns_raises_404_for_cross_engineer():
    from fastapi import HTTPException
    from utils.audit_log import assert_engineer_owns
    try:
        assert_engineer_owns("eng-1", "eng-2", label="Job")
        raise AssertionError()
    except HTTPException as exc:
        assert exc.status_code == 404
        assert "Job" in exc.detail


def test_assert_engineer_owns_raises_404_for_missing_owner():
    from fastapi import HTTPException
    from utils.audit_log import assert_engineer_owns
    for engineer_id, row_engineer_id in (
        (None, "eng-1"),
        ("eng-1", None),
        (None, None),
        ("", "eng-1"),
    ):
        try:
            assert_engineer_owns(engineer_id, row_engineer_id)
            raise AssertionError()
        except HTTPException as exc:
            assert exc.status_code == 404


# ── ensure_indexes ─────────────────────────────────────────────────


def test_audit_ensure_indexes_creates_4_indexes():
    from utils import audit_log

    with patch.object(audit_log, "db") as mock_db:
        mock_db.export_events.create_index = AsyncMock(return_value="idx")
        mock_db.impersonation_events.create_index = AsyncMock(return_value="idx")
        _run(audit_log.ensure_indexes())
        assert mock_db.export_events.create_index.await_count == 3
        assert mock_db.impersonation_events.create_index.await_count == 3


def test_audit_ensure_indexes_swallows_errors():
    from utils import audit_log

    with patch.object(audit_log, "db") as mock_db:
        mock_db.export_events.create_index = AsyncMock(side_effect=RuntimeError("boom"))
        mock_db.impersonation_events.create_index = AsyncMock(side_effect=RuntimeError("boom"))
        # Must not raise — startup must be resilient.
        _run(audit_log.ensure_indexes())


# ── F-31 / F-32 regression-lock smokes ────────────────────────────


def test_health_endpoint_is_minimal():
    """F-31 — /api/health must NOT leak service version / env / build.

    Read the source rather than importing the FastAPI app (which has
    side-effects that conflict with other tests in the suite).
    """
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent / "server.py"
    text = src.read_text(encoding="utf-8")
    # Locate the /health handler body and assert it returns the minimal
    # ``{"status": "ok"}`` shape with no version / env leak.
    import re
    m = re.search(
        r'@api_router\.get\("/health"\)\s*async def health_root.*?return\s*(\{[^}]+\})',
        text, flags=re.DOTALL,
    )
    assert m, "could not locate /api/health handler"
    body = m.group(1)
    assert '"status"' in body and '"ok"' in body
    # MUST NOT include version / env / build / commit info.
    for forbidden in ("version", "build", "commit", "env", "SENTRY_RELEASE",
                      "MONGO_URL", "secret", "hostname"):
        assert forbidden not in body, f"/health body leaks {forbidden!r}: {body}"


def test_unhandled_exception_handler_redacts():
    """F-32 — the global 500 handler must NEVER return the stack trace
    or raw exception message in production responses.

    Source-level check (no FastAPI import) to keep the test isolated.
    """
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent / "server.py"
    text = src.read_text(encoding="utf-8")
    import re
    m = re.search(
        r"@app\.exception_handler\(Exception\).*?async def _unhandled_exception_handler.*?return\s+_JSONResp\((.*?)\)\n",
        text, flags=re.DOTALL,
    )
    assert m, "could not locate global exception handler"
    call_args = m.group(1)
    # Must hard-code status_code=500 + a canned detail string.
    assert "status_code=500" in call_args
    # Must NOT include `str(exc)` / `repr(exc)` / `traceback` in the body.
    for forbidden in ("str(exc)", "repr(exc)", "traceback.format",
                      "tb_lines", "format_exception"):
        assert forbidden not in call_args, (
            f"500 handler leaks raw exception via {forbidden!r}: {call_args}"
        )
