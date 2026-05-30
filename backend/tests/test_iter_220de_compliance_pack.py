"""Iter 220de — Compliance Pack: Permit to Work, COSHH register, LOTO.

Pinned behaviour:

  * PTW: lazy-seeds 3 default templates per org on first read.
    Engineer requests → admin issues (validity stamped) → engineer
    completes. State machine: requested → issued → completed.
  * COSHH: lazy-seeds 3 default chemicals per org. Admin CRUDs the
    register; engineer records per-case usage.
  * LOTO: per-case checklist with 7 default steps (5 required).
    Submit 400s if any required step is missing.
  * Compliance summary endpoint composes all three into a single
    read for the JobAtAGlance ``ComplianceCard``.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="eng-1", org="org-1", role=""):
    return {
        "id": uid, "organization_id": org, "role": role,
        "email": "u@x.test", "full_name": "Test U",
    }


def _admin():
    return _user(uid="admin-1", role="owner")


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


# ══════ PTW ══════════════════════════════════════════════════════


def test_ptw_templates_lazy_seed_when_empty():
    fdb = MagicMock()
    fdb.svc_ptw_templates.count_documents = AsyncMock(return_value=0)
    fdb.svc_ptw_templates.insert_many = AsyncMock()
    fdb.svc_ptw_templates.find = MagicMock(return_value=_chain([]))

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import list_ptw_templates
            return await list_ptw_templates(user=_user())

    out = _run(run())
    fdb.svc_ptw_templates.insert_many.assert_awaited_once()
    seeded = fdb.svc_ptw_templates.insert_many.await_args.args[0]
    # Three defaults: hot_work, electrical, height.
    cats = {t["hazard_category"] for t in seeded}
    assert {"hot_work", "electrical", "height"} <= cats
    assert "items" in out
    assert "categories" in out


def test_ptw_template_requires_admin():
    import pytest
    from fastapi import HTTPException

    async def run():
        from routes.svc.compliance import create_ptw_template, PtwTemplateIn
        return await create_ptw_template(
            body=PtwTemplateIn(name="Test", hazard_category="hot_work"),
            user=_user(role="staff"),
        )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 403


def test_ptw_template_rejects_invalid_category():
    import pytest
    from fastapi import HTTPException

    async def run():
        from routes.svc.compliance import create_ptw_template, PtwTemplateIn
        return await create_ptw_template(
            body=PtwTemplateIn(name="Test", hazard_category="banana"),
            user=_admin(),
        )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 422


def test_ptw_request_creates_and_emits_event():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(
        return_value={"id": "case-1", "reference": "GA-100"},
    )
    fdb.svc_ptw_templates.find_one = AsyncMock(
        return_value={
            "id": "tpl-1", "name": "Hot Work",
            "hazard_category": "hot_work", "validity_hours": 8,
            "hazards": ["x"], "controls": ["y"],
        },
    )
    fdb.svc_ptw_requests.insert_one = AsyncMock()
    append = AsyncMock()

    async def run():
        with patch("routes.svc.compliance.db", fdb), \
             patch("routes.svc.compliance.append_event", append):
            from routes.svc.compliance import create_ptw_request, PtwRequestIn
            return await create_ptw_request(
                case_id="case-1",
                body=PtwRequestIn(template_id="tpl-1", notes="Welding shroud"),
                user=_user(),
            )

    out = _run(run())
    assert out["status"] == "requested"
    assert out["template_name"] == "Hot Work"
    assert out["requested_by_id"] == "eng-1"
    append.assert_awaited_once()


def test_ptw_issue_stamps_validity_window():
    fdb = MagicMock()
    req = {"id": "req-1", "case_id": "case-1", "template_name": "Hot Work",
           "status": "requested", "validity_hours": 4,
           "organization_id": "org-1"}
    fdb.svc_ptw_requests.find_one = AsyncMock(side_effect=[req, {**req, "status": "issued"}])
    fdb.svc_ptw_requests.update_one = AsyncMock()

    async def run():
        with patch("routes.svc.compliance.db", fdb), \
             patch("routes.svc.compliance.append_event", AsyncMock()):
            from routes.svc.compliance import issue_ptw_request
            return await issue_ptw_request(request_id="req-1", user=_admin())

    _run(run())
    fdb.svc_ptw_requests.update_one.assert_awaited_once()
    set_doc = fdb.svc_ptw_requests.update_one.await_args.args[1]["$set"]
    assert set_doc["status"] == "issued"
    assert set_doc["valid_from"] is not None
    assert set_doc["valid_until"] is not None


def test_ptw_complete_rejects_when_not_issued():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_ptw_requests.find_one = AsyncMock(
        return_value={"id": "req-1", "status": "requested",
                      "case_id": "case-1", "organization_id": "org-1"},
    )

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import complete_ptw_request
            return await complete_ptw_request(
                request_id="req-1", user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 409


# ══════ COSHH ════════════════════════════════════════════════════


def test_coshh_register_lazy_seeds_three_defaults():
    fdb = MagicMock()
    fdb.svc_coshh_entries.count_documents = AsyncMock(return_value=0)
    fdb.svc_coshh_entries.insert_many = AsyncMock()
    fdb.svc_coshh_entries.find = MagicMock(return_value=_chain([]))

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import list_coshh_entries
            return await list_coshh_entries(user=_user())

    _run(run())
    seeded = fdb.svc_coshh_entries.insert_many.await_args.args[0]
    assert len(seeded) == 3
    assert all("hazard_class" in e for e in seeded)


def test_coshh_usage_records_picked_entries():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "case-1"})
    fdb.svc_coshh_entries.find = MagicMock(return_value=_chain([
        {"id": "e1", "name": "WD-40", "hazard_class": "flammable"},
        {"id": "e2", "name": "IPA",   "hazard_class": "flammable"},
    ]))
    fdb.svc_coshh_usage.insert_one = AsyncMock()
    append = AsyncMock()

    async def run():
        with patch("routes.svc.compliance.db", fdb), \
             patch("routes.svc.compliance.append_event", append):
            from routes.svc.compliance import record_coshh_usage, CoshhUsageIn
            return await record_coshh_usage(
                case_id="case-1",
                body=CoshhUsageIn(entry_ids=["e1", "e2"], notes=""),
                user=_user(),
            )

    out = _run(run())
    assert len(out["entries"]) == 2
    assert {e["name"] for e in out["entries"]} == {"WD-40", "IPA"}
    append.assert_awaited_once()


def test_coshh_usage_400s_on_empty_pick():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "case-1"})

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import record_coshh_usage, CoshhUsageIn
            return await record_coshh_usage(
                case_id="case-1",
                body=CoshhUsageIn(entry_ids=[]),
                user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 400


# ══════ LOTO ═════════════════════════════════════════════════════


def test_loto_get_returns_default_steps():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "case-1"})
    fdb.svc_loto_checklists.find = MagicMock(return_value=_chain([]))

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import get_loto_for_case
            return await get_loto_for_case(case_id="case-1", user=_user())

    out = _run(run())
    assert len(out["steps"]) >= 5
    assert any(s["id"] == "lockout" for s in out["steps"])
    assert any(s["id"] == "verify" for s in out["steps"])


def test_loto_submit_rejects_when_required_steps_missing():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "case-1"})

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import submit_loto_checklist, LotoIn
            # Only tick a few — required ones (notify/shutdown/isolate/...) missing.
            return await submit_loto_checklist(
                case_id="case-1",
                body=LotoIn(ticked_step_ids=["notify"]),
                user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 400


def test_loto_submit_happy_path_persists_and_events():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={"id": "case-1"})
    fdb.svc_loto_checklists.insert_one = AsyncMock()
    append = AsyncMock()

    async def run():
        with patch("routes.svc.compliance.db", fdb), \
             patch("routes.svc.compliance.append_event", append):
            from routes.svc.compliance import (
                submit_loto_checklist, LotoIn, DEFAULT_LOTO_STEPS,
            )
            ticked = [s["id"] for s in DEFAULT_LOTO_STEPS if s["required"]]
            return await submit_loto_checklist(
                case_id="case-1",
                body=LotoIn(
                    ticked_step_ids=ticked,
                    energy_sources=["mains 240V"],
                ),
                user=_user(),
            )

    out = _run(run())
    assert out["case_id"] == "case-1"
    assert "mains 240V" in out["energy_sources"]
    append.assert_awaited_once()


# ══════ Summary endpoint ═════════════════════════════════════════


def test_compliance_summary_composes_three_sections():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(
        return_value={"id": "case-1", "ptw_required": True},
    )
    fdb.svc_ptw_requests.find = MagicMock(return_value=_chain([
        {"status": "issued", "id": "p1", "template_name": "Hot Work"},
    ]))
    fdb.svc_loto_checklists.count_documents = AsyncMock(return_value=0)
    fdb.svc_coshh_usage.count_documents    = AsyncMock(return_value=2)

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import compliance_summary
            return await compliance_summary(case_id="case-1", user=_user())

    out = _run(run())
    assert out["ptw"]["active"]["id"] == "p1"
    assert out["ptw"]["needs_action"] is False  # has an issued ticket
    assert out["loto"]["needs_action"] is True
    assert out["coshh"]["recorded_count"] == 2


def test_compliance_summary_flags_ptw_needed_when_required_and_none_issued():
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(
        return_value={"id": "case-1", "ptw_required": True},
    )
    fdb.svc_ptw_requests.find = MagicMock(return_value=_chain([]))
    fdb.svc_loto_checklists.count_documents = AsyncMock(return_value=1)
    fdb.svc_coshh_usage.count_documents    = AsyncMock(return_value=0)

    async def run():
        with patch("routes.svc.compliance.db", fdb):
            from routes.svc.compliance import compliance_summary
            return await compliance_summary(case_id="case-1", user=_user())

    out = _run(run())
    assert out["ptw"]["needs_action"] is True
    assert out["loto"]["needs_action"] is False


# ══════ Frontend wiring ══════════════════════════════════════════


def test_frontend_compliance_card_mounted_on_jobatagance():
    src = Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js"
    ).read_text()
    assert "import ComplianceCard" in src
    assert "<ComplianceCard" in src


def test_frontend_compliance_card_renders_three_dialogs():
    src = Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/ComplianceCard.js"
    ).read_text()
    for tid in (
        "compliance-card", "compliance-toggle",
        "compliance-ptw-open", "compliance-loto-open", "compliance-coshh-open",
        "ptw-template-select", "ptw-request-submit",
        "loto-steps", "loto-submit",
        "coshh-list", "coshh-submit",
    ):
        assert f'data-testid="{tid}"' in src, f"missing test-id: {tid}"
    # Hits all three endpoints.
    assert "/svc/engineer/jobs/${caseId}/compliance-summary" in src
    assert "/svc/engineer/jobs/${caseId}/ptw-requests" in src
    assert "/svc/engineer/jobs/${caseId}/loto" in src
    assert "/svc/engineer/jobs/${caseId}/coshh-used" in src
