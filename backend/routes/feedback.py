"""In-app feedback + NPS widget (iter 215c0).

Records Net Promoter Score responses (0–10 + optional comment) and
generic page feedback. Master admins get a roll-up: distribution,
verbatim list, NPS trend over time.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/nps")
async def submit_nps(payload: dict, request: Request, user: dict = Depends(get_current_user)) -> dict:
    score = payload.get("score")
    if not isinstance(score, int) or score < 0 or score > 10:
        raise HTTPException(status_code=400, detail="Score must be an integer 0–10")
    comment = (payload.get("comment") or "").strip()[:1000]
    page = (payload.get("page") or "").strip()[:200]
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "type": "nps",
        "score": int(score),
        "comment": comment,
        "page": page,
        "user_id": user["id"],
        "user_email": user.get("email"),
        "organization_id": user.get("organization_id"),
        "user_role": user.get("role"),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:300],
        "created_at": now,
    }
    await db.feedback_responses.insert_one(doc)
    return {"id": doc["id"], "ok": True}


@router.post("/general")
async def submit_general(payload: dict, request: Request, user: dict = Depends(get_current_user)) -> dict:
    """Open-ended feedback widget (e.g. emoji + textarea)."""
    rating = payload.get("rating")
    comment = (payload.get("comment") or "").strip()
    if not comment and rating is None:
        raise HTTPException(status_code=400, detail="Provide a comment or rating")
    doc = {
        "id": str(uuid.uuid4()),
        "type": "general",
        "rating": rating if isinstance(rating, (int, str)) else None,
        "comment": comment[:2000],
        "page": (payload.get("page") or "").strip()[:200],
        "user_id": user["id"],
        "user_email": user.get("email"),
        "organization_id": user.get("organization_id"),
        "ip": request.client.host if request.client else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.feedback_responses.insert_one(doc)
    return {"id": doc["id"], "ok": True}


@router.get("/should-prompt")
async def should_prompt_user(user: dict = Depends(get_current_user)) -> dict:
    """Return whether to show the NPS widget. Show if the user has never
    answered, or last answered more than 90 days ago."""
    last = await db.feedback_responses.find_one(
        {"user_id": user["id"], "type": "nps"}, {"_id": 0, "created_at": 1},
        sort=[("created_at", -1)],
    )
    if not last:
        return {"should_prompt": True, "reason": "never_asked"}
    try:
        last_at = datetime.fromisoformat((last.get("created_at") or "").replace("Z", "+00:00"))
    except Exception:
        return {"should_prompt": True, "reason": "bad_timestamp"}
    age_days = (datetime.now(timezone.utc) - last_at).days
    return {"should_prompt": age_days >= 90, "reason": "cooldown", "age_days": age_days}


@router.post("/dismiss")
async def dismiss_prompt(user: dict = Depends(get_current_user)) -> dict:
    """Soft-dismiss: snooze the prompt 30 days by inserting a 'snooze' marker."""
    await db.feedback_responses.insert_one({
        "id": str(uuid.uuid4()),
        "type": "nps",
        "score": -1,  # sentinel: snoozed
        "comment": "",
        "snoozed": True,
        "user_id": user["id"],
        "user_email": user.get("email"),
        "organization_id": user.get("organization_id"),
        "created_at": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
    })
    return {"ok": True}


@router.get("/master-admin/nps")
async def admin_nps_summary(
    days: int = 90, user: dict = Depends(get_current_user)
) -> dict:
    """NPS roll-up for the master admin dashboard."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")
    days = max(1, min(int(days or 90), 365))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cursor = db.feedback_responses.find(
        {"type": "nps", "score": {"$gte": 0}, "created_at": {"$gte": since}},
        {"_id": 0},
    ).sort("created_at", -1)
    rows = await cursor.to_list(2_000)
    total = len(rows)
    promoters = sum(1 for r in rows if r["score"] >= 9)
    detractors = sum(1 for r in rows if r["score"] <= 6)
    nps = round(((promoters - detractors) / total) * 100, 1) if total else 0.0
    distribution = {str(i): 0 for i in range(11)}
    for r in rows:
        distribution[str(r["score"])] += 1
    verbatim = [
        {"score": r["score"], "comment": r.get("comment"), "user_email": r.get("user_email"),
         "page": r.get("page"), "created_at": r.get("created_at")}
        for r in rows if (r.get("comment") or "").strip()
    ][:50]
    return {
        "window_days": days,
        "total_responses": total,
        "promoters": promoters,
        "passives": total - promoters - detractors,
        "detractors": detractors,
        "nps": nps,
        "distribution": distribution,
        "verbatim": verbatim,
    }
