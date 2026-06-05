from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import uuid

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit

router = APIRouter(prefix="/crm/workflows", tags=["CRM Workflows"])

TRIGGER_TYPES = {
    "deal_stage_changed": {"label": "Deal Stage Changed", "fields": ["from_stage", "to_stage"]},
    "contact_created": {"label": "Contact Created", "fields": []},
    "deal_created": {"label": "Deal Created", "fields": []},
    "contact_tag_added": {"label": "Tag Added to Contact", "fields": ["tag"]},
    "deal_value_above": {"label": "Deal Value Above", "fields": ["threshold"]},
    "no_activity_days": {"label": "No Activity for X Days", "fields": ["days"]},
}

ACTION_TYPES = {
    "create_task": {"label": "Create Task", "fields": ["task_description", "priority"]},
    "send_notification": {"label": "Send Notification", "fields": ["message"]},
    "move_deal_stage": {"label": "Move Deal Stage", "fields": ["target_stage"]},
    "add_tag": {"label": "Add Tag to Contact", "fields": ["tag"]},
    "create_activity": {"label": "Log Activity", "fields": ["activity_type", "description"]},
    "wait": {"label": "Wait (Days)", "fields": ["days"]},
}


@router.get("/meta")
async def workflow_meta(user=Depends(get_crm_user)):
    """Return available trigger and action types for the builder UI."""
    return {"triggers": TRIGGER_TYPES, "actions": ACTION_TYPES}


@router.get("")
async def list_workflows(user=Depends(get_crm_user)):
    workflows = await db.crm_workflows.find({"organization_id": user.get("organization_id")}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"workflows": workflows}


@router.post("")
async def create_workflow(data: dict, user=Depends(get_crm_user)):
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Only admins/managers can create workflows")

    wf_id = str(uuid.uuid4())
    workflow = {
        "id": wf_id,
        "organization_id": user.get("organization_id"),
        "name": data.get("name", "Untitled Workflow"),
        "description": data.get("description", ""),
        "active": data.get("active", False),
        "trigger": data.get("trigger", {}),
        "conditions": data.get("conditions", []),
        "actions": data.get("actions", []),
        "created_by": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "execution_count": 0,
        "last_executed": None,
    }
    await db.crm_workflows.insert_one(workflow)
    await log_audit(user, "workflow", wf_id, "created")
    workflow.pop("_id", None)
    return workflow


@router.get("/{wf_id}")
async def get_workflow(wf_id: str, user=Depends(get_crm_user)):
    wf = await db.crm_workflows.find_one({"id": wf_id, "organization_id": user.get("organization_id")}, {"_id": 0})
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/{wf_id}")
async def update_workflow(wf_id: str, data: dict, user=Depends(get_crm_user)):
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Only admins/managers can edit workflows")
    updates = {k: v for k, v in data.items() if k not in ("id", "created_at", "created_by")}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.crm_workflows.update_one({"id": wf_id, "organization_id": user.get("organization_id")}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await log_audit(user, "workflow", wf_id, "updated")
    return {"status": "updated"}


@router.delete("/{wf_id}")
async def delete_workflow(wf_id: str, user=Depends(get_crm_user)):
    if user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Only admins/managers can delete workflows")
    result = await db.crm_workflows.delete_one({"id": wf_id, "organization_id": user.get("organization_id")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await log_audit(user, "workflow", wf_id, "deleted")
    return {"status": "deleted"}


@router.post("/{wf_id}/toggle")
async def toggle_workflow(wf_id: str, user=Depends(get_crm_user)):
    wf = await db.crm_workflows.find_one({"id": wf_id, "organization_id": user.get("organization_id")})
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    new_status = not wf.get("active", False)
    await db.crm_workflows.update_one({"id": wf_id, "organization_id": user.get("organization_id")}, {"$set": {"active": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}})
    await log_audit(user, "workflow", wf_id, "toggled", {"active": new_status})
    return {"active": new_status}


@router.get("/{wf_id}/logs")
async def workflow_logs(wf_id: str, skip: int = 0, limit: int = 20, user=Depends(get_crm_user)):
    logs = await db.crm_workflow_logs.find({"workflow_id": wf_id}, {"_id": 0}).sort("executed_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"logs": logs}


def _check_trigger_match(trigger_type: str, trigger: dict, context: dict) -> bool:
    """Check if workflow trigger conditions match the event context."""
    matchers = {
        "deal_stage_changed": _match_stage_change,
        "deal_value_above": _match_value_threshold,
        "contact_tag_added": _match_tag,
    }
    matcher = matchers.get(trigger_type)
    if matcher:
        return matcher(trigger, context)
    return True


def _match_stage_change(trigger: dict, context: dict) -> bool:
    if trigger.get("from_stage") and trigger["from_stage"] != context.get("from_stage"):
        return False
    return not (trigger.get("to_stage") and trigger["to_stage"] != context.get("to_stage"))


def _match_value_threshold(trigger: dict, context: dict) -> bool:
    return float(context.get("value", 0)) >= float(trigger.get("threshold", 0))


def _match_tag(trigger: dict, context: dict) -> bool:
    return not (trigger.get("tag") and trigger["tag"] != context.get("tag"))


async def _execute_action(action: dict, context: dict, wf_name: str) -> str:
    """Execute a single workflow action. Returns the action type executed."""
    now = datetime.now(timezone.utc).isoformat()
    action_type = action.get("type")

    if action_type == "create_task":
        await db.crm_activities.insert_one({
            "id": str(uuid.uuid4()), "type": "task",
            "contact_id": context.get("contact_id"), "deal_id": context.get("deal_id"),
            "company_id": context.get("company_id"),
            "description": action.get("task_description", "Auto-created task"),
            "metadata": {"priority": action.get("priority", "medium"), "from_workflow": context.get("wf_id"), "completed": False},
            "created_by": "system", "created_by_name": f"Workflow: {wf_name}", "created_at": now,
        })
    elif action_type == "create_activity":
        await db.crm_activities.insert_one({
            "id": str(uuid.uuid4()), "type": action.get("activity_type", "note"),
            "contact_id": context.get("contact_id"), "deal_id": context.get("deal_id"),
            "company_id": context.get("company_id"),
            "description": action.get("description", "Auto-logged activity"),
            "created_by": "system", "created_by_name": f"Workflow: {wf_name}", "created_at": now,
        })
    elif action_type == "move_deal_stage" and context.get("deal_id"):
        await db.crm_deals.update_one(
            {"id": context["deal_id"]},
            {"$set": {"stage": action.get("target_stage"), "updated_at": now}},
        )
    elif action_type == "add_tag" and context.get("contact_id"):
        await db.crm_contacts.update_one(
            {"id": context["contact_id"]},
            {"$addToSet": {"tags": action.get("tag")}},
        )
    else:
        return ""
    return action_type


async def execute_workflow_trigger(trigger_type: str, context: dict):
    """Called internally when a trigger event occurs."""
    import logging
    logger = logging.getLogger(__name__)

    workflows = await db.crm_workflows.find({"active": True, "trigger.type": trigger_type}, {"_id": 0}).to_list(50)

    for wf in workflows:
        try:
            if not _check_trigger_match(trigger_type, wf.get("trigger", {}), context):
                continue

            ctx = {**context, "wf_id": wf["id"]}
            actions_executed = []
            for action in wf.get("actions", []):
                result = await _execute_action(action, ctx, wf["name"])
                if result:
                    actions_executed.append(result)

            await db.crm_workflow_logs.insert_one({
                "id": str(uuid.uuid4()), "workflow_id": wf["id"], "trigger_type": trigger_type,
                "context": {k: v for k, v in context.items() if k != "_id"},
                "actions_executed": actions_executed,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            })
            await db.crm_workflows.update_one(
                {"id": wf["id"]},
                {"$inc": {"execution_count": 1}, "$set": {"last_executed": datetime.now(timezone.utc).isoformat()}},
            )

        except Exception as e:
            logger.error(f"Workflow {wf['id']} execution failed: {e}")
