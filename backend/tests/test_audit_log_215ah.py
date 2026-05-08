"""Iter 215ah — Audit log viewer unit tests.

Covers:
* severity mapping per kind
* org enrichment from id → name
* access gate (require_master_admin)
* CSV shape has the expected columns
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from routes import master_admin_audit_log as audit


def test_severity_mapping_covers_expected_kinds():
    assert audit._severity_for("login") == "info"
    assert audit._severity_for("login_failed") == "warning"
    assert audit._severity_for("autopay_exhausted") == "critical"
    assert audit._severity_for("unknown_kind_xyz") == "info"  # default


def test_enrich_orgs_adds_names():
    to_list = AsyncMock(return_value=[
        {"id": "org-a", "name": "Studio A"},
        {"id": "org-b", "name": "Studio B"},
    ])
    find_mock = lambda q, proj: SimpleNamespace(to_list=to_list)  # noqa: E731

    with patch.object(audit.db, "organizations", SimpleNamespace(find=find_mock)):
        events = [
            {"organization_id": "org-a", "kind": "login"},
            {"organization_id": "org-b", "kind": "invoice_paid"},
            {"organization_id": None, "kind": "autopay_sweep"},
        ]
        out = asyncio.run(audit._enrich_orgs(events))
    assert out[0]["organization_name"] == "Studio A"
    assert out[1]["organization_name"] == "Studio B"
    assert "organization_name" not in out[2]


def test_enrich_orgs_noop_when_empty():
    find_mock = lambda q, proj: SimpleNamespace(to_list=AsyncMock(return_value=[]))  # noqa: E731
    with patch.object(audit.db, "organizations", SimpleNamespace(find=find_mock)):
        out = asyncio.run(audit._enrich_orgs([{"organization_id": None}]))
    assert out == [{"organization_id": None}]


def test_list_requires_master_admin():
    """Non-master admins must hit the require_master_admin() gate."""
    try:
        asyncio.run(audit.list_audit_events(
            user={"id": "u1", "email": "nobody@x.com", "is_master_admin": False},
            since_days=7, kinds=None, organization_id=None,
            actor_email=None, limit=50,
        ))
        raise AssertionError("Expected HTTPException 403")
    except HTTPException as e:
        assert e.status_code == 403


def test_summary_requires_master_admin():
    try:
        asyncio.run(audit.audit_summary(
            user={"id": "u1", "email": "nobody@x.com", "is_master_admin": False},
            since_days=7,
        ))
        raise AssertionError("Expected HTTPException 403")
    except HTTPException as e:
        assert e.status_code == 403


def test_csv_export_requires_master_admin():
    try:
        asyncio.run(audit.export_audit_csv(
            user={"id": "u1", "email": "nobody@x.com", "is_master_admin": False},
            since_days=30, kinds=None, organization_id=None,
            actor_email=None, limit=100,
        ))
        raise AssertionError("Expected HTTPException 403")
    except HTTPException as e:
        assert e.status_code == 403


def test_csv_export_produces_streaming_response():
    """Happy-path shape check — StreamingResponse + expected headers."""
    with patch.object(audit, "_gather", new=AsyncMock(return_value=[
        {
            "timestamp": "2026-05-01T00:00:00+00:00",
            "kind": "login", "severity": "info",
            "organization_id": "org1", "organization_name": "X",
            "actor_email": "a@b.com", "actor_type": "operator",
            "summary": "Login from 1.2.3.4",
        },
    ])), patch.object(audit, "_enrich_orgs", new=AsyncMock(side_effect=lambda x: x)):
        res = asyncio.run(audit.export_audit_csv(
            user={"id": "u1", "email": "admin@gymaxisai.com", "is_master_admin": True},
            since_days=30, kinds=None, organization_id=None,
            actor_email=None, limit=100,
        ))
    assert res.media_type.startswith("text/csv")
    assert "attachment" in res.headers.get("Content-Disposition", "")
    # body_iterator is an async generator — drain it.
    async def _drain():
        out = []
        async for chunk in res.body_iterator:
            out.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        return b"".join(out).decode()
    body = asyncio.run(_drain())
    assert "timestamp,kind,severity" in body
    assert "login" in body
    assert "a@b.com" in body


def test_event_kind_allowlist_filters_noise(monkeypatch):
    """Unknown kinds passed via ?kinds= query should be discarded by the
    _EVENT_KINDS allowlist before the Mongo query runs."""
    async def fake_gather(**kw):
        # Assert that the set we receive has only valid kinds
        assert kw["kinds"] is not None
        assert "login" in kw["kinds"]
        assert "hacker_kind" not in kw["kinds"]
        return []
    with patch.object(audit, "_gather", new=fake_gather), \
         patch.object(audit, "_enrich_orgs", new=AsyncMock(side_effect=lambda x: x)):
        res = asyncio.run(audit.list_audit_events(
            user={"id": "u1", "email": "admin@gymaxisai.com", "is_master_admin": True},
            since_days=7, kinds="login,hacker_kind,autopay_sweep",
            organization_id=None, actor_email=None, limit=50,
        ))
    assert res["count"] == 0
