from fastapi import APIRouter, Depends
from datetime import datetime, timezone
import uuid
import asyncio
import logging

from utils.database import db, EMERGENT_LLM_KEY
from utils.auth import get_current_user
from utils.ai_access import require_ai_access
from utils.email import send_report_notification
from models.schemas import ChatMessage, AuditRequest
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Knowledge Helpers ──────────────────────────────────────────────


def _format_section(items: list, prefix: str, fmt) -> list[str]:
    """Format a list of items into context lines."""
    return [fmt(item) for item in (items or [])]


def _format_knowledge_entry(kd: dict) -> str:
    """Format a single knowledge document into context text."""
    ext = kd.get("extraction", {})
    equip_info = ext.get("equipment_info", {})
    source = f"{kd.get('supplier_name', '')} {equip_info.get('model', '')}".strip()
    lines = [f"\n[Source: {source or kd.get('filename', 'Document')}]"]
    lines.append(f"Equipment: {equip_info.get('manufacturer', '')} {equip_info.get('model', '')} ({equip_info.get('equipment_type', '')})")

    lines += _format_section((ext.get("common_faults") or [])[:4], "Known fault",
        lambda f: f"  Known fault: {f.get('fault','')}: {f.get('symptoms','')} -> Fix: {f.get('fix','')} [Severity: {f.get('severity','N/A')}]")
    lines += _format_section((ext.get("troubleshooting_tips") or [])[:4], "Tip", lambda t: f"  Tip: {t}")
    lines += _format_section((ext.get("spare_parts") or [])[:3], "Part", lambda p: f"  Part: {p.get('part','')}: {p.get('part_number','')}")
    lines += _format_section((ext.get("maintenance_schedule") or [])[:2], "Maint", lambda m: f"  Maintenance: {m.get('task','')}: {m.get('frequency','')}")
    lines += _format_section((ext.get("safety_warnings") or [])[:2], "Safety", lambda w: f"  Safety: {w}")
    return "\n".join(lines)


def _build_diagnosis_context(knowledge_docs: list) -> str:
    """Build the knowledge context section for diagnosis prompts."""
    if not knowledge_docs:
        return ""
    ctx = "\n\nYou have access to the following knowledge from uploaded equipment manuals and service guides:\n"
    for kd in knowledge_docs[:5]:
        ctx += _format_knowledge_entry(kd)
    ctx += (
        "\nWhen answering, reference the specific manual/guide source so the user "
        "knows where to find detailed instructions. Include part numbers from "
        "documents when recommending replacements."
    )
    return ctx


def _build_audit_context(knowledge_docs: list) -> str:
    """Build the knowledge context section for audit prompts."""
    if not knowledge_docs:
        return ""
    ctx = "\n\nRELEVANT DOCUMENT KNOWLEDGE:\n"
    for kd in knowledge_docs[:3]:
        ext = kd.get("extraction", {})
        equip_info = ext.get("equipment_info", {})
        ctx += f"\n[Source: {kd.get('supplier_name', '')} {equip_info.get('model', '')}]\n"
        for m in (ext.get("maintenance_schedule") or []):
            ctx += f"  - {m.get('task','')}: {m.get('frequency','')}\n"
        for f in (ext.get("common_faults") or [])[:4]:
            ctx += f"  - {f.get('fault','')}: {f.get('symptoms','')} [Severity: {f.get('severity','N/A')}]\n"
        if ext.get("key_specifications"):
            ctx += f"  Key specs: {', '.join(ext['key_specifications'][:5])}\n"
        for w in (ext.get("safety_warnings") or [])[:3]:
            ctx += f"  - {w}\n"
    ctx += "\nUse this manufacturer data to make the audit more specific and actionable. Reference the source documents."
    return ctx


async def _fetch_equipment_details(equipment_id: str, user: dict) -> dict:
    """Fetch equipment details by ID for a given user's org."""
    from utils.auth import get_organization_filter
    org_filter = get_organization_filter(user)
    equip = await db.equipment.find_one({"id": equipment_id, **org_filter}, {"_id": 0})
    if not equip:
        return {}
    return {
        "name": equip.get("name", ""),
        "serial_number": equip.get("serial_number", ""),
        "location": equip.get("location", ""),
        "manufacturer": equip.get("manufacturer", ""),
        "model": equip.get("model", ""),
    }


def _score_type_match(eq_type: str, type_lower: str) -> int:
    """Score how well equipment type matches the query."""
    if not eq_type or not type_lower:
        return 0
    if eq_type in type_lower or type_lower in eq_type:
        return 10
    if any(w in eq_type for w in type_lower.split() if len(w) > 3):
        return 5
    return 0


def _score_manufacturer_match(eq_mfr: str, eq_model: str, doc_supplier: str, mfr_lower: str) -> int:
    """Score manufacturer/model/supplier matches."""
    if not mfr_lower:
        return 0
    score = 0
    if mfr_lower in eq_mfr or eq_mfr in mfr_lower:
        score += 8
    if mfr_lower in doc_supplier or doc_supplier in mfr_lower:
        score += 8
    if mfr_lower in eq_model or eq_model in mfr_lower:
        score += 6
    return score


def _score_content_richness(extraction: dict) -> int:
    """Bonus score for docs with useful diagnostic content."""
    score = 0
    if extraction.get("common_faults"):
        score += 2
    if extraction.get("troubleshooting_tips"):
        score += 1
    return score


async def _score_knowledge_docs(all_docs: list, equipment_type: str, model_or_manufacturer: str) -> list:
    """Score and rank knowledge docs by relevance."""
    type_lower = (equipment_type or "").lower()
    mfr_lower = (model_or_manufacturer or "").lower()

    scored = []
    for kd in all_docs:
        ext = kd.get("extraction", {})
        equip_info = ext.get("equipment_info", {})
        eq_type = (equip_info.get("equipment_type") or "").lower()
        eq_mfr = (equip_info.get("manufacturer") or "").lower()
        eq_model = (equip_info.get("model") or "").lower()
        doc_supplier = (kd.get("supplier_name") or "").lower()

        score = (
            _score_type_match(eq_type, type_lower)
            + _score_manufacturer_match(eq_mfr, eq_model, doc_supplier, mfr_lower)
            + _score_content_richness(ext)
        )

        if score > 0:
            scored.append((score, kd))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [kd for _, kd in scored[:5]]


async def _fetch_diagnosis_knowledge(equipment_type: str, model_or_manufacturer: str = "", organization_id: str = None) -> list:
    """Search document knowledge globally + org-specific with relevance scoring."""
    org_query = {"$or": [{"organization_id": None}]}
    if organization_id:
        org_query["$or"].append({"organization_id": organization_id})

    all_docs = await db.equipment_knowledge.find(org_query, {"_id": 0}).to_list(100)
    if not all_docs:
        return []
    return await _score_knowledge_docs(all_docs, equipment_type, model_or_manufacturer)


# ─── Endpoints ──────────────────────────────────────────────────────


DIAGNOSIS_SYSTEM = (
    "You are an expert gym equipment diagnostic AI. Your job is to help diagnose "
    "equipment faults and provide repair guidance.\n\n"
    "IMPORTANT: You must ONLY answer questions related to gym equipment, fitness facility "
    "maintenance, and the gym environment. If someone asks about anything unrelated to "
    "gym/fitness equipment maintenance, politely redirect them.\n\n"
    "For each fault report:\n"
    "1. Ask clarifying questions about symptoms\n"
    "2. Provide likely diagnosis\n"
    "3. Give step-by-step fix instructions\n"
    "4. Indicate severity: low/medium/critical\n"
    "5. Indicate if fixable on-site: YES/NO\n\n"
    "Equipment types: treadmills, bikes, cross trainers, strength equipment, rowing machines\n\n"
    "Be concise, technical, and actionable."
)

AUDIT_SYSTEM = (
    "You are an expert gym equipment auditor. Generate comprehensive audit reports. "
    "ONLY respond to queries about gym equipment and fitness facility environments.\n\n"
    "Include:\n"
    "1. Overall condition rating (Excellent/Good/Fair/Poor/Critical)\n"
    "2. Maintenance risks identified\n"
    "3. Health & safety concerns\n"
    "4. Cleaning standards assessment\n"
    "5. Recommended immediate actions\n"
    "6. Long-term maintenance plan\n"
    "7. Replacement timeline if beyond economical repair\n\n"
    "Format as professional report suitable for management review."
)


@router.post("/chat/diagnose")
async def diagnose_fault(message: ChatMessage, user: dict = Depends(require_ai_access)) -> dict:
    session_id = f"diagnosis_{user['id']}_{datetime.now().timestamp()}"

    knowledge_docs = await _fetch_diagnosis_knowledge(
        message.equipment_type or "", "", user.get("organization_id")
    )
    knowledge_context = _build_diagnosis_context(knowledge_docs)
    system_message = DIAGNOSIS_SYSTEM + knowledge_context

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=system_message
    ).with_model("openai", "gpt-5.2")

    response = await chat.send_message(UserMessage(text=message.message))

    chat_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "session_id": session_id,
        "message": message.message,
        "response": response,
        "equipment_type": message.equipment_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chat_history.insert_one(chat_doc)
    return {"response": response, "session_id": session_id}


@router.post("/diagnosis/save-fix")
async def save_fix(data: dict, user: dict = Depends(get_current_user)) -> dict:
    fix_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "machine_type": data.get("machine_type", ""),
        "fault_description": data.get("fault_description", ""),
        "fix_applied": data.get("fix_applied", ""),
        "resolution_type": data.get("resolution_type", "manual_fix"),
        "organization_id": user.get("organization_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.fix_history.insert_one(fix_doc)
    return {"id": fix_doc["id"], "message": "Fix saved"}


@router.get("/diagnosis/fix-history")
async def get_fix_history(machine_type: str = None, user: dict = Depends(get_current_user)) -> dict:
    from utils.auth import get_organization_filter
    query = get_organization_filter(user)
    if machine_type:
        query["machine_type"] = machine_type
    fixes = await db.fix_history.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"fixes": fixes}


def _build_audit_prompt(request: AuditRequest, equip_details: dict, knowledge_section: str) -> str:
    """Assemble the audit prompt from request data and knowledge context."""
    lines = [f"Generate an audit report for:\n    Equipment Type: {request.equipment_type}"]
    optional_fields: list[tuple[str, str]] = [
        ("Equipment Name", equip_details.get("name", "")),
        ("Serial Number", equip_details.get("serial_number", "")),
        ("Manufacturer", equip_details.get("manufacturer", "")),
        ("Model", equip_details.get("model", "")),
        ("Location", equip_details.get("location", "")),
    ]
    for label, value in optional_fields:
        if value:
            lines.append(f"    {label}: {value}")
    lines.append(f"    Usage Frequency: {request.usage_frequency}")
    lines.append(f"    Last Maintenance: {request.last_maintenance}")
    lines.append(f"    Additional Notes: {request.notes or 'None'}")
    lines.append(f"    {knowledge_section}")
    return "\n".join(lines)


async def _save_audit_doc(
    user: dict, request: AuditRequest, equip_details: dict, report: str,
) -> dict:
    """Persist an audit report and trigger an email notification."""
    audit_doc: dict = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "equipment_id": request.equipment_id,
        "equipment_type": request.equipment_type,
        "equipment_name": equip_details.get("name", ""),
        "equipment_serial": equip_details.get("serial_number", ""),
        "usage_frequency": request.usage_frequency,
        "last_maintenance": request.last_maintenance,
        "notes": request.notes,
        "report": report,
        "organization_id": user.get("organization_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.audits.insert_one(audit_doc)
    asyncio.create_task(
        send_report_notification(user["email"], user.get("full_name", ""), "Audit Report", audit_doc["id"]),
    )
    return audit_doc


@router.post("/audit/generate")
async def generate_audit(request: AuditRequest, user: dict = Depends(get_current_user)) -> dict:
    """Generate an AI-powered audit report for a piece of equipment."""
    equip_details: dict = {}
    if request.equipment_id:
        equip_details = await _fetch_equipment_details(request.equipment_id, user)

    audit_knowledge = await _fetch_diagnosis_knowledge(
        request.equipment_type or "",
        equip_details.get("model") or equip_details.get("manufacturer") or "",
        user.get("organization_id"),
    )
    prompt = _build_audit_prompt(request, equip_details, _build_audit_context(audit_knowledge))

    session_id = f"audit_{user['id']}_{datetime.now().timestamp()}"
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=AUDIT_SYSTEM,
    ).with_model("openai", "gpt-5.2")
    report: str = await chat.send_message(UserMessage(text=prompt))

    audit_doc = await _save_audit_doc(user, request, equip_details, report)
    return {
        "id": audit_doc["id"],
        "equipment_id": request.equipment_id,
        "equipment_type": request.equipment_type,
        "equipment_name": equip_details.get("name", ""),
        "report": report,
        "created_at": audit_doc["created_at"],
    }


@router.get("/audit/history")
async def get_audit_history(equipment_id: str = None, user: dict = Depends(get_current_user)) -> dict:
    from utils.auth import get_organization_filter
    query = get_organization_filter(user)
    if equipment_id:
        query["equipment_id"] = equipment_id
    audits = await db.audits.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"audits": audits}
