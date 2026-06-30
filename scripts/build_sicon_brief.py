"""Generate the Pulse Fitness x Sicon integration brief as DOCX + PDF."""
import os

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

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

# ── Structured content ────────────────────────────────────────────────────
# Each block: ("h1"/"h2"/"p"/"bul"/"table", payload)
BLOCKS = [
    ("title", "Pulse Fitness AI × Sicon / Sage 200 — Integration Brief"),
    ("meta", [
        "Prepared for: Sicon Integration / Partner Team",
        "Prepared by: Pulse Fitness AI (pulsefitness.ai)",
        "Date: 29 June 2026",
        "Status: For review — confirmation requested on the open items in Section 6",
    ]),

    ("h1", "1. Executive Summary"),
    ("p", "Pulse Fitness AI is onboarding our customer base onto the platform and needs to migrate and then "
          "continuously synchronise three data domains from Sicon / Sage 200: Customers, Equipment (installed, "
          "serial-numbered assets) and Service Contracts."),
    ("p", "Scale: approximately 5,000 customers and 300,000 pieces of equipment."),
    ("p", "We have reviewed six published Sicon/Sage WebAPI specifications (Section 2). Our connection and "
          "authentication layer is built and tested against the documented Basic-auth + companyId model."),
    ("p", "Headline finding: two of the three domains are achievable today with the published APIs, but one "
          "critical capability is missing from every published specification we hold — there is no published "
          "endpoint to list/read the installed Equipment register (serial-numbered service assets). This is our "
          "largest data domain (300k records) and the primary blocker to a fully automated migration. Section 6 "
          "lists the specific questions we need Sicon to answer."),
    ("table", [
        ["Domain", "Volume", "Read/List API available?", "Verdict"],
        ["Customers", "~5,000", "Yes (Sage Core + Sicon CRM)", "Ready to automate"],
        ["Contracts", "per customer", "No (push-only API)", "Manual/export interim; needs read API"],
        ["Equipment", "~300,000", "No list endpoint found", "BLOCKED — Sicon input required"],
    ]),

    ("h1", "2. APIs Reviewed"),
    ("table", [
        ["Specification", "Scope", "Relevance"],
        ["Service.R260200c", "Service Mgmt — cases, appointments, notes, resources", "Operational case sync; equipment only embedded on cases"],
        ["Contracts.R260200c", "Service Contracts", "Push-only (4x POST, no GET)"],
        ["CRM.R221200c", "Sicon CRM — companies, people, opportunities", "Customer/contact read (paged)"],
        ["CoreWebAPI.R260200c", "Sage 200 Core — customers, suppliers, stock, ledgers", "Customer master read (incremental)"],
        ["Projects.R260200c", "Sicon Project / Job Costing (SIJC)", "Jobs/labour/budgets — no equipment"],
        ["Sicon WebAPI Auth Guide", "Basic auth + companyId", "Connection model confirmed"],
    ]),

    ("h1", "3. Connection & Authentication (confirmed)"),
    ("bul", [
        "Method: HTTP Basic over TLS — Authorization: Basic base64(username:password) (ISO-8859-1).",
        "Company scoping: companyId query parameter on every request.",
        "Credential source (per company): Sage 200 client -> Sicon WebAPI -> Maintain WebAPI Users; "
        "companyId from Sage System Administration.",
        "Pulse Fitness storage: credentials Fernet-encrypted at rest, per-organisation, never exposed to the "
        "browser; all calls server-to-server.",
    ]),
    ("p", "What we need from each customer at go-live: Base URL, WebAPI username/password, Sage companyId."),

    ("h1", "4. Entity Mapping"),

    ("h2", "4.1 Customers — READY"),
    ("p", "Source of truth: Sage 200 (customer account); enriched by Sicon CRM."),
    ("table", [
        ["Pulse Fitness field", "Sicon/Sage field", "Source API", "Direction"],
        ["company_name", "Customer Account Name / Name", "Core GET /api/Customer/GetCustomers", "Sage -> Pulse"],
        ["sage_customer_id", "SLCustomerAccountID", "Core / CRM Companies/SL/{id}", "Sage -> Pulse"],
        ["sage_customer_reference", "Customer Reference", "Core GetCustomers?Reference=", "Sage -> Pulse"],
        ["sicon_company_id", "SiconCRMCompanyID", "CRM GET /api/CRM/Companies", "Sicon -> Pulse"],
        ["address / postcode / phone", "Customer + delivery addresses", "Core CustomerDeliveryAddress, CRM Addresses", "Sage -> Pulse"],
        ["contacts (people)", "Customer Contacts / CRM People", "Core Customers/Contacts, CRM GET /api/CRM/People", "Sage/Sicon -> Pulse"],
        ["VAT / currency / terms / credit / status", "Customer financial fields", "Core Customer", "Sage -> Pulse"],
    ]),
    ("p", "Incremental sync: Core GetCustomers supports AmendedAfterDate (delta pulls). CRM list endpoints "
          "support page / pageSize pagination. Both scale to 5,000 cleanly."),

    ("h2", "4.2 Equipment — BLOCKED (no read/list API found)"),
    ("table", [
        ["Pulse Fitness field", "Expected Sicon field", "Status"],
        ["sicon_equipment_id", "SiconEquipmentID", "In Service spec but only embedded on a Case (Equipments[])"],
        ["serial_number", "(equipment identifier)", "No list/search endpoint"],
        ["sage_item_id", "ItemID (stock link)", "Stock catalogue only (SKU, not installed asset)"],
        ["machine_type / make / model", "Equipment Name / item attributes", "No standalone read"],
        ["install / warranty / contract cover", "—", "No standalone read"],
    ]),
    ("p", "Problem: across Service, CRM, Core and Projects there is no endpoint that lists or searches "
          "installed equipment. Service exposes Equipment only as a child array on a Service Case; Core StockItem "
          "is the product/SKU catalogue (traceable serial/batch stock, but not the installed service-asset "
          "register). We cannot enumerate 300k assets from any documented route. See Section 6, Q1-Q3."),

    ("h2", "4.3 Service Contracts — PARTIAL (push-only; no read)"),
    ("table", [
        ["Pulse Fitness field", "Sicon field", "API", "Direction"],
        ["contract_number", "SiconContractNumber", "POST /api/Contract/CreateUpdateContract", "Pulse -> Sicon"],
        ["sicon_contract_id", "SiconContractID", "(creation response)", "Sicon -> Pulse"],
        ["customer link", "CustomerNumber / SLCustomerAccountID", "Contract POST", "Pulse -> Sicon"],
        ["customer_order_number", "—", "POST UpdateContractCustomerOrderNumber", "Pulse -> Sicon"],
        ["contract lines", "—", "POST /api/ContractLine/PostContractLine", "Pulse -> Sicon"],
        ["start / end / value / SLA", "Contract fields", "Contract POST", "Pulse -> Sicon"],
    ]),
    ("p", "Problem: Contracts.R260200c contains only POST endpoints — no GET/list/read of existing contracts or "
          "lines. We can write contracts into Sicon but cannot pull a customer's existing contract book out for "
          "migration, nor read contract state back for two-way sync. See Section 6, Q4."),

    ("h2", "4.4 Service Cases / Appointments / Notes — already built"),
    ("table", [
        ["Pulse Fitness", "Sicon", "API"],
        ["Issue (fault)", "Service Case", "POST /api/service/cases; GET /api/service/cases (list)"],
        ["Case status / engineer / teams", "Case fields", "GET /api/service/cases/{id} (poll)"],
        ["Appointments / time bookings", "Appointments", "Service/Appointments, .../TimeBookings"],
        ["Timeline notes", "Tracking Notes", "Service/Cases/{caseID}/TrackingNotes (bi-directional)"],
        ["Engineers", "Appointment Resources / SIJCEMP", "appointments/resources, Projects SIJCEMP/GetEmployees"],
    ]),
    ("p", "This domain is fully mapped and implemented (push + 5-minute poll-back)."),

    ("h1", "5. What Works vs What's Missing"),
    ("p", "Available now via published APIs:"),
    ("bul", [
        "Customer/contact migration + incremental sync (Sage Core GetCustomers + Sicon CRM).",
        "Suppliers, stock catalogue, sales orders, invoices/ledgers (Sage Core) — if needed.",
        "Service case create + status/appointment/notes sync (Service API) — already live.",
        "Contract creation/push into Sicon (Contracts API).",
        "Authentication / multi-company connection.",
    ]),
    ("p", "Missing / blocked:"),
    ("bul", [
        "Equipment register read/list API (installed serial-numbered assets) — critical, 300k records.",
        "Contracts read/list API — cannot pull existing contracts or read them back for sync.",
        "Equipment <-> contract / site linkage read — needed to know which assets a contract covers.",
    ]),

    ("h1", "6. Questions for Sicon (what we need to proceed)"),
    ("p", "Equipment (highest priority):"),
    ("bul", [
        "Q1. Is there an API to list/search the installed Equipment / Service Asset register for a company — "
        "ideally paged and with a 'changed since' filter for incremental sync?",
        "Q2. If not a dedicated endpoint, can Equipment be read via the Service API generic "
        "GET /~/api/v2/TEntity paged reader? If so, what is the entity type/identifier for Equipment and what "
        "fields are returned?",
        "Q3. If no API path exists, can you provide a one-time SQL/DB or CSV export of all equipment per "
        "company (SiconEquipmentID, serial, make/model/type, install date, warranty/contract cover, linked "
        "customer SLCustomerAccountID and site/sub-location)? We have an importer ready to ingest it.",
    ]),
    ("p", "Contracts:"),
    ("bul", [
        "Q4. Is there (or planned) a GET/list endpoint for Service Contracts and contract lines so we can "
        "migrate existing contracts and read contract state back? If not, can you provide a CSV/DB export?",
    ]),
    ("p", "Equipment <-> coverage:"),
    ("bul", [
        "Q5. How is the link between an equipment asset, its site/sub-location, and its covering contract "
        "exposed for reading?",
    ]),
    ("p", "Operational:"),
    ("bul", [
        "Q6. Recommended rate limits / page sizes for bulk reads at our scale (5k customers / 300k assets)?",
        "Q7. Any webhooks / change-notification mechanism, or is scheduled polling (AmendedAfterDate / "
        "updated-since) the expected pattern?",
        "Q8. Confirm the production base URL pattern per customer instance and any IP allow-listing needs.",
    ]),

    ("h1", "7. Proposed Plan"),
    ("table", [
        ["Phase", "Scope", "Dependency"],
        ["1 (in progress)", "CSV importers for equipment + contracts (idempotent, batched); capture SiconEquipmentID / SiconContractID", "None — live"],
        ["2", "Automated customer pull + incremental sync (Sage Core GetCustomers / CRM)", "None — ready to build"],
        ["3", "Automated equipment migration + sync", "Q1-Q3 (Sicon)"],
        ["4", "Contract migration + two-way read", "Q4 (Sicon)"],
    ]),
    ("p", "Contact: the Pulse Fitness AI integration team. We are happy to join a technical call to walk "
          "through any of the above."),
]


# ── DOCX builder ────────────────────────────────────────────────────────────
def build_docx(path):
    doc = Document()
    styles = doc.styles
    normal = styles["Normal"].font
    normal.name = "Calibri"; normal.size = Pt(10.5)
    for kind, payload in BLOCKS:
        if kind == "title":
            p = doc.add_paragraph(); r = p.add_run(payload)
            r.bold = True; r.font.size = Pt(20); r.font.color.rgb = BRAND
        elif kind == "meta":
            for line in payload:
                p = doc.add_paragraph(); r = p.add_run(line)
                r.font.size = Pt(9.5); r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            doc.add_paragraph()
        elif kind == "h1":
            p = doc.add_paragraph(); r = p.add_run(payload)
            r.bold = True; r.font.size = Pt(14); r.font.color.rgb = BRAND
            p.space_before = Pt(10)
        elif kind == "h2":
            p = doc.add_paragraph(); r = p.add_run(payload)
            r.bold = True; r.font.size = Pt(12); r.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
        elif kind == "p":
            doc.add_paragraph(payload)
        elif kind == "bul":
            for item in payload:
                doc.add_paragraph(item, style="List Bullet")
        elif kind == "table":
            rows = payload
            t = doc.add_table(rows=len(rows), cols=len(rows[0]))
            t.style = "Light Grid Accent 1"
            for ri, row in enumerate(rows):
                for ci, cell in enumerate(row):
                    c = t.cell(ri, ci)
                    c.text = str(cell)
                    for par in c.paragraphs:
                        for run in par.runs:
                            run.font.size = Pt(8.5)
                            if ri == 0:
                                run.bold = True
            doc.add_paragraph()
    doc.save(path)


# ── PDF builder ─────────────────────────────────────────────────────────────
def build_pdf(path):
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=ss["Heading1"], textColor=BRAND_HEX, fontSize=14, spaceBefore=12, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=ss["BodyText"], fontSize=9.5, leading=13)
    titlest = ParagraphStyle("T", parent=ss["Title"], textColor=BRAND_HEX, fontSize=20)
    meta = ParagraphStyle("M", parent=ss["BodyText"], fontSize=9, textColor=colors.HexColor("#555555"), leading=12)
    flow = []
    for kind, payload in BLOCKS:
        if kind == "title":
            flow.append(Paragraph(payload, titlest)); flow.append(Spacer(1, 6))
        elif kind == "meta":
            for line in payload:
                flow.append(Paragraph(line, meta))
            flow.append(Spacer(1, 8))
        elif kind == "h1":
            flow.append(Paragraph(payload, h1))
        elif kind == "h2":
            flow.append(Paragraph(payload, h2))
        elif kind == "p":
            flow.append(Paragraph(payload, body)); flow.append(Spacer(1, 4))
        elif kind == "bul":
            items = [ListItem(Paragraph(it, body), leftIndent=10) for it in payload]
            flow.append(ListFlowable(items, bulletType="bullet", start="•"))
            flow.append(Spacer(1, 4))
        elif kind == "table":
            rows = payload
            data = [[Paragraph(str(c), ParagraphStyle("c", parent=body, fontSize=7.8, leading=10,
                     textColor=colors.white if ri == 0 else colors.black))
                     for c in row] for ri, row in enumerate(rows)]
            ncols = len(rows[0])
            avail = A4[0] - 30 * mm
            tbl = Table(data, colWidths=[avail / ncols] * ncols, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_HEX),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f8fc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            flow.append(tbl); flow.append(Spacer(1, 8))
    SimpleDocTemplate(path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm,
                      title="Pulse Fitness AI x Sicon Integration Brief").build(flow)


docx_path = os.path.join(OUT_DIR, "Pulse_Fitness_AI_x_Sicon_Integration_Brief.docx")
pdf_path = os.path.join(OUT_DIR, "Pulse_Fitness_AI_x_Sicon_Integration_Brief.pdf")
build_docx(docx_path)
build_pdf(pdf_path)
print("WROTE:", docx_path)
print("WROTE:", pdf_path)
