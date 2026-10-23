# Service report PDF header: Pulse logo only (no 'Pulse Fitness' wordmark); footer keeps registered office.
import io
import os
import pytest
import requests
import fitz  # PyMuPDF

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
BYPASS = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only"}


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


def _regions(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    p = doc[0]
    h = p.rect.height
    top = p.get_text("text", clip=fitz.Rect(0, 0, p.rect.width, 60))
    # header table region (logo row) ~ top 110pt
    header = p.get_text("text", clip=fitz.Rect(0, 0, p.rect.width / 2, 110))
    full = "\n".join(pg.get_text() for pg in doc)
    last = doc[-1]
    footer = last.get_text("text", clip=fitz.Rect(0, last.rect.height - 90, last.rect.width, last.rect.height))
    imgs = p.get_images(full=True)
    return top, header, footer, full, imgs


# Service report via API
class TestServiceReportHeader:
    CASE = "0bf5a90a-e9c4-454a-a1b1-912b5cebee4d"  # SVC-00026 (iso-demo-org)

    def _cases(self, owner):
        r = owner.get(f"{BASE_URL}/api/svc/cases?limit=50", timeout=30)
        assert r.status_code == 200
        d = r.json()
        return d if isinstance(d, list) else d.get("cases") or d.get("items") or []

    def test_header_logo_only_footer_kept(self, owner):
        r = owner.get(f"{BASE_URL}/api/svc/cases/{self.CASE}/service-report.pdf", timeout=60)
        if r.status_code == 404:
            cases = self._cases(owner)
            closed = [c for c in cases if (c.get("status") or "").lower() in ("closed", "completed", "resolved")]
            assert closed or cases, "no cases"
            r = owner.get(f"{BASE_URL}/api/svc/cases/{(closed or cases)[0]['id']}/service-report.pdf", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.content[:4] == b"%PDF"
        top, header, footer, full, imgs = _regions(r.content)
        open("/tmp/svc_report_hdr.pdf", "wb").write(r.content)
        assert "Pulse Fitness" not in top, f"top region has wordmark: {top!r}"
        assert "Pulse Fitness" not in header, f"header-left has wordmark: {header!r}"
        assert len(imgs) >= 1, "logo image missing from page 1"
        assert "Pulse Fitness Limited" in footer or "Pulse Fitness Limited" in full
        assert "Registered Office" in full
        assert "Service Report" in full

    def test_closed_case_report(self, owner):
        cases = self._cases(owner)
        closed = [c for c in cases if (c.get("status") or "").lower() == "closed"]
        if not closed:
            pytest.skip("no closed case")
        r = owner.get(f"{BASE_URL}/api/svc/cases/{closed[0]['id']}/service-report.pdf", timeout=60)
        assert r.status_code == 200, r.text[:300]
        top, header, footer, full, imgs = _regions(r.content)
        assert "Pulse Fitness" not in header
        assert "Pulse Fitness Limited" in full


# Other pulse_header-based PDFs still build (unit level)
class TestPulseHeaderUnit:
    def _build(self, flow):
        from reportlab.platypus import SimpleDocTemplate
        from reportlab.lib.pagesizes import A4
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=A4).build(flow)
        return buf.getvalue()

    def test_default_header_no_wordmark(self):
        from utils.pulse_doc_template import pulse_header, pulse_styles
        pdf = self._build([pulse_header(pulse_styles())])
        doc = fitz.open(stream=pdf, filetype="pdf")
        t = doc[0].get_text()
        assert "Pulse Fitness" not in t
        assert len(doc[0].get_images()) >= 1

    def test_tenant_branded_keeps_name(self):
        from utils.pulse_doc_template import pulse_header, pulse_styles
        pdf = self._build([pulse_header(pulse_styles(), {"name": "TEST_Acme Gyms", "use_default_logo": False})])
        assert "TEST_Acme Gyms" in fitz.open(stream=pdf, filetype="pdf")[0].get_text()

    def test_warranty_and_quote_generators_import(self):
        import utils.warranty_certificate_pdf  # noqa
        import utils.crm_quote_pdf  # noqa
        import utils.engineer_invoice_pdf  # noqa
        import utils.calibration_certificate_pdf  # noqa
