"""Iter 220z — Legacy report: machine photos (max 3), comments, dual sign-off.

Builder-level guards (no network): the PDF embeds machine photos, the comments
section, and engineer + customer signatures.
"""
import base64
import io

from PIL import Image, ImageDraw

from routes.svc.legacy_reports import SaveReport
from utils.legacy_report_pdf import build_legacy_pdf


def _jpeg_bytes(color=(20, 90, 200)):
    img = Image.new("RGB", (400, 300), color)
    ImageDraw.Draw(img).rectangle([20, 20, 380, 280], outline=(255, 255, 255), width=6)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _sig_data_url():
    img = Image.new("RGBA", (400, 120), (255, 255, 255, 0))
    ImageDraw.Draw(img).line([(20, 90), (120, 30), (240, 90)], fill=(15, 23, 42, 255), width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _base_report(machines):
    return {
        "title": "Service report — Test Gym",
        "customer": {"name": "Test Gym", "site_name": "Main", "contact_name": "Sam"},
        "visits": [{"service_date": "2026-05-01", "job_number": "J1", "summary": "QS",
                    "machines": machines}],
    }


def test_pdf_builds_without_extras():
    report = _base_report([{"name": "Treadmill", "work_done": "Serviced", "photos": []}])
    pdf = build_legacy_pdf(report, {"company_name": "Eng"}, None)
    assert pdf[:5] == b"%PDF-"


def test_pdf_embeds_photos_comments_signatures():
    report = _base_report([{
        "name": "Treadmill", "work_done": "Serviced",
        "photos": [{"_bytes": _jpeg_bytes()}, {"_bytes": _jpeg_bytes((200, 60, 60))}],
    }])
    report["comments"] = "Recommend rower seat replacement next visit."
    report["signatures"] = {
        "engineer": {"name": "Eng One", "data_url": _sig_data_url(), "signed_date": "2026-06-03"},
        "customer": {"name": "Sam Client", "data_url": _sig_data_url(), "signed_date": "2026-06-03"},
    }
    pdf = build_legacy_pdf(report, {"company_name": "Eng"}, None)
    assert pdf[:5] == b"%PDF-"
    # With 2 photos + 2 signatures embedded, the PDF is materially larger.
    baseline = build_legacy_pdf(_base_report([{"name": "Treadmill", "photos": []}]), {"company_name": "Eng"}, None)
    assert len(pdf) > len(baseline) + 5000


def test_save_report_model_accepts_extras_and_validates():
    payload = SaveReport(**{
        "customer": {"name": "G"},
        "visits": [{"machines": [{
            "name": "M1",
            "photos": [{"storage_path": "p/1.jpg"}, {"storage_path": "p/2.jpg"}],
        }]}],
        "comments": "notes",
        "signatures": {"engineer": {"name": "E", "signed_date": "2026-06-03"}},
    })
    assert payload.visits[0].machines[0].photos[1].storage_path == "p/2.jpg"
    assert payload.signatures.engineer.name == "E"
    assert payload.signatures.customer is None
