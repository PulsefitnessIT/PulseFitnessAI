"""Iter 220dl — Customer tracking page: compliance chips.

Mirrors the PDF compliance evidence pack (Iter 220dj) on the
public live-tracking surface so the customer can see the safety
work landing in real time, not only in the post-visit report.

Pins:

  * ``_public_compliance_summary(case)`` returns three keys
    (``ptw`` / ``loto`` / ``coshh``), each with ``state``,
    ``count`` and ``label``.
  * PTW state:
      - any ``completed`` → ``done``
      - else any ``issued`` → ``in_progress``
      - else → ``none``
  * LOTO / COSHH state:
      - ``count > 0`` → ``done``
      - ``count == 0`` → ``none``
  * Public payload exposes the ``compliance`` key on the
    ``GET /api/svc/public/track/{token}`` response.
  * Frontend renders ``ComplianceChip`` with the right
    ``data-testid`` per kind.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


def _patch_db(*, ptws=None, loto_count=0, coshh_count=0):
    fdb = MagicMock()
    fdb.svc_ptw_requests.find = MagicMock(return_value=_chain(ptws or []))
    fdb.svc_loto_checklists.count_documents = AsyncMock(return_value=loto_count)
    fdb.svc_coshh_usage.count_documents = AsyncMock(return_value=coshh_count)
    return fdb


def _case():
    return {"id": "case-1", "organization_id": "org-1"}


# ── 1 · State logic ──────────────────────────────────────────────


def test_summary_returns_three_kinds_when_nothing_captured():
    fdb = _patch_db()

    async def run():
        with patch("routes.svc.public_tracking.db", fdb):
            from routes.svc.public_tracking import _public_compliance_summary
            return await _public_compliance_summary(_case())

    out = _run(run())
    assert set(out.keys()) == {"ptw", "loto", "coshh"}
    assert out["ptw"]["state"]   == "none"
    assert out["loto"]["state"]  == "none"
    assert out["coshh"]["state"] == "none"
    assert out["ptw"]["count"]   == 0
    assert out["loto"]["count"]  == 0
    assert out["coshh"]["count"] == 0


def test_ptw_done_when_any_completed():
    fdb = _patch_db(ptws=[
        {"status": "completed"},
        {"status": "issued"},  # still in force; but completed wins.
    ])

    async def run():
        with patch("routes.svc.public_tracking.db", fdb):
            from routes.svc.public_tracking import _public_compliance_summary
            return await _public_compliance_summary(_case())

    out = _run(run())
    assert out["ptw"]["state"] == "done"
    assert out["ptw"]["count"] == 2
    assert "completed" in out["ptw"]["label"]


def test_ptw_in_progress_when_only_issued():
    fdb = _patch_db(ptws=[{"status": "issued"}, {"status": "issued"}])

    async def run():
        with patch("routes.svc.public_tracking.db", fdb):
            from routes.svc.public_tracking import _public_compliance_summary
            return await _public_compliance_summary(_case())

    out = _run(run())
    assert out["ptw"]["state"] == "in_progress"
    assert out["ptw"]["count"] == 2
    assert "in force" in out["ptw"]["label"]


def test_loto_done_with_any_signoff_count():
    fdb = _patch_db(loto_count=1)

    async def run():
        with patch("routes.svc.public_tracking.db", fdb):
            from routes.svc.public_tracking import _public_compliance_summary
            return await _public_compliance_summary(_case())

    out = _run(run())
    assert out["loto"]["state"] == "done"
    assert out["loto"]["count"] == 1
    assert "1 isolation signoff" in out["loto"]["label"]


def test_coshh_done_pluralises_label():
    fdb = _patch_db(coshh_count=3)

    async def run():
        with patch("routes.svc.public_tracking.db", fdb):
            from routes.svc.public_tracking import _public_compliance_summary
            return await _public_compliance_summary(_case())

    out = _run(run())
    assert out["coshh"]["state"] == "done"
    assert out["coshh"]["count"] == 3
    assert "3 chemical logs" in out["coshh"]["label"]


def test_summary_safe_for_orphan_case_dict():
    """A case without ``id`` or ``organization_id`` must not blow up
    the public tracking response."""

    async def run():
        from routes.svc.public_tracking import _public_compliance_summary
        return await _public_compliance_summary({})

    out = _run(run())
    assert out == {"ptw": None, "loto": None, "coshh": None}


# ── 2 · Mongo scope guard ────────────────────────────────────────


def test_summary_queries_are_org_and_case_scoped():
    """Pin the Mongo filters — a regression widening scope would
    leak other cases' compliance data onto this customer's page."""
    fdb = _patch_db()

    async def run():
        with patch("routes.svc.public_tracking.db", fdb):
            from routes.svc.public_tracking import _public_compliance_summary
            await _public_compliance_summary(_case())

    _run(run())
    flt = fdb.svc_ptw_requests.find.call_args.args[0]
    assert flt == {"case_id": "case-1", "organization_id": "org-1"}
    loto_flt = fdb.svc_loto_checklists.count_documents.await_args.args[0]
    assert loto_flt == {"case_id": "case-1", "organization_id": "org-1"}
    coshh_flt = fdb.svc_coshh_usage.count_documents.await_args.args[0]
    assert coshh_flt == {"case_id": "case-1", "organization_id": "org-1"}


# ── 3 · Public payload shape ─────────────────────────────────────


def test_public_payload_includes_compliance_block():
    """Sanity guard that the public_tracking response surfaces the
    new ``compliance`` key alongside ``eta`` and ``events``."""
    src = Path("/app/backend/routes/svc/public_tracking.py").read_text()
    assert '"compliance": compliance' in src
    assert "_public_compliance_summary" in src


# ── 4 · Frontend wiring ──────────────────────────────────────────


def test_frontend_compliance_chips_mounted_and_wired():
    src = Path(
        "/app/frontend/src/pages/PublicTracking/PublicTrackingPage.js"
    ).read_text()
    # Imports.
    assert "ShieldCheck" in src
    assert "ClipboardCheck" in src
    assert "FlaskConical" in src
    # Component definition.
    assert "function ComplianceChip" in src
    # Three chips rendered. The component uses a templated testid;
    # check the literal template string + the wrapper testid.
    assert 'data-testid="track-compliance"' in src
    assert "data-testid={`track-compliance-${kind}`}" in src
    # All three kinds passed through.
    assert 'kind="ptw"' in src
    assert 'kind="loto"' in src
    assert 'kind="coshh"' in src
    # Reads from the new payload key.
    assert "data.compliance.ptw" in src
    assert "data.compliance.loto" in src
    assert "data.compliance.coshh" in src
