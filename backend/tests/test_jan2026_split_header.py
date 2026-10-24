# Split invoice header (logo flush-left, address block flush-right) on Pulse PDFs:
# pulse_header flowable, service report API, BFPO job sheet builder, fire-station certificates (stored + download).
import asyncio
import base64
import io
import os
import pytest
import requests
import fitz  # PyMuPDF

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
BYPASS = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only"}
LOGO_PX, ADDR_PX = (810, 151), (980, 192)
A4_W = 595.2756


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw},
                      headers=BYPASS, timeout=30)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def owner():
    return _login("owner@isodemo.com", "IsoDemo123!")


def _rects(pdf):
    doc = fitz.open(stream=pdf, filetype="pdf")
    pg = doc[0]
    logo = addr = None
    for img in pg.get_images(full=True):
        size = (img[2], img[3])
        rs = pg.get_image_rects(img[0])
        if size == LOGO_PX and rs:
            logo = rs[0]
        if size == ADDR_PX and rs:
            addr = rs[0]
    return doc, logo, addr


def _assert_split(pdf, left, right, label):
    doc, logo, addr = _rects(pdf)
    assert logo is not None and addr is not None, f"{label}: split header images missing"
    assert abs(logo.x0 - left) < 1.5, f"{label}: logo x0={logo.x0} expected {left}"
    assert abs(addr.x1 - right) < 1.5, f"{label}: addr x1={addr.x1} expected {right}"
    assert logo.x1 < addr.x0 - 20, f"{label}: logo/addr overlap {logo} {addr}"
    assert logo.y0 >= 10 and addr.y0 >= 10, f"{label}: header too close to top {logo} {addr}"
    # vertical centre roughly aligned
    assert abs((logo.y0 + logo.y1) / 2 - (addr.y0 + addr.y1) / 2) < 6, f"{label}: {logo} {addr}"
    # old single-strip artwork no longer used
    assert not any(i[2] == 1800 and i[3] == 215 for i in doc[0].get_images(full=True)), f"{label}: old header art"
    return doc, logo, addr


class TestUnitHeader:
    def test_pulse_header_flowable_split(self):
        from reportlab.platypus import SimpleDocTemplate
        from reportlab.lib.pagesizes import A4
        from utils.pulse_doc_template import pulse_header, pulse_styles
        buf = io.BytesIO()
        d = SimpleDocTemplate(buf, pagesize=A4, leftMargin=50, rightMargin=50)
        d.build([pulse_header(pulse_styles())])
        doc, _, _ = _assert_split(buf.getvalue(), 56, A4_W - 56, "flowable")  # 6pt default frame padding
        assert "Pulse Fitness" not in doc[0].get_text()

    def test_draw_invoice_header_raw_canvas(self):
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from utils.pulse_doc_template import draw_invoice_header, HEADER_H
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        bottom = draw_invoice_header(c, A4[1], 51, 544)
        c.showPage(); c.save()
        assert abs(bottom - (A4[1] - 40 - HEADER_H)) < 0.1
        _assert_split(buf.getvalue(), 51, 544, "raw")

    def test_job_sheet_builder(self):
        from routes.bfpo import _build_job_sheet_pdf
        from reportlab.lib.units import mm
        pdf = _build_job_sheet_pdf({"id": "TEST_x", "reference": "TEST-1", "title": "TEST"}, [], None)
        _assert_split(pdf, 18 * mm, A4_W - 18 * mm, "job sheet")


class TestServiceReportApi:
    def test_service_report_split(self, owner):
        r = owner.get(f"{BASE_URL}/api/svc/cases?limit=50", timeout=30)
        assert r.status_code == 200
        d = r.json()
        cases = d if isinstance(d, list) else d.get("cases") or d.get("items") or []
        if not cases:
            pytest.skip("no svc cases")
        c = cases[0]
        r = owner.get(f"{BASE_URL}/api/svc/cases/{c['id']}/service-report.pdf", timeout=60)
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        doc, logo, addr = _rects(r.content)
        assert logo is not None and addr is not None
        # body text must start below the header
        hdr_bottom = max(logo.y1, addr.y1)
        blocks = [b for b in doc[0].get_text("blocks") if b[1] < hdr_bottom - 1 and b[4].strip()]
        assert not blocks, f"text overlaps header: {blocks[:3]}"
        open("/tmp/split_svc.pdf", "wb").write(r.content)


class TestCertificates:
    def _stored(self):
        from utils.database import db

        async def q():
            certs = await db.crm2_certificates.find({}, {"_id": 0}).to_list(100)
            out = []
            for c in certs:
                f = await db.crm2_certificate_files.find_one({"cert_id": c["id"]}, {"_id": 0, "pdf_b64": 1})
                out.append((c, f))
            return out
        return asyncio.run(q())

    def test_stored_certs_split_header_one_page(self):
        rows = self._stored()
        if not rows:
            pytest.skip("no stored certificates")
        for c, f in rows:
            assert c.get("rebrand_tag") == "pulse-split-header-2026-06", c.get("rebrand_tag")
            assert c.get("status") in ("sent", "awaiting_review", "approved", "draft"), c.get("status")
            pdf = base64.b64decode(f["pdf_b64"])
            doc, logo, addr = _assert_split(pdf, 42, A4_W - 42, f"cert {c['id'][:8]}")
            assert doc.page_count == 1, f"cert {c['id'][:8]} pages={doc.page_count}"
            # crest (if any) must sit below the header, not overlap the address block
            for img in doc[0].get_images(full=True):
                if (img[2], img[3]) in (LOGO_PX, ADDR_PX) or img[2] in (1, 1800):
                    continue
                for rr in doc[0].get_image_rects(img[0]):
                    assert rr.y0 >= addr.y1 - 0.5, f"crest {rr} overlaps header {addr}"
            # body text must be below the header
            hdr_bottom = max(logo.y1, addr.y1)
            tb = [b for b in doc[0].get_text("blocks") if b[1] < hdr_bottom - 1 and b[4].strip()]
            assert not tb, f"text in header zone: {tb[:3]}"
            assert "Qualified to deliver the best" not in doc[0].get_text()
            open(f"/tmp/split_cert_{c['id'][:8]}.pdf", "wb").write(pdf)

    def test_download_endpoint_matches_stored(self):
        r = requests.post(f"{BASE_URL}/api/crm/auth/login", json={"email": "owner@isodemo.com", "password": "IsoDemo123!"},
                          headers=BYPASS, timeout=30)
        if r.status_code != 200 or not r.json().get("token"):
            pytest.skip(f"crm login failed {r.status_code}")
        owner = requests.Session()
        owner.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        rows = self._stored()
        if not rows:
            pytest.skip("no stored certificates")
        c, f = rows[0]
        r = owner.get(f"{BASE_URL}/api/crm/v2/certificates/{c['id']}/download", timeout=60)
        if r.status_code in (401, 403, 404):
            pytest.skip(f"download not accessible to owner: {r.status_code} {r.text[:120]}")
        assert r.status_code == 200, r.text[:200]
        assert r.content[:4] == b"%PDF"
        _assert_split(r.content, 42, A4_W - 42, "download")

    def test_fresh_build_one_page_with_crest(self):
        # Fresh render from stored inputs (worst case: crest + all treadmills) stays 1 page.
        from utils.blue_light_certificate_pdf import build_certificate_pdf
        tm = [{"serial_number": f"TEST{i}", "asset_name": "Treadmill",
               "speed": [{"target": s, "measured": s, "result": "pass"} for s in (4, 8, 12, 16)],
               "incline": [{"target": s, "measured": s, "result": "pass"} for s in (0, 5, 10)],
               "overall": "pass"} for i in range(2)]
        pdf = build_certificate_pdf(contract={"customer_name": "TEST FRS"}, station={"name": "TEST Station"},
                                    visit={"scheduled_date": "2026-01-10"}, treadmills=tm, config={})
        doc, _, _ = _assert_split(pdf, 42, A4_W - 42, "fresh")
        assert doc.page_count == 1
        open("/tmp/split_cert_fresh.pdf", "wb").write(pdf)
