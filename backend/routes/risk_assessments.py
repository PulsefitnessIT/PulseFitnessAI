from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid
import base64
import json as json_module
import logging

from utils.database import db, EMERGENT_LLM_KEY, APP_NAME, put_object
from utils.auth import get_current_user, get_organization_filter
from models.schemas import RiskAssessmentCreate
# emergentintegrations (litellm) imported lazily inside functions to keep it off the startup import path

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/risk-assessments")
async def create_risk_assessment(ra: RiskAssessmentCreate, user: dict = Depends(get_current_user)):
    hazards = []
    for h in ra.hazards:
        plr = int(h.get('plr', 1))
        psr = int(h.get('psr', 1))
        rrn = plr * psr
        post_plr = int(h.get('post_plr', plr))
        post_psr = int(h.get('post_psr', psr))
        post_rrn = post_plr * post_psr
        hazards.append({
            **h,
            'plr': plr, 'psr': psr, 'rrn': rrn,
            'post_plr': post_plr, 'post_psr': post_psr, 'post_rrn': post_rrn
        })

    ra_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "organization_id": user.get('organization_id'),
        "title": ra.title,
        "site_name": ra.site_name,
        "assessor": ra.assessor,
        "assessment_date": ra.assessment_date,
        "validity_period": ra.validity_period,
        "hazards": hazards,
        "recommendations": ra.recommendations,
        "notes": ra.notes,
        "photo_url": ra.photo_url,
        "photo_urls": ra.photo_urls or ([ra.photo_url] if ra.photo_url else []),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.risk_assessments.insert_one(ra_doc)
    ra_doc.pop('_id', None)
    return ra_doc


@router.get("/risk-assessments")
async def get_risk_assessments(user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    assessments = await db.risk_assessments.find(org_filter, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"assessments": assessments}


@router.get("/risk-assessments/{ra_id}")
async def get_risk_assessment(ra_id: str, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    ra = await db.risk_assessments.find_one({"id": ra_id, **org_filter}, {"_id": 0})
    if not ra:
        raise HTTPException(status_code=404, detail="Risk assessment not found")
    return ra


_RISK_SYSTEM_MSG = """You are an expert health & safety risk assessor for gyms and fitness facilities ONLY.
Generate a comprehensive risk assessment following this exact JSON format. Return ONLY valid JSON array.
Each hazard object: hazard, harm, who, recommended_controls, controls_in_place, plr (1-6), psr (1-6), further_controls (empty string), post_plr (1-6), post_psr (1-6).
CRITICAL: Be realistic. Most gym hazards: PLR 1-3, PSR 2-4. Only life-threatening = PSR 5-6. After controls, post values LOWER than pre. Do NOT inflate."""

_RISK_FALLBACK = [
    {"hazard": "Manual Handling", "harm": "Musculoskeletal injuries", "who": "Staff, Engineers", "recommended_controls": "Manual handling training, use mechanical aids", "controls_in_place": "Staff training provided", "plr": 2, "psr": 3, "further_controls": "", "post_plr": 1, "post_psr": 2},
    {"hazard": "Slips, Trips and Falls", "harm": "Injuries from wet floors, loose cables", "who": "Staff, Members", "recommended_controls": "Regular cleaning, cable management", "controls_in_place": "Cleaning schedule", "plr": 2, "psr": 2, "further_controls": "", "post_plr": 1, "post_psr": 2},
    {"hazard": "Electrical Hazards", "harm": "Electric shock from faulty equipment", "who": "Staff, Engineers", "recommended_controls": "PAT testing, de-energize before repair", "controls_in_place": "Annual PAT testing", "plr": 1, "psr": 4, "further_controls": "", "post_plr": 1, "post_psr": 3},
]


@router.post("/risk-assessments/ai-generate")
async def ai_generate_risk_assessment(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    site_name = data.get('site_name', 'Gym')
    equipment_types = data.get('equipment_types', [])
    focus = data.get('specific_focus', '') or (', '.join(equipment_types) if equipment_types else 'General gym equipment')

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"risk_{datetime.now().timestamp()}", system_message=_RISK_SYSTEM_MSG).with_model("openai", "gpt-5.2")
        prompt = (
            f"Generate a risk assessment for:\nSite: {site_name}\n"
            f"SPECIFIC FOCUS: {focus}\nDescription: {data.get('site_description', '') or 'Standard commercial gym'}\n"
            f"Assessor: {data.get('assessor', 'N/A')}\nDate: {data.get('assessment_date', 'N/A')}\n\n"
            f"Only generate hazards for \"{focus}\". Return JSON array of 4-8 hazard objects, no markdown."
        )
        raw = (await chat.send_message(UserMessage(text=prompt))).strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0]
        return {"hazards": json_module.loads(raw)}
    except Exception as e:
        logger.error(f"AI risk assessment failed: {e}")
        return {"hazards": _RISK_FALLBACK}


_RA_VISION_SYSTEM = """You are an expert health & safety risk assessor for gyms and fitness facilities.
You are given one or more PHOTOGRAPHS. Analyse what is ACTUALLY VISIBLE in the images — the
specific equipment, its condition, cabling, flooring, spacing, signage, guarding, leaks, damage,
trip hazards, etc. Do NOT invent hazards that are not supported by the photos.

Return ONLY valid JSON (no markdown, no extra text) in this exact shape:
{
  "equipment_identified": "what you can actually see across the photos (be specific — make/type if legible)",
  "environment_observations": "concrete observations visible in the photos (flooring, cabling, spacing, signage, damage...)",
  "hazards": [
    {"hazard": "...", "harm": "...", "who": "Staff / Members / Engineers", "recommended_controls": "...", "controls_in_place": "", "plr": 3, "psr": 3, "further_controls": "", "post_plr": 2, "post_psr": 2}
  ],
  "follow_up_questions": ["question1", "question2"]
}
Scoring: PLR/PSR are 1-6. Be realistic — most gym hazards PLR 1-3, PSR 2-4; only life-threatening PSR 5-6.
post_plr/post_psr must be LOWER than the pre-control values. Base every hazard on visible evidence."""


@router.post("/risk-assessments/photo-analyze")
async def analyze_photo_for_risk(
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    """Vision-based risk-assessment photo analysis.

    Accepts one OR MORE photos, stores them, and sends the ACTUAL images to a
    vision model so the AI assesses what is really in the picture (previously
    it only received the filename as text and hallucinated a generic result).
    """
    from utils.file_validation import validate_upload, MIME_IMAGES

    if not files:
        raise HTTPException(status_code=400, detail="At least one photo is required")

    photo_urls: list[str] = []
    images_b64: list[str] = []
    for f in files[:8]:  # cap at 8 images per analysis
        data = await f.read()
        if not data:
            continue
        ext = f.filename.split(".")[-1] if f.filename and "." in f.filename else "bin"
        ct = validate_upload(file_bytes=data, filename=f.filename or "photo", allowed=MIME_IMAGES, max_size=15 * 1024 * 1024)
        path = f"{APP_NAME}/ra-photos/{user.get('organization_id', user['id'])}/{uuid.uuid4()}.{ext}"
        result = put_object(path, data, ct)
        photo_urls.append(result.get("url", result["path"]))
        images_b64.append(base64.b64encode(data).decode())

    if not images_b64:
        raise HTTPException(status_code=400, detail="No valid photos provided")

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"ra_photo_{datetime.now().timestamp()}",
            system_message=_RA_VISION_SYSTEM,
        ).with_model("openai", "gpt-4o")  # vision-capable

        prompt = (
            f"Analyse the {len(images_b64)} attached gym photo"
            f"{'s' if len(images_b64) != 1 else ''} for health & safety risk assessment. "
            "Identify the equipment and every hazard you can SEE in the images, then return "
            "the JSON described in your instructions. Consider the photos together as one scene."
        )
        msg = UserMessage(
            text=prompt,
            file_contents=[ImageContent(image_base64=b) for b in images_b64],
        )
        raw = await chat.send_message(msg)

        cleaned = raw.strip()
        if cleaned.startswith('```'):
            cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        parsed = json_module.loads(cleaned)
        parsed["photo_urls"] = photo_urls
        parsed["photo_url"] = photo_urls[0]  # back-compat (single-photo callers)
        return parsed
    except Exception as e:
        logger.error(f"Photo analysis failed: {e}")
        return {
            "equipment_identified": "Unable to analyze - please describe manually",
            "environment_observations": "",
            "hazards": [],
            "follow_up_questions": ["What type of equipment is in the photo?", "What is the environment like?"],
            "photo_urls": photo_urls,
            "photo_url": photo_urls[0] if photo_urls else "",
        }
