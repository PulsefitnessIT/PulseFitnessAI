from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import uuid
import os
import logging

from utils.database import db
from routes.crm_auth import get_crm_user

import json as json_mod

router = APIRouter(prefix="/crm/ai", tags=["CRM AI"])
logger = logging.getLogger(__name__)


async def call_llm(prompt: str, max_tokens: int = 1500) -> str:
    """Call GPT-5.2 via Emergent LLM key."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import uuid

        api_key = os.environ.get("EMERGENT_LLM_KEY", "")
        if not api_key:
            api_key = os.environ.get("EMERGENT_MODEL_API_KEY", "")

        session_id = str(uuid.uuid4())
        system_message = "You are an expert sales and CRM AI assistant for Pulse Fitness AI CRM. Provide actionable, concise, professional responses."

        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=system_message
        ).with_model("openai", "gpt-4o")

        user_msg = UserMessage(text=prompt)
        response = await chat.send_message(user_msg)
        return response
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return f"AI service temporarily unavailable: {str(e)}"


def _parse_llm_json(response: str, fallback: dict) -> dict:
    """Parse JSON from LLM response, stripping markdown fences. Returns fallback on failure."""
    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json_mod.loads(cleaned)
    except Exception:
        return fallback


async def _build_lead_context(contact_id: str) -> tuple:
    """Fetch contact, deals, and activities for lead scoring. Returns (contact, prompt_section)."""
    contact = await db.crm_contacts.find_one({"id": contact_id}, {"_id": 0})
    if not contact:
        return None, ""

    deals = await db.crm_deals.find({"contact_id": contact_id}, {"_id": 0}).to_list(20)
    activities = await db.crm_activities.find({"contact_id": contact_id}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)

    prompt = f"""Analyse this CRM contact and provide a lead score from 0-100 with reasoning.

Contact:
- Name: {contact.get('first_name', '')} {contact.get('last_name', '')}
- Email: {contact.get('email', '')}
- Company: {contact.get('company_name', '')}
- Title: {contact.get('title', '')}
- Source: {contact.get('source', '')}
- Tags: {', '.join(contact.get('tags', []))}
- LinkedIn: {contact.get('linkedin_url', 'N/A')}

Deals ({len(deals)}):
{chr(10).join([f"- {d['title']}: £{d['value']:,.0f} (stage: {d['stage']})" for d in deals[:5]]) or 'No deals yet'}

Recent Activities ({len(activities)}):
{chr(10).join([f"- {a['type']}: {a['description'][:100]}" for a in activities[:5]]) or 'No activities yet'}

Return a JSON object with these exact keys:
- "score": integer 0-100
- "label": one of "Hot", "Warm", "Cool", "Cold"
- "reasoning": brief explanation (2-3 sentences)
- "next_action": suggested next step for the sales rep

Return ONLY the JSON, no markdown fences."""

    return contact, prompt


async def _store_meeting_record(result: dict, data: dict, user: dict) -> tuple:
    """Store meeting record, create timeline activity, and auto-create tasks. Returns (meeting_id, tasks_created)."""
    contact_id = data.get("contact_id")
    deal_id = data.get("deal_id")
    meeting_title = data.get("title", "Meeting")
    meeting_id = str(uuid.uuid4())

    meeting_doc = {
        "id": meeting_id,
        "title": meeting_title,
        "transcript": data.get("transcript", ""),
        "contact_id": contact_id,
        "deal_id": deal_id,
        "summary": result.get("summary", ""),
        "key_points": result.get("key_points", []),
        "action_items": result.get("action_items", []),
        "sentiment": result.get("sentiment", "neutral"),
        "next_steps": result.get("next_steps", []),
        "follow_up_date": result.get("follow_up_date", ""),
        "created_by": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_meetings.insert_one(meeting_doc)

    if contact_id:
        await db.crm_activities.insert_one({
            "id": str(uuid.uuid4()), "type": "meeting",
            "contact_id": contact_id, "deal_id": deal_id, "company_id": None,
            "description": f"Meeting '{meeting_title}' — {result.get('summary', '')[:100]}",
            "metadata": {"meeting_id": meeting_id, "sentiment": result.get("sentiment")},
            "created_by": user["id"], "created_by_name": user["full_name"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    tasks_created = 0
    for item in result.get("action_items", []):
        await db.crm_activities.insert_one({
            "id": str(uuid.uuid4()), "type": "task",
            "contact_id": contact_id, "deal_id": deal_id, "company_id": None,
            "description": item.get("task", ""),
            "metadata": {"priority": item.get("priority", "medium"), "assignee": item.get("assignee", ""), "from_meeting": meeting_id, "completed": False},
            "created_by": user["id"], "created_by_name": user["full_name"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        tasks_created += 1

    return meeting_id, tasks_created


@router.post("/lead-score")
async def ai_lead_score(data: dict, user=Depends(get_crm_user)):
    contact_id = data.get("contact_id")
    if not contact_id:
        raise HTTPException(status_code=400, detail="contact_id required")

    contact, prompt = await _build_lead_context(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    response = await call_llm(prompt, 500)
    result = _parse_llm_json(response, {"score": 50, "label": "Warm", "reasoning": response[:200], "next_action": "Follow up with a call"})
    score = min(100, max(0, int(result.get("score", 50))))

    await db.crm_contacts.update_one(
        {"id": contact_id},
        {"$set": {"lead_score": score, "lead_label": result.get("label", "Warm"), "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    return {
        "contact_id": contact_id,
        "score": score,
        "label": result.get("label", "Warm"),
        "reasoning": result.get("reasoning", ""),
        "next_action": result.get("next_action", ""),
    }


@router.post("/generate-email")
async def ai_generate_email(data: dict, user=Depends(get_crm_user)):
    contact_id = data.get("contact_id")
    tone = data.get("tone", "professional")
    purpose = data.get("purpose", "follow-up")
    context = data.get("context", "")

    contact = None
    if contact_id:
        contact = await db.crm_contacts.find_one({"id": contact_id}, {"_id": 0})

    contact_info = ""
    if contact:
        contact_info = f"""Recipient:
- Name: {contact.get('first_name', '')} {contact.get('last_name', '')}
- Company: {contact.get('company_name', '')}
- Title: {contact.get('title', '')}"""

    prompt = f"""Write a sales email with the following parameters:
Tone: {tone}
Purpose: {purpose}
{contact_info}
Additional Context: {context or 'None provided'}

Sender: {user['full_name']} from Pulse Fitness AI

Return a JSON object with:
- "subject": email subject line
- "body": full email body (plain text, professional formatting)
- "follow_up_note": brief internal note for the sales rep

Return ONLY the JSON, no markdown fences."""

    response = await call_llm(prompt, 800)
    result = _parse_llm_json(response, {"subject": f"Follow-up from {user['full_name']}", "body": response, "follow_up_note": "Review before sending"})
    return result


@router.post("/deal-insights")
async def ai_deal_insights(data: dict, user=Depends(get_crm_user)):
    deal_id = data.get("deal_id")
    if not deal_id:
        raise HTTPException(status_code=400, detail="deal_id required")

    deal = await db.crm_deals.find_one({"id": deal_id}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    activities = await db.crm_activities.find({"deal_id": deal_id}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)

    prompt = f"""Analyse this sales deal and provide insights:

Deal: {deal.get('title', '')}
Value: £{deal.get('value', 0):,.0f}
Stage: {deal.get('stage', '')}
Probability: {deal.get('probability', 0)}%
Expected Close: {deal.get('expected_close', 'Not set')}
Contact: {deal.get('contact_name', '')}
Company: {deal.get('company_name', '')}
Created: {deal.get('created_at', '')}

Recent Activities:
{chr(10).join([f"- {a['type']}: {a['description'][:80]}" for a in activities]) or 'No activities'}

Provide a JSON object with:
- "win_probability": estimated percentage (0-100)
- "risk_factors": array of risk strings
- "recommendations": array of action items
- "summary": 2-sentence deal health summary

Return ONLY the JSON, no markdown fences."""

    response = await call_llm(prompt, 600)
    fallback = {
        "win_probability": deal.get("probability", 50),
        "risk_factors": ["Unable to analyse at this time"],
        "recommendations": ["Schedule a follow-up call"],
        "summary": response[:200]
    }
    return _parse_llm_json(response, fallback)


# ==================== MEETING INTELLIGENCE ====================
@router.post("/meeting-intelligence")
async def meeting_intelligence(data: dict, user=Depends(get_crm_user)):
    transcript = data.get("transcript", "")
    if not transcript or len(transcript.strip()) < 20:
        raise HTTPException(status_code=400, detail="Transcript must be at least 20 characters")

    contact_info = ""
    contact_id = data.get("contact_id")
    if contact_id:
        contact = await db.crm_contacts.find_one({"id": contact_id}, {"_id": 0})
        if contact:
            contact_info = f"\nContact: {contact.get('first_name','')} {contact.get('last_name','')} ({contact.get('company_name','')})"

    prompt = f"""Analyse this meeting transcript and extract structured intelligence.

Meeting: {data.get("title", "Meeting")}{contact_info}

TRANSCRIPT:
{transcript[:4000]}

Return a JSON object with:
- "summary": concise 3-4 sentence summary of the meeting
- "key_points": array of 3-6 key discussion points (strings)
- "action_items": array of objects with "task" (string), "assignee" (string or "Unassigned"), "priority" ("high"/"medium"/"low")
- "sentiment": overall meeting sentiment ("positive"/"neutral"/"negative")
- "next_steps": array of recommended next steps (strings)
- "follow_up_date": suggested follow-up date description (e.g. "Within 3 days")

Return ONLY the JSON, no markdown fences."""

    response = await call_llm(prompt, 1000)
    fallback = {"summary": response[:300], "key_points": [], "action_items": [], "sentiment": "neutral", "next_steps": [], "follow_up_date": "Review manually"}
    result = _parse_llm_json(response, fallback)

    meeting_id, tasks_created = await _store_meeting_record(result, data, user)
    return {**result, "meeting_id": meeting_id, "tasks_created": tasks_created}


@router.get("/meetings")
async def list_meetings(contact_id: str = "", skip: int = 0, limit: int = 20, user=Depends(get_crm_user)):
    query = {}
    if contact_id:
        query["contact_id"] = contact_id
    meetings = await db.crm_meetings.find(query, {"_id": 0, "transcript": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.crm_meetings.count_documents(query)
    return {"meetings": meetings, "total": total}


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str, user=Depends(get_crm_user)):
    meeting = await db.crm_meetings.find_one({"id": meeting_id}, {"_id": 0})
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


# ==================== DATA CLEANING ====================
def _check_missing_fields(contacts: list) -> dict:
    """Check contacts for missing email, phone, and company fields."""
    missing = {"missing_email": [], "missing_phone": [], "missing_company": []}
    for c in contacts:
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}"
        cid = c["id"]
        if not (c.get("email") or "").strip():
            missing["missing_email"].append({"id": cid, "name": name})
        if not c.get("phone"):
            missing["missing_phone"].append({"id": cid, "name": name})
        if not c.get("company_name"):
            missing["missing_company"].append({"id": cid, "name": name})
    return missing


def _check_invalid_emails(contacts: list) -> list:
    """Find contacts with malformed email addresses."""
    import re
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    invalid = []
    for c in contacts:
        email = (c.get("email") or "").strip().lower()
        if email and not email_pattern.match(email):
            invalid.append({"id": c["id"], "name": f"{c.get('first_name', '')} {c.get('last_name', '')}", "email": email})
    return invalid


def _find_duplicates(contacts: list) -> list:
    """Detect duplicate contacts by exact email or name match."""
    seen_emails, seen_names = {}, {}
    dupes = []
    for c in contacts:
        cid = c["id"]
        email = (c.get("email") or "").strip().lower()
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip().lower()

        if email:
            if email in seen_emails:
                dupes.append({"ids": [seen_emails[email], cid], "match_type": "email", "value": email})
            else:
                seen_emails[email] = cid

        if name and len(name) > 3:
            if name in seen_names:
                dupes.append({"ids": [seen_names[name], cid], "match_type": "name", "value": name})
            else:
                seen_names[name] = cid

    return dupes


@router.get("/data-cleaning/report")
async def data_cleaning_report(user=Depends(get_crm_user)):
    """Scan contacts for quality issues."""
    contacts = await db.crm_contacts.find({}, {"_id": 0}).to_list(5000)

    missing = _check_missing_fields(contacts)
    invalid_emails = _check_invalid_emails(contacts)
    duplicates = _find_duplicates(contacts)

    issues = {**missing, "invalid_email": invalid_emails, "potential_duplicates": duplicates}

    return {
        "total_contacts": len(contacts),
        "missing_email": len(issues["missing_email"]),
        "missing_phone": len(issues["missing_phone"]),
        "missing_company": len(issues["missing_company"]),
        "invalid_email": len(issues["invalid_email"]),
        "potential_duplicates": len(issues["potential_duplicates"]),
        "details": {k: v[:20] for k, v in issues.items()},
    }


@router.post("/data-cleaning/merge-contacts")
async def merge_contacts(data: dict, user=Depends(get_crm_user)):
    """Merge two duplicate contacts. Keep primary, delete secondary, merge fields."""
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    primary_id = data.get("primary_id")
    secondary_id = data.get("secondary_id")
    if not primary_id or not secondary_id:
        raise HTTPException(status_code=400, detail="primary_id and secondary_id required")

    primary = await db.crm_contacts.find_one({"id": primary_id}, {"_id": 0})
    secondary = await db.crm_contacts.find_one({"id": secondary_id}, {"_id": 0})
    if not primary or not secondary:
        raise HTTPException(status_code=404, detail="One or both contacts not found")

    # Merge: fill empty fields from secondary
    updates = {}
    for field in ["email", "phone", "company_name", "title", "linkedin_url", "address"]:
        if not primary.get(field) and secondary.get(field):
            updates[field] = secondary[field]

    # Merge tags
    merged_tags = list(set(primary.get("tags", []) + secondary.get("tags", [])))
    updates["tags"] = merged_tags
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.crm_contacts.update_one({"id": primary_id}, {"$set": updates})

    # Re-link secondary's activities and deals to primary
    await db.crm_activities.update_many({"contact_id": secondary_id}, {"$set": {"contact_id": primary_id}})
    await db.crm_deals.update_many({"contact_id": secondary_id}, {"$set": {"contact_id": primary_id}})

    # Delete secondary
    await db.crm_contacts.delete_one({"id": secondary_id})

    from routes.crm_core import log_audit
    await log_audit(user, "contact", primary_id, "merged", {"merged_from": secondary_id})

    return {"status": "merged", "primary_id": primary_id, "deleted_id": secondary_id, "fields_updated": list(updates.keys())}
