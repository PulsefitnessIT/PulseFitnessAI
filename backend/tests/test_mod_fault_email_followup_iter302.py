"""Iter 302 — follow-up to iter301 MOD fault emails: doc.serial fallback in
header + subjects, 'N attached' photos row, steps_taken escaping, reporter
confirmation escaping, _tracked_send long wait for notified_recipients.

No real email is sent (send_email + resend.Emails.send mocked). TEST_ data
only, removed by id.
"""
import asyncio
import re
import time
import uuid
from datetime import datetime, timezone
from unittest import mock

import pytest

from tests.conftest import drive_async
import routes.mod_portal as mp
import routes.supplier_portal as sp
import routes.bfpo as bfpo
import utils.email as ue
from utils.database import db

DOC_SERIAL = "TEST_DOCSER99"


def _site(**kw):
    b = {"id": "TEST_s", "name": "TEST_Site", "address_line1": "1 Road", "city": "Town",
         "postcode": "AB1 2CD", "country": "United Kingdom"}
    b.update(kw)
    return b


def _eq(**kw):
    b = {"name": "Rower", "manufacturer": "Concept2", "model": "D2", "serial_number": ""}
    b.update(kw)
    return b


def _doc(**kw):
    b = {"mod_ticket_ref": "MOD-2026-00002", "priority": "high",
         "created_at": "2026-01-10T09:30:00+00:00", "reporter_name": "TEST Rep",
         "reporter_email": "rep@example.com", "reporter_phone": "+44 1",
         "fault_type_mod": "noise", "safe_in_service": "yes", "usable": "limited",
         "issue_description": "Loud grinding noise from the flywheel area.",
         "steps_taken": "", "attachment_urls": [], "serial_number": DOC_SERIAL}
    b.update(kw)
    return b


def _pairs(html):
    return dict(re.findall(r'<td style="padding:7px 12px 7px 0;[^"]*">(.*?)</td><td style="[^"]*">(.*?)</td>', html))


def _render(fn, site, eq, doc):
    if fn == "esc":
        return mp._escalation_email_html(site, eq, doc)
    return mp._supplier_fault_email_html(site, eq, doc, {"contact_name": "Jo"}, "https://x/case")


# Header S/N falls back to doc.serial_number
class TestDocSerialFallbackRender:
    @pytest.mark.parametrize("fn", ["esc", "sup"])
    def test_header_uses_doc_serial(self, fn):
        html = _render(fn, _site(), _eq(serial_number=""), _doc())
        assert f"Rower &middot; S/N {DOC_SERIAL}</div>" in html
        assert _pairs(html)["Serial number"] == DOC_SERIAL
        assert f"Serial number: {DOC_SERIAL}" in html

    @pytest.mark.parametrize("fn", ["esc", "sup"])
    def test_header_no_serial_anywhere(self, fn):
        html = _render(fn, _site(), _eq(serial_number=None), _doc(serial_number=None))
        assert "S/N" not in html and "None" not in html

    @pytest.mark.parametrize("fn", ["esc", "sup"])
    def test_eq_serial_preferred(self, fn):
        html = _render(fn, _site(), _eq(serial_number="EQSER1"), _doc())
        assert "Rower &middot; S/N EQSER1</div>" in html
        assert DOC_SERIAL not in html


# Photos row text
class TestPhotosRow:
    @pytest.mark.parametrize("n", [1, 3])
    def test_photos_exact(self, n):
        rows = dict(mp._fault_detail_rows(_site(), _eq(), _doc(attachment_urls=[f"p{i}.jpg" for i in range(n)] + [""])))
        photos = [v for l, v, _ in rows["Fault"] if l == "Photos"]
        assert photos == [f"{n} attached"]
        html = mp._escalation_email_html(_site(), _eq(), _doc(attachment_urls=["a.jpg"]))
        assert "shown below" not in html


# steps_taken escaping
class TestStepsEscaped:
    @pytest.mark.parametrize("fn", ["esc", "sup"])
    def test_steps_escaped_in_row(self, fn):
        steps = '<script>alert(1)</script><b>reset</b> & "unplugged"'
        html = _render(fn, _site(), _eq(), _doc(steps_taken=steps))
        assert "<script>" not in html and "<b>reset</b>" not in html
        row = _pairs(html)["Steps taken on site"]
        assert row == "&lt;script&gt;alert(1)&lt;/script&gt;&lt;b&gt;reset&lt;/b&gt; &amp; &quot;unplugged&quot;"
        assert "steps_row" not in open(mp.__file__).read()


# Reporter confirmation escaping
class TestConfirmationEscaping:
    def test_all_fields_escaped(self):
        html = mp._confirmation_email_html(
            _site(name="<b>site</b>"), _eq(name="<b>machine</b>"),
            _doc(reporter_name="<b>x</b> Smith", reporter_email="<b>e</b>@x.com",
                 reporter_phone="<b>123</b>", mod_ticket_ref="<i>REF</i>", priority="<u>p</u>"))
        for raw in ["<b>x</b>", "<b>site</b>", "<b>machine</b>", "<b>e</b>", "<b>123</b>", "<i>REF</i>", "<u>p</u>"]:
            assert raw not in html, raw
        for esc in ["&lt;b&gt;x&lt;/b&gt;", "&lt;b&gt;site&lt;/b&gt;", "&lt;b&gt;machine&lt;/b&gt;",
                    "&lt;b&gt;e&lt;/b&gt;@x.com", "&lt;b&gt;123&lt;/b&gt;", "&lt;i&gt;REF&lt;/i&gt;"]:
            assert esc in html, esc

    def test_missing_phone_renders(self):
        html = mp._confirmation_email_html(_site(), _eq(), _doc(reporter_phone=None))
        # Known: renders "... on rep@example.com or  as the engineer" (empty)
        assert "None" not in html


# Integration: submit flow (subjects with doc serial + delayed recipients write)
def _run_submit(suffix, eq_serial, mutate_doc_serial=None, supplier_case_delay=0.0, wait_after=2.0):
    from starlette.requests import Request
    site_id, eq_id, sup_id = f"TEST_site_{suffix}", f"TEST_eq_{suffix}", f"TEST_sup_{suffix}"
    sup_email = f"test_sup_{suffix}@example.com"
    sent = []

    async def fake_send_email(to, subject, html, *a, result_out=None, **kw):
        sent.append({"to": to, "subject": subject, "html": html, "kind": kw.get("kind"), "t": time.monotonic()})
        if result_out is not None:
            result_out["message_id"] = "TEST_mid"
        return True

    def resend_guard(params):
        sent.append({"resend": True})
        return {"id": "TEST_guard"}

    orig_case = sp.create_supplier_case

    async def slow_case(**kw):
        await asyncio.sleep(supplier_case_delay)
        return await orig_case(**kw)

    async def fake_bridge(doc):
        if mutate_doc_serial:
            doc["serial_number"] = mutate_doc_serial

    async def run():
        now = datetime.now(timezone.utc).isoformat()
        await db.organizations.insert_one({"id": site_id, "name": f"TEST_Site {suffix}",
                                           "account_type": "mod_site", "created_at": now})
        eqd = {"id": eq_id, "organization_id": site_id, "name": "TEST_Rower",
               "manufacturer": "Concept2", "model": "D2", "supplier_id": sup_id, "created_at": now}
        if eq_serial is not None:
            eqd["serial_number"] = eq_serial
        await db.equipment.insert_one(eqd)
        await db.suppliers.insert_one({"id": sup_id, "organization_id": site_id,
                                       "name": "TEST_Supplier", "email": sup_email})
        issue_id = None
        try:
            payload = mp.FaultSubmit(
                equipment_id=eq_id, fault_type="noise",
                description="TEST_ loud grinding noise from the flywheel area today.",
                steps_taken="<b>power</b> cycled", onset="today", usable="limited", safe_in_service="yes",
                reporter_name="TEST_Reporter", reporter_email="test_rep@example.com",
                reporter_phone="+44 7700 900000")
            req = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})
            user = {"id": f"TEST_user_{suffix}", "organization_id": site_id, "role": "owner"}
            with mock.patch.object(mp, "send_email", side_effect=fake_send_email), \
                 mock.patch.object(ue, "send_email", side_effect=fake_send_email), \
                 mock.patch.object(ue.resend.Emails, "send", side_effect=resend_guard), \
                 mock.patch.object(sp, "create_supplier_case", side_effect=slow_case), \
                 mock.patch.object(bfpo, "_bridge_mod_fault_to_bfpo", side_effect=fake_bridge):
                t0 = time.monotonic()
                res = await mp.mod_fault_submit(payload, req, user)
                t_return = time.monotonic() - t0
                issue_id = res["issue_id"]
                await asyncio.sleep(wait_after)
            issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
            return res, issue, t_return
        finally:
            if issue_id:
                await db.issues.delete_one({"id": issue_id})
                await db.supplier_cases.delete_many({"issue_id": issue_id})
                cases = await db.svc_cases.find({"mod_issue_id": issue_id}, {"_id": 0, "id": 1}).to_list(10)
                for c in cases:
                    await db.svc_case_events.delete_many({"case_id": c["id"]})
                await db.svc_cases.delete_many({"mod_issue_id": issue_id})
            await db.mod_site_staff.delete_many({"site_id": site_id})
            await db.mod_audit_log.delete_many({"site_id": site_id})
            await db.equipment.delete_one({"id": eq_id})
            await db.suppliers.delete_one({"id": sup_id})
            await db.organizations.delete_one({"id": site_id})

    res, issue, t_return = drive_async(run())
    return res, issue, sent, sup_email, t_return


class TestSubmitFlow:
    def test_subjects_use_doc_serial_when_equipment_has_none(self):
        suffix = uuid.uuid4().hex[:8]
        res, issue, sent, _, _ = _run_submit(suffix, eq_serial=None, mutate_doc_serial=DOC_SERIAL)
        pulse = [s for s in sent if s.get("kind") == "mod_fault_pulse"]
        supm = [s for s in sent if s.get("kind") == "mod_fault_supplier"]
        assert pulse and supm
        assert pulse[0]["subject"].endswith(f" — S/N {DOC_SERIAL}"), pulse[0]["subject"]
        assert supm[0]["subject"].endswith(f" — S/N {DOC_SERIAL}"), supm[0]["subject"]
        for m in (pulse[0], supm[0]):
            assert f"TEST_Rower &middot; S/N {DOC_SERIAL}" in m["html"]
            assert "&lt;b&gt;power&lt;/b&gt; cycled" in m["html"] and "<b>power</b>" not in m["html"]
        rep = [s for s in sent if s.get("kind") == "mod_fault_reporter"]
        assert rep and "<b>" not in rep[0]["html"].replace("<strong", "")
        assert not [s for s in sent if s.get("resend")]

    def test_no_serial_anywhere_no_sn_in_subjects(self):
        suffix = uuid.uuid4().hex[:8]
        res, issue, sent, _, _ = _run_submit(suffix, eq_serial=None)
        for s in sent:
            if s.get("kind") in ("mod_fault_pulse", "mod_fault_supplier"):
                assert "S/N" not in s["subject"] and "None" not in s["subject"], s["subject"]

    def test_whitespace_serial_subject_consistency(self):
        """Pulse subject doesn't .strip() the serial (supplier one does)."""
        suffix = uuid.uuid4().hex[:8]
        res, issue, sent, _, _ = _run_submit(suffix, eq_serial="   ")
        pulse = [s for s in sent if s.get("kind") == "mod_fault_pulse"][0]["subject"]
        supm = [s for s in sent if s.get("kind") == "mod_fault_supplier"][0]["subject"]
        assert "S/N" not in supm, supm
        assert "S/N" not in pulse, f"Pulse subject has blank S/N: {pulse!r}"

    def test_tracked_send_stamps_after_3s_delayed_recipients_write(self):
        suffix = uuid.uuid4().hex[:8]
        res, issue, sent, sup_email, t_return = _run_submit(
            suffix, eq_serial="EQ1", supplier_case_delay=3.0, wait_after=3.0)
        assert t_return >= 3.0  # recipients written >=3s after Pulse task spawned
        recips = {r["role"]: r for r in issue.get("notified_recipients") or []}
        assert "pulse" in recips and "supplier" in recips, recips
        for r in recips.values():
            assert r.get("delivered") is True, r
            assert r.get("message_id") == "TEST_mid", r
