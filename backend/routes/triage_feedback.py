"""Triage learning loop — capture what the user tried before logging.

After a fault is logged, the floor staff is asked: "Did you try
anything before logging this?" If yes, we capture which AI-suggested
fix steps they attempted (or freeform notes) and persist to
``triage_attempts``. This becomes training data for the AI brain so
future triage suggestions can be ranked by what real users
historically tried first.

Per Craig's exec review feedback (Apr 29 2026, iteration 222).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/issues/{issue_id}/triage-feedback")
async def record_triage_feedback(
    issue_id: str,
    payload: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Capture what the user tried before logging a fault.

    Payload::

        {
            "attempted":      bool,                  # did they try anything?
            "tried_steps":    [str, str, ...],       # repair_steps[].title strings they tried
            "tried_other":    str,                   # freeform "tried something else" note
            "outcome":        "worked" | "no_change" | "made_worse" | None,
        }
    """
    issue = await db.issues.find_one({"id": issue_id}, {"_id": 0, "id": 1, "organization_id": 1, "ai_triage": 1})
    if not issue:
        raise HTTPException(404, "Issue not found")
    # Tenancy guard: only allow attribution within the user's org.
    if user.get("organization_id") and issue.get("organization_id") and \
       user.get("organization_id") != issue.get("organization_id"):
        raise HTTPException(403, "Cross-tenant feedback not allowed")

    attempted = bool(payload.get("attempted"))
    tried_steps = [s for s in (payload.get("tried_steps") or []) if isinstance(s, str)]
    tried_other = (payload.get("tried_other") or "").strip()[:500]
    outcome_raw = (payload.get("outcome") or "").strip().lower()
    outcome = outcome_raw if outcome_raw in ("worked", "no_change", "made_worse") else None

    record = {
        "id": str(uuid.uuid4()),
        "issue_id": issue_id,
        "organization_id": issue.get("organization_id"),
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "attempted": attempted,
        "tried_steps": tried_steps,
        "tried_other": tried_other,
        "outcome": outcome,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.triage_attempts.insert_one(dict(record))
    record.pop("_id", None)
    return {"ok": True, "id": record["id"], "stored": record}


@router.get("/issues/{issue_id}/triage-feedback")
async def list_triage_feedback(
    issue_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return all triage-attempt rows for one issue (admin/debug view)."""
    rows = await db.triage_attempts.find(
        {"issue_id": issue_id}, {"_id": 0},
    ).sort("created_at", 1).to_list(length=200)
    return {"feedback": rows}


async def ensure_triage_attempts_indexes() -> None:
    try:
        await db.triage_attempts.create_index("issue_id")
        await db.triage_attempts.create_index("organization_id")
        await db.triage_attempts.create_index("created_at")
    except Exception:
        logger.exception("ensure_triage_attempts_indexes failed (non-fatal)")
