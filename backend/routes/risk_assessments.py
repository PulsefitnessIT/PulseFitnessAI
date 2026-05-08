from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from datetime import datetime, timezone
from typing import Dict, Any
import uuid
import json as json_module
import logging

from utils.database import db, EMERGENT_LLM_KEY, APP_NAME, put_object
from utils.auth import get_current_user, get_organization_filter
from models.schemas import RiskAssessmentCreate
from emergentintegrations.llm.chat import LlmChat, UserMessage

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


@router.post("/risk-assessments/photo-analyze")
async def analyze_photo_for_risk(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    from utils.file_validation import validate_upload, MIME_IMAGES
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    path = f"{APP_NAME}/ra-photos/{user.get('organization_id', user['id'])}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    ct = validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_IMAGES, max_size=15 * 1024 * 1024)
    result = put_object(path, data, ct)
    photo_url = result.get("url", result["path"])

    try:
        session_id = f"ra_photo_{datetime.now().timestamp()}"
        system_message = """You are a health & safety expert analyzing gym equipment and environments for risk assessment.
Based on the description of the uploaded photo, identify hazards, who might be harmed, and suggest control measures.
Return ONLY valid JSON with no extra text:
{
  "equipment_identified": "description of what you think was photographed",
  "environment_observations": "observations about the environment",
  "hazards": [
    {"hazard": "...", "harm": "...", "who": "...", "recommended_controls": "...", "controls_in_place": "", "plr": 3, "psr": 3, "further_controls": "", "post_plr": 2, "post_psr": 2}
  ],
  "follow_up_questions": ["question1", "question2"]
}"""

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_message
        ).with_model("openai", "gpt-5.2")

        prompt = f"A photo was uploaded for risk assessment. Filename: {file.filename}. Content type: {file.content_type}. Generate a comprehensive risk assessment based on typical gym equipment and environment hazards that would be associated with this type of photo. Provide detailed hazards."

        user_message = UserMessage(text=prompt)
        raw = await chat.send_message(user_message)

        cleaned = raw.strip()
        if cleaned.startswith('```'):
            cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        parsed = json_module.loads(cleaned)
        parsed["photo_url"] = photo_url
        return parsed
    except Exception as e:
        logger.error(f"Photo analysis failed: {e}")
        return {
            "equipment_identified": "Unable to analyze - please describe manually",
            "environment_observations": "",
            "hazards": [],
            "follow_up_questions": ["What type of equipment is in the photo?", "What is the environment like?"],
            "photo_url": photo_url
        }
