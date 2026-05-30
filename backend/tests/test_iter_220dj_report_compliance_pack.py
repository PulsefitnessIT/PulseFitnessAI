"""Iter 220dj — Compliance evidence pack auto-attached to service-report PDF.

Pins:

  * ``_gather_report_data`` now pulls per-case PTW (issued+completed),
    LOTO checklists, and COSHH usage rows + a `loto_step_labels` map.
  * ``_build_pdf`` renders a **COMPLIANCE EVIDENCE PACK** section
    with one block per kind (PTW / LOTO / COSHH) when data exists.
  * Section is omitted entirely when there is no evidence (no
    empty-shell footer noise).
  * "requested"-only PTWs are deliberately excluded — only issued
    and completed permits count as customer-visible evidence.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


def _setup_db(*, ptws=None, lotos=None, coshhs=None,
              case=None, machines=None):
    """Build a MagicMock db that wires every collection touched by
    ``_gather_report_data`` so the helper runs end-to-end."""
    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=case or {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "title": "Treadmill belt",
        "customer_name": "Acme", "customer_email": "a@x.test",
    })
    # Photos, signature, time entries, org, engineer.
    fdb.svc_engineer_photos.find = MagicMock(return_value=_chain([]))
    fdb.svc_signatures.find_one = AsyncMock(return_value=None)
    fdb.svc_time_entries.find = MagicMock(return_value=_chain([]))
    fdb.organizations.find_one = AsyncMock(return_value={"name": "Pulse"})
    fdb.svc_engineers.find_one = AsyncMock(return_value=None)
    fdb.users.find_one = AsyncMock(return_value=None)
    fdb.svc_case_safety_signoffs.find_one = AsyncMock(return_value=None)
    # Custom fields + machines.
    fdb.svc_work_report_field_defs.find = MagicMock(return_value=_chain([]))
    fdb.svc_work_visit_machines.find = MagicMock(return_value=_chain(machines or []))
    # Iter 220dj — the three compliance collections.
    fdb.svc_ptw_requests.find = MagicMock(return_value=_chain(ptws or []))
    fdb.svc_loto_checklists.find = MagicMock(return_value=_chain(lotos or []))
    fdb.svc_coshh_usage.find = MagicMock(return_value=_chain(coshhs or []))
    return fdb


# ── 1 · _gather_report_data enrichment ────────────────────────────


def test_gather_pulls_issued_and_completed_ptws_only():
    """The Mongo query filter is the contract — pin it so a future
    refactor can't widen scope to include 'requested' or 'cancelled'."""
    fdb = _setup_db()

    async def run():
        with patch("routes.svc.service_report.db", fdb):
            from routes.svc.service_report import _gather_report_data
            await _gather_report_data("case-1", {"organization_id": "org-1"})

    _run(run())
    # First positional arg to ``find`` is the filter.
    flt = fdb.svc_ptw_requests.find.call_args.args[0]
    assert flt["case_id"] == "case-1"
    assert flt["status"]["$in"] == ["issued", "completed"]


def test_gather_returns_three_compliance_buckets_plus_labels():
    fdb = _setup_db(
        ptws=[{"template_name": "Hot Work", "status": "completed",
               "hazard_category": "hot_work"}],
        lotos=[{"engineer_name": "Eng",
                "ticked_step_ids": ["notify", "verify"]}],
        coshhs=[{"engineer_name": "Eng",
                 "entries": [{"name": "WD-40", "hazard_class": "flammable"}]}],
    )

    async def run():
        with patch("routes.svc.service_report.db", fdb):
            from routes.svc.service_report import _gather_report_data
            return await _gather_report_data("case-1", {"organization_id": "org-1"})

    out = _run(run())
    assert len(out["ptw_records"]) == 1
    assert len(out["loto_records"]) == 1
    assert len(out["coshh_records"]) == 1
    # Label dict has the 7 default steps from Iter 220de.
    assert "notify" in out["loto_step_labels"]
    assert "verify" in out["loto_step_labels"]


def test_gather_empty_when_no_compliance_records():
    fdb = _setup_db()

    async def run():
        with patch("routes.svc.service_report.db", fdb):
            from routes.svc.service_report import _gather_report_data
            return await _gather_report_data("case-1", {"organization_id": "org-1"})

    out = _run(run())
    assert out["ptw_records"]   == []
    assert out["loto_records"]  == []
    assert out["coshh_records"] == []


# ── 2 · _build_pdf renders the section ────────────────────────────


def _minimal_payload(*, ptws=None, lotos=None, coshhs=None):
    return {
        "case": {
            "id": "case-1", "reference": "GA-100",
            "title": "Treadmill repair",
            "customer_name": "Acme", "site_name": "HQ",
            "site_address": "1 Street",
            "scheduled_at": "2026-05-30T09:00:00Z",
            "engineer_notes": "",
            "fault_summary": "Belt slipping",
            "fix_summary": "Replaced belt",
            "status": "closed",
            "priority": "p2",
            "customer_email": "a@x.test",
        },
        "photos": [],
        "signature": None,
        "time_entries": [],
        "org": {"name": "Pulse"},
        "engineer": None,
        "safety_signoff": None,
        "rating": None,
        "rating_comment": None,
        "custom_field_defs": [],
        "machines": [],
        "engineer_branding": {},
        "ptw_records": ptws or [],
        "loto_records": lotos or [],
        "coshh_records": coshhs or [],
        "loto_step_labels": {
            "notify": "Notify staff",
            "verify": "Zero-energy verified",
        },
    }


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract concatenated text from a ReportLab-generated PDF."""
    import io
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def test_build_pdf_renders_compliance_section_when_data_present():
    payload = _minimal_payload(
        ptws=[{
            "template_name": "Hot Work Permit",
            "hazard_category": "hot_work",
            "status": "completed",
            "valid_until": "2026-05-30T17:00:00Z",
            "issued_by_name": "Admin One",
            "completed_at": "2026-05-30T16:30:00Z",
        }],
        lotos=[{
            "engineer_name": "Eng One",
            "completed_at": "2026-05-30T10:15:00Z",
            "ticked_step_ids": ["notify", "verify"],
            "energy_sources": ["mains 240V"],
        }],
        coshhs=[{
            "engineer_name": "Eng One",
            "recorded_at": "2026-05-30T11:00:00Z",
            "entries": [
                {"name": "WD-40", "hazard_class": "flammable"},
                {"name": "IPA",   "hazard_class": "flammable"},
            ],
            "notes": "Used to clean motor housing.",
        }],
    )
    from routes.svc.service_report import _build_pdf

    pdf = _build_pdf(payload, image_bytes=[], sig_bytes=None, logo_bytes=None)
    assert pdf.startswith(b"%PDF")
    text = _pdf_text(pdf)
    assert "COMPLIANCE EVIDENCE PACK" in text
    assert "Permit to Work" in text
    assert "Hot Work Permit" in text
    assert "Lockout / Tagout" in text
    assert "COSHH usage" in text
    assert "WD-40" in text
    assert "mains 240V" in text


def test_build_pdf_omits_compliance_section_when_no_records():
    payload = _minimal_payload()
    from routes.svc.service_report import _build_pdf

    pdf = _build_pdf(payload, image_bytes=[], sig_bytes=None, logo_bytes=None)
    text = _pdf_text(pdf)
    assert "COMPLIANCE EVIDENCE PACK" not in text


def test_build_pdf_renders_with_only_loto_when_others_empty():
    payload = _minimal_payload(lotos=[{
        "engineer_name": "Eng One",
        "completed_at": "2026-05-30T10:15:00Z",
        "ticked_step_ids": ["notify"],
        "energy_sources": [],
    }])
    from routes.svc.service_report import _build_pdf

    pdf = _build_pdf(payload, image_bytes=[], sig_bytes=None, logo_bytes=None)
    text = _pdf_text(pdf)
    assert "COMPLIANCE EVIDENCE PACK" in text
    assert "Lockout / Tagout" in text
    assert "Permit to Work" not in text
    assert "COSHH usage" not in text


def test_loto_steps_labels_default_to_iter_220de_defaults():
    """Belt-and-braces: the step-label dict must come from the
    canonical DEFAULT_LOTO_STEPS so a renamed step doesn't silently
    leak the raw step id onto the PDF."""
    from routes.svc.compliance import DEFAULT_LOTO_STEPS
    ids = {s["id"] for s in DEFAULT_LOTO_STEPS}
    # Required step ids must all be present (regression guard).
    for required in ("notify", "isolate", "lockout", "verify"):
        assert required in ids
