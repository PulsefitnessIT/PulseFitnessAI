from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response
from datetime import datetime, timezone
import uuid
import json
import re
import logging

from utils.database import db, EMERGENT_LLM_KEY, APP_NAME, put_object, get_object
from utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/spec-sheets", tags=["Spec Sheets"])


def _extract_pdf_content(data: bytes) -> tuple[str, bytes | None, str]:
    """Extract text and the largest image from a PDF. Returns (text, image_bytes, image_ext)."""
    import fitz
    pdf_text = ""
    hero_image_data: bytes | None = None
    hero_image_ext = "png"

    doc = fitz.open(stream=data, filetype="pdf")
    for page in doc:
        pdf_text += page.get_text()

    largest_size = 0
    for page_num in range(len(doc)):
        for img_info in doc[page_num].get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                if base_image and len(base_image["image"]) > largest_size:
                    largest_size = len(base_image["image"])
                    hero_image_data = base_image["image"]
                    hero_image_ext = base_image.get("ext", "png")
            except Exception:
                continue
    doc.close()
    return pdf_text, hero_image_data, hero_image_ext


async def _ai_extract_spec(pdf_text: str, filename: str) -> dict:
    """Use LLM to extract structured spec data from PDF text."""
    prompt = (
        "You are analysing a gym equipment spec sheet / product datasheet.\n\n"
        "Extract the following:\n"
        "1. **equipment_model**: Full product/model name\n"
        "2. **equipment_type**: Category — Treadmill, Cycle, Cross-Trainer, Rower, Stepper, Strength, Functional, Multi-Station, Other\n"
        "3. **manufacturer**: Brand/manufacturer\n"
        "4. **key_specs**: Object with dimensions, weight, max_user_weight, console, etc.\n"
        "5. **description**: 1-2 sentence product description\n\n"
        "Return ONLY valid JSON:\n"
        '{"equipment_model":"string","equipment_type":"string","manufacturer":"string","description":"string","key_specs":{}}\n\n'
        f"SPEC SHEET TEXT:\n{pdf_text[:8000]}"
    )
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        llm = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=str(uuid.uuid4()),
            system_message="You extract structured data from equipment spec sheets. Return ONLY valid JSON.",
        ).with_model("openai", "gpt-5.2")
        response = await llm.send_message(UserMessage(text=prompt))

        raw = response.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)
    except Exception as exc:
        logger.error("AI spec extraction failed: %s", exc)
        return {
            "equipment_model": filename.rsplit(".", 1)[0],
            "equipment_type": "Other",
            "manufacturer": "Pulse Fitness",
            "description": "", "key_specs": {},
        }


def _store_hero_image(hero_data: bytes | None, hero_ext: str, spec_id: str) -> str:
    """Upload hero image and return URL, or empty string."""
    if not hero_data or len(hero_data) <= 5000:
        return ""
    ct = f"image/{hero_ext}" if hero_ext != "jpg" else "image/jpeg"
    result = put_object(f"{APP_NAME}/spec-sheets/images/{spec_id}.{hero_ext}", hero_data, ct)
    return result.get("url", result["path"])


@router.post("/upload")
async def upload_spec_sheet(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    """Upload a single spec sheet PDF. AI extracts model name, specs, and hero image."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 30MB)")

    # Sniff real bytes — reject anything that isn't a PDF, even if the
    # client sends ``Content-Type: application/pdf``.
    from utils.file_validation import validate_upload
    validate_upload(file_bytes=data, filename=file.filename, allowed={"application/pdf"})

    try:
        pdf_text, hero_data, hero_ext = _extract_pdf_content(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc!s}")
    if len(pdf_text) < 20:
        raise HTTPException(status_code=400, detail="Could not extract text from PDF")

    extracted = await _ai_extract_spec(pdf_text, file.filename or "spec_sheet")
    from utils.pdf_compress import compress_pdf
    spec_id = str(uuid.uuid4())
    pdf_result = put_object(f"{APP_NAME}/spec-sheets/{spec_id}.pdf", compress_pdf(data), "application/pdf")
    hero_url = _store_hero_image(hero_data, hero_ext, spec_id)

    spec_doc = {
        "id": spec_id, "original_filename": file.filename,
        "equipment_model": extracted.get("equipment_model", ""), "equipment_type": extracted.get("equipment_type", "Other"),
        "manufacturer": extracted.get("manufacturer", "Pulse Fitness"), "product_level": _derive_product_level(file.filename),
        "description": extracted.get("description", ""), "key_specs": extracted.get("key_specs", {}),
        "pdf_path": pdf_result["path"], "pdf_url": pdf_result.get("url", pdf_result["path"]),
        "hero_image_url": hero_url, "hero_image_ext": hero_ext if hero_data else "",
        "matched_equipment_ids": [], "uploaded_by": user["id"], "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.spec_sheets.insert_one(spec_doc)
    match_count = await _auto_match_spec_sheet(spec_doc)

    return {
        "id": spec_id, "equipment_model": extracted.get("equipment_model", ""),
        "equipment_type": extracted.get("equipment_type", ""), "manufacturer": extracted.get("manufacturer", ""),
        "description": extracted.get("description", ""), "hero_image_url": hero_url,
        "matched_count": match_count, "filename": file.filename,
    }


@router.post("/upload-bulk")
async def upload_spec_sheets_bulk(files: list[UploadFile] = File(...), user: dict = Depends(get_current_user)) -> dict:
    """Upload multiple spec sheet PDFs at once."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 spec sheets per batch")

    results = []
    errors = []

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            errors.append({"filename": file.filename, "error": "Not a PDF"})
            continue
        try:
            # Reuse single upload logic by reading file and calling internal
            file_data = await file.read()
            # Reset file position for potential re-read
            result = await _process_spec_sheet(file_data, file.filename, user)
            results.append(result)
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})

    return {
        "uploaded": len(results),
        "errors": errors,
        "spec_sheets": results,
    }


@router.get("/list")
async def list_spec_sheets(user: dict = Depends(get_current_user)) -> dict:
    """List all spec sheets."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    specs = await db.spec_sheets.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"spec_sheets": specs, "count": len(specs)}


@router.delete("/{spec_id}")
async def delete_spec_sheet(spec_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Delete a spec sheet and remove it from matched equipment."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    spec = await db.spec_sheets.find_one({"id": spec_id}, {"_id": 0})
    if not spec:
        raise HTTPException(status_code=404, detail="Spec sheet not found")

    # Remove spec_sheet_id from all matched equipment
    await db.equipment.update_many(
        {"spec_sheet_id": spec_id},
        {"$unset": {"spec_sheet_id": "", "spec_sheet_image": "", "spec_sheet_url": ""}},
    )

    await db.spec_sheets.delete_one({"id": spec_id})
    return {"success": True, "message": f"Spec sheet '{spec.get('equipment_model')}' deleted"}


@router.post("/{spec_id}/rematch")
async def rematch_spec_sheet(spec_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Re-run AI matching for a spec sheet against all equipment."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    spec = await db.spec_sheets.find_one({"id": spec_id}, {"_id": 0})
    if not spec:
        raise HTTPException(status_code=404, detail="Spec sheet not found")

    match_count = await _auto_match_spec_sheet(spec)
    return {"matched_count": match_count}


@router.get("/for-equipment/{equipment_id}")
async def get_spec_for_equipment(equipment_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Get spec sheet data for a specific equipment item."""
    equip = await db.equipment.find_one({"id": equipment_id}, {"_id": 0, "spec_sheet_id": 1})
    if not equip or not equip.get("spec_sheet_id"):
        return {"spec_sheet": None}

    spec = await db.spec_sheets.find_one({"id": equip["spec_sheet_id"]}, {"_id": 0})
    return {"spec_sheet": spec}


@router.get("/pdf/{spec_id}")
async def get_spec_sheet_pdf(spec_id: str) -> Response:
    """Serve the spec sheet PDF for inline viewing."""
    spec = await db.spec_sheets.find_one({"id": spec_id}, {"_id": 0, "pdf_path": 1})
    if not spec or not spec.get("pdf_path"):
        raise HTTPException(status_code=404, detail="Spec sheet not found")

    try:
        data, content_type = get_object(spec["pdf_path"])
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=spec_{spec_id}.pdf"},
        )
    except Exception:
        raise HTTPException(status_code=404, detail="PDF file not found in storage")


@router.get("/image/{spec_id}")
async def get_spec_sheet_image(spec_id: str) -> Response:
    """Serve the hero image extracted from the spec sheet."""
    spec = await db.spec_sheets.find_one({"id": spec_id}, {"_id": 0, "hero_image_url": 1, "hero_image_ext": 1})
    if not spec or not spec.get("hero_image_url"):
        raise HTTPException(status_code=404, detail="Image not found")

    url = spec["hero_image_url"]
    if url.startswith("http"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=url)

    try:
        data, content_type = get_object(url)
        return Response(content=data, media_type=content_type)
    except Exception:
        raise HTTPException(status_code=404, detail="Image file not found in storage")


@router.post("/backfill-levels")
async def backfill_product_levels(user: dict = Depends(get_current_user)) -> dict:
    """Backfill product_level from filenames for all spec sheets."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    specs = await db.spec_sheets.find({}, {"_id": 0, "id": 1, "original_filename": 1}).to_list(500)
    updated = 0
    for s in specs:
        level = _derive_product_level(s.get("original_filename", ""))
        if level:
            await db.spec_sheets.update_one({"id": s["id"]}, {"$set": {"product_level": level}})
            updated += 1
    return {"updated": updated, "total": len(specs)}


@router.post("/compress-existing")
async def compress_existing_spec_sheets(user: dict = Depends(get_current_user)) -> dict:
    """One-time compression of all existing stored spec sheet PDFs."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")

    from utils.pdf_compress import compress_pdf
    specs = await db.spec_sheets.find({}, {"_id": 0, "id": 1, "pdf_path": 1}).to_list(500)
    compressed_count = 0
    total_saved = 0

    for s in specs:
        pdf_path = s.get("pdf_path", "")
        if not pdf_path:
            continue
        try:
            original_data, _ = get_object(pdf_path)
            original_size = len(original_data)
            compressed_data = compress_pdf(original_data)
            compressed_size = len(compressed_data)
            if compressed_size < original_size:
                put_object(pdf_path, compressed_data, "application/pdf")
                total_saved += original_size - compressed_size
                compressed_count += 1
        except Exception:
            continue

    return {
        "compressed": compressed_count,
        "total": len(specs),
        "bytes_saved": total_saved,
        "mb_saved": round(total_saved / (1024 * 1024), 2),
    }


# ── Internal helpers ──────────────────────────────────────────────

def _derive_product_level(filename: str) -> str:
    """Extract product level (Classic/Club Line/Premium/Dual) from filename."""
    fn = filename.lower()
    if "premium" in fn:
        return "Premium"
    if "club line" in fn or "club_line" in fn:
        return "Club Line"
    if "classic" in fn:
        return "Classic"
    if "dual" in fn:
        return "Dual"
    return ""


async def _process_spec_sheet(data: bytes, filename: str, user: dict) -> dict:
    """Process a single spec sheet PDF — extract info, store, match."""
    pdf_text, hero_data, hero_ext = _extract_pdf_content(data)
    extracted = await _ai_extract_spec(pdf_text, filename)

    from utils.pdf_compress import compress_pdf
    spec_id = str(uuid.uuid4())
    pdf_result = put_object(f"{APP_NAME}/spec-sheets/{spec_id}.pdf", compress_pdf(data), "application/pdf")

    hero_url = ""
    if hero_data and len(hero_data) > 5000:
        ct = f"image/{hero_ext}" if hero_ext != "jpg" else "image/jpeg"
        img_result = put_object(f"{APP_NAME}/spec-sheets/images/{spec_id}.{hero_ext}", hero_data, ct)
        hero_url = img_result.get("url", img_result["path"])

    spec_doc = {
        "id": spec_id, "original_filename": filename,
        "equipment_model": extracted.get("equipment_model", ""), "equipment_type": extracted.get("equipment_type", "Other"),
        "manufacturer": extracted.get("manufacturer", "Pulse Fitness"), "product_level": _derive_product_level(filename),
        "description": extracted.get("description", ""), "key_specs": extracted.get("key_specs", {}),
        "pdf_path": pdf_result["path"], "pdf_url": pdf_result.get("url", pdf_result["path"]),
        "hero_image_url": hero_url, "hero_image_ext": hero_ext if hero_data else "",
        "matched_equipment_ids": [], "uploaded_by": user["id"], "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.spec_sheets.insert_one(spec_doc)
    match_count = await _auto_match_spec_sheet(spec_doc)

    return {
        "id": spec_id, "equipment_model": extracted.get("equipment_model", ""),
        "equipment_type": extracted.get("equipment_type", ""), "manufacturer": extracted.get("manufacturer", ""),
        "hero_image_url": hero_url, "matched_count": match_count, "filename": filename,
    }


_KEYWORD_PATTERNS: list[str] = [
    'stepmill', 'treadmill', 'cross trainer', 'cross-trainer', 'crossclimb',
    'upright cycle', 'upright bike', 'recumbent cycle', 'recumbent bike',
    'airbike', 'air bike', 'rower', 'indoor rower', 'step ',
    'chest press', 'shoulder press', 'lat pulldown', 'leg press',
    'leg extension', 'leg curl', 'abdominal', 'lower back', 'glute',
    'adductor', 'abductor', 'pec deck', 'pec fly', 'rear deltoid',
    'tricep', 'arm curl', 'seated row', 'chin', 'dip', 'hack squat',
    'calf', 'hip', 'deltoid', 'long pull', 'multi hip', 'rotary torso',
    'ski erg', 'multi-pulley', 'multi pulley',
]


def _extract_model_codes(model_name: str) -> list[str]:
    """Extract product model codes like '200H', '260G', '38-600' from a model name."""
    codes = re.findall(r'\b(\d{2,4}[HGCDF])\b', model_name, re.IGNORECASE)
    codes += re.findall(r'\b(\d{2}-\d{3}(?:-\d)?)\b', model_name)
    return codes


def _extract_product_keywords(model_lower: str, filename: str) -> list[str]:
    """Return product keyword matches found in model name or filename."""
    return [kw for kw in _KEYWORD_PATTERNS if kw in model_lower or kw in filename]


def _derive_spec_level(product_level: str, filename: str) -> str:
    """Derive the product level from metadata or filename."""
    if product_level:
        return product_level
    for level in ("premium", "club line", "classic"):
        if level in filename:
            return level
    return ""


def _equipment_matches(eq_combined: str, model_codes: list[str], keywords: list[str], spec_level: str) -> bool:
    """Check whether a single equipment item matches the spec sheet."""
    if any(code.lower() in eq_combined for code in model_codes):
        return True
    if not keywords:
        return False
    if not any(kw in eq_combined for kw in keywords):
        return False
    if not spec_level:
        return True
    eq_level = ""
    for level in ("premium", "club line", "classic"):
        if level in eq_combined:
            eq_level = level
            break
    return eq_level == spec_level or not eq_level


async def _persist_spec_matches(spec: dict, matched_ids: list[str]) -> None:
    """Write match results to equipment and spec_sheets collections."""
    await db.equipment.update_many(
        {"id": {"$in": matched_ids}},
        {"$set": {
            "spec_sheet_id": spec["id"],
            "spec_sheet_image": spec.get("hero_image_url", ""),
            "spec_sheet_url": spec.get("pdf_url", ""),
        }},
    )
    await db.spec_sheets.update_one(
        {"id": spec["id"]},
        {"$set": {"matched_equipment_ids": matched_ids, "matched_count": len(matched_ids)}},
    )


async def _auto_match_spec_sheet(spec: dict) -> int:
    """Match spec sheet to equipment by product name and level."""
    model_name = (spec.get("equipment_model") or "").strip()
    if not model_name:
        return 0

    model_lower = model_name.lower()
    filename = (spec.get("original_filename") or "").lower()
    model_codes = _extract_model_codes(model_name)
    keywords = _extract_product_keywords(model_lower, filename)
    spec_level = _derive_spec_level((spec.get("product_level") or "").lower(), filename)

    all_equipment = await db.equipment.find({}, {"_id": 0, "id": 1, "name": 1, "model": 1}).to_list(2000)
    matched_ids = [
        equip["id"]
        for equip in all_equipment
        if _equipment_matches(
            f"{(equip.get('name') or '').lower()} {(equip.get('model') or '').lower()}",
            model_codes, keywords, spec_level,
        )
    ]

    if matched_ids:
        await _persist_spec_matches(spec, matched_ids)
    return len(matched_ids)



# ──────────────────────────────────────────────────────────────────────
# Iter 216bn — auto-match a single equipment item against existing
# uploaded spec sheets when it's created or imported. The legacy
# direction (spec sheet → match all equipment) already exists at
# `_auto_match_spec_sheet`. This is the inverse.
# ──────────────────────────────────────────────────────────────────────
async def auto_match_equipment_to_specs(equipment: dict) -> dict:
    """Return {spec_sheet_id, hero_image_url, pdf_url} when a matching
    spec sheet exists; empty dict otherwise. Caller is responsible for
    persisting these onto the equipment row.
    """
    eq_name = (equipment.get("name") or "").lower()
    eq_model = (equipment.get("model") or "").lower()
    if not eq_name and not eq_model:
        return {}
    eq_combined = f"{eq_name} {eq_model}".strip()

    # All spec sheets are global (master-admin uploads) — match across
    # the whole collection, not org-scoped.
    cursor = db.spec_sheets.find(
        {}, {"_id": 0, "id": 1, "equipment_model": 1, "product_level": 1,
             "original_filename": 1, "hero_image_url": 1, "pdf_url": 1},
    )
    candidates = await cursor.to_list(500)
    for spec in candidates:
        model_name = (spec.get("equipment_model") or "").strip()
        if not model_name:
            continue
        filename = (spec.get("original_filename") or "").lower()
        codes = _extract_model_codes(model_name)
        keywords = _extract_product_keywords(model_name.lower(), filename)
        level = _derive_spec_level((spec.get("product_level") or "").lower(), filename)
        if _equipment_matches(eq_combined, codes, keywords, level):
            return {
                "spec_sheet_id": spec["id"],
                "spec_sheet_image": spec.get("hero_image_url", ""),
                "spec_sheet_url": spec.get("pdf_url", ""),
            }
    return {}
