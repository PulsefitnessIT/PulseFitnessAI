from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid
import logging

from utils.database import db
from utils.auth import verify_api_key
from utils.helpers import get_equipment_stats

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def supplier_api_health():
    return {"status": "healthy", "version": "1.0.0"}


@router.get("/equipment")
async def supplier_list_equipment(api_key_doc: dict = Depends(verify_api_key)):
    equipment_list = await db.equipment.find({"user_id": api_key_doc['user_id']}, {"_id": 0}).to_list(500)
    for equip in equipment_list:
        equip['stats'] = await get_equipment_stats(equip['id'], api_key_doc['user_id'])
    return {"equipment": equipment_list, "count": len(equipment_list)}


@router.get("/equipment/{equipment_id}")
async def supplier_get_equipment(equipment_id: str, api_key_doc: dict = Depends(verify_api_key)):
    equipment = await db.equipment.find_one({"id": equipment_id, "user_id": api_key_doc['user_id']}, {"_id": 0})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    equipment['stats'] = await get_equipment_stats(equipment_id, api_key_doc['user_id'])
    issues = await db.issues.find({"user_id": api_key_doc['user_id'], "machine_name": equipment['name']}, {"_id": 0}).to_list(50)
    equipment['issues'] = issues
    return equipment


@router.post("/equipment")
async def supplier_create_equipment(equipment: Dict[str, Any], api_key_doc: dict = Depends(verify_api_key)):
    equipment_doc = {
        "id": str(uuid.uuid4()),
        "user_id": api_key_doc['user_id'],
        "name": equipment.get('name'),
        "equipment_type": equipment.get('equipment_type'),
        "manufacturer": equipment.get('manufacturer'),
        "model": equipment.get('model'),
        "serial_number": equipment.get('serial_number'),
        "purchase_date": equipment.get('purchase_date'),
        "warranty_expiry": equipment.get('warranty_expiry'),
        "length": equipment.get('length'),
        "width": equipment.get('width'),
        "height": equipment.get('height'),
        "notes": equipment.get('notes'),
        "manuals": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.equipment.insert_one(equipment_doc)
    equipment_doc.pop('_id', None)
    return equipment_doc


@router.patch("/equipment/{equipment_id}")
async def supplier_update_equipment(equipment_id: str, updates: Dict[str, Any], api_key_doc: dict = Depends(verify_api_key)):
    updates['updated_at'] = datetime.now(timezone.utc).isoformat()
    result = await db.equipment.update_one(
        {"id": equipment_id, "user_id": api_key_doc['user_id']},
        {"$set": updates}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return {"success": True, "updated_fields": list(updates.keys())}


@router.get("/issues")
async def supplier_list_issues(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    api_key_doc: dict = Depends(verify_api_key)
):
    query = {"user_id": api_key_doc['user_id']}
    if status:
        query['status'] = status
    if severity:
        query['severity'] = severity
    issues = await db.issues.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"issues": issues, "count": len(issues)}


@router.post("/issues")
async def supplier_create_issue(issue: Dict[str, Any], api_key_doc: dict = Depends(verify_api_key)):
    issue_doc = {
        "id": str(uuid.uuid4()),
        "user_id": api_key_doc['user_id'],
        "machine_name": issue.get('machine_name'),
        "machine_type": issue.get('machine_type'),
        "issue_description": issue.get('issue_description'),
        "severity": issue.get('severity', 'medium'),
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.issues.insert_one(issue_doc)
    issue_doc.pop('_id', None)
    return issue_doc


@router.patch("/issues/{issue_id}")
async def supplier_update_issue(issue_id: str, status: str, api_key_doc: dict = Depends(verify_api_key)):
    result = await db.issues.update_one(
        {"id": issue_id, "user_id": api_key_doc['user_id']},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Issue not found")
    return {"success": True}


@router.get("/service-requests")
async def supplier_list_service_requests(api_key_doc: dict = Depends(verify_api_key)):
    requests_list = await db.service_requests.find({"user_id": api_key_doc['user_id']}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"service_requests": requests_list, "count": len(requests_list)}


@router.patch("/service-requests/{request_id}")
async def supplier_update_service_request(request_id: str, status: str, api_key_doc: dict = Depends(verify_api_key)):
    result = await db.service_requests.update_one(
        {"id": request_id, "user_id": api_key_doc['user_id']},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Service request not found")
    return {"success": True}


@router.get("/webhooks/status")
async def supplier_webhook_status(api_key_doc: dict = Depends(verify_api_key)):
    webhook = await db.webhooks.find_one({"user_id": api_key_doc['user_id']}, {"_id": 0})
    return webhook if webhook else {"configured": False}


@router.post("/webhooks/register")
async def supplier_register_webhook(webhook_data: Dict[str, Any], api_key_doc: dict = Depends(verify_api_key)):
    webhook_doc = {
        "id": str(uuid.uuid4()),
        "user_id": api_key_doc['user_id'],
        "url": webhook_data.get('url'),
        "events": webhook_data.get('events', ['issue.created', 'service_request.created', 'equipment.updated']),
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.webhooks.update_one(
        {"user_id": api_key_doc['user_id']},
        {"$set": webhook_doc},
        upsert=True
    )
    return webhook_doc
