"""Iter 301 — MOD fault emails (Pulse desk + supplier): rich details, serial,
site address in point-of-contact, safe->usable rule, Sicon summary, escaping,
header initial-chip removal, MOD .ai sanitising and _tracked_send stamping.

NO real email is ever sent: resend.Emails.send and routes.mod_portal.send_email
are mocked in-process. All seeded data is TEST_ prefixed and removed by id.
"""
import asyncio
import re
import uuid
from datetime import datetime, timezone
from unittest import mock

import pytest

from tests.conftest import drive_async
import routes.mod_portal as mp
import utils.email as ue
from utils.database import db


SERIAL = "PF12345XYZ"


def _site(**kw):
    base = {
        "id": "TEST_site_render", "name": "TEST_Gibraltar Gym",
        "address_line1": "1 Queensway", "address_line2": "Block B",
        "city": "Gibraltar", "postcode": "GX11 1AA", "country": "Gibraltar",
        "bfpo_number": "52", "classification": "OFFICIAL-SENSITIVE",
    }
    base.update(kw)
    return base


def _eq(**kw):
    base = {"name": "Rower", "manufacturer": "Concept2", "model": "D2",
            "serial_number": SERIAL, "equipment_type": "Cardio",
            "location": "Main hall"}
    base.update(kw)
    return base


def _doc(**kw):
    base = {
        "mod_ticket_ref": "MOD-2026-00001", "priority": "urgent",
        "created_at": "2026-01-10T09:30:00+00:00",
        "reporter_name": "Sgt TEST Smith", "reporter_email": "test.smith@example.test",
        "reporter_phone": "+350 200 12345", "fault_type_mod": "not_working",
        "safe_in_service": "no", "usable": "yes",
        "issue_description": "Flywheel grinding loudly and the seat is stuck.",
        "steps_taken": "Power cycled the monitor.",
        "attachment_urls": [],
    }
    base.update(kw)
    return base


def _pairs(html):
    """Return list of (label, value) from the details table rows."""
    rows = re.findall(r'<td style="padding:7px 12px 7px 0;[^"]*">(.*?)</td><td style="[^"]*">(.*?)</td>', html)
    return rows


def _poc_block(html):
    m = re.search(r'Point of contact</div>(.*?)</div>\s*</div>', html, re.S)
    i = html.index("Point of contact")
    j = html.index('<table role="presentation" style="width:100%;color:#1B1D1D', i)
    return html[i:j]


# ── Rendering: Point of contact ─────────────────────────────────────────
class TestPointOfContact:
    @pytest.mark.parametrize("fn", ["esc", "sup"])
    def test_structured_address_and_reporter(self, fn):
        html = (mp._escalation_email_html(_site(), _eq(), _doc()) if fn == "esc"
                else mp._supplier_fault_email_html(_site(), _eq(), _doc(), {"contact_name": "Jo"}, "https://x/case"))
        poc = _poc_block(html)
        for s in ["Sgt TEST Smith", "test.smith@example.test", "+350 200 12345",
                  "TEST_Gibraltar Gym", "1 Queensway", "Block B", "Gibraltar",
                  "GX11 1AA", "BFPO 52"]:
            assert s in poc, f"{s} missing from Point of contact ({fn})"

    def test_legacy_comma_address_fallback(self):
        site = {"id": "x", "name": "TEST_Legacy", "address": "Old Barracks, Aldershot, GU11 2AA"}
        assert mp._site_address_lines(site) == ["Old Barracks", "Aldershot", "GU11 2AA"]
        # Country-only structured + legacy address -> legacy used
        site2 = dict(site, country="United Kingdom")
        assert mp._site_address_lines(site2) == ["Old Barracks", "Aldershot", "GU11 2AA"]
        poc = _poc_block(mp._escalation_email_html(site, _eq(), _doc()))
        assert "Old Barracks<br>Aldershot<br>GU11 2AA" in poc


# ── Rendering: sectioned rows ───────────────────────────────────────────
class TestDetailRows:
    def test_sections_and_row_order(self):
        rows = mp._fault_detail_rows(_site(), _eq(), _doc(attachment_urls=["a.jpg", "b.jpg"]))
        titles = [t for t, _ in rows]
        assert titles == ["Job", "Site", "Machine", "Fault"]
        labels = {t: [r[0] for r in rs] for t, rs in rows}
        assert labels["Job"] == ["Job reference", "Priority", "Logged", "Logged by"]
        assert labels["Site"] == ["Site", "Site address"]
        assert labels["Machine"][:4] == ["Machine", "Make", "Model", "Serial number"]
        assert "Type" in labels["Machine"] and "Location on site" in labels["Machine"]
        assert labels["Fault"][:4] == ["Fault", "Safe to use?", "Usable?", "Description"]
        assert "Steps taken on site" in labels["Fault"]
        assert "Photos" in labels["Fault"]

    def test_optional_rows_absent_when_missing(self):
        rows = dict(mp._fault_detail_rows(_site(), _eq(location="", equipment_type=""),
                                          _doc(steps_taken="", attachment_urls=[])))
        assert "Location on site" not in [r[0] for r in rows["Machine"]]
        assert "Type" not in [r[0] for r in rows["Machine"]]
        assert [r[0] for r in rows["Fault"]] == ["Fault", "Safe to use?", "Usable?", "Description"]

    def test_one_item_per_row_html(self):
        html = mp._escalation_email_html(_site(), _eq(), _doc())
        pairs = dict(_pairs(html))
        assert pairs["Fault"] and pairs["Safe to use?"] == "No"
        assert "Flywheel grinding" in pairs["Description"]
        assert pairs["Serial number"] == SERIAL
        assert pairs["Make"] == "Concept2" and pairs["Model"] == "D2"


# ── Serial number everywhere + no empty brackets ───────────────────────
class TestSerial:
    @pytest.mark.parametrize("fn", ["esc", "sup"])
    def test_serial_header_line_and_table(self, fn):
        html = (mp._escalation_email_html(_site(), _eq(), _doc()) if fn == "esc"
                else mp._supplier_fault_email_html(_site(), _eq(), _doc(), {"name": "S"}))
        assert f"Rower &middot; S/N {SERIAL}" in html
        assert "()" not in html
        assert f"Serial number: {SERIAL}" in html  # sicon summary

    def test_no_serial_no_empty_brackets(self):
        html = mp._escalation_email_html(_site(), _eq(serial_number=""), _doc())
        assert "S/N" not in html and "()" not in html
        assert dict(_pairs(html))["Serial number"] == "Not on file"

    def test_model_equal_to_serial_prefix_hidden(self):
        html = mp._escalation_email_html(_site(), _eq(model="PF123"), _doc())
        assert dict(_pairs(html))["Model"] == "Not on file"


# ── Safe/usable rule ────────────────────────────────────────────────────
class TestSafeUsable:
    def test_not_safe_means_not_usable(self):
        html = mp._escalation_email_html(_site(), _eq(), _doc(safe_in_service="no", usable="yes"))
        assert dict(_pairs(html))["Usable?"] == "No — not safe to use (taken out of service)"

    def test_safe_usable_passthrough(self):
        html = mp._escalation_email_html(_site(), _eq(), _doc(safe_in_service="yes", usable="limited"))
        p = dict(_pairs(html))
        assert p["Safe to use?"] == "Yes"
        assert p["Usable?"] == "Limited"


# ── Sicon summary + escaping ────────────────────────────────────────────
class TestSiconAndEscaping:
    def test_sicon_summary(self):
        html = mp._supplier_fault_email_html(_site(), _eq(), _doc(), {"name": "S"})
        assert "Case summary (copy into Sicon)" in html
        block = html[html.index("Case summary (copy into Sicon)"):]
        for line in ["Job reference: MOD-2026-00001", "Priority: URGENT", "Site: TEST_Gibraltar Gym",
                     "Site address: 1 Queensway, Block B, Gibraltar, GX11 1AA, Gibraltar, BFPO 52",
                     "Machine: Rower", "Make: Concept2", "Model: D2", f"Serial number: {SERIAL}",
                     "Fault: ", "Safe to use?: No", "Usable?: No — not safe to use",
                     "Description: Flywheel", "Contact name: Sgt TEST Smith",
                     "Contact email: test.smith@example.test", "Contact phone: +350 200 12345"]:
            assert line in block, f"missing '{line}'"

    def test_html_escaped(self):
        bad = "<script>x</script> description long enough"
        html = mp._escalation_email_html(_site(name="<b>S</b>"), _eq(name="<i>R</i>"),
                                         _doc(issue_description=bad, reporter_name="<img src=x>"))
        assert "<script>" not in html and "<img src=x>" not in html and "<i>R</i>" not in html
        assert "&lt;script&gt;x&lt;/script&gt;" in html
        sup = mp._supplier_fault_email_html(_site(), _eq(), _doc(issue_description=bad), {"contact_name": "<u>J</u>"})
        assert "<script>" not in sup and "<u>J</u>" not in sup


# ── utils.email header + MOD sanitising ────────────────────────────────
class TestEmailShell:
    def test_header_no_initial_chip(self):
        h = ue._header_html({"gym_logo": "", "gym_name": "TEST_Bravo Site"})
        assert "TEST_Bravo Site" in h
        assert "38px" not in h
        assert ">B<" not in h

    def test_mod_send_has_no_ai_strings(self):
        org_id = f"TEST_modorg_{uuid.uuid4().hex[:8]}"
        captured = []

        def fake_send(params):
            captured.append(params)
            return {"id": "TEST_resend_id"}

        async def run():
            await db.organizations.insert_one({"id": org_id, "name": "TEST_MOD Site",
                                               "account_type": "mod_site"})
            try:
                with mock.patch.object(ue, "RESEND_API_KEY", "re_test"), \
                     mock.patch.object(ue, "SENDER_EMAIL", "Pulse <noreply@pulsefitness.ai>"), \
                     mock.patch.object(ue.resend.Emails, "send", side_effect=fake_send):
                    out = {}
                    html = mp._escalation_email_html({"id": org_id, "name": "TEST_MOD Site"}, _eq(), _doc())
                    html += '<p>see https://www.pulsefitness.ai/x or support@pulsefitness.ai — Pulse Fitness AI</p>'
                    ok = await ue.send_email("test.dest@example.test", "TEST subj Pulse Fitness AI", html,
                                             organization_id=org_id, category="mod", kind="mod_fault_pulse",
                                             result_out=out)
                    return ok, out
            finally:
                await db.organizations.delete_one({"id": org_id})
                await db.email_send_events.delete_many({"to": "test.dest@example.test"})

        ok, out = drive_async(run())
        assert ok is True and out.get("message_id") == "TEST_resend_id"
        assert len(captured) == 1
        p = captured[0]
        blob = p["html"] + p["subject"] + p["from"] + str(p.get("reply_to"))
        assert "pulsefitness.ai" not in blob.lower()
        assert "Pulse Fitness AI" not in blob
        assert "38px" not in p["html"]


# ── Integration: MOD fault create endpoint (in-process) ─────────────────
class TestFaultCreateTracked:
    def test_create_stamps_delivery_and_usable(self):
        from starlette.requests import Request
        suffix = uuid.uuid4().hex[:8]
        site_id = f"TEST_site_{suffix}"
        eq_id = f"TEST_eq_{suffix}"
        sup_id = f"TEST_sup_{suffix}"
        sup_email = f"test_sup_{suffix}@example.test"
        sent = []

        async def fake_send_email(to, subject, html, *a, result_out=None, **kw):
            sent.append({"to": to, "subject": subject, "html": html, "kw": kw})
            if result_out is not None:
                result_out["message_id"] = "TEST_mid"
            return True

        def resend_guard(params):  # any other path must not hit the real provider
            sent.append({"to": params.get("to"), "subject": params.get("subject"), "resend": True})
            return {"id": "TEST_guard"}

        async def run():
            now = datetime.now(timezone.utc).isoformat()
            await db.organizations.insert_one({
                "id": site_id, "name": f"TEST_Site {suffix}", "account_type": "mod_site",
                "address_line1": "1 Test Road", "city": "Testville", "postcode": "TE1 1ST",
                "country": "United Kingdom", "created_at": now})
            await db.equipment.insert_one({
                "id": eq_id, "organization_id": site_id, "name": "TEST_Rower",
                "manufacturer": "Concept2", "model": "D2", "serial_number": SERIAL,
                "supplier_id": sup_id, "created_at": now})
            await db.suppliers.insert_one({"id": sup_id, "organization_id": site_id,
                                           "name": "TEST_Supplier", "email": sup_email})
            issue_id = None
            try:
                payload = mp.FaultSubmit(
                    equipment_id=eq_id, fault_type="not_working",
                    description="TEST_ flywheel grinding loudly, seat is stuck in place.",
                    onset="today", usable="yes", safe_in_service="no",
                    reporter_name="TEST_Reporter", reporter_email="test_rep@example.com",
                    reporter_phone="+44 7700 900000")
                req = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})
                user = {"id": f"TEST_user_{suffix}", "organization_id": site_id, "role": "owner"}
                with mock.patch.object(mp, "send_email", side_effect=fake_send_email), \
                     mock.patch.object(ue, "send_email", side_effect=fake_send_email), \
                     mock.patch.object(ue.resend.Emails, "send", side_effect=resend_guard):
                    res = await mp.mod_fault_submit(payload, req, user)
                    issue_id = res["issue_id"]
                    await asyncio.sleep(3)
                issue = await db.issues.find_one({"id": issue_id}, {"_id": 0})
                return res, issue
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

        res, issue = drive_async(run())
        assert res["priority"] == "urgent"
        assert issue["usable"] == "no", "safe_in_service=no must store usable=no"
        recips = issue.get("notified_recipients") or []
        roles = {r["role"]: r for r in recips}
        assert "pulse" in roles and "supplier" in roles, recips
        for r in recips:
            assert r.get("delivered") is True, r
            assert r.get("message_id") == "TEST_mid", r
        assert roles["supplier"]["email"] == sup_email
        # Subjects
        pulse = [s for s in sent if s.get("kw", {}).get("kind") == "mod_fault_pulse"]
        supm = [s for s in sent if s.get("kw", {}).get("kind") == "mod_fault_supplier"]
        assert pulse and supm
        assert re.fullmatch(rf"\[MOD URGENT\] {res['ticket_ref']} — TEST_Site \w+ — TEST_Rower — S/N {SERIAL}", pulse[0]["subject"]), pulse[0]["subject"]
        assert re.fullmatch(rf"\[Fault Log\] {res['ticket_ref']} — TEST_Site \w+ — TEST_Rower — S/N {SERIAL}", supm[0]["subject"]), supm[0]["subject"]
        assert "No — not safe to use (taken out of service)" in pulse[0]["html"]
        assert "1 Test Road" in pulse[0]["html"] and "Case summary (copy into Sicon)" in supm[0]["html"]
        assert not [s for s in sent if s.get("resend")], "a real-provider path was hit"
