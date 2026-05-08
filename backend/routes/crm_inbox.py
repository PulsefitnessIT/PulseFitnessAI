from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import uuid

from utils.database import db
from routes.crm_auth import get_crm_user

router = APIRouter(prefix="/crm/inbox", tags=["CRM Inbox"])


# ==================== CONVERSATIONS ====================
@router.get("/conversations")
async def list_conversations(
    status: str = "", assigned_to: str = "", priority: str = "",
    skip: int = 0, limit: int = 50,
    user=Depends(get_crm_user)
):
    query = {}
    if status:
        query["status"] = status
    if assigned_to:
        query["assigned_to"] = assigned_to
    if priority:
        query["priority"] = priority

    total = await db.crm_conversations.count_documents(query)
    conversations = await db.crm_conversations.find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"conversations": conversations, "total": total}


@router.post("/conversations")
async def create_conversation(data: dict, user=Depends(get_crm_user)):
    conv_id = str(uuid.uuid4())
    conversation = {
        "id": conv_id,
        "subject": data.get("subject", ""),
        "contact_id": data.get("contact_id"),
        "contact_name": data.get("contact_name", ""),
        "deal_id": data.get("deal_id"),
        "channel": data.get("channel", "internal"),
        "status": "open",
        "priority": data.get("priority", "normal"),
        "assigned_to": data.get("assigned_to", user["id"]),
        "assigned_to_name": data.get("assigned_to_name", user["full_name"]),
        "created_by": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_message": data.get("message", ""),
        "message_count": 1,
    }
    await db.crm_conversations.insert_one(conversation)

    # Create first message
    if data.get("message"):
        await db.crm_messages.insert_one({
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "sender_id": user["id"],
            "sender_name": user["full_name"],
            "content": data["message"],
            "is_internal_note": data.get("is_internal_note", False),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    conversation.pop("_id", None)
    return conversation


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, user=Depends(get_crm_user)):
    conv = await db.crm_conversations.find_one({"id": conv_id}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await db.crm_messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {**conv, "messages": messages}


@router.post("/conversations/{conv_id}/messages")
async def add_message(conv_id: str, data: dict, user=Depends(get_crm_user)):
    conv = await db.crm_conversations.find_one({"id": conv_id})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message = {
        "id": str(uuid.uuid4()),
        "conversation_id": conv_id,
        "sender_id": user["id"],
        "sender_name": user["full_name"],
        "content": data.get("content", ""),
        "is_internal_note": data.get("is_internal_note", False),
        "mentioned_users": data.get("mentioned_users", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_messages.insert_one(message)

    # Update conversation
    await db.crm_conversations.update_one(
        {"id": conv_id},
        {"$set": {
            "last_message": data.get("content", ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, "$inc": {"message_count": 1}}
    )

    message.pop("_id", None)
    return message


@router.put("/conversations/{conv_id}")
async def update_conversation(conv_id: str, data: dict, user=Depends(get_crm_user)):
    updates = {k: v for k, v in data.items() if k in ("status", "priority", "assigned_to", "assigned_to_name", "subject")}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.crm_conversations.update_one({"id": conv_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Log status change as activity
    if "status" in updates:
        await db.crm_messages.insert_one({
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "sender_id": user["id"],
            "sender_name": user["full_name"],
            "content": f"Status changed to {updates['status']}",
            "is_internal_note": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    return {"status": "updated"}


@router.get("/stats")
async def inbox_stats(user=Depends(get_crm_user)):
    total = await db.crm_conversations.count_documents({})
    open_count = await db.crm_conversations.count_documents({"status": "open"})
    assigned_to_me = await db.crm_conversations.count_documents({"assigned_to": user["id"], "status": "open"})
    high_priority = await db.crm_conversations.count_documents({"priority": "high", "status": "open"})
    return {
        "total": total,
        "open": open_count,
        "assigned_to_me": assigned_to_me,
        "high_priority": high_priority,
    }
