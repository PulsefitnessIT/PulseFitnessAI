"""Generate the one-page Pulse Fitness x Sicon meeting checklist as PDF + DOCX."""
import os

from docx import Document
from docx.shared import Pt, RGBColor

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, ListFlowable, ListItem)

BRAND = RGBColor(0x06, 0x84, 0xC7)
BRAND_HEX = colors.HexColor("#0684C7")
OUT_DIR = "/app/docs"
os.makedirs(OUT_DIR, exist_ok=True)

# kinds: title / meta / h1 / p / table / check (checkbox bullets)
BLOCKS = [
    ("title", "Pulse Fitness AI x Sicon - Meeting Checklist"),
    ("meta", [
        "Date: June 2026   |   Prepared by: Pulse Fitness AI (pulsefitness.ai)",
        "Purpose: confirm the open technical + data questions to complete an automated, scalable "
        "migration (approx. 5,000 customers / 300,000 equipment).",
    ]),

    ("h1", "Status at a glance"),
    ("table", [
        ["Domain", "Read/List API today?", "Status"],
        ["Customers / contacts", "Yes (Sage Core + Sicon CRM, paged, delta)", "Ready to automate"],
        ["Service cases / appts / notes", "Yes (live, push + poll)", "Built"],
        ["Contracts", "Push-only (no GET)", "Interim CSV - needs read API"],
        ["Equipment (300k)", "No list endpoint", "BLOCKED - primary ask"],
    ]),
    ("p", "Specs re-verified June 2026 - all 5 unchanged (Service R260200c, CRM R221200c, Contracts "
          "R260200c, CoreWebAPI R260200c, Projects R260200c). Auth: HTTP Basic over TLS + companyId per call."),

    ("h1", "A. Routing / API-shape (from our client integration)"),
    ("check", [
        "A1 - Appointment routes. Our client targets /~/api/v2/TEntity/api/Service/Appointments "
        "(create/get/update) and /~/api/v2/TEntity/{id} (delete). Confirm this /~/api/v2/TEntity/ prefix is "
        "the real production route (and that ~ resolves to the WebAPI site root).",
        "A2 - Appointments by case. No case-scoped appointment list exists in the spec. How should we poll "
        "all appointments for a given SiSMCaseID?",
        "A3 - Priorities lookup. The Service spec exposes no priorities endpoint. Is a priorities list "
        "available anywhere, or do we hard-map PriorityID via config only?",
    ]),

    ("h1", "B. Equipment - highest priority (300k assets)"),
    ("check", [
        "B1 - List/search API. Any endpoint to list/search the installed Equipment / Service Asset register "
        "per company - ideally paged with a 'changed since' filter for delta sync?",
        "B2 - Generic reader. If not dedicated, can Equipment be read via GET /~/api/v2/TEntity? If so, what "
        "is the entity type/identifier for Equipment and which fields are returned?",
        "B3 - Export fallback. If no API exists, a one-time SQL/CSV export per company with: "
        "SiconEquipmentID, serial, make/model/type, install date, warranty/contract cover, linked customer "
        "(SLCustomerAccountID), site/sub-location. Our importer is ready.",
    ]),

    ("h1", "C. Contracts"),
    ("check", [
        "C1 - Read endpoint. Is a GET/list endpoint for Service Contracts + contract lines available or "
        "planned (migrate existing contracts + read state back)? If not, a CSV/DB export?",
        "C2 - Coverage linkage. How is the link between an equipment asset, its site/sub-location, and its "
        "covering contract exposed for reading?",
    ]),

    ("h1", "D. Operational"),
    ("check", [
        "D1 - Limits. Recommended rate limits / page sizes for bulk reads at scale (5k customers / 300k assets)?",
        "D2 - Change feed. Any webhooks / change notifications, or is scheduled polling "
        "(AmendedAfterDate / updated-since) the expected pattern?",
        "D3 - Endpoints. Confirm the production base URL pattern per customer instance and any IP "
        "allow-listing needs.",
    ]),

    ("h1", "Our asks / next steps"),
    ("check", [
        "Unblock Equipment (B1-B3) - the largest domain and main migration blocker.",
        "Confirm contract read path (C1) so we can drop the CSV interim.",
        "Confirm routing (A1-A3) so our built integration validates against a live instance.",
        "On receipt of Base URL + WebAPI username/password + companyId, we run a live connection test (Ping) same day.",
    ]),
]


def build_docx(path):
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10.5)
    for kind, payload in BLOCKS:
        if kind == "title":
            p = doc.add_paragraph(); r = p.add_run(payload)
            r.bold = True; r.font.size = Pt(19); r.font.color.rgb = BRAND
        elif kind == "meta":
            for line in payload:
                p = doc.add_paragraph(); r = p.add_run(line)
                r.font.size = Pt(9.5); r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            doc.add_paragraph()
        elif kind == "h1":
            p = doc.add_paragraph(); r = p.add_run(payload)
            r.bold = True; r.font.size = Pt(13); r.font.color.rgb = BRAND
        elif kind == "p":
            doc.add_paragraph(payload)
        elif kind == "check":
            for item in payload:
                doc.add_paragraph(item, style="List Bullet")
        elif kind == "table":
            rows = payload
            t = doc.add_table(rows=len(rows), cols=len(rows[0])); t.style = "Light Grid Accent 1"
            for ri, row in enumerate(rows):
                for ci, cell in enumerate(row):
                    c = t.cell(ri, ci); c.text = str(cell)
                    for par in c.paragraphs:
                        for run in par.runs:
                            run.font.size = Pt(8.5)
                            if ri == 0:
                                run.bold = True
            doc.add_paragraph()
    doc.save(path)


def build_pdf(path):
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=ss["Heading1"], textColor=BRAND_HEX, fontSize=11, spaceBefore=6, spaceAfter=2)
    body = ParagraphStyle("Body", parent=ss["BodyText"], fontSize=8.2, leading=10.5)
    titlest = ParagraphStyle("T", parent=ss["Title"], textColor=BRAND_HEX, fontSize=17, spaceAfter=1)
    meta = ParagraphStyle("M", parent=ss["BodyText"], fontSize=8, textColor=colors.HexColor("#555555"), leading=10)
    chk = ParagraphStyle("Chk", parent=body, fontSize=7.9, leading=10)
    flow = []
    for kind, payload in BLOCKS:
        if kind == "title":
            flow.append(Paragraph(payload, titlest)); flow.append(Spacer(1, 2))
        elif kind == "meta":
            for line in payload:
                flow.append(Paragraph(line, meta))
            flow.append(Spacer(1, 4))
        elif kind == "h1":
            flow.append(Paragraph(payload, h1))
        elif kind == "p":
            flow.append(Paragraph(payload, body)); flow.append(Spacer(1, 2))
        elif kind == "check":
            items = [ListItem(Paragraph(it, chk), leftIndent=8, value="\u2610") for it in payload]
            flow.append(ListFlowable(items, bulletType="bullet", start="\u2610", bulletFontSize=9))
            flow.append(Spacer(1, 2))
        elif kind == "table":
            rows = payload
            data = [[Paragraph(str(c), ParagraphStyle("c", parent=body, fontSize=7.6, leading=9.5,
                     textColor=colors.white if ri == 0 else colors.black))
                     for c in row] for ri, row in enumerate(rows)]
            ncols = len(rows[0]); avail = A4[0] - 30 * mm
            tbl = Table(data, colWidths=[avail * w for w in (0.30, 0.42, 0.28)], repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_HEX),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f8fc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            flow.append(tbl); flow.append(Spacer(1, 4))
    SimpleDocTemplate(path, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                      topMargin=10 * mm, bottomMargin=10 * mm,
                      title="Pulse Fitness AI x Sicon Meeting Checklist").build(flow)


docx_path = os.path.join(OUT_DIR, "Sicon_Meeting_Checklist.docx")
pdf_path = os.path.join(OUT_DIR, "Sicon_Meeting_Checklist.pdf")
build_docx(docx_path)
build_pdf(pdf_path)
print("WROTE:", docx_path)
print("WROTE:", pdf_path)
