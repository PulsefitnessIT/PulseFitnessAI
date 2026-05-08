from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Body
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid
import asyncio
import logging

from utils.database import db, EMERGENT_LLM_KEY, RESEND_API_KEY, SENDER_EMAIL, APP_NAME, put_object
from utils.auth import get_current_user, get_organization_filter
from models.schemas import IssueCreate, ServiceRequest
from emergentintegrations.llm.chat import LlmChat, UserMessage

from routes.issue_helpers import (
    build_triage_system_message, build_triage_prompt, append_past_fixes,
    format_knowledge_context, call_ai_with_retry, parse_ai_json,
    build_fallback_triage, store_fix_history, handle_engineer_escalation,
)

logger = logging.getLogger(__name__)
router = APIRouter()

try:
    import resend
except ImportError:
    resend = None


@router.post("/issues/triage")
async def triage_issue(issue: IssueCreate, user: dict = Depends(get_current_user)) -> dict:
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"triage_{datetime.now().timestamp()}",
            system_message=build_triage_system_message(issue.language),
        ).with_model("openai", "gpt-5.2")

        prompt = build_triage_prompt(issue)
        prompt = await append_past_fixes(prompt, issue.machine_type, user.get('organization_id'))

        knowledge_docs = await _fetch_relevant_knowledge(issue.machine_type, issue.supplier, user.get('organization_id'))
        prompt += format_knowledge_context(knowledge_docs)
        prompt += "\n\nPerform triage and provide structured repair steps."

        raw_result = await call_ai_with_retry(chat, UserMessage(text=prompt))
        parsed = parse_ai_json(raw_result)

        # Validate AI-suggested fault_code against the taxonomy (drop if unknown/null)
        from constants.fault_codes import VALID_FAULT_CODES
        suggested_code = parsed.get('fault_code')
        if suggested_code and suggested_code not in VALID_FAULT_CODES:
            suggested_code = None

        return {
            "diagnosis": parsed.get('diagnosis', ''),
            "can_fix_onsite": parsed.get('can_fix_onsite', False),
            "repair_steps": parsed.get('repair_steps', []),
            "tools_needed": parsed.get('tools_needed', []),
            "estimated_time": parsed.get('estimated_time', 'Unknown'),
            "engineer_reason": parsed.get('engineer_reason'),
            "severity_assessment": parsed.get('severity_assessment', issue.severity),
            "fault_code": suggested_code,
            "raw_triage": raw_result,
        }
    except Exception as e:
        logger.error(f"AI triage failed: {e}")
        return build_fallback_triage(issue.severity, str(e).lower())


def _derive_issue_defaults(issue: IssueCreate) -> tuple[str, str, str, str]:
    """Derive (status, fault_type, sla_category, resolved_by) from the inbound issue."""
    is_self_fix = issue.resolution_type == "self_fix"
    is_engineer = issue.resolution_type == "engineer"
    status = "resolved" if is_self_fix else "open"
    fault_type = getattr(issue, 'fault_type', None) or (
        "safety_critical" if issue.severity == "safety_critical" else "standard"
    )
    sla_category = getattr(issue, 'sla_category', None) or "standard"
    resolved_by = "gymaxis_ai" if is_self_fix else ("engineer" if is_engineer else None)
    return status, fault_type, sla_category, resolved_by


def _build_issue_doc(issue: IssueCreate, user: dict) -> dict:
    """Build an issue document from input data."""
    from utils.security import sanitise_string
    status, fault_type, sla_category, resolved_by = _derive_issue_defaults(issue)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "organization_id": user.get('organization_id'),
        "created_by_name": user.get('full_name'),
        "serial_number": issue.serial_number,
        "machine_type": sanitise_string(issue.machine_type or ""),
        "issue_description": sanitise_string(issue.issue_description or ""),
        "severity": issue.severity,
        "fault_type": fault_type,
        "sla_category": sla_category,
        "supplier": sanitise_string(issue.supplier or ""),
        "steps_taken": sanitise_string(issue.steps_taken or ""),
        "status": status,
        "resolution_type": issue.resolution_type,
        "resolution_note": issue.resolution_note,
        "resolved_by": resolved_by,
        "ai_triage": issue.ai_triage,
        "can_fix_onsite": issue.can_fix_onsite,
        "selected_fix_step": issue.selected_fix_step,
        "selected_fix_title": issue.selected_fix_title,
        "fix_method": issue.fix_method,
        "fault_code": issue.fault_code,
        # KPI timestamps (auto-captured)
        "created_at": now,
        "updated_at": now,
        "resolved_at": now if status == "resolved" else None,
        "engineer_assigned_at": None,
        "engineer_arrived_at": None,
        "work_started_at": None,
        "work_completed_at": None,
        "first_response_at": None,
        # Engineer activity
        "parts_used": [],
        "engineer_notes": None,
        "safety_checks_passed": None,
        # Timeline
        "timeline": [{"event": "fault_logged", "timestamp": now, "by": user.get("full_name", "")}],
    }


async def _publish_issue_event(issue_doc: dict, user: dict):
    """Publish service issue created event to integration hub (best-effort)."""
    try:
        from routes.integration_hub import publish_event
        await publish_event(
            event_type="service_issue_created", source_system="service_portal", target_system="crm",
            entity_type="service_case", entity_id=issue_doc["id"],
            payload={
                "issue_id": issue_doc["id"], "title": issue_doc.get("machine_type", "Service Issue"),
                "description": issue_doc.get("issue_description", ""),
                "priority": issue_doc.get("severity", "medium"),
                "equipment_name": issue_doc.get("machine_type", ""),
                "organization_name": user.get("organization_name", ""),
            },
            organization_id=user.get("organization_id", ""),
            triggered_by=user.get("full_name", "system"),
        )
    except Exception:
        pass


def _severity_to_priority(severity: Optional[str]) -> str:
    """Map ops-portal severity buckets to Service Desk priority codes."""
    s = (severity or "").lower()
    if s in ("safety_critical", "critical"):
        return "p1"
    if s in ("operational_major", "major", "high"):
        return "p2"
    if s in ("operational_minor", "minor", "medium"):
        return "p3"
    return "p4"


async def _mirror_issue_to_svc_case(issue_doc: dict, user: dict) -> None:
    """Bridge: when an Operations Portal fault is escalated to engineer
    (resolution_type='engineer'), materialise an `svc_cases` row so the
    Service Desk team see Pulse Fitness fault logs in their queue.

    Best-effort — never blocks the issue write. Idempotent on (issue_id).
    """
    try:
        if (issue_doc.get("resolution_type") or "") != "engineer":
            return
        # Skip if a case already exists for this issue (replay safe).
        existing = await db.svc_cases.find_one(
            {"organization_id": issue_doc.get("organization_id"), "source_meta.issue_id": issue_doc["id"]},
            {"_id": 0, "id": 1},
        )
        if existing:
            return
        # Resolve site context from the equipment serial when possible.
        site_id = ""
        site_name = ""
        site_postcode = ""
        equipment_id = ""
        try:
            equip = await db.equipment.find_one(
                {"organization_id": issue_doc.get("organization_id"),
                 "$or": [{"serial_number": issue_doc.get("serial_number")},
                         {"name": issue_doc.get("serial_number")}]},
                {"_id": 0, "id": 1, "site_id": 1, "name": 1},
            )
            if equip:
                equipment_id = equip.get("id") or ""
                site_id = equip.get("site_id") or ""
                if site_id:
                    site = await db.sites.find_one(
                        {"id": site_id}, {"_id": 0, "name": 1, "postcode": 1, "address": 1},
                    )
                    if site:
                        site_name = site.get("name") or ""
                        site_postcode = site.get("postcode") or ""
        except Exception:
            pass

        # Build the bridged intake payload and reuse the canonical creator.
        from routes.svc.intake import _create_case as _svc_create_case
        priority = _severity_to_priority(issue_doc.get("severity"))
        payload = {
            "title": issue_doc.get("machine_type") or "Operations Portal fault",
            "description": issue_doc.get("issue_description") or "",
            "priority": priority,
            "cover_type": "contract",
            "site_id": site_id,
            "site_name": site_name,
            "site_postcode": site_postcode,
            "asset_id": equipment_id,
            "asset_name": issue_doc.get("machine_type") or "",
            "equipment_ids": [equipment_id] if equipment_id else [],
            "equipment_serials": [issue_doc.get("serial_number") or ""] if issue_doc.get("serial_number") else [],
            "fault_code": issue_doc.get("fault_code") or "",
            "customer_name": user.get("full_name") or "",
            "customer_email": user.get("email") or "",
            "customer_phone": user.get("phone") or "",
            "source_meta": {
                "issue_id": issue_doc["id"],
                "channel": "operations_portal",
                "severity": issue_doc.get("severity"),
            },
        }
        await _svc_create_case(payload=payload, source="portal", user=user)
    except Exception as e:
        logger.warning(f"_mirror_issue_to_svc_case failed: {e}")


@router.post("/issues")
async def create_issue(issue: IssueCreate, user: dict = Depends(get_current_user)) -> dict:
    issue_doc = _build_issue_doc(issue, user)
    await db.issues.insert_one(issue_doc)
    issue_doc.pop('_id', None)

    await store_fix_history(issue, issue_doc['id'], user)
    await handle_engineer_escalation(issue, issue_doc, user)
    await _publish_issue_event(issue_doc, user)
    # Bridge: if escalated to engineer, mirror to Service Desk (best-effort).
    await _mirror_issue_to_svc_case(issue_doc, user)

    return issue_doc


def _parse_ai_triage(issue: dict):
    """Parse raw AI triage JSON into structured fields on the issue dict."""
    raw = issue.pop('ai_triage', None)
    if raw and not issue.get('ai_triage_parsed'):
        try:
            import json as json_mod
            cleaned = raw.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0]
            issue['ai_triage_parsed'] = json_mod.loads(cleaned)
        except Exception:
            issue['ai_triage_summary'] = raw[:200] if raw else ''


async def _batch_enrich_supplier_cases(issues: list[dict]):
    """Attach supplier case summary to each issue via batch lookup."""
    issue_ids = [i["id"] for i in issues]
    if not issue_ids:
        return
    cases = await db.supplier_cases.find(
        {"issue_id": {"$in": issue_ids}},
        {"_id": 0, "issue_id": 1, "token": 1, "current_status": 1, "scheduled_date": 1, "engineer_name": 1}
    ).to_list(500)
    by_issue = {c["issue_id"]: c for c in cases}
    for issue in issues:
        sc = by_issue.get(issue.get("id"))
        if sc:
            issue["supplier_case"] = {k: v for k, v in sc.items() if k != "issue_id"}


@router.get("/issues")
async def get_issues(user: dict = Depends(get_current_user), site_id: str = None) -> dict:
    org_filter = get_organization_filter(user)
    if site_id:
        org_filter["$or"] = [
            {"site_id": site_id},
            {"site_id": {"$exists": False}},
            {"site_id": None},
            {"site_id": ""},
        ]
    issues = await db.issues.find(org_filter, {"_id": 0}).sort("created_at", -1).to_list(500)

    await _batch_enrich_supplier_cases(issues)

    for issue in issues:
        if 'serial_number' not in issue and 'machine_name' in issue:
            issue['serial_number'] = issue['machine_name']
        _parse_ai_triage(issue)

    return {"issues": issues}


@router.get("/issues/{issue_id}")
async def get_issue_detail(issue_id: str, user: dict = Depends(get_current_user)) -> dict:
    org_filter = get_organization_filter(user)
    issue = await db.issues.find_one({"id": issue_id, **org_filter}, {"_id": 0})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if 'serial_number' not in issue and 'machine_name' in issue:
        issue['serial_number'] = issue['machine_name']

    # Enrich with supplier case data (comments, scheduled date, etc.)
    supplier_case = await db.supplier_cases.find_one({"issue_id": issue_id}, {"_id": 0})
    if supplier_case:
        issue["supplier_case"] = {
            "token": supplier_case.get("token"),
            "current_status": supplier_case.get("current_status"),
            "scheduled_date": supplier_case.get("scheduled_date"),
            "engineer_name": supplier_case.get("engineer_name"),
            "supplier_name": supplier_case.get("supplier_name"),
            "supplier_email": supplier_case.get("supplier_email", ""),
            "rating": supplier_case.get("rating"),
            "rating_feedback": supplier_case.get("rating_feedback"),
            "status_history": supplier_case.get("status_history", []),
        }
        comments = await db.supplier_case_comments.find(
            {"case_id": supplier_case["id"]}, {"_id": 0}
        ).sort("created_at", 1).to_list(500)
        issue["supplier_case"]["comments"] = comments
        # Mirror read-receipts: mark all unread supplier-authored comments as
        # seen by the gym now that an authenticated gym user has opened the
        # issue. The gym UI doesn't need this flag — it's for the supplier's
        # public case page so the supplier knows their reply was read.
        try:
            from routes.supplier_portal import mark_supplier_comments_read_by_gym
            await mark_supplier_comments_read_by_gym(supplier_case["id"])
        except Exception:  # pragma: no cover — non-blocking
            pass

    # Parse AI triage if raw
    raw = issue.get('ai_triage')
    if raw and not issue.get('ai_triage_parsed'):
        try:
            import json as json_mod
            cleaned = raw.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0]
            issue['ai_triage_parsed'] = json_mod.loads(cleaned)
        except Exception:
            pass

    return issue


# ── update_issue helpers ─────────────────────────────────────────

_KPI_TIMESTAMP_FIELDS = (
    "engineer_assigned_at", "engineer_arrived_at", "work_started_at",
    "work_completed_at", "first_response_at", "resolved_at",
)

_ENGINEER_ACTIVITY_FIELDS = (
    "parts_used", "engineer_notes", "safety_checks_passed",
    "fault_type", "sla_category", "fault_code",
)


def _apply_status_change(data: dict, update_fields: dict, user: dict, now: str) -> dict | None:
    """Apply status transition. Returns a timeline entry if status changed, else None."""
    status = data.get("status")
    if not status:
        return None
    update_fields["status"] = status
    if status == "resolved" and "resolved_at" not in data:
        update_fields["resolved_at"] = now
    return {"event": f"status_changed_to_{status}", "timestamp": now, "by": user.get("full_name", "")}


def _apply_resolution_fields(data: dict, update_fields: dict) -> None:
    for key in ("resolution_type", "resolved_by"):
        if data.get(key):
            update_fields[key] = data[key]


def _apply_kpi_timestamps(data: dict, update_fields: dict, user: dict, now: str) -> dict | None:
    """Copy KPI timestamps from payload. Returns a fallback timeline entry if no prior entry."""
    fallback_entry = None
    for ts_field in _KPI_TIMESTAMP_FIELDS:
        if ts_field not in data:
            continue
        ts_value = data[ts_field] or now
        update_fields[ts_field] = ts_value
        if fallback_entry is None:
            fallback_entry = {"event": ts_field, "timestamp": ts_value, "by": user.get("full_name", "")}
    return fallback_entry


def _apply_engineer_fields(data: dict, update_fields: dict) -> None:
    for field in _ENGINEER_ACTIVITY_FIELDS:
        if field in data:
            update_fields[field] = data[field]


@router.patch("/issues/{issue_id}")
async def update_issue(issue_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    org_filter = get_organization_filter(user)
    now = datetime.now(timezone.utc).isoformat()

    update_fields: dict = {"updated_at": now}

    timeline_entry = _apply_status_change(data, update_fields, user, now)
    _apply_resolution_fields(data, update_fields)
    fallback_entry = _apply_kpi_timestamps(data, update_fields, user, now)
    if timeline_entry is None:
        timeline_entry = fallback_entry
    _apply_engineer_fields(data, update_fields)

    update_ops: dict = {"$set": update_fields}
    if timeline_entry:
        update_ops["$push"] = {"timeline": timeline_entry}

    result = await db.issues.update_one({"id": issue_id, **org_filter}, update_ops)
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Issue not found")
    return {"success": True}


@router.post("/issues/{issue_id}/attachments")
async def add_issue_attachment(issue_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    from utils.file_validation import validate_upload, MIME_FAULT_MEDIA
    org_filter = get_organization_filter(user)
    issue = await db.issues.find_one({"id": issue_id, **org_filter})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    path = f"{APP_NAME}/issues/{issue_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    ct = validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_FAULT_MEDIA, max_size=50 * 1024 * 1024)
    result = put_object(path, data, ct)

    attachment = {
        "id": str(uuid.uuid4()),
        "filename": file.filename,
        "storage_path": result["path"],
        "download_url": result.get("url", result["path"]),
        "content_type": ct,
        "size": result.get("size", len(data)),
        "uploaded_by": user.get('full_name'),
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }
    await db.issues.update_one({"id": issue_id}, {"$push": {"attachments": attachment}})
    return attachment


@router.patch("/issues/{issue_id}/details")
async def update_issue_details(issue_id: str, data: Dict[str, Any], user: dict = Depends(get_current_user)) -> dict:
    org_filter = get_organization_filter(user)
    allowed_fields = {"supplier_ref", "quote_amount", "engineer_notes"}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.issues.update_one({"id": issue_id, **org_filter}, {"$set": update_data})
    return {"success": True}


@router.post("/service/request")
async def request_service(request: ServiceRequest, user: dict = Depends(get_current_user)) -> dict:
    service_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "machine_type": request.machine_type,
        "issue_summary": request.issue_summary,
        "site_info": request.site_info,
        "contact_name": request.contact_name,
        "contact_email": request.contact_email,
        "contact_phone": request.contact_phone,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.service_requests.insert_one(service_doc)

    if RESEND_API_KEY and resend:
        try:
            html_content = f'''<h2>New Service Request</h2>
            <p><strong>Machine Type:</strong> {request.machine_type}</p>
            <p><strong>Issue:</strong> {request.issue_summary}</p>
            <p><strong>Site:</strong> {request.site_info}</p>
            <p><strong>Contact:</strong> {request.contact_name}</p>
            <p><strong>Email:</strong> {request.contact_email}</p>
            <p><strong>Phone:</strong> {request.contact_phone}</p>'''
            params = {
                "from": SENDER_EMAIL,
                "to": [request.contact_email],
                "subject": "Service Request Received - GymAxis AI",
                "html": html_content
            }
            await asyncio.to_thread(resend.Emails.send, params)
        except Exception as e:
            logger.error(f"Failed to send email: {e}")

    return {"id": service_doc['id'], "status": "pending"}



def _score_type_match(eq_type: str, machine_lower: str) -> int:
    """Score equipment type match for knowledge docs."""
    if not eq_type or not machine_lower:
        return 0
    if eq_type in machine_lower or machine_lower in eq_type:
        return 10
    if any(w in eq_type for w in machine_lower.split() if len(w) > 3):
        return 5
    return 0


def _score_supplier_relevance(supplier_lower: str, eq_mfr: str, doc_supplier: str) -> int:
    """Score supplier relevance for knowledge docs."""
    if not supplier_lower:
        return 0
    score = 0
    if supplier_lower in eq_mfr or eq_mfr in supplier_lower:
        score += 8
    if supplier_lower in doc_supplier or doc_supplier in supplier_lower:
        score += 8
    return score


_KNOWLEDGE_FIELD_WEIGHTS = {
    "common_faults": 2,
    "troubleshooting_tips": 1,
    "spare_parts": 1,
}


def _score_knowledge_doc(kd: dict, machine_lower: str, supplier_lower: str) -> int:
    """Score a single knowledge document by relevance."""
    ext = kd.get("extraction", {})
    equip_info = ext.get("equipment_info", {})
    eq_type = (equip_info.get("equipment_type") or "").lower()
    eq_mfr = (equip_info.get("manufacturer") or "").lower()
    eq_model = (equip_info.get("model") or "").lower()
    doc_supplier = (kd.get("supplier_name") or "").lower()

    score = _score_type_match(eq_type, machine_lower)
    score += _score_supplier_relevance(supplier_lower, eq_mfr, doc_supplier)
    if eq_model and machine_lower and eq_model in machine_lower:
        score += 6
    for field, weight in _KNOWLEDGE_FIELD_WEIGHTS.items():
        if ext.get(field):
            score += weight
    return score


async def _fetch_relevant_knowledge(machine_type: str, supplier: Optional[str] = None, organization_id: Optional[str] = None) -> list[dict]:
    """Search document knowledge globally + org-specific."""
    org_query: dict = {"$or": [{"organization_id": None}]}
    if organization_id:
        org_query["$or"].append({"organization_id": organization_id})

    all_docs = await db.equipment_knowledge.find(org_query, {"_id": 0}).to_list(100)
    if not all_docs:
        return []

    machine_lower = (machine_type or "").lower()
    supplier_lower = (supplier or "").lower()

    scored = [(s, kd) for kd in all_docs if (s := _score_knowledge_doc(kd, machine_lower, supplier_lower)) > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [kd for _, kd in scored[:5]]
