"""Seed a couple of ready-made Pulse Fitness house .docx tender templates into
an org's CRM template library so the Submission Pack Wizard is instantly
demoable.

The exporter keeps a template's STYLES + page setup + HEADERS/FOOTERS (the body
is regenerated from the tender), and find/replaces {{TOKENS}} in the header/
footer + generated content. So the tokens ({{CLIENT}}, {{REFERENCE}}, {{SCOPE}},
{{DATE}}) live in the header/footer where they will actually be substituted.

Idempotent: rows tagged seed_house=True for the org are removed and re-created.

Run:  cd /app/backend && PYTHONPATH=/app/backend python scripts/seed_tender_house_templates.py
Env:  ORG_ID (default iso-demo-org)
"""
import asyncio
import base64
import io
import os
import uuid
from datetime import datetime, timezone

from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from motor.motor_asyncio import AsyncIOMotorClient

from utils.tender_docx_exporter import detect_template_styles

BRAND_INK = RGBColor(0x0B, 0x2A, 0x4A)   # deep navy
BRAND_ACCENT = RGBColor(0x00, 0x74, 0xD9)  # pulse blue


def _style_house(doc, accent):
    styles = doc.styles
    for nm, sz, col in [
        ("Title", 26, BRAND_INK), ("Heading 1", 18, BRAND_INK),
        ("Heading 2", 14, accent), ("Heading 3", 12, BRAND_INK),
    ]:
        try:
            st = styles[nm]
            st.font.name = "Arial"
            st.font.size = Pt(sz)
            st.font.color.rgb = col
        except Exception:
            pass
    try:
        nrm = styles["Normal"]
        nrm.font.name = "Arial"
        nrm.font.size = Pt(11)
    except Exception:
        pass


def _set_header_footer(doc, header_text, footer_text):
    sec = doc.sections[0]
    hp = sec.header.paragraphs[0]
    hp.text = ""
    hr = hp.add_run(header_text)
    hr.font.name = "Arial"; hr.font.size = Pt(9); hr.bold = True
    hr.font.color.rgb = BRAND_INK
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT

    fp = sec.footer.paragraphs[0]
    fp.text = ""
    fr = fp.add_run(footer_text)
    fr.font.name = "Arial"; fr.font.size = Pt(8)
    fr.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _build_template(title, header_text, footer_text, accent, intro):
    doc = Document()
    _style_house(doc, accent)
    _set_header_footer(doc, header_text, footer_text)
    # Body is illustrative only (regenerated on export) — but makes the raw
    # .docx readable if someone opens it directly.
    t = doc.add_paragraph(style="Title")
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.add_run("{{CLIENT}} — Tender Response")
    m = doc.add_paragraph(); m.alignment = WD_ALIGN_PARAGRAPH.CENTER
    m.add_run("Reference {{REFERENCE}} · {{SCOPE}} · {{DATE}}").font.color.rgb = accent
    doc.add_paragraph()
    doc.add_paragraph(intro)
    for h in ["1. Executive Summary", "2. Service Delivery", "3. Social Value",
              "4. Health, Safety & Quality", "5. Mobilisation & Programme"]:
        doc.add_paragraph(h, style="Heading 2")
        doc.add_paragraph("[Response inserted automatically from the tender's answered questions.]")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


HOUSE_TEMPLATES = [
    {
        "label": "Pulse Fitness — MOD Submission (House Style)",
        "filename": "pulse-mod-submission-house.docx",
        "header": "PULSE FITNESS LTD  —  OFFICIAL  —  Prepared for {{CLIENT}}",
        "footer": "Reference {{REFERENCE}}  ·  {{SCOPE}}  ·  {{DATE}}  ·  Pulse Fitness Ltd — Commercial in Confidence",
        "accent": BRAND_ACCENT,
        "intro": "Pulse Fitness is pleased to submit this response to {{CLIENT}} under reference {{REFERENCE}} for {{SCOPE}}.",
    },
    {
        "label": "Pulse Fitness — Commercial Tender (House Style)",
        "filename": "pulse-commercial-tender-house.docx",
        "header": "PULSE FITNESS LTD  —  Prepared for {{CLIENT}}",
        "footer": "Ref {{REFERENCE}}  ·  {{SCOPE}}  ·  {{DATE}}  ·  www.pulsefitness.com",
        "accent": RGBColor(0x16, 0x8A, 0x5A),
        "intro": "This proposal is prepared for {{CLIENT}} (reference {{REFERENCE}}) covering {{SCOPE}}.",
    },
]


async def main():
    org_id = os.environ.get("ORG_ID", "iso-demo-org")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    col = db.crm2_tender_docx_templates

    removed = await col.delete_many({"organization_id": org_id, "seed_house": True})
    print(f"Removed {removed.deleted_count} previous house templates for {org_id}")

    for spec in HOUSE_TEMPLATES:
        content = _build_template(
            spec["label"], spec["header"], spec["footer"], spec["accent"], spec["intro"])
        meta = detect_template_styles(content)
        tokens = [{"find": k, "replace": ""} for k in meta.get("detected_tokens", [])]
        rec = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "label": spec["label"],
            "original_filename": spec["filename"],
            "size": len(content),
            "data_b64": base64.b64encode(content).decode("utf-8"),
            "styles": meta.get("styles", []),
            "header_text": meta.get("header_text", ""),
            "tokens": tokens,
            "seed_house": True,
            "created_by": "system (house template)",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await col.insert_one(rec)
        print(f"Seeded: {spec['label']}  ({len(content)} bytes, tokens: {[t['find'] for t in tokens]})")

    total = await col.count_documents({"organization_id": org_id})
    print(f"Done. {org_id} now has {total} template(s) in the library.")


if __name__ == "__main__":
    asyncio.run(main())
