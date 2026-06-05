"""Iter 216h209 — Client error telemetry endpoint.

`ModalErrorBoundary.jsx` (front-end) POSTs a structured error payload
here whenever a React render crashes inside a wrapped modal/drawer.
Stored to `client_errors` so the next session can grep for repeat
offenders instead of relying on stakeholder screenshots.

The endpoint is intentionally permissive:
  • Auth header is optional (member portals run unauth → still send).
  • No Pydantic validation — we want partial payloads through.
  • Returns 204 on success (no body).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from utils.security_plus import safe_regex

from utils.auth import get_current_user
from utils.database import db


router = APIRouter()


@router.post("/client-errors", status_code=204)
async def ingest_client_error(request: Request) -> Response:
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}
    user_id = None
    org_id = None
    # Best-effort: if there's an Authorization header, decode it.
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from utils.security import verify_token
            payload = verify_token(auth.split(" ", 1)[1])
            if payload:
                user_id = payload.get("user_id") or payload.get("member_id")
                org_id = payload.get("organization_id")
        except Exception:
            pass
    doc = {
        "id": str(uuid.uuid4()),
        "scope": str(body.get("scope", "unknown"))[:40],
        "label": str(body.get("label", ""))[:120],
        "message": str(body.get("message", ""))[:600],
        "stack": str(body.get("stack", ""))[:4000],
        "component_stack": str(body.get("component_stack", ""))[:4000],
        "url": str(body.get("url", ""))[:500],
        "user_agent": str(body.get("ua", ""))[:300],
        "client_ts": str(body.get("ts", ""))[:40],
        "server_ts": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "organization_id": org_id,
        "ip": request.client.host if request.client else None,
    }
    try:
        await db.client_errors.insert_one(doc)
    except Exception:
        # Telemetry must never break the request.
        pass
    return Response(status_code=204)


@router.get("/master-admin/client-errors")
async def list_client_errors(
    limit: int = 100,
    label: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """Master Admin diagnostics — list the most recent client-side
    render crashes captured by ``ModalErrorBoundary``.

    Iter 216h210 — paired with the failed-login timeline so the
    security/QA team has a single page that answers "why did Craig's
    session break".
    """
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")
    limit_i = max(1, min(int(limit or 100), 500))
    query: dict[str, Any] = {}
    if label:
        query["label"] = safe_regex(label)
    cursor = db.client_errors.find(query, {"_id": 0}).sort("server_ts", -1).limit(limit_i)
    rows = await cursor.to_list(length=limit_i)
    # Group counts by label so the dashboard can show "Class Builder: 4 errors".
    by_label: dict[str, int] = {}
    for r in rows:
        lab = r.get("label") or "unknown"
        by_label[lab] = by_label.get(lab, 0) + 1
    return {
        "errors": rows,
        "count": len(rows),
        "by_label": [{"label": k, "count": v} for k, v in sorted(by_label.items(), key=lambda kv: -kv[1])],
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
