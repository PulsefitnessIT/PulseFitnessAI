from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from datetime import datetime, timezone
from typing import Optional
import uuid
import logging
import base64
import json as json_module

from utils.database import db, EMERGENT_LLM_KEY
from utils.auth import get_current_user
from models.schemas import GymLayoutCreate
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/gym-layouts")
async def create_gym_layout(layout: GymLayoutCreate, user: dict = Depends(get_current_user)):
    layout_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        **layout.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.gym_layouts.insert_one(layout_doc)
    layout_doc.pop('_id', None)
    return layout_doc


@router.get("/gym-layouts")
async def get_gym_layouts(user: dict = Depends(get_current_user)):
    layouts = await db.gym_layouts.find({"user_id": user['id']}, {"_id": 0}).sort("updated_at", -1).to_list(50)
    return {"layouts": layouts}


_UNIT_DIVISORS = {"cm": 100, "mm": 1000}


def _extract_numeric(val) -> tuple[float | None, str]:
    """Extract numeric value and unit suffix from a dimension value."""
    if val is None:
        return None, ""
    if isinstance(val, (int, float)):
        return float(val), ""
    v = str(val).strip().lower()
    for unit in ("cm", "mm"):
        if unit in v:
            try:
                return float(v.replace(unit, "").strip()), unit
            except ValueError:
                return None, ""
    try:
        return float(v), ""
    except ValueError:
        return None, ""


def _guess_unit_from_hint(key_hint: str) -> str:
    """Infer unit from key name (e.g. 'length_cm' → 'cm')."""
    h = key_hint.lower()
    for unit in ("cm", "mm"):
        if f"_{unit}" in h or unit in h:
            return unit
    return ""


def _parse_dim_to_meters(val, key_hint: str = "") -> float | None:
    """Convert dimension value to meters, using key name as unit hint."""
    num, unit = _extract_numeric(val)
    if num is None:
        return None
    unit = unit or _guess_unit_from_hint(key_hint)
    if unit in _UNIT_DIVISORS:
        return round(num / _UNIT_DIVISORS[unit], 3)
    # Guess from magnitude
    if num > 500:
        return round(num / 1000, 3)
    if num > 10:
        return round(num / 100, 3)
    return round(num, 3)


_DIM_LENGTH_KEYS = ("length_cm", "length_mm", "length")
_DIM_WIDTH_KEYS = ("width_cm", "width_mm", "width")
_FALLBACK_LENGTH_KEYS = ("length", "product_length")
_FALLBACK_WIDTH_KEYS = ("width", "product_width")


def _resolve_dimensions(spec: dict | None) -> tuple[float | None, float | None]:
    """Extract length_m and width_m from a spec sheet document."""
    if not spec:
        return None, None
    ks = spec.get("key_specs", {})
    dims = ks.get("dimensions") or ks.get("dimensions_mm") or {}
    length_m = _search_dim(dims, _DIM_LENGTH_KEYS) if isinstance(dims, dict) else None
    width_m = _search_dim(dims, _DIM_WIDTH_KEYS) if isinstance(dims, dict) else None
    if not length_m:
        length_m = _search_dim(ks, _FALLBACK_LENGTH_KEYS)
    if not width_m:
        width_m = _search_dim(ks, _FALLBACK_WIDTH_KEYS)
    return length_m, width_m


def _search_dim(source: dict, keys: tuple) -> float | None:
    """Try multiple keys in a dict, returning the first valid parsed dimension."""
    for dk in keys:
        if dk in source:
            val = _parse_dim_to_meters(source[dk], dk)
            if val:
                return val
    return None


def _build_equipment_entry(eq: dict, specs: dict, type_numbers: dict, counter_ref: list) -> dict:
    """Build a single equipment dimension entry."""
    etype = eq.get("equipment_type") or eq.get("name", "Unknown")
    model = eq.get("model") or ""
    key = f"{etype}|{model}" if model else etype
    if key not in type_numbers:
        type_numbers[key] = counter_ref[0]
        counter_ref[0] += 1

    length_m, width_m = _resolve_dimensions(specs.get(eq.get("spec_sheet_id")))
    return {
        "id": eq["id"], "name": eq.get("name", ""),
        "equipment_type": eq.get("equipment_type", ""),
        "manufacturer": eq.get("manufacturer", ""),
        "serial_number": eq.get("serial_number", ""),
        "model": model, "number": type_numbers[key],
        "length_m": round(length_m, 2) if length_m else None,
        "width_m": round(width_m, 2) if width_m else None,
        "spec_sheet_id": eq.get("spec_sheet_id"),
    }


@router.get("/gym-layouts/equipment-dimensions")
async def get_equipment_dimensions(user: dict = Depends(get_current_user)) -> dict:
    """Return equipment with resolved dimensions from spec sheets."""
    from utils.auth import get_organization_filter
    org_filter = get_organization_filter(user)
    equipment = await db.equipment.find(org_filter, {"_id": 0}).to_list(500)
    spec_ids = list({e.get("spec_sheet_id") for e in equipment if e.get("spec_sheet_id")})
    specs = {}
    if spec_ids:
        for s in await db.spec_sheets.find({"id": {"$in": spec_ids}}, {"_id": 0}).to_list(500):
            specs[s["id"]] = s

    type_numbers: dict[str, int] = {}
    counter_ref = [1]
    results = [_build_equipment_entry(eq, specs, type_numbers, counter_ref) for eq in equipment]

    legend = [{"number": v, "label": k.split("|")[0], "model": k.split("|")[1] if "|" in k else ""} for k, v in type_numbers.items()]
    return {"equipment": results, "legend": sorted(legend, key=lambda x: x["number"])}




@router.get("/gym-layouts/{layout_id}")
async def get_gym_layout(layout_id: str, user: dict = Depends(get_current_user)):
    layout = await db.gym_layouts.find_one({"id": layout_id, "user_id": user['id']}, {"_id": 0})
    if not layout:
        raise HTTPException(status_code=404, detail="Layout not found")
    return layout


@router.patch("/gym-layouts/{layout_id}")
async def update_gym_layout(layout_id: str, layout: GymLayoutCreate, user: dict = Depends(get_current_user)):
    result = await db.gym_layouts.update_one(
        {"id": layout_id, "user_id": user['id']},
        {"$set": {**layout.model_dump(), "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Layout not found")
    return {"success": True}


@router.delete("/gym-layouts/{layout_id}")
async def delete_gym_layout(layout_id: str, user: dict = Depends(get_current_user)):
    result = await db.gym_layouts.delete_one({"id": layout_id, "user_id": user['id']})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Layout not found")
    return {"success": True}


def _convert_pdf_to_image(contents: bytes, filename: str | None) -> tuple[bytes, str] | None:
    """Convert the first page of a PDF to PNG bytes. Returns (image_bytes, content_type) or None."""
    try:
        from pdf2image import convert_from_bytes
        import io
        images = convert_from_bytes(contents, first_page=1, last_page=1, dpi=300)
        if images:
            buf = io.BytesIO()
            images[0].save(buf, format='PNG')
            return buf.getvalue(), 'image/png'
    except Exception as exc:
        logger.error("PDF conversion failed: %s", exc)
    return None


def _build_annotation_context(user_annotations: list[dict]) -> str:
    """Build annotation context string for the AI prompt."""
    if not user_annotations:
        return ""
    lines = [
        "\n\nCRITICAL REFERENCE — The user has manually identified these specific equipment "
        "on the floor plan image:",
    ]
    for ann in user_annotations:
        lines.append(
            f"- {ann.get('name', 'Unknown')} at image position "
            f"({ann.get('x_percent', 0):.0f}% from left, {ann.get('y_percent', 0):.0f}% from top)"
        )
    lines.append(
        "\nThese positions tell you EXACTLY what each equipment type looks like on this "
        "specific drawing style/symbology.\n"
        "Use these as anchors: find ALL remaining machines of the same types throughout the floor plan.\n"
        "Also identify any other gym equipment visible that the user did not mark.\n"
        "You MUST include the user-identified equipment in your response as well."
    )
    return "\n".join(lines)


def _parse_ai_json(raw: str) -> dict:
    """Strip markdown fences from an LLM response and parse JSON."""
    clean = raw.strip()
    if clean.startswith('```'):
        clean = clean.split('\n', 1)[1] if '\n' in clean else clean[3:]
        clean = clean.rsplit('```', 1)[0]
    if clean.startswith('json'):
        clean = clean[4:].strip()
    return json_module.loads(clean)


_DETECT_EMPTY: dict = {"equipment": [], "total_count": 0}


def _build_detect_system_msg(annotation_context: str) -> str:
    """Build the system message for equipment detection from floor plan images."""
    return (
        "You are an expert at analysing gym floor plan images and identifying gym equipment. "
        "You can read architectural floor plans, CAD drawings, annotated layouts, and photographs of gym spaces.\n\n"
        "When given a floor plan image:\n"
        "1. FIRST look for a KEY / LEGEND table on the drawing. If a legend exists, use it as your PRIMARY source.\n"
        "2. Then look at the floor plan itself for numbered labels, codes, or icons.\n"
        "3. If no legend is present, identify equipment from their visual shapes and text labels.\n"
        "4. Count EVERY individual machine separately.\n"
        f"5. Estimate positions relative to the overall image dimensions.{annotation_context}\n\n"
        "Return ONLY a valid JSON object with: equipment (array of type/name/x_percent/y_percent/width_m/length_m), "
        "total_count, notes. Return ONLY the JSON, no markdown fences."
    )


def _prepare_image(contents: bytes, content_type: str, filename: str | None) -> tuple[str, str] | None:
    """Convert uploaded file to base64 image, handling PDF conversion."""
    if content_type == 'application/pdf' or (filename and filename.lower().endswith('.pdf')):
        result = _convert_pdf_to_image(contents, filename)
        if not result:
            return None
        contents, content_type = result
    return base64.b64encode(contents).decode('utf-8'), content_type


def _parse_annotations(raw: str | None) -> list[dict]:
    """Safely parse user annotation JSON."""
    if not raw:
        return []
    import contextlib
    with contextlib.suppress(json_module.JSONDecodeError, TypeError):
        return json_module.loads(raw)
    return []


async def _call_detection_ai(b64_image: str, user_annotations: list[dict], user_id: str) -> dict:
    """Send image to GPT vision and return parsed equipment data."""
    system_msg = _build_detect_system_msg(_build_annotation_context(user_annotations))
    hint = " The user has marked specific equipment examples on this image — use those as anchors." if user_annotations else ""

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"gym_detect_{user_id}_{datetime.now().timestamp()}",
        system_message=system_msg,
    ).with_model("openai", "gpt-4o")

    response = await chat.send_message(UserMessage(
        text=f"This is a gym floor plan.{hint} Identify every piece of gym equipment visible. Return only valid JSON.",
        file_contents=[ImageContent(image_base64=b64_image)],
    ))
    return _parse_ai_json(response)


@router.post("/gym-layouts/detect-equipment")
async def detect_equipment_from_image(
    file: UploadFile = File(...),
    annotations: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
) -> dict:
    """Use GPT vision to detect gym equipment from a floor plan image."""
    from utils.file_validation import validate_upload, MIME_IMAGES
    contents = await file.read()
    # Allow PDF floor-plans too — they get rasterised inside _prepare_image.
    ct = validate_upload(
        file_bytes=contents, filename=file.filename,
        allowed=MIME_IMAGES | {"application/pdf"},
        max_size=20 * 1024 * 1024,
    )
    content_type = ct or 'image/png'

    prepared = _prepare_image(contents, content_type, file.filename)
    if prepared is None:
        return {**_DETECT_EMPTY, "notes": "Failed to convert PDF to image for analysis."}
    b64_image = prepared[0]

    user_annotations = _parse_annotations(annotations)

    try:
        return await _call_detection_ai(b64_image, user_annotations, user['id'])
    except json_module.JSONDecodeError:
        logger.error("Failed to parse AI JSON response for equipment detection")
        return {**_DETECT_EMPTY, "notes": "AI could not parse the floor plan. Try uploading a clearer image."}
    except Exception as exc:
        logger.error("Equipment detection failed: %s", exc)
        return {**_DETECT_EMPTY, "notes": f"Detection failed: {exc!s}"}
