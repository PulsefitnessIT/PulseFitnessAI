# New wide Pulse logo: service report PDF header, fire-station certificate banner, frontend asset.
import io
import os
import pytest
import requests
import fitz  # PyMuPDF

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
BYPASS = {"X-RateLimit-Bypass": "test-bypass-secret-for-ci-runs-only"}
WIDE = "/app/backend/assets/pulse-logo-wide.jpg"
LIGHT = "/app/backend/assets/pulse-logo-wide-light.png"


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


def _page1_images(pdf):
    doc = fitz.open(stream=pdf, filetype="pdf")
    out = []
    for img in doc[0].get_images(full=True):
        xref = img[0]
        rects = doc[0].get_image_rects(xref)
        out.append({"w": img[2], "h": img[3], "rects": rects})
    return doc, out


# Asset files
class TestAssets:
    def test_wide_logo_files(self):
        from PIL import Image
        assert Image.open(WIDE).size == (1193, 216)
        im = Image.open(LIGHT)
        assert im.mode in ("RGBA", "LA", "P")
        w, h = im.size
        assert w > h * 3

    def test_frontend_public_asset_served(self):
        r = requests.get(f"{BASE_URL}/brand/pulse-logo-wide.jpg", timeout=30)
        assert r.status_code == 200
        assert r.content[:3] == b"\xff\xd8\xff", f"not a jpeg: {r.headers.get('content-type')}"
        assert len(r.content) == os.path.getsize(WIDE)


# pulse_header unit: uses the wide logo
class TestPulseHeaderWide:
    def test_header_uses_wide_logo(self):
        from reportlab.platypus import SimpleDocTemplate
        from reportlab.lib.pagesizes import A4
        from utils.pulse_doc_template import pulse_header, pulse_styles
        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=A4).build([pulse_header(pulse_styles())])
        doc, imgs = _page1_images(buf.getvalue())
        # Header is now the split invoice header: logo (810px) left + address block (980px) right.
        assert any(i["w"] == 810 for i in imgs) and any(i["w"] == 980 for i in imgs), imgs
        assert "Pulse Fitness" not in doc[0].get_text()


# Service report via live API
class TestServiceReportPdf:
    def _cases(self, owner):
        r = owner.get(f"{BASE_URL}/api/svc/cases?limit=50", timeout=30)
        assert r.status_code == 200
        d = r.json()
        return d if isinstance(d, list) else d.get("cases") or d.get("items") or []

    def test_completed_reports_show_wide_logo(self, owner):
        cases = self._cases(owner)
        assert cases, "no svc cases"
        closed = [c for c in cases if (c.get("status") or "").lower() in ("closed", "completed", "resolved")]
        targets = (closed or cases)[:3]
        for c in targets:
            r = owner.get(f"{BASE_URL}/api/svc/cases/{c['id']}/service-report.pdf", timeout=60)
            assert r.status_code == 200, f"{c['id']}: {r.status_code} {r.text[:200]}"
            assert r.content[:4] == b"%PDF"
            doc, imgs = _page1_images(r.content)
            assert any(i["w"] == 1800 for i in imgs), f"{c['id']} imgs={imgs}"
            top = doc[0].get_text("text", clip=fitz.Rect(0, 0, doc[0].rect.width / 2, 110))
            assert "Pulse Fitness" not in top
            open(f"/tmp/svc_wide_{c['id'][:8]}.pdf", "wb").write(r.content)


# Fire station certificates: stored PDFs rebuilt with the light wide logo
class TestFireCertificate:
    def test_stored_certs_rebranded_and_contain_logo(self):
        import asyncio, base64
        from utils.database import db

        async def q():
            certs = await db.crm2_certificates.find({}, {"_id": 0, "id": 1, "rebrand_tag": 1, "status": 1}).to_list(100)
            files = {}
            for c in certs:
                f = await db.crm2_certificate_files.find_one({"cert_id": c["id"]}, {"_id": 0, "pdf_b64": 1})
                files[c["id"]] = f
            return certs, files
        certs, files = asyncio.get_event_loop().run_until_complete(q()) if False else asyncio.run(q())
        if not certs:
            pytest.skip("no stored certificates")
        print("certs:", [(c["id"][:8], c.get("status"), c.get("rebrand_tag")) for c in certs])
        for c in certs:
            assert c.get("rebrand_tag") == "pulse-split-header-2026-06", c
            f = files[c["id"]]
            assert f and f.get("pdf_b64"), f"missing file {c['id']}"
            pdf = base64.b64decode(f["pdf_b64"])
            doc, imgs = _page1_images(pdf)
            # split header (logo 810px + address 980px) + invoice footer (1800px)
            assert {810, 980, 1800} <= {i["w"] for i in imgs}, f"{c['id']} imgs={[(i['w'], i['h']) for i in imgs]}"
            open(f"/tmp/cert_{c['id'][:8]}.pdf", "wb").write(pdf)
