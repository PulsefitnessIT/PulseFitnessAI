from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
import uuid
import json
import re
import io
import csv
import logging

from utils.database import db, EMERGENT_LLM_KEY
from utils.auth import get_current_user
from utils.ai_guardrails import sanitize_prompt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/equipment-import", tags=["Equipment Import"])

# ── Shared AI extraction prompt (adaptive to any supplier) ────────

_EXTRACTION_TEMPLATE = """You are an expert data extraction assistant for gym and fitness equipment invoices.

IMPORTANT — ADAPTIVE EXTRACTION:
Invoices come from many different suppliers (Pulse Fitness, Life Fitness, Technogym, Precor, Matrix, Cybex, etc.).
Each supplier uses a different invoice layout, terminology, and format. You must:
1. First IDENTIFY the supplier from the invoice branding, letterhead, logo text, or company details.
   - Look at the HEADER, top of page, "From:", "Sold By", "Invoice From", company-info block, footer.
   - Common signals: large logo text, "VAT No", "Company No.", "@pulsefitness.com" emails, payment-instruction blocks.
   - "Pulse Fitness" / "Pulse Fitness Limited" / "PULSE" as a header → supplier_name = "Pulse Fitness".
   - Use the supplier as the equipment `make` for items that don't show an explicit manufacturer
     (most invoices list the supplier's own product range without re-stating the manufacturer per line).
2. Then ADAPT your extraction to that supplier's format — different suppliers label fields differently:
   - "Customer Ref" / "Account No" / "Client Code" / "Reference" → account_ref
   - "Delivery Address" / "Ship To" / "Site" / "Installation Location" → site_name
   - "Invoice No" / "Invoice #" / "Document Number" / "Ref" → invoice_number
   - "Delivery Date" / "Install Date" / "Completion Date" / "Ship Date" → install_date
   - "Serial No" / "S/N" / "Serial" / "Asset Tag" → serial_number
   - "Unit Price" / "Each" / "Price" / "Net" → unit_price
   - "Part No" / "SKU" / "Item Code" / "Product Code" → stock_item_code

EQUIPMENT EXTRACTION RULES:
1. For each LINE ITEM with quantity > 1, create SEPARATE entries — one per unit.
2. Match serial numbers to individual equipment items.
3. If serial numbers are fewer than quantity, leave remaining entries with empty serial numbers.
4. SKIP non-equipment items: delivery charges, installation fees, training sessions, warranty line items, toolboxes, spare parts kits, consumables.
5. The "make" is the manufacturer/brand. If a line item doesn't state a manufacturer, USE THE SUPPLIER NAME you identified above (never leave `make` blank when a supplier was identified).
6. If the invoice doesn't clearly show a site/location, use the delivery address or "Ship To" as the site_name.
7. CATEGORISE every machine into ONE of these exact buckets (use the description / model name as the signal):
   - "Cardiovascular" — treadmills, bikes (upright/recumbent/spin/air), rowers, ellipticals, cross-trainers, stair climbers, ski ergs, stepmills.
   - "Strength" — pin/plate-loaded machines, smith machines, cable crossovers, leg press, chest press, lat pulldown, all "selectorized" or "plate-loaded" station equipment.
   - "Free Weights" — dumbbells, barbells, kettlebells, weight plates, racks, benches (flat/incline/decline/Olympic), platforms.
   - "Functional" — rigs, sleds, suspension trainers, plyo boxes, battle ropes, sled tracks, monkey bars, multi-jungles, turf zones, FT rigs.
   - "Accessories" — mats, water dispensers, mirrors, signage, scales, foam rollers, anything not in the above 4.
   Output the chosen value verbatim into the `equipment_category` field on every line. NEVER invent new categories.

WARRANTY EXTRACTION:
- Pulse Fitness format: "3 Year Gold Level Warranty" → WAR-BBB-003 (Platinum=AAA, Gold=BBB, Silver=CCC, Resale=DDD)
- Other suppliers: "2 Year Parts & Labour", "3yr Warranty", "36 Month Cover"
- For non-Pulse warranties, generate normalised warranty_code (years + default Silver=CCC).
- If NO warranty information exists, leave warranty_code and warranty_description empty.

EQUIPMENT NAMING RULES (CRITICAL — fixes long unreadable rows):
- `equipment_name` is the SHORT subtype, e.g. "Treadmill", "StepMill", "Upright Cycle", "Recumbent Cycle", "Cross-Trainer", "Rower", "Smith Machine", "Lat Pulldown". Pick the shortest accurate noun. NEVER include console / colour / connectivity details here.
- `model` is the SHORT product code printed on the invoice (the part number / SKU like "260G", "200H-AAF", "240G-AAV"). Use the line's stock_item_code if present; otherwise fall back to a short manufacturer model number.
- `description` is the FULL marketing line, verbatim (e.g. "Premium StepMill with 18.5\" (Cirrus V4) Touchscreen Console, Apple/Samsung Watch Connectivity, Content Mirroring & Wireless Charging in Sand Black"). Operators want this kept for search, but it MUST NOT be the model.

Return ONLY valid JSON with this structure:
{{
  "account_ref": "string",
  "site_name": "string",
  "invoice_number": "string",
  "install_date": "dd/mm/yyyy",
  "supplier_name": "string",
  "supplier_vat_number": "string or empty (UK suppliers usually 9 digits)",
  "supplier_company_number": "string or empty",
  "delivery_address": "string (multiline, as-printed on invoice — used for site postcode parsing)",
  "customer_name": "string (the 'Bill To' / 'Invoice Address' company name — NOT the delivery site)",
  "customer_reference": "string or empty (PO ref / customer code printed under 'Please quote on payment')",
  "due_date": "dd/mm/yyyy or empty",
  "payment_terms": "string or empty (e.g. '7 days from document date', 'Net 30')",
  "bank_details": {{
    "bank_name": "string or empty",
    "account_name": "string or empty",
    "account_number": "string or empty",
    "sort_code": "string or empty"
  }},
  "totals": {{
    "net": number,
    "vat": number,
    "gross": number
  }},
  "warranty_code": "WAR-XXX-YYY or empty",
  "warranty_description": "e.g. 3 Year Gold Level Warranty or empty",
  "equipment": [
    {{
      "make": "string (manufacturer; fall back to supplier_name if line doesn't state one)",
      "equipment_name": "string (SHORT — e.g. 'Treadmill', 'StepMill', 'Upright Cycle')",
      "model": "string (SHORT — invoice stock_item_code / part number, e.g. '260G', '200H-AAF')",
      "description": "string (FULL marketing line as printed on the invoice)",
      "equipment_category": "Cardiovascular|Strength|Free Weights|Functional|Accessories",
      "serial_number": "string or empty",
      "unit_price": number,
      "stock_item_code": "string or empty"
    }}
  ]
}}

INVOICE TEXT:
{pdf_text}
"""


# Iter 216h12 — raised from 12 000 → 40 000 to cover multi-page Pulse
# Fitness invoices (Carshalton was 24 090 chars; previous cap dropped
# the second half — every line item past page 5 plus the totals / bank /
# customer-ref blocks). Haiku-4.5 input window is 200 K tokens; 40 K
# chars ≈ 10 K tokens, well within budget.
_PDF_TEXT_MAX_CHARS = 40_000


def _build_extraction_prompt(pdf_text: str) -> str:
    """Build the AI extraction prompt with the (almost) full invoice text."""
    return _EXTRACTION_TEMPLATE.format(pdf_text=pdf_text[:_PDF_TEXT_MAX_CHARS])
WARRANTY_SLA_MAP = {
    "AAA": "Platinum",
    "BBB": "Gold",
    "CCC": "Silver",
    "DDD": "Resale",
}

SICON_COLUMNS = [
    "Invoice Customer Ref", "Location Description", "Sublocation Description",
    "Supplier Reference", "Supplier Name", "Contract Number", "Contract Line No",
    "SLA Name", "Stock Item Code", "Description", "Make", "Model", "Serial Number",
    "Install Date", "Manufacturer Warranty Expiry Date", "Last Service Date",
    "Service Interval", "Service Period", "Next Service Date", "ID Number",
    "Service Template", "Equipment Group",
    "Analysis Code 1", "Analysis Code 2", "Analysis Code 3", "Analysis Code 4",
    "Analysis Code 5", "Analysis Code 6", "Analysis Code 7", "Analysis Code 8",
    "Analysis Code 9", "Analysis Code 10", "Analysis Code 11", "Analysis Code 12",
    "Analysis Code 13", "Analysis Code 14", "Analysis Code 15", "Analysis Code 16",
    "Analysis Code 17", "Analysis Code 18", "Analysis Code 19", "Analysis Code 20",
    "End User Company External Reference", "End User Person External Reference",
]


def _parse_warranty_years(years_part: str) -> int:
    """Parse the years segment of a warranty code; 'VAR' → 1, numeric → int, else 0."""
    if years_part == "VAR":
        return 1
    try:
        return int(years_part)
    except ValueError:
        return 0


def _compute_warranty_expiry(install_date_str: str, years: int) -> str:
    """Given an install date (multiple formats) and +years, return dd/mm/yyyy expiry."""
    if years <= 0 or not install_date_str:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(install_date_str, fmt)
            return dt.replace(year=dt.year + years).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return ""


def parse_warranty_code(code: str, install_date_str: str) -> dict[str, str | int]:
    """Parse a warranty code like WAR-BBB-003 into SLA level and expiry date."""
    if not code:
        return {"sla": "", "expiry_date": "", "years": 0}

    parts = code.upper().strip().split("-")
    if len(parts) != 3 or parts[0] != "WAR":
        return {"sla": "", "expiry_date": "", "years": 0}

    sla = WARRANTY_SLA_MAP.get(parts[1], "")
    years = _parse_warranty_years(parts[2])
    expiry_date = _compute_warranty_expiry(install_date_str, years)

    return {"sla": sla, "expiry_date": expiry_date, "years": years}


def compute_next_service(install_date_str: str) -> str:
    """1 year from install date."""
    if not install_date_str:
        return ""
    try:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(install_date_str, fmt)
                nxt = dt.replace(year=dt.year + 1)
                return nxt.strftime("%d/%m/%Y")
            except ValueError:
                continue
    except Exception:
        pass
    return ""


def _extract_pdf_text(data: bytes) -> str:
    """Extract text content from a PDF file. Page breaks are preserved
    via an explicit `--- PAGE BREAK ---` marker so chunked extraction
    can split on whole-page boundaries."""
    import fitz
    parts: list[str] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        for page in doc:
            parts.append(page.get_text())
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {str(e)}")

    pdf_text = "\n--- PAGE BREAK ---\n".join(parts)
    if len(pdf_text) < 50:
        raise HTTPException(status_code=400, detail="Could not extract text from PDF. Ensure it's not a scanned image.")
    return pdf_text


async def _ai_extract_invoice(pdf_text: str) -> dict:
    """Send PDF text to AI and parse the structured JSON response.

    Iter 216l — investigated chunked parallel haiku (2–5 chunks via
    asyncio.gather) and dropped it: the EMERGENT_LLM_KEY gateway
    serialises Anthropic concurrent requests, so 2 parallel haiku calls
    end up taking ~50s wall (vs 32s single-shot). Cross-provider
    chunking (haiku + gpt-4o-mini) doesn't help either — output token
    count (60 items × ~150 tokens each) dominates latency regardless of
    splitting. Single-shot haiku is optimal until we have a way to
    drastically cut output token count.

    Iter 216k bench (Carshalton 6.9 MB / 25 k chars):
       gpt-5.2 single-shot          → 50–60 s (502 on prod ingress)
       claude-haiku-4-5 single-shot → 30–35 s ✅ shipped
       claude-haiku-4-5 × 5 chunks  → 50–60 s + lower quality
       gpt-4o-mini single-shot      → 55–60 s
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    # Iter 220at / F-11 — strip control chars from extracted PDF text
    # so any embedded "ignore prev instructions" payload at least
    # can't smuggle null bytes / BOMs through the JSON contract.
    # We DO NOT injection-score here: invoice text often contains
    # vendor boilerplate that triggers false positives, and the
    # downstream parser only accepts strict JSON anyway (XSS surface
    # is zero).
    pdf_text = sanitize_prompt(pdf_text, max_chars=120_000)
    prompt = _build_extraction_prompt(pdf_text)
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=str(uuid.uuid4()),
        system_message="You extract structured data from invoices. Return ONLY valid JSON, no markdown.",
    ).with_model("anthropic", "claude-haiku-4-5")
    response = await llm.send_message(UserMessage(text=prompt))
    raw = response.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)


# ── Iter 216g — Vision-based extraction for scanned PDFs and image
#     uploads. We render each PDF page to a PNG (fitz at 144 DPI) and
#     send them as base64 ImageContent attachments. Same prompt schema
#     so downstream code in `parse_invoice` etc. is untouched.
async def _ai_extract_invoice_from_images(images_b64: list[str]) -> dict:
    """Send invoice page images to a vision-capable model and parse the
    structured JSON response. Up to 8 pages — beyond that we truncate."""
    if not images_b64:
        raise HTTPException(status_code=400, detail="No invoice pages to read")
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

    images_b64 = images_b64[:8]
    # Reuse the text prompt template but blank out the {pdf_text}
    # placeholder — vision models read the image directly, the prompt
    # only carries instructions + JSON schema.
    instructions = _EXTRACTION_TEMPLATE.replace("{pdf_text}", "(image-based invoice — read the page(s) attached)")
    import_session = str(uuid.uuid4())
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=import_session,
        system_message="You extract structured data from invoice IMAGES. Return ONLY valid JSON, no markdown.",
    ).with_model("anthropic", "claude-haiku-4-5")
    msg = UserMessage(
        text=instructions,
        file_contents=[ImageContent(image_base64=b) for b in images_b64],
    )
    response = await llm.send_message(msg)
    raw = response.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)


def _pdf_to_image_base64s(data: bytes, dpi: int = 144, max_pages: int = 8) -> list[str]:
    """Render PDF pages to PNG and return base64-encoded list."""
    import fitz
    import base64 as _b64
    out: list[str] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        # 72 dpi is the PDF default; matrix scale = dpi / 72.
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        for page in doc:
            if len(out) >= max_pages:
                break
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png = pix.tobytes("png")
            out.append(_b64.b64encode(png).decode("ascii"))
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not rasterise PDF: {e}")
    return out


def _image_bytes_to_base64(data: bytes, mime: str) -> str:
    """Normalise an uploaded JPG/PNG/WEBP into a single base64 string.
    Decodes via Pillow first to (a) reject corrupt files and (b) flatten
    multi-frame images to a single PNG frame, per the testing playbook."""
    import base64 as _b64
    from PIL import Image
    import io as _io
    try:
        img = Image.open(_io.BytesIO(data))
        # Some scans come in CMYK or P; convert to RGB to keep models happy.
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        # Flatten any animation to first frame.
        try:
            img.seek(0)
        except Exception:
            pass
        # Resize aggressive (keep aspect, max edge 2400px).
        max_edge = 2400
        if max(img.size) > max_edge:
            ratio = max_edge / max(img.size)
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)))
        out = _io.BytesIO()
        img.save(out, format="PNG")
        return _b64.b64encode(out.getvalue()).decode("ascii")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read image: {e}")


async def _vision_supplier_lookup(data: bytes) -> str:
    """Iter 216k — when text extraction yields no supplier, render the
    first PDF page and ask a vision model to identify the supplier from
    the letterhead/logo. Many invoices (e.g. Pulse Fitness) bury the
    company name in an image header that fitz can't read as text.

    Returns the supplier name (string) or "" if the call fails.
    """
    try:
        import fitz
        import base64 as _b64
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.page_count == 0:
            doc.close()
            return ""
        # Render page 1 at 144 DPI (matches existing vision pipeline).
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
        png_bytes = pix.tobytes("png")
        doc.close()
        b64 = _b64.b64encode(png_bytes).decode()
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        llm = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=str(uuid.uuid4()),
            system_message="You identify the SUPPLIER company name from invoice letterheads. Return ONLY the name, no extra words.",
        ).with_model("openai", "gpt-4o-mini")
        msg = UserMessage(
            text=(
                "Identify the supplier (the company that issued / sold this invoice). "
                "Look at the LOGO, letterhead, top-of-page company-info block. "
                "Return ONLY the company name (e.g. 'Pulse Fitness', 'Life Fitness', 'Technogym'). "
                "If you cannot tell, return the single word: Unknown."
            ),
            file_contents=[ImageContent(image_base64=b64)],
        )
        resp = await llm.send_message(msg)
        name = (resp or "").strip().strip('"').strip("'")
        # Strip trailing punctuation / common boilerplate
        name = re.sub(r"^(supplier|name)[:\s]+", "", name, flags=re.I).strip()
        if not name or name.lower() == "unknown" or len(name) > 80:
            return ""
        return name
    except Exception:
        # Best-effort; never block the main extraction on this.
        return ""


async def extract_invoice_smart(data: bytes, content_type: str | None) -> dict:
    """Top-level entry — dispatches to text, vision-PDF, or vision-image
    based on the upload. Used by both the equipment-import suite and the
    head-office onboarding wizard.

    Strategy:
      1. If MIME is image/* → render single image, vision extract.
      2. If MIME is PDF → try text extraction first (cheap). If the
         resulting text is too short (<50 chars), assume scanned and
         fall back to rendering pages → vision.
      3. Iter 216k — supplier-from-logo fallback. We kick off a vision
         supplier-lookup IN PARALLEL with the main text extraction so
         we don't add latency on top of the already-50s text path. If
         the main extraction returns no supplier (image-only logo), we
         splice the vision result in. Otherwise the vision call result
         is discarded.
    """
    import asyncio as _asyncio
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        b64 = _image_bytes_to_base64(data, ct)
        return await _ai_extract_invoice_from_images([b64])
    # PDF (default) — run main extraction + supplier-vision in parallel.
    async def _main_extract() -> dict:
        try:
            txt = _extract_pdf_text(data)
            return await _ai_extract_invoice(txt)
        except HTTPException as exc:
            msg = str(getattr(exc, "detail", "") or "").lower()
            if exc.status_code == 400 and ("scanned" in msg or "extract text" in msg):
                images = _pdf_to_image_base64s(data)
                return await _ai_extract_invoice_from_images(images)
            raise

    main_task = _asyncio.create_task(_main_extract())
    vision_task = _asyncio.create_task(_vision_supplier_lookup(data))
    result = await main_task
    vision_supplier = ""
    try:
        vision_supplier = await _asyncio.wait_for(vision_task, timeout=8)
    except TimeoutError:
        vision_task.cancel()
    except Exception:
        pass

    supplier = (result.get("supplier_name") or "").strip()
    if (not supplier or supplier.lower() == "unknown") and vision_supplier:
        result["supplier_name"] = vision_supplier
        for eq in (result.get("equipment") or []):
            if not (eq.get("make") or "").strip():
                eq["make"] = vision_supplier
    return result


def _normalise_supplier_name(name: str) -> str:
    """Lowercase + strip company suffixes + non-alphanum so 'Pulse
    Fitness Limited' / 'PULSE FITNESS LTD.' / 'Pulse Fitness' all
    collapse to the same key for fuzzy matching."""
    if not name:
        return ""
    n = name.lower().strip()
    for suffix in (" limited", " ltd.", " ltd", " plc", " inc", " inc.", " llc", " gmbh", " (uk)"):
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    return re.sub(r"[^a-z0-9]+", "", n)


async def match_supplier(
    org_id: str, supplier_name: str, vat_number: str = "",
) -> dict | None:
    """Iter 216h12 — look up an existing supplier in the org's directory
    that matches the AI-extracted `supplier_name`. Match priority:

      1. Exact (case-insensitive) name match.
      2. VAT number match (if the AI got the VAT number AND we stored it).
      3. Normalised name match (strips 'Ltd', punctuation, spaces).

    Returns the matched supplier doc (no `_id`) or None.
    """
    if not org_id or not supplier_name:
        return None
    org_filter = {"organization_id": org_id}
    # 1. Exact, case-insensitive name (anchored regex)
    safe = re.escape(supplier_name.strip())
    match = await db.suppliers.find_one(
        {**org_filter, "name": {"$regex": f"^{safe}$", "$options": "i"}},
        {"_id": 0},
    )
    if match:
        return match
    # 2. VAT match
    if vat_number:
        match = await db.suppliers.find_one(
            {**org_filter, "vat_number": vat_number.strip()},
            {"_id": 0},
        )
        if match:
            return match
    # 3. Normalised name match (load shortlist + compare in python — small N)
    target = _normalise_supplier_name(supplier_name)
    if not target:
        return None
    cursor = db.suppliers.find(org_filter, {"_id": 0, "id": 1, "name": 1, "vat_number": 1, "email": 1, "phone": 1, "address": 1})
    async for sup in cursor:
        if _normalise_supplier_name(sup.get("name", "")) == target:
            return sup
    return None


def _enrich_equipment_dates(extracted: dict) -> dict:
    """Add warranty, SLA, and service dates to each equipment item."""
    install_date = extracted.get("install_date", "")
    warranty_code = extracted.get("warranty_code", "")
    warranty_info = parse_warranty_code(warranty_code, install_date)
    next_service = compute_next_service(install_date)

    for eq in extracted.get("equipment", []):
        eq["warranty_code"] = warranty_code
        eq["warranty_expiry"] = warranty_info["expiry_date"]
        eq["sla_name"] = warranty_info["sla"]
        eq["install_date"] = install_date
        eq["next_service_date"] = next_service

    return warranty_info


async def _store_invoice_pdf(data: bytes, filename: str) -> dict:
    """Compress and store the invoice PDF or image, returning storage metadata.
    Iter 216g — also accepts JPG/PNG/WEBP images. PDFs go through the
    pdf_compress pipeline; images are stored as-is (already compressed)."""
    from utils.database import APP_NAME, put_object
    import hashlib
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    if ext in ("jpg", "jpeg"):
        mime = "image/jpeg"
        payload = data
    elif ext == "png":
        mime = "image/png"
        payload = data
    elif ext == "webp":
        mime = "image/webp"
        payload = data
    else:
        # PDF path — keep the existing compression pipeline.
        from utils.pdf_compress import compress_pdf
        payload = compress_pdf(data)
        mime = "application/pdf"
        ext = "pdf"
    content_hash = hashlib.sha256(payload).hexdigest()
    storage_path = f"{APP_NAME}/invoices/{uuid.uuid4()}.{ext}"
    storage_result = put_object(storage_path, payload, mime)
    return {
        "path": storage_result["path"],
        "url": storage_result.get("url", storage_result["path"]),
        "hash": content_hash,
        "size": storage_result.get("size", len(data)),
    }


def _build_import_record(import_id: str, user_id: str, filename: str, extracted: dict, warranty_info: dict, storage: dict) -> dict:
    """Build the import document for equipment_imports collection."""
    return {
        "id": import_id, "user_id": user_id, "status": "pending_review",
        "original_filename": filename, "extracted_data": extracted,
        "warranty_info": warranty_info, "equipment_count": len(extracted.get("equipment", [])),
        "invoice_storage_path": storage["path"], "invoice_download_url": storage["url"],
        "invoice_content_hash": storage["hash"], "invoice_size": storage["size"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def _run_invoice_extraction(data: bytes, filename: str, content_type: str | None, user: dict) -> dict:
    """Shared invoice-extraction pipeline used by both the direct
    `/parse-invoice` upload and the chunked finalize endpoint."""
    try:
        extracted = await extract_invoice_smart(data, content_type)
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"AI returned invalid JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

    warranty_info = _enrich_equipment_dates(extracted)
    storage = await _store_invoice_pdf(data, filename)
    import_id = str(uuid.uuid4())

    supplier = (extracted.get("supplier_name") or "").strip()
    enriched_eq = []
    for eq in (extracted.get("equipment") or []):
        cur = dict(eq or {})
        make = (cur.get("make") or cur.get("manufacturer") or "").strip()
        if not make and supplier and supplier.lower() != "unknown":
            make = supplier
        cur["make"] = make
        short_name = _short_equipment_name(cur)
        short_model = _short_model_code(cur)
        full_desc = (cur.get("description") or cur.get("model") or "").strip()
        cur["name"] = short_name
        cur["description"] = full_desc
        cur["model"] = short_model
        enriched_eq.append(cur)
    extracted["equipment"] = enriched_eq

    await db.equipment_imports.insert_one(
        _build_import_record(import_id, user["id"], filename, extracted, warranty_info, storage)
    )

    matched_supplier = await match_supplier(
        user.get("organization_id"),
        extracted.get("supplier_name", ""),
        extracted.get("supplier_vat_number", "") or "",
    )

    return {
        "import_id": import_id,
        "account_ref": extracted.get("account_ref", ""),
        "site_name": extracted.get("site_name", ""),
        "invoice_number": extracted.get("invoice_number", ""),
        "install_date": extracted.get("install_date", ""),
        "supplier_name": extracted.get("supplier_name", ""),
        "supplier_vat_number": extracted.get("supplier_vat_number", ""),
        "supplier_company_number": extracted.get("supplier_company_number", ""),
        "customer_name": extracted.get("customer_name", ""),
        "customer_reference": extracted.get("customer_reference", ""),
        "due_date": extracted.get("due_date", ""),
        "payment_terms": extracted.get("payment_terms", ""),
        "bank_details": extracted.get("bank_details") or {},
        "totals": extracted.get("totals") or {},
        "warranty_code": extracted.get("warranty_code", ""),
        "warranty_description": extracted.get("warranty_description", ""),
        "warranty_expiry": warranty_info["expiry_date"],
        "sla_name": warranty_info["sla"],
        "equipment": enriched_eq,
        "equipment_count": len(enriched_eq),
        "matched_supplier": matched_supplier,
        "matched_supplier_id": (matched_supplier or {}).get("id") or "",
    }


# ── Chunked invoice upload (bypasses the 2MB ingress body limit) ──────────
_CHUNK_DIR = "/tmp/pulse_invoice_chunks"
_INVOICE_ALLOWED = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
# Large multi-page leisure-centre invoices can be big scanned PDFs. Chunked
# upload (1.5MB slices) means this cap is only checked on the reassembled
# file server-side; the AI extraction itself is bounded (first ~120k chars /
# 8 rendered pages), so a high ceiling is safe for memory/latency.
_INVOICE_MAX_SIZE = 100 * 1024 * 1024  # 100 MB


async def _resolve_import_site_id(org_id: str | None, explicit: str | None) -> str | None:
    """Pick the site to tag imported equipment with. An explicit body value
    wins; otherwise default to the org's primary (or earliest active) site so
    the equipment is immediately visible in the per-site portal view — the
    old logic only inferred a site when the org had EXACTLY one, so multi-site
    / head-office imports landed with no site_id and showed 'No equipment
    found' on every per-site view."""
    explicit = (explicit or "").strip() or None
    if explicit or not org_id:
        return explicit
    sites = await db.sites.find(
        {"organization_id": org_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "is_primary": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(100)
    if not sites:
        return None
    primary = next((s for s in sites if s.get("is_primary")), None)
    return (primary or sites[0]).get("id")


@router.post("/parse-invoice/chunk")
async def parse_invoice_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Receive one < 2MB slice of an invoice. Chunks are persisted in MongoDB
    (NOT local disk) keyed by upload_id so reassembly works regardless of which
    backend replica handles the chunk vs the finalize request. Call
    /parse-invoice/finalize to reassemble + process."""
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", upload_id)[:64]
    if not safe_id:
        raise HTTPException(400, "Invalid upload id")
    part = await file.read()
    if len(part) > 2 * 1024 * 1024:
        raise HTTPException(413, "Chunk exceeds 2MB")
    now = datetime.now(timezone.utc).isoformat()
    # chunk_index 0 clears any stale chunks for this id (fresh upload).
    if chunk_index == 0:
        await db.invoice_upload_chunks.delete_many({"upload_id": safe_id})
    await db.invoice_upload_chunks.update_one(
        {"upload_id": safe_id, "chunk_index": chunk_index},
        {"$set": {
            "upload_id": safe_id, "chunk_index": chunk_index,
            "total_chunks": total_chunks, "user_id": user["id"],
            "data": part, "created_at": now,
        }},
        upsert=True,
    )
    received = await db.invoice_upload_chunks.count_documents({"upload_id": safe_id})
    return {"ok": True, "upload_id": safe_id, "received": received, "total": total_chunks}


@router.post("/parse-invoice/finalize")
async def parse_invoice_finalize(
    upload_id: str = Form(...),
    filename: str = Form(...),
    content_type: str = Form(default="application/pdf"),
    user=Depends(get_current_user),
):
    """Reassemble the MongoDB-stored chunks and run extraction in a DECOUPLED
    background task (large multi-page invoices can exceed the gateway
    timeout). Returns a job_id immediately; poll /parse-invoice/status/{id}."""
    import asyncio
    from utils.file_validation import validate_upload
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", upload_id)[:64]
    if not safe_id:
        raise HTTPException(400, "Invalid upload id")
    chunks = await db.invoice_upload_chunks.find(
        {"upload_id": safe_id}, {"_id": 0, "chunk_index": 1, "data": 1}
    ).sort("chunk_index", 1).to_list(2000)
    if not chunks:
        raise HTTPException(404, "Upload not found or expired")
    data = b"".join(c["data"] for c in chunks)
    # Reassembled — drop the chunk docs immediately.
    await db.invoice_upload_chunks.delete_many({"upload_id": safe_id})
    # Validate synchronously so the user gets immediate feedback on bad files.
    validate_upload(file_bytes=data, filename=filename, allowed=_INVOICE_ALLOWED, max_size=_INVOICE_MAX_SIZE)

    job_id = str(uuid.uuid4())
    await db.invoice_parse_jobs.insert_one({
        "id": job_id, "user_id": user["id"], "filename": filename,
        "status": "processing", "phase": "queued", "page_count": None,
        "result": None, "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    async def _worker():
        try:
            # Instant page count (fitz) so the UI can say "Reading an N-page
            # invoice…" while the single LLM extraction call runs.
            page_count = None
            try:
                if (content_type or "").lower().endswith("pdf") or filename.lower().endswith(".pdf"):
                    import fitz
                    with fitz.open(stream=data, filetype="pdf") as _doc:
                        page_count = _doc.page_count
            except Exception:
                pass
            await db.invoice_parse_jobs.update_one(
                {"id": job_id}, {"$set": {"phase": "extracting", "page_count": page_count}})
            result = await _run_invoice_extraction(data, filename, content_type, user)
            await db.invoice_parse_jobs.update_one(
                {"id": job_id}, {"$set": {"status": "done", "phase": "done", "result": result}})
        except HTTPException as e:
            await db.invoice_parse_jobs.update_one(
                {"id": job_id}, {"$set": {"status": "error", "phase": "error", "error": str(e.detail)}})
        except Exception as e:
            await db.invoice_parse_jobs.update_one(
                {"id": job_id}, {"$set": {"status": "error", "phase": "error", "error": str(e)}})

    # Decoupled from the request so a client disconnect won't cancel it.
    asyncio.create_task(_worker())
    return {"job_id": job_id, "status": "processing"}


@router.get("/parse-invoice/status/{job_id}")
async def parse_invoice_status(job_id: str, user=Depends(get_current_user)):
    """Poll a background invoice-parse job. When status=='done', the full
    parse-invoice response is under `result`."""
    job = await db.invoice_parse_jobs.find_one(
        {"id": job_id, "user_id": user["id"]}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/parse-invoice")
async def parse_invoice(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload a supplier invoice (PDF or image — JPG/PNG/WEBP).
    AI extracts equipment data for import. Iter 216g — accepts scanned
    PDFs and image uploads via the smart extractor (vision fallback)."""
    from utils.file_validation import validate_upload
    data = await file.read()
    validate_upload(file_bytes=data, filename=file.filename, allowed=_INVOICE_ALLOWED, max_size=_INVOICE_MAX_SIZE)
    return await _run_invoice_extraction(data, file.filename, file.content_type, user)


@router.post("/parse-spreadsheet")
async def parse_spreadsheet(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Parse a CSV/XLSX equipment spreadsheet into a `pending_review`
    import (same shape as /parse-invoice) so the onboarding wizard can
    review + edit the rows and then confirm them through the identical
    import_id → /confirm flow. No equipment is created here."""
    from utils.file_validation import validate_upload, MIME_SPREADSHEETS
    from utils.spreadsheet_import import iter_rows, normalise_row, parse_date_cell

    data = await file.read()
    validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=50 * 1024 * 1024)

    equipment: list[dict] = []
    site_name = ""
    supplier_name = ""
    skipped = 0
    for raw in iter_rows(data, file.filename):
        row = normalise_row(raw)
        if not any((str(v).strip() if v is not None else "") for v in row.values()):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            skipped += 1
            continue
        manufacturer = str(row.get("manufacturer") or "").strip()
        model = str(row.get("model") or "").strip()
        if not site_name:
            site_name = str(row.get("site_name") or "").strip()
        if not supplier_name:
            supplier_name = str(row.get("supplier") or manufacturer or "").strip()
        equipment.append({
            "equipment_name": name,
            "name": name,
            "make": manufacturer,
            "manufacturer": manufacturer,
            "model": model,
            "stock_item_code": model,
            "description": str(row.get("notes") or "").strip() or name,
            "equipment_category": str(row.get("equipment_type") or "").strip(),
            "serial_number": str(row.get("serial_number") or "").strip(),
            "unit_price": _parse_date_safe_float(row.get("unit_price")),
            "install_date": parse_date_cell(row.get("purchase_date")),
            "warranty_expiry": parse_date_cell(row.get("warranty_expiry")),
            "warranty_code": "",
            "sla_name": "",
            "location": str(row.get("location") or "").strip(),
        })

    if not equipment:
        raise HTTPException(status_code=400, detail="No valid equipment rows found. Each row needs at least a 'name'.")

    import_id = str(uuid.uuid4())
    extracted = {
        "account_ref": "", "site_name": site_name, "invoice_number": "",
        "install_date": "", "supplier_name": supplier_name,
        "warranty_code": "", "warranty_description": "", "equipment": equipment,
    }
    await db.equipment_imports.insert_one({
        "id": import_id, "user_id": user["id"], "status": "pending_review",
        "original_filename": file.filename, "extracted_data": extracted,
        "warranty_info": {"sla": "", "expiry_date": "", "years": 0},
        "equipment_count": len(equipment),
        "invoice_storage_path": "", "invoice_download_url": "",
        "invoice_content_hash": "", "invoice_size": 0,
        "source": "spreadsheet",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "import_id": import_id, "account_ref": "", "site_name": site_name,
        "invoice_number": "", "install_date": "", "supplier_name": supplier_name,
        "warranty_code": "", "warranty_description": "", "warranty_expiry": "",
        "sla_name": "", "equipment": equipment, "equipment_count": len(equipment),
        "skipped": skipped,
    }


def _parse_date_safe_float(value) -> float:
    if value is None:
        return 0
    try:
        return float(str(value).replace(",", "").replace("£", "").strip() or 0)
    except (ValueError, TypeError):
        return 0


@router.put("/update/{import_id}")
async def update_import(import_id: str, data: dict, user: dict = Depends(get_current_user)) -> dict:
    """User edits the extracted data before confirming."""
    imp = await db.equipment_imports.find_one({"id": import_id, "user_id": user["id"]})
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")

    update = {}
    if "equipment" in data:
        update["extracted_data.equipment"] = data["equipment"]
        update["equipment_count"] = len(data["equipment"])
    if "account_ref" in data:
        update["extracted_data.account_ref"] = data["account_ref"]
    if "site_name" in data:
        update["extracted_data.site_name"] = data["site_name"]
    if "warranty_code" in data:
        update["extracted_data.warranty_code"] = data["warranty_code"]
    if "default_location" in data:
        update["extracted_data.default_location"] = data["default_location"]

    if update:
        await db.equipment_imports.update_one({"id": import_id}, {"$set": update})

    return {"message": "Updated"}


@router.post("/confirm/{import_id}")
async def confirm_import(import_id: str, body: dict = None, user: dict = Depends(get_current_user)) -> dict:
    """Confirm import — creates equipment in the system."""
    imp = await db.equipment_imports.find_one({"id": import_id, "user_id": user["id"]})
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")

    body = body or {}
    target_org_id, target_user_id = await _resolve_target_user(body, user)

    # Iter — tag imported equipment with a concrete site (body override, else
    # the org's primary/first site) so per-site portal filters surface it.
    target_site_id = await _resolve_import_site_id(target_org_id, body.get("site_id"))

    extracted = imp.get("extracted_data", {})
    supplier = extracted.get("supplier_name", "")
    site_name = extracted.get("site_name", "")
    account_ref = extracted.get("account_ref", "")
    invoice_number = extracted.get("invoice_number", "")
    default_location = extracted.get("default_location", "") or site_name

    created = 0
    import_ctx = {
        "target_user_id": target_user_id, "target_org_id": target_org_id,
        "supplier": supplier, "account_ref": account_ref,
        "invoice_number": invoice_number, "default_location": default_location,
        "import_id": import_id, "site_name": site_name,
        "site_id": target_site_id,
    }
    for eq in extracted.get("equipment", []):
        doc = _build_equipment_doc(eq, import_ctx)
        await db.equipment.insert_one(doc)
        created += 1

    await db.equipment_imports.update_one(
        {"id": import_id},
        {"$set": {"status": "imported", "imported_at": datetime.now(timezone.utc).isoformat(), "imported_count": created}},
    )

    invoice_doc = _build_invoice_doc(imp, import_ctx)
    if imp.get("invoice_storage_path"):
        await db.files.insert_one(invoice_doc)
    from routes.equipment import schedule_image_backfill
    from utils.auth import get_organization_filter
    schedule_image_backfill(get_organization_filter(user))
    return {"message": f"{created} equipment items imported", "created": created}


@router.get("/download/{import_id}")
async def download_sicon_csv(import_id: str, user: dict = Depends(get_current_user)) -> StreamingResponse:
    """Generate and download a Sicon-compatible CSV import file."""
    imp = await db.equipment_imports.find_one({"id": import_id, "user_id": user["id"]})
    if not imp:
        raise HTTPException(status_code=404, detail="Import not found")

    extracted = imp.get("extracted_data", {})
    account_ref = extracted.get("account_ref", "")
    site_name = extracted.get("site_name", "")
    supplier = extracted.get("supplier_name", "")
    invoice_number = extracted.get("invoice_number", "")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(SICON_COLUMNS)
    for eq in extracted.get("equipment", []):
        row = _build_sicon_row(eq, account_ref, site_name, supplier, invoice_number)
        writer.writerow([row.get(col, "") for col in SICON_COLUMNS])

    csv_bytes = output.getvalue().encode("utf-8")
    output.close()
    filename = f"Sicon_Import_{site_name.replace(' ', '_')}_{invoice_number}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/list")
async def list_imports(user: dict = Depends(get_current_user)) -> dict:
    """List all equipment imports for the current user."""
    imports = await db.equipment_imports.find(
        {"user_id": user["id"]}, {"_id": 0, "extracted_data": 0}
    ).sort("created_at", -1).to_list(50)
    return {"imports": imports}


# ── Bulk Invoice Processing ──────────────────────────────────────────

async def _parse_single_pdf(data: bytes, filename: str, user: dict) -> dict:
    """Parse a single PDF file and return the extracted data with import_id."""
    try:
        pdf_text = _extract_pdf_text(data)
    except HTTPException as exc:
        return {"error": f"{filename}: {exc.detail}", "filename": filename}

    try:
        extracted = await _ai_extract_invoice(pdf_text)
    except Exception as exc:
        return {"error": f"AI extraction failed for {filename}: {exc!s}", "filename": filename}

    _enrich_equipment_dates(extracted)
    storage = await _store_invoice_pdf(data, filename)

    import_id = str(uuid.uuid4())
    import_doc = {
        "id": import_id,
        "user_id": user["id"],
        "status": "pending_review",
        "original_filename": filename,
        "extracted_data": extracted,
        "warranty_info": parse_warranty_code(extracted.get("warranty_code", ""), extracted.get("install_date", "")),
        "equipment_count": len(extracted.get("equipment", [])),
        "invoice_storage_path": storage["path"],
        "invoice_download_url": storage["url"],
        "invoice_content_hash": storage["hash"],
        "invoice_size": storage["size"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.equipment_imports.insert_one(import_doc)

    return {
        "import_id": import_id,
        "filename": filename,
        "account_ref": extracted.get("account_ref", ""),
        "site_name": extracted.get("site_name", ""),
        "invoice_number": extracted.get("invoice_number", ""),
        "install_date": extracted.get("install_date", ""),
        "supplier_name": extracted.get("supplier_name", ""),
        "warranty_code": extracted.get("warranty_code", ""),
        "warranty_description": extracted.get("warranty_description", ""),
        "warranty_expiry": import_doc["warranty_info"]["expiry_date"],
        "sla_name": import_doc["warranty_info"]["sla"],
        "equipment": extracted.get("equipment", []),
        "equipment_count": len(extracted.get("equipment", [])),
    }


@router.post("/parse-bulk")
async def parse_invoices_bulk(files: list[UploadFile] = File(...), user: dict = Depends(get_current_user)) -> dict:
    """Upload multiple invoice PDFs. AI extracts equipment from each."""
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 invoices per batch")

    batch_id = str(uuid.uuid4())
    results = []
    errors = []
    total_equipment = 0

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            errors.append({"filename": file.filename, "error": "Not a PDF file"})
            continue
        data = await file.read()
        try:
            from utils.file_validation import validate_upload
            validate_upload(file_bytes=data, filename=file.filename, allowed={"application/pdf"}, max_size=30 * 1024 * 1024)
        except HTTPException as exc:
            errors.append({"filename": file.filename, "error": exc.detail})
            continue

        result = await _parse_single_pdf(data, file.filename, user)
        if "error" in result:
            errors.append(result)
        else:
            total_equipment += result["equipment_count"]
            results.append(result)

    # Store the batch record
    batch_doc = {
        "id": batch_id,
        "user_id": user["id"],
        "import_ids": [r["import_id"] for r in results],
        "total_invoices": len(results),
        "total_equipment": total_equipment,
        "status": "pending_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.equipment_import_batches.insert_one(batch_doc)

    return {
        "batch_id": batch_id,
        "invoices": results,
        "errors": errors,
        "total_invoices": len(results),
        "total_equipment": total_equipment,
    }


@router.post("/confirm-bulk/{batch_id}")
async def confirm_bulk_import(batch_id: str, body: dict = None, user: dict = Depends(get_current_user)) -> dict:
    """Confirm all imports in a batch — creates equipment for each invoice."""
    batch = await db.equipment_import_batches.find_one({"id": batch_id, "user_id": user["id"]})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    body = body or {}
    target_org_id, target_user_id = await _resolve_target_user(body, user)

    # Iter — tag imported equipment with a concrete site (body override, else
    # the org's primary/first site) so per-site portal filters surface it.
    target_site_id = await _resolve_import_site_id(target_org_id, body.get("site_id"))

    total_created = 0
    for import_id in batch.get("import_ids", []):
        imp = await db.equipment_imports.find_one({"id": import_id, "user_id": user["id"]})
        if not imp or imp.get("status") == "imported":
            continue

        extracted = imp.get("extracted_data", {})
        supplier = extracted.get("supplier_name", "")
        site_name = extracted.get("site_name", "")
        account_ref = extracted.get("account_ref", "")
        invoice_number = extracted.get("invoice_number", "")
        default_location = extracted.get("default_location", "") or site_name

        for eq in extracted.get("equipment", []):
            bulk_ctx = {
                "target_user_id": target_user_id, "target_org_id": target_org_id,
                "supplier": supplier, "account_ref": account_ref,
                "invoice_number": invoice_number, "default_location": default_location,
                "import_id": import_id, "batch_id": batch_id, "site_name": site_name,
                "site_id": target_site_id,
            }
            doc = _build_equipment_doc(eq, bulk_ctx)
            await db.equipment.insert_one(doc)
            total_created += 1

        await db.equipment_imports.update_one(
            {"id": import_id},
            {"$set": {"status": "imported", "imported_at": datetime.now(timezone.utc).isoformat(), "batch_id": batch_id}},
        )

        invoice_doc = _build_invoice_doc(imp, bulk_ctx)
        await db.files.insert_one(invoice_doc)

    await db.equipment_import_batches.update_one(
        {"id": batch_id},
        {"$set": {"status": "imported", "imported_at": datetime.now(timezone.utc).isoformat(), "total_created": total_created}},
    )
    from routes.equipment import schedule_image_backfill
    from utils.auth import get_organization_filter
    schedule_image_backfill(get_organization_filter(user))
    return {
        "message": f"{total_created} equipment items imported from {len(batch.get('import_ids', []))} invoices",
        "created": total_created,
    }


@router.get("/download-bulk/{batch_id}")
async def download_bulk_sicon_csv(batch_id: str, mode: str = "combined", user: dict = Depends(get_current_user)) -> StreamingResponse:
    """Download Sicon CSV for a batch. mode=combined (one CSV) or mode=per-invoice (zip of CSVs)."""
    batch = await db.equipment_import_batches.find_one({"id": batch_id, "user_id": user["id"]})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    all_imports = []
    for import_id in batch.get("import_ids", []):
        imp = await db.equipment_imports.find_one({"id": import_id, "user_id": user["id"]})
        if imp:
            all_imports.append(imp)

    if not all_imports:
        raise HTTPException(status_code=404, detail="No invoices found in batch")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(SICON_COLUMNS)

    for imp in all_imports:
        extracted = imp.get("extracted_data", {})
        account_ref = extracted.get("account_ref", "")
        site_name = extracted.get("site_name", "")
        supplier = extracted.get("supplier_name", "")
        invoice_number = extracted.get("invoice_number", "")
        for eq in extracted.get("equipment", []):
            row = _build_sicon_row(eq, account_ref, site_name, supplier, invoice_number)
            writer.writerow([row.get(col, "") for col in SICON_COLUMNS])

    csv_bytes = output.getvalue().encode("utf-8")
    output.close()

    filename = f"Sicon_Bulk_Import_{batch_id[:8]}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_EQUIPMENT_KEYWORDS = {
    "Treadmill": ["treadmill"],
    "Cycle": ["cycle", "bike"],
    "Cross-Trainer": ["elliptical", "cross-trainer"],
    "Rower": ["rower", "rowing"],
    "Stepper": ["stepmill", "stepper"],
    "Strength": [
        "press", "pulldown", "pull", "curl", "smith", "fly", "deltoid",
        "leg", "abdom", "chin", "dip", "abduct", "adduct", "hip", "calf", "row ",
    ],
    "Functional": ["sled", "ski", "ube", "upper body"],
    "Multi-Station": ["multi", "station"],
}


def _build_sicon_row(eq: dict, account_ref: str, site_name: str, supplier: str, invoice_number: str) -> dict:
    """Build a single Sicon CSV row dict from an equipment item."""
    full_desc = (eq.get("description") or eq.get("model") or "").strip()
    short_model = _short_model_code(eq) or eq.get("model", "")
    return {
        "Invoice Customer Ref": account_ref,
        "Location Description": site_name,
        "Sublocation Description": "",
        "Supplier Reference": "",
        "Supplier Name": supplier,
        "Contract Number": "",
        "Contract Line No": "",
        "SLA Name": eq.get("sla_name", ""),
        "Stock Item Code": eq.get("stock_item_code", "") or short_model,
        "Description": full_desc,
        "Make": eq.get("make", supplier),
        "Model": short_model,
        "Serial Number": eq.get("serial_number", ""),
        "Install Date": eq.get("install_date", ""),
        "Manufacturer Warranty Expiry Date": eq.get("warranty_expiry", ""),
        "Last Service Date": "",
        "Service Interval": "Year",
        "Service Period": 1,
        "Next Service Date": eq.get("next_service_date", ""),
        "ID Number": "",
        "Service Template": "",
        "Equipment Group": "",
        "Analysis Code 1": "",
        "Analysis Code 2": eq.get("unit_price", "") or "",
        "Analysis Code 3": invoice_number,
        "Analysis Code 4": eq.get("warranty_code", ""),
    }


def _short_equipment_name(eq: dict) -> str:
    """Iter 216h13 — pick the SHORT subtype noun for the equipment row
    display. Order of preference:
      1. AI-extracted `equipment_name` (new field added to the prompt).
      2. Heuristic from the long description (treadmill / cycle / etc.).
      3. The equipment_category (Cardiovascular, etc.) as last resort.
    Never returns the full marketing line — that goes in `notes`.
    """
    name = (eq.get("equipment_name") or "").strip()
    if name and len(name) <= 40:
        return name
    desc = (eq.get("description") or eq.get("model") or "").lower()
    # Walk a small ordered keyword list — earlier matches win.
    for keyword, label in [
        ("recumbent cycle", "Recumbent Cycle"),
        ("upright cycle", "Upright Cycle"),
        ("indoor cycle", "Indoor Cycle"),
        ("spin bike", "Spin Bike"),
        ("air bike", "Air Bike"),
        ("treadmill", "Treadmill"),
        ("stepmill", "StepMill"),
        ("stair climber", "Stair Climber"),
        ("cross-trainer", "Cross-Trainer"),
        ("cross trainer", "Cross-Trainer"),
        ("elliptical", "Elliptical"),
        ("rower", "Rower"),
        ("ski erg", "Ski Erg"),
        ("smith machine", "Smith Machine"),
        ("lat pulldown", "Lat Pulldown"),
        ("leg press", "Leg Press"),
        ("chest press", "Chest Press"),
        ("cable crossover", "Cable Crossover"),
        ("dumbbell", "Dumbbell"),
        ("kettlebell", "Kettlebell"),
        ("barbell", "Barbell"),
        ("rack", "Rack"),
        ("bench", "Bench"),
    ]:
        if keyword in desc:
            return label
    cat = (eq.get("equipment_category") or "").strip()
    return cat or "Equipment"


def _short_model_code(eq: dict) -> str:
    """Iter 216h13 — use the short part number / stock_item_code as the
    `model` field so equipment rows read 'Pulse Fitness · 260G · 12345'
    instead of pasting the full 200-char marketing description.
    """
    code = (eq.get("stock_item_code") or "").strip()
    if code:
        return code
    raw_model = (eq.get("model") or "").strip()
    # If `model` already looks short (≤ 24 chars, no spaces beyond 2 words)
    # treat it as a code; otherwise return empty so the UI can show "—".
    if raw_model and len(raw_model) <= 24 and raw_model.count(" ") <= 2:
        return raw_model
    return ""


def _build_equipment_doc(eq: dict, ctx: dict) -> dict:
    """Build a single equipment document from extracted invoice data.
    ctx keys: target_user_id, target_org_id, supplier, account_ref,
              invoice_number, default_location, import_id, batch_id

    Iter 216h13 — split AI output into display vs storage:
      - `name`   = SHORT subtype (e.g. 'Treadmill', 'StepMill', 'Upright Cycle')
      - `model`  = SHORT stock code (e.g. '260G', '200H-AAF')
      - `notes`  = "Imported from invoice {n}" + the FULL marketing
                   description (so it's still searchable in the
                   equipment search bar without crowding the row).
    """
    short_name = _short_equipment_name(eq)
    short_model = _short_model_code(eq)
    description = (eq.get("description") or eq.get("model") or "").strip()
    note_parts = [f"Imported from invoice {ctx['invoice_number']}"]
    if ctx.get("batch_id"):
        note_parts.append(f"batch {ctx['batch_id']}")
    if description and description != short_name and description != short_model:
        note_parts.append(description)
    note = " · ".join(note_parts)
    return {
        "id": str(uuid.uuid4()),
        "user_id": ctx["target_user_id"],
        "organization_id": ctx["target_org_id"],
        "name": short_name,
        "equipment_type": _classify_equipment(description or short_name),
        "manufacturer": eq.get("make", ctx["supplier"]),
        "model": short_model,
        "serial_number": eq.get("serial_number", ""),
        "location": eq.get("location", "") or ctx["default_location"],
        "purchase_date": _parse_date_to_iso(eq.get("install_date", "")),
        "purchase_price": eq.get("unit_price", 0),
        "warranty_expiry": _parse_date_to_iso(eq.get("warranty_expiry", "")),
        "warranty_code": eq.get("warranty_code", ""),
        "sla_level": eq.get("sla_name", ""),
        "supplier": ctx["supplier"],
        "account_ref": ctx["account_ref"],
        "invoice_number": ctx["invoice_number"],
        "status": "operational",
        "condition": "excellent",
        "notes": note,
        "description": description,
        "import_id": ctx["import_id"],
        # Iter 216h240 — integration round-trip placeholders. Populated
        # when the AI extractor finds them on the invoice (rare today)
        # or left as None so a later Sicon/Orbit 4 sync can backfill.
        "qr_code": eq.get("qr_code") or None,
        "manufacturing_date": _parse_date_to_iso(eq.get("manufacturing_date", "")) or None,
        "deprecation_date": _parse_date_to_iso(eq.get("deprecation_date", "")) or None,
        "orbit4_asset_id": eq.get("orbit4_asset_id") or None,
        "sicon_equipment_id": eq.get("sicon_equipment_id") or None,
        **({"batch_id": ctx["batch_id"]} if ctx.get("batch_id") else {}),
        **({"site_id": ctx["site_id"]} if ctx.get("site_id") else {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_invoice_doc(imp: dict, ctx: dict) -> dict:
    """Build an invoice document record for the site's documents section.
    ctx keys: target_user_id, target_org_id, supplier, invoice_number,
              site_name, account_ref, import_id, batch_id
    """
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": ctx["target_user_id"],
        "organization_id": ctx["target_org_id"],
        "original_filename": imp.get("original_filename", "Invoice.pdf"),
        "category": "invoice",
        "supplier_name": ctx["supplier"],
        "invoice_number": ctx["invoice_number"],
        "site_name": ctx["site_name"],
        "account_ref": ctx["account_ref"],
        "import_id": ctx["import_id"],
        "storage_path": imp.get("invoice_storage_path", ""),
        "download_url": imp.get("invoice_download_url", ""),
        "content_type": "application/pdf",
        "size": imp.get("invoice_size", 0),
        "content_hash": imp.get("invoice_content_hash", ""),
        "is_import_invoice": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if ctx.get("batch_id"):
        doc["batch_id"] = ctx["batch_id"]
    return doc


async def _resolve_target_user(body: dict, user: dict) -> tuple[str, str]:
    """Determine target org and user for an import confirmation."""
    target_org_id = body.get("target_organization_id") or user.get("organization_id")
    target_user_id = user["id"]
    if body.get("target_organization_id") and body["target_organization_id"] != user.get("organization_id"):
        org_owner = await db.users.find_one(
            {"organization_id": body["target_organization_id"], "role": "owner"}, {"_id": 0, "id": 1},
        )
        if org_owner:
            target_user_id = org_owner["id"]
    return target_org_id, target_user_id


def _classify_equipment(model: str) -> str:
    """Classify equipment type from model name using keyword lookup."""
    model_lower = model.lower()
    for category, keywords in _EQUIPMENT_KEYWORDS.items():
        if any(kw in model_lower for kw in keywords):
            return category
    return "Other"


def _parse_date_to_iso(date_str: str) -> str:
    """Convert dd/mm/yyyy to ISO format."""
    if not date_str:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    return date_str
