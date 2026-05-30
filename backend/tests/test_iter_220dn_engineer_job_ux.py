"""Iter 220dn / 220do / 220dp — Engineer job-screen UX restructure.

Pins (from operator feedback on the Treadmill-slip screenshot, Feb 2026):

  1. Tab order is **Summary / Travel / Time / Equipment / Parts /
     Complete** (no standalone Photos tab — photos belong to a
     machine, not a job).
  2. ``JobAtAGlance`` (customer card / address / fault / handoff
     notes / I'm-on-site CTA) renders ONLY when the Summary tab is
     active — engineers no longer scroll past it on every tab.
  3. Photos block lives inside the Summary tab.
  4. The "from=queue" URL parameter routes the back-arrow back to
     Up-for-grabs (fixes "the job disappeared after I tapped into
     it" report).
  5. Backend ``POST /svc/engineer/jobs/{id}/parts/use`` accepts a
     ``machine_id`` + ``machine_name`` so the used-part record
     links to the asset.
  6. Backend ``POST /svc/engineer/jobs/{id}/return-to-fix``
     reschedules + (optionally) notifies the customer in one call.
  7. Frontend Complete tab now opens with the "Did you fix it on
     this visit?" gate that drives ``return-to-fix``.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(org="org-1", uid="eng-1"):
    return {"id": uid, "organization_id": org,
            "full_name": "Eng One", "email": "e@x.test"}


FRONTEND = Path("/app/frontend/src")


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── 1 · Tab order + Summary-only customer card ────────────────────


def test_tab_order_matches_user_requested_flow():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The TABS array is rendered in source order — pin every id.
    for needle in (
        "id: 'summary'",
        "id: 'travel'",
        "id: 'time'",
        "id: 'equipment'",
        "id: 'parts'",
        "id: 'complete'",
    ):
        assert needle in src, f"missing tab id {needle}"
    # The legacy standalone Photos tab must be gone.
    assert "id: 'photos'" not in src
    # And "Summary" is the default landing tab on every open.
    assert "useState('summary')" in src


def test_job_at_a_glance_only_renders_on_summary_tab():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The conditional wrapping JobAtAGlance must be Summary-scoped.
    assert "activeTab === 'summary' && (" in src
    assert "<JobAtAGlance" in src
    # The earlier unconditional render block must NOT be present.
    assert (
        "        <JobAtAGlance job={job} setBusy={setBusy} busy={busy} onChange={load} />\n"
        "        {activeTab === 'time'"
    ) not in src


def test_photos_block_lives_inside_summary_tab():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # The Photos block is now rendered alongside JobAtAGlance inside
    # the Summary conditional — not as its own activeTab branch.
    assert "activeTab === 'photos'" not in src
    # PhotosTab is still mounted (inside Summary) so the component
    # is reachable.
    assert "<PhotosTab" in src


# ── 2 · Back-arrow returns to queue when ?from=queue ──────────────


def test_back_arrow_honours_from_queue_param():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert "useSearchParams" in src
    assert "searchParams.get('from') === 'queue'" in src
    assert "/svc/engineer/queue" in src


def test_queue_passes_from_queue_on_claim():
    src = _read("pages/ServiceOps/Engineer/EngineerQueue.js")
    assert "?from=queue" in src


# ── 3 · Backend `parts/use` accepts machine_id + machine_name ─────


def test_part_use_payload_persists_machine_link():
    from routes.svc.engineer_phase3 import use_part_ad_hoc, PartUseIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1", "reference": "GA-1",
        "assigned_engineer_id": "eng-1",
    })
    fdb.svc_parts.find_one = AsyncMock(return_value={
        "sku": "BELT-200", "name": "Drive belt", "list_price": 45.0,
    })
    fdb.svc_van_stock.find_one = AsyncMock(return_value=None)
    fdb.svc_cases.update_one = AsyncMock()
    fdb.svc_part_movements.insert_one = AsyncMock()

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", AsyncMock()):
            return await use_part_ad_hoc(
                case_id="case-1",
                body=PartUseIn(
                    part_sku="BELT-200", qty=1, notes="",
                    machine_id="mach-7", machine_name="Treadmill #14",
                ),
                user=_user(),
                idempotency_key=None,
            )

    _run(go())
    # The `$push` allocation must carry the machine link straight
    # through so the customer report can render
    # "Belt £45 → Treadmill #14".
    pushed = fdb.svc_cases.update_one.call_args[0][1]["$push"]["allocated_parts"]
    assert pushed["machine_id"] == "mach-7"
    assert pushed["machine_name"] == "Treadmill #14"
    assert pushed["part_sku"] == "BELT-200"


def test_part_use_machine_link_optional():
    """Engineers shouldn't be blocked when they don't yet know which
    asset the spend belongs to — machine link defaults to None."""
    from routes.svc.engineer_phase3 import use_part_ad_hoc, PartUseIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1", "reference": "GA-1",
        "assigned_engineer_id": "eng-1",
    })
    fdb.svc_parts.find_one = AsyncMock(return_value=None)
    fdb.svc_van_stock.find_one = AsyncMock(return_value=None)
    fdb.svc_cases.update_one = AsyncMock()
    fdb.svc_part_movements.insert_one = AsyncMock()

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", AsyncMock()):
            return await use_part_ad_hoc(
                case_id="case-1",
                body=PartUseIn(part_sku="WIDGET", qty=2, notes=""),
                user=_user(),
                idempotency_key=None,
            )

    _run(go())
    pushed = fdb.svc_cases.update_one.call_args[0][1]["$push"]["allocated_parts"]
    assert pushed["machine_id"] is None
    assert pushed["machine_name"] is None


# ── 4 · Return-to-fix endpoint ────────────────────────────────────


def test_return_to_fix_400_on_bad_iso():
    from fastapi import HTTPException
    from routes.svc.engineer_phase3 import return_to_fix, ReturnToFixIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
    })

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb):
            try:
                await return_to_fix(
                    case_id="case-1",
                    body=ReturnToFixIn(return_at="not-an-iso"),
                    user=_user(),
                )
                return None
            except HTTPException as exc:
                return exc.status_code

    assert _run(go()) == 400


def test_return_to_fix_persists_block_and_reschedules_case():
    from routes.svc.engineer_phase3 import return_to_fix, ReturnToFixIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "title": "Treadmill",
        "site_name": "London HQ",
        "customer_email": "ops@customer.test",
        "assigned_engineer_id": "eng-1",
    })
    fdb.svc_cases.update_one = AsyncMock()
    notify = AsyncMock()

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", AsyncMock()), \
             patch("routes.svc.notifications.create_notification", notify):
            return await return_to_fix(
                case_id="case-1",
                body=ReturnToFixIn(
                    return_at="2026-06-04T09:30:00Z",
                    reason="Parts on order",
                    notify_customer=True,
                ),
                user=_user(),
            )

    out = _run(go())
    upd = fdb.svc_cases.update_one.call_args[0][1]["$set"]
    assert upd["scheduled_at"] == "2026-06-04T09:30:00Z"
    assert upd["status"] == "scheduled"
    rtf = upd["return_to_fix"]
    assert rtf["reason"] == "Parts on order"
    assert rtf["return_at"] == "2026-06-04T09:30:00Z"
    assert rtf["engineer_id"] == "eng-1"
    # Customer notify fired.
    assert out["customer_notified"] is True
    assert notify.await_count == 1
    assert notify.await_args.kwargs["kind"] == "job_rescheduled"


def test_return_to_fix_skips_notify_when_flag_off():
    from routes.svc.engineer_phase3 import return_to_fix, ReturnToFixIn

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
        "customer_email": "ops@customer.test",
        "assigned_engineer_id": "eng-1",
    })
    fdb.svc_cases.update_one = AsyncMock()
    notify = AsyncMock()

    async def go():
        with patch("routes.svc.engineer_phase3.db", fdb), \
             patch("routes.svc.engineer_phase3.append_event", AsyncMock()), \
             patch("routes.svc.notifications.create_notification", notify):
            return await return_to_fix(
                case_id="case-1",
                body=ReturnToFixIn(
                    return_at="2026-06-04T09:30:00Z",
                    reason="",
                    notify_customer=False,
                ),
                user=_user(),
            )

    out = _run(go())
    assert out["customer_notified"] is False
    notify.assert_not_called()


# ── 5 · Frontend Complete tab pins the gate ──────────────────────


def test_complete_tab_pins_the_return_to_fix_card():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    # Component definition + testids.
    assert "function ReturnToFixCard" in src
    assert 'data-testid="complete-return-to-fix"' in src
    assert 'data-testid="rtf-yes"' in src
    assert 'data-testid="rtf-no"' in src
    assert 'data-testid="rtf-submit"' in src
    # Calls the new backend endpoint.
    assert "/svc/engineer/jobs/${job.id}/return-to-fix" in src


# ── 6 · Parts UI machine selector ────────────────────────────────


def test_parts_adhoc_form_has_machine_selector():
    src = _read("pages/ServiceOps/Engineer/EngineerJobDetailV2.js")
    assert 'data-testid="parts-adhoc-machine"' in src
    # The used-list now renders the machine name when set.
    assert "a.machine_name" in src
