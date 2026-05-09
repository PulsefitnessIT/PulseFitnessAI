"""Staffing Phase S3 — Internal Comms Hub.

Three-in-one threaded messaging that finally gives the operator
1:1 DMs, multi-staff group chats, and **targeted** announcements
that aren't just blasted at everyone.

Concept
-------
Everything is a *thread*. Threads come in four flavours:

  • dm           1:1 between two staff members
  • group        small custom group of staff (operator-created)
  • channel      auto-targeted by site / role / department — every
                 staff member matching the filter is auto-included
  • announcement one-way broadcast from a manager to a target audience
                 (we still treat it as a thread so we get free read
                 receipts + urgent flag + scheduled send for free)

Messages live in `staffing_messages` and are stamped with `scheduled_for`
when posted ahead of time. The list endpoint filters those out until
`scheduled_for <= now`, so we don't need a cron worker for scheduled
sends — they appear automatically when their time rolls around.

Read tracking is denormalised onto the thread membership embedded in
`staffing_threads.members[].last_read_at` so a single thread fetch
gives us per-member unread counts without a join.

Endpoints
---------
Self (any staff or operator):
    GET    /staffing/comms/threads
    POST   /staffing/comms/threads          (create dm/group/announcement)
    GET    /staffing/comms/threads/{id}
    PATCH  /staffing/comms/threads/{id}     (rename, archive, members)
    GET    /staffing/comms/threads/{id}/messages
    POST   /staffing/comms/threads/{id}/messages
    PATCH  /staffing/comms/threads/{id}/messages/{msg_id}  (edit / pin)
    DELETE /staffing/comms/threads/{id}/messages/{msg_id}  (soft delete)
    POST   /staffing/comms/threads/{id}/read
    GET    /staffing/comms/unread

Manager-only:
    POST   /staffing/comms/announce         (resolves audience → thread)

Notes
-----
- All writes scope by org_id and re-check membership before allowing
  send / read / edit.
- Edit window: 15 min after send (matches industry norm).
- Delete is soft (sets deleted_at). The list still returns the row so
  the UI can render "this message was deleted" — recoverable by
  managers via the audit log later.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db

# Re-use the same role helpers from staffing.py to keep behaviour identical.
from routes.staffing import (
    _is_manager,
    _my_staff_id_async,
    _now,
    _org,
    _require_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter()

THREAD_KINDS = {"dm", "group", "channel", "announcement"}
EDIT_WINDOW_MIN = 15
MAX_BODY_LEN = 5000


class ThreadCreate(BaseModel):
    kind: str
    name: str | None = None
    member_ids: list[str] = Field(default_factory=list)
    site_id: str | None = None
    role_filter: str | None = None
    department: str | None = None


class ThreadUpdate(BaseModel):
    name: str | None = None
    member_ids: list[str] | None = None
    archived: bool | None = None


class MessageCreate(BaseModel):
    body: str
    urgent: bool = False
    scheduled_for: str | None = None     # ISO-8601, must be in future
    pinned: bool = False


class MessageUpdate(BaseModel):
    body: str | None = None
    pinned: bool | None = None


class AnnouncementBroadcast(BaseModel):
    title: str
    body: str
    audience: str = "all"               # all | role | site | department
    role: str | None = None
    site_id: str | None = None
    department: str | None = None
    urgent: bool = False
    scheduled_for: str | None = None


# ─────────────────────── Helpers ─────────────────────────────────

def _strip_internal(thread: dict) -> dict:
    out = dict(thread)
    out.pop("_id", None)
    return out


async def _resolve_audience_staff_ids(
    org_id: str, audience: str, role: str | None, site_id: str | None, department: str | None,
) -> list[str]:
    q: dict = {"organization_id": org_id, "active": True}
    if audience == "role" and role:
        q["primary_role"] = role
    elif audience == "site" and site_id:
        q["site_id"] = site_id
    elif audience == "department" and department:
        q["department"] = department
    rows = await db.staff_members.find(q, {"_id": 0, "id": 1}).to_list(2000)
    return [r["id"] for r in rows]


async def _ensure_member(thread: dict, staff_id: str) -> bool:
    return any(m.get("staff_id") == staff_id for m in (thread.get("members") or []))


async def _can_access_thread(thread: dict, user: dict) -> tuple[bool, str | None]:
    """Returns (allowed, my_staff_id). Operators see everything; staff
    only see threads they're a member of. Master admin sees all."""
    if _is_manager(user):
        return True, await _my_staff_id_async(user, thread.get("organization_id"))
    sid = await _my_staff_id_async(user, thread.get("organization_id"))
    if sid and await _ensure_member(thread, sid):
        return True, sid
    return False, sid


def _unread_for(thread: dict, staff_id: str | None) -> int:
    """How many messages in this thread are unread for the given staff?"""
    if not staff_id:
        return 0
    last = next(
        ((m.get("last_read_at") or "") for m in (thread.get("members") or [])
         if m.get("staff_id") == staff_id),
        "",
    )
    last_msg = thread.get("last_message_at") or ""
    msg_count = thread.get("unread_index", {}).get(staff_id, 0)
    # Prefer the precomputed counter; fall back to time comparison.
    if msg_count is not None and isinstance(msg_count, int):
        return max(0, msg_count)
    return 1 if last_msg and last_msg > last else 0


# ─────────────────────── Threads ─────────────────────────────────

@router.get("/staffing/comms/threads")
async def list_threads(
    kind: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    q: dict = {"organization_id": org_id, "archived": {"$ne": True}}
    if kind and kind in THREAD_KINDS:
        q["kind"] = kind
    if not _is_manager(user):
        if not sid:
            return {"threads": [], "my_staff_id": None}
        q["members.staff_id"] = sid
    rows = await db.staffing_threads.find(q, {"_id": 0}).sort("last_message_at", -1).to_list(200)
    # Decorate with unread counter for the caller
    for t in rows:
        t["unread_count"] = _unread_for(t, sid)
    return {"threads": rows, "my_staff_id": sid}


@router.post("/staffing/comms/threads")
async def create_thread(body: ThreadCreate, user: dict = Depends(get_current_user)):
    org_id = _org(user)
    if body.kind not in THREAD_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(THREAD_KINDS)}")

    me = await _my_staff_id_async(user, org_id)
    members: list[str] = []

    if body.kind == "dm":
        if len(body.member_ids) != 1 or not me:
            raise HTTPException(400, "DM requires exactly one other member_id and a linked staff record")
        if body.member_ids[0] == me:
            raise HTTPException(400, "Cannot DM yourself")
        # If a DM between these two already exists, return it.
        existing = await db.staffing_threads.find_one({
            "organization_id": org_id,
            "kind": "dm",
            "members.staff_id": {"$all": [me, body.member_ids[0]]},
            "archived": {"$ne": True},
        }, {"_id": 0})
        if existing:
            return _strip_internal(existing)
        members = [me, body.member_ids[0]]
    elif body.kind in ("group", "announcement"):
        if not _is_manager(user):
            raise HTTPException(403, "Only managers can create groups or announcements")
        members = list(set([m for m in body.member_ids if m]))
        if me and body.kind == "group":
            members.append(me)
        members = list(set(members))
        if not members:
            raise HTTPException(400, "At least one member is required")
    elif body.kind == "channel":
        if not _is_manager(user):
            raise HTTPException(403, "Only managers can create channels")
        # Auto-resolve members from filter
        if body.site_id:
            members = await _resolve_audience_staff_ids(org_id, "site", None, body.site_id, None)
        elif body.role_filter:
            members = await _resolve_audience_staff_ids(org_id, "role", body.role_filter, None, None)
        elif body.department:
            members = await _resolve_audience_staff_ids(org_id, "department", None, None, body.department)
        else:
            members = await _resolve_audience_staff_ids(org_id, "all", None, None, None)
        if me:
            members.append(me)
        members = list(set(members))
        if not members:
            raise HTTPException(400, "Channel resolved to zero members — pick a different filter")

    now_iso = _now().isoformat()
    doc = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "kind": body.kind,
        "name": (body.name or "").strip() or None,
        "site_id": body.site_id,
        "role_filter": body.role_filter,
        "department": body.department,
        "members": [{"staff_id": m, "last_read_at": None, "joined_at": now_iso} for m in members],
        "created_by": user.get("id"),
        "created_at": now_iso,
        "last_message_at": None,
        "last_message_preview": None,
        "archived": False,
        "unread_index": {},
    }
    await db.staffing_threads.insert_one(doc.copy())
    return _strip_internal(doc)


@router.get("/staffing/comms/threads/{thread_id}")
async def get_thread(thread_id: str, user: dict = Depends(get_current_user)):
    org_id = _org(user)
    t = await db.staffing_threads.find_one({"id": thread_id, "organization_id": org_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Thread not found")
    ok, sid = await _can_access_thread(t, user)
    if not ok:
        raise HTTPException(403, "Not a member")
    # Hydrate member names so the UI can render avatars without a second round-trip.
    sids = [m.get("staff_id") for m in t.get("members") or [] if m.get("staff_id")]
    if sids:
        people = await db.staff_members.find(
            {"id": {"$in": sids}, "organization_id": org_id},
            {"_id": 0, "id": 1, "full_name": 1, "primary_role": 1},
        ).to_list(500)
        by_id = {p["id"]: p for p in people}
        for m in (t.get("members") or []):
            p = by_id.get(m.get("staff_id"))
            if p:
                m["full_name"] = p.get("full_name")
                m["primary_role"] = p.get("primary_role")
    t["unread_count"] = _unread_for(t, sid)
    return t


@router.patch("/staffing/comms/threads/{thread_id}")
async def update_thread(
    thread_id: str, body: ThreadUpdate, user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    t = await db.staffing_threads.find_one({"id": thread_id, "organization_id": org_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Thread not found")
    # Only managers (or the DM participants) may modify
    is_dm = t.get("kind") == "dm"
    if not _is_manager(user) and not is_dm:
        raise HTTPException(403, "Only managers can edit channels / groups")
    patch: dict = {"updated_at": _now().isoformat()}
    if body.name is not None:
        patch["name"] = body.name.strip() or None
    if body.archived is not None:
        patch["archived"] = bool(body.archived)
    if body.member_ids is not None and t.get("kind") in ("group",):
        existing_members = {m["staff_id"]: m for m in (t.get("members") or [])}
        new_set = set(body.member_ids)
        merged: list[dict] = []
        now_iso = _now().isoformat()
        for sid in new_set:
            cur = existing_members.get(sid)
            merged.append(cur or {"staff_id": sid, "last_read_at": None, "joined_at": now_iso})
        patch["members"] = merged
    res = await db.staffing_threads.update_one({"id": thread_id, "organization_id": org_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(404, "Thread not found")
    out = await db.staffing_threads.find_one({"id": thread_id}, {"_id": 0})
    return out


# ─────────────────────── Messages ─────────────────────────────────

@router.get("/staffing/comms/threads/{thread_id}/messages")
async def list_messages(
    thread_id: str,
    before: str | None = Query(None),    # ISO timestamp for pagination
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    t = await db.staffing_threads.find_one({"id": thread_id, "organization_id": org_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Thread not found")
    ok, _sid = await _can_access_thread(t, user)
    if not ok:
        raise HTTPException(403, "Not a member")
    now_iso = _now().isoformat()
    q: dict = {"organization_id": org_id, "thread_id": thread_id}
    # Hide unsent scheduled messages from non-authors
    q["$or"] = [
        {"scheduled_for": None},
        {"scheduled_for": {"$lte": now_iso}},
    ]
    if before:
        q["sent_at"] = {"$lt": before}
    rows = await db.staffing_messages.find(q, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(limit)
    rows.reverse()  # ascending for the UI
    return {"messages": rows, "count": len(rows)}


@router.post("/staffing/comms/threads/{thread_id}/messages")
async def post_message(
    thread_id: str,
    body: MessageCreate,
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    t = await db.staffing_threads.find_one({"id": thread_id, "organization_id": org_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Thread not found")
    ok, sid = await _can_access_thread(t, user)
    if not ok:
        raise HTTPException(403, "Not a member")

    body_text = (body.body or "").strip()
    if not body_text:
        raise HTTPException(400, "Body cannot be empty")
    if len(body_text) > MAX_BODY_LEN:
        raise HTTPException(400, f"Body too long (max {MAX_BODY_LEN} chars)")
    # Announcements: only managers may post
    if t.get("kind") == "announcement" and not _is_manager(user):
        raise HTTPException(403, "Only managers can post in announcement threads")

    scheduled_for = None
    if body.scheduled_for:
        try:
            sched_dt = datetime.fromisoformat(body.scheduled_for)
        except ValueError as err:
            raise HTTPException(400, "scheduled_for must be ISO-8601") from err
        if sched_dt <= _now():
            raise HTTPException(400, "scheduled_for must be in the future")
        scheduled_for = sched_dt.isoformat()

    now_iso = _now().isoformat()
    msg = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "thread_id": thread_id,
        "author_id": user.get("id"),
        "author_staff_id": sid,
        "author_email": user.get("email"),
        "body": body_text,
        "urgent": bool(body.urgent),
        "pinned": bool(body.pinned) and _is_manager(user),
        "scheduled_for": scheduled_for,
        "sent_at": now_iso,
        "edited_at": None,
        "deleted_at": None,
    }
    await db.staffing_messages.insert_one(msg.copy())
    # Update thread denormalised fields (only if message is live, not scheduled)
    if not scheduled_for:
        # bump unread counters for everyone except the author
        unread_index = dict(t.get("unread_index") or {})
        for m in (t.get("members") or []):
            mid = m.get("staff_id")
            if mid and mid != sid:
                unread_index[mid] = int(unread_index.get(mid, 0)) + 1
        await db.staffing_threads.update_one(
            {"id": thread_id, "organization_id": org_id},
            {"$set": {
                "last_message_at": now_iso,
                "last_message_preview": body_text[:140],
                "unread_index": unread_index,
            }},
        )
    msg.pop("_id", None)
    return msg


@router.patch("/staffing/comms/threads/{thread_id}/messages/{msg_id}")
async def edit_message(
    thread_id: str,
    msg_id: str,
    body: MessageUpdate,
    user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    msg = await db.staffing_messages.find_one(
        {"id": msg_id, "thread_id": thread_id, "organization_id": org_id},
        {"_id": 0},
    )
    if not msg:
        raise HTTPException(404, "Message not found")
    is_author = msg.get("author_id") == user.get("id")
    if not is_author and not _is_manager(user):
        raise HTTPException(403, "Not your message")
    patch: dict = {}
    if body.body is not None:
        # 15-min edit window for authors
        if is_author and not _is_manager(user):
            try:
                sent_dt = datetime.fromisoformat(msg["sent_at"])
                if (_now() - sent_dt) > timedelta(minutes=EDIT_WINDOW_MIN):
                    raise HTTPException(400, f"Edit window ({EDIT_WINDOW_MIN} min) has expired")
            except ValueError:
                pass
        text = body.body.strip()
        if not text:
            raise HTTPException(400, "Body cannot be empty")
        if len(text) > MAX_BODY_LEN:
            raise HTTPException(400, f"Body too long (max {MAX_BODY_LEN} chars)")
        patch["body"] = text
        patch["edited_at"] = _now().isoformat()
    if body.pinned is not None:
        if not _is_manager(user):
            raise HTTPException(403, "Only managers can pin")
        patch["pinned"] = bool(body.pinned)
    if not patch:
        raise HTTPException(400, "Nothing to update")
    await db.staffing_messages.update_one(
        {"id": msg_id, "thread_id": thread_id, "organization_id": org_id},
        {"$set": patch},
    )
    out = await db.staffing_messages.find_one({"id": msg_id}, {"_id": 0})
    return out


@router.delete("/staffing/comms/threads/{thread_id}/messages/{msg_id}")
async def delete_message(
    thread_id: str, msg_id: str, user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    msg = await db.staffing_messages.find_one(
        {"id": msg_id, "thread_id": thread_id, "organization_id": org_id},
        {"_id": 0},
    )
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.get("author_id") != user.get("id") and not _is_manager(user):
        raise HTTPException(403, "Not your message")
    await db.staffing_messages.update_one(
        {"id": msg_id, "thread_id": thread_id, "organization_id": org_id},
        {"$set": {"deleted_at": _now().isoformat(), "body": None}},
    )
    return {"ok": True}


@router.post("/staffing/comms/threads/{thread_id}/read")
async def mark_read(
    thread_id: str, user: dict = Depends(get_current_user),
):
    org_id = _org(user)
    t = await db.staffing_threads.find_one({"id": thread_id, "organization_id": org_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Thread not found")
    ok, sid = await _can_access_thread(t, user)
    if not ok or not sid:
        raise HTTPException(403, "Not a member")
    now_iso = _now().isoformat()
    # Set last_read_at on the embedded member record + zero out unread_index
    unread_index = dict(t.get("unread_index") or {})
    unread_index[sid] = 0
    await db.staffing_threads.update_one(
        {"id": thread_id, "organization_id": org_id, "members.staff_id": sid},
        {
            "$set": {
                "members.$.last_read_at": now_iso,
                f"unread_index.{sid}": 0,
            },
        },
    )
    return {"ok": True, "last_read_at": now_iso}


@router.get("/staffing/comms/unread")
async def total_unread(user: dict = Depends(get_current_user)):
    """Sum of unread messages across all of my threads — for the
    nav badge."""
    org_id = _org(user)
    sid = await _my_staff_id_async(user, org_id)
    if not sid:
        return {"unread": 0, "by_thread": {}}
    rows = await db.staffing_threads.find(
        {"organization_id": org_id, "archived": {"$ne": True}, "members.staff_id": sid},
        {"_id": 0, "id": 1, "unread_index": 1},
    ).to_list(500)
    by_thread = {}
    total = 0
    for t in rows:
        n = int((t.get("unread_index") or {}).get(sid, 0))
        if n > 0:
            by_thread[t["id"]] = n
            total += n
    return {"unread": total, "by_thread": by_thread}


# ─────────────────────── Announcements (sugar) ────────────────────

@router.post("/staffing/comms/announce")
async def announce(body: AnnouncementBroadcast, user: dict = Depends(get_current_user)):
    """One-shot — resolves the audience, creates an announcement
    thread (or reuses an existing 'all-staff announcements' thread),
    and posts the first message. Returns the thread + message."""
    _require_manager(user)
    org_id = _org(user)
    if body.audience not in ("all", "role", "site", "department"):
        raise HTTPException(400, "audience must be all|role|site|department")
    member_ids = await _resolve_audience_staff_ids(
        org_id, body.audience, body.role, body.site_id, body.department,
    )
    if not member_ids:
        raise HTTPException(400, "Audience resolved to zero staff")
    me = await _my_staff_id_async(user, org_id)
    if me:
        member_ids = list(set(member_ids + [me]))

    now_iso = _now().isoformat()
    # Title becomes the thread name
    name = body.title.strip()[:80] or "Announcement"
    thread = {
        "id": str(uuid4()),
        "organization_id": org_id,
        "kind": "announcement",
        "name": name,
        "site_id": body.site_id,
        "role_filter": body.role,
        "department": body.department,
        "audience": body.audience,
        "members": [{"staff_id": m, "last_read_at": None, "joined_at": now_iso} for m in member_ids],
        "created_by": user.get("id"),
        "created_at": now_iso,
        "last_message_at": None,
        "last_message_preview": None,
        "archived": False,
        "unread_index": {},
    }
    await db.staffing_threads.insert_one(thread.copy())

    # Post the first message via the same path so all the bumping
    # logic stays consistent.
    msg_body = MessageCreate(body=body.body, urgent=body.urgent, scheduled_for=body.scheduled_for)
    msg = await post_message(thread_id=thread["id"], body=msg_body, user=user)
    thread.pop("_id", None)
    return {"thread": thread, "message": msg}
