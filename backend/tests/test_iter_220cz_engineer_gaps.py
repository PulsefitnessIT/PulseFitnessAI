"""Iter 220cz — Engineer P1 gap-closing: overrun warning, sibling-site
jobs, and engineer-to-engineer handoff notes.

Pinned behaviour:

Backend changes to ``GET /api/svc/engineer/jobs/{case_id}``
  * Response includes ``overrun`` with ``estimated_minutes``,
    ``on_site_minutes``, ``is_overrun``, ``is_approaching``,
    ``percent_used``.
  * Response includes ``sibling_jobs`` — up to 5 other OPEN cases
    for the same customer at the same site.

Backend ``POST /api/svc/engineer/jobs/{case_id}/handoff-note``
  * Appends a note to ``case.handoff_notes``.
  * Empty body → 400.
  * Missing case → 404.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="eng-1", org="org-1"):
    return {"id": uid, "organization_id": org,
            "email": "eng@example.com", "full_name": "Eng One"}


def _chain(default):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=default)
    return cur


def _job_db(*, case, time_entries=None, sibling_cases=None):
    fdb = MagicMock()
    # The case lookup.
    fdb.svc_cases.find_one = AsyncMock(return_value=case)

    def _cases_find(query, *_a, **_k):
        # asset-history query has ``status: {$in: [...closed states]}``;
        # sibling-jobs query has the OPEN set.
        in_set = (query.get("status") or {}).get("$in") or []
        if "new" in in_set or "in_progress" in in_set:
            return _chain(sibling_cases or [])
        return _chain([])

    fdb.svc_cases.find = MagicMock(side_effect=_cases_find)
    fdb.svc_case_events.find = MagicMock(return_value=_chain([]))
    fdb.svc_engineer_photos.find = MagicMock(return_value=_chain([]))
    fdb.svc_time_entries.find = MagicMock(return_value=_chain(time_entries or []))
    fdb.svc_case_safety_signoffs.find_one = AsyncMock(
        return_value={"id": "s-1", "signed_at": "2026-05-30T00:00:00Z",
                      "ticked_item_ids": [], "remarks": ""},
    )
    # Iter 220ed added a completed-job recap read (signature + resolution).
    fdb.svc_signatures.find_one = AsyncMock(return_value=None)
    return fdb


# ── 1 · Overrun math ──────────────────────────────────────────────


def test_job_detail_returns_overrun_block_when_over_estimate():
    case = {
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
        "status": "in_progress",
        "estimated_minutes": 60,
        "customer_name": "Acme", "site_name": "HQ",
        "customer_email": "a@b.test",
    }
    time_entries = [
        {"category": "on_site", "duration_minutes": 75, "end_at": "x"},
    ]
    fdb = _job_db(case=case, time_entries=time_entries)

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_job_detail
            return await engineer_job_detail(case_id="case-1", user=_user())

    out = _run(run())
    assert out["overrun"]["estimated_minutes"] == 60
    assert out["overrun"]["on_site_minutes"] == 75
    assert out["overrun"]["is_overrun"] is True
    assert out["overrun"]["is_approaching"] is False
    assert out["overrun"]["percent_used"] == 125.0


def test_job_detail_flags_approaching_estimate():
    case = {
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
        "status": "in_progress",
        "estimated_minutes": 100,
    }
    time_entries = [{"category": "on_site", "duration_minutes": 90}]
    fdb = _job_db(case=case, time_entries=time_entries)

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_job_detail
            return await engineer_job_detail(case_id="case-1", user=_user())

    out = _run(run())
    assert out["overrun"]["is_approaching"] is True
    assert out["overrun"]["is_overrun"] is False


def test_job_detail_overrun_zero_when_no_estimate():
    case = {
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
        "status": "in_progress",
    }
    fdb = _job_db(case=case, time_entries=[])

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_job_detail
            return await engineer_job_detail(case_id="case-1", user=_user())

    out = _run(run())
    assert out["overrun"]["estimated_minutes"] == 0
    assert out["overrun"]["is_overrun"] is False
    assert out["overrun"]["is_approaching"] is False
    assert out["overrun"]["percent_used"] == 0


# ── 2 · Sibling-jobs warning ──────────────────────────────────────


def test_job_detail_returns_sibling_jobs_at_same_site():
    case = {
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
        "status": "in_progress",
        "customer_email": "ops@acme.test",
        "customer_name": "Acme",
        "site_name": "Acme HQ",
    }
    siblings = [
        {"id": "case-2", "reference": "GA-200", "title": "Belt swap",
         "priority": "p2", "status": "scheduled"},
        {"id": "case-3", "reference": "GA-201", "title": "Display",
         "priority": "p3", "status": "new"},
    ]
    fdb = _job_db(case=case, sibling_cases=siblings)

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_job_detail
            return await engineer_job_detail(case_id="case-1", user=_user())

    out = _run(run())
    assert len(out["sibling_jobs"]) == 2
    assert {c["id"] for c in out["sibling_jobs"]} == {"case-2", "case-3"}


def test_job_detail_no_sibling_query_when_site_or_customer_missing():
    """If we don't have a customer key OR a site name, we don't even
    fire the sibling-jobs query (would be too broad)."""
    case = {
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
        "status": "new",
        # Deliberately blank.
        "customer_email": "", "customer_name": "", "site_name": "",
    }
    fdb = _job_db(case=case, sibling_cases=[])

    async def run():
        with patch("routes.svc.engineer.db", fdb):
            from routes.svc.engineer import engineer_job_detail
            return await engineer_job_detail(case_id="case-1", user=_user())

    out = _run(run())
    assert out["sibling_jobs"] == []


# ── 3 · Handoff notes endpoint ────────────────────────────────────


def test_handoff_note_happy_path_pushes_entry_and_emits_event():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(
        return_value={"id": "case-1", "reference": "GA-100"},
    )
    fdb.svc_cases.update_one = AsyncMock()
    append = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", append):
            from routes.svc.engineer_phase3 import add_handoff_note
            return await add_handoff_note(
                case_id="case-1",
                body={"note": "Belt frayed, swap on next visit."},
                user=_user(),
            )

    out = _run(run())
    assert out["ok"] is True
    assert out["entry"]["note"] == "Belt frayed, swap on next visit."
    assert out["entry"]["engineer_id"] == "eng-1"

    fdb.svc_cases.update_one.assert_awaited_once()
    update_args = fdb.svc_cases.update_one.await_args
    push = update_args.args[1]["$push"]["handoff_notes"]
    assert push["note"] == "Belt frayed, swap on next visit."
    assert push["engineer_id"] == "eng-1"

    append.assert_awaited_once()
    kwargs = append.await_args.kwargs
    assert kwargs["case_id"] == "case-1"
    assert kwargs["event_type"] == "note"
    assert kwargs["extra"]["kind"] == "handoff_note"


def test_handoff_note_rejects_empty_body():
    import pytest
    from fastapi import HTTPException

    async def run():
        from routes.svc.engineer_phase3 import add_handoff_note
        return await add_handoff_note(
            case_id="case-1", body={"note": "   "}, user=_user(),
        )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 400


def test_handoff_note_404s_on_missing_case():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=None)

    async def run():
        with patch("routes.svc.engineer_phase3.db", fdb):
            from routes.svc.engineer_phase3 import add_handoff_note
            return await add_handoff_note(
                case_id="missing", body={"note": "hi"}, user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 404


def test_handoff_note_truncates_at_2000_chars():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(
        return_value={"id": "case-1", "reference": "GA-100"},
    )
    fdb.svc_cases.update_one = AsyncMock()

    long_note = "x" * 3000

    async def run():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", AsyncMock()):
            from routes.svc.engineer_phase3 import add_handoff_note
            return await add_handoff_note(
                case_id="case-1", body={"note": long_note}, user=_user(),
            )

    out = _run(run())
    assert len(out["entry"]["note"]) == 2000


# ── 4 · Frontend wiring guard ─────────────────────────────────────


def test_frontend_jaag_consumes_new_fields():
    """Smoke check that the JobAtAGlance section consumes the
    three new fields and renders a handoff composer."""
    from pathlib import Path
    src = Path("/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js").read_text()
    assert "JobOverrunBanner" in src
    assert "SiblingJobsBanner" in src
    assert "HandoffNotesPanel" in src
    assert "/handoff-note" in src
    # Stable test IDs (literal strings present in JSX).
    for tid in (
        "jaag-sibling-jobs", "jaag-sibling-jobs-list",
        "jaag-handoff-panel", "jaag-handoff-add", "jaag-handoff-submit",
        "jaag-handoff-input", "jaag-handoff-list",
    ):
        assert f'data-testid="{tid}"' in src, f"missing test-id: {tid}"
    # Overrun banner uses a conditional testid; ensure both labels present.
    assert "'jaag-overrun'" in src and "'jaag-overrun-approaching'" in src
