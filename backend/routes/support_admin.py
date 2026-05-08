"""Master Admin — Ask-Assistant audit export for SOC 2 / ISO 27001 evidence."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from utils.auth import get_current_user
from utils.database import db

from routes.master_admin import require_master_admin

router = APIRouter(prefix="/master-admin/support", tags=["support-admin"])


async def _scan_audit(org_id: str, since: str, until: str, limit: int) -> list[dict]:
    query: dict = {"created_at": {"$gte": since, "$lt": until}}
    if org_id:
        query["org_id"] = org_id
    return await db.support_audit.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)


def _iso_bounds(since: Optional[str], until: Optional[str]) -> tuple[str, str]:
    default_until = datetime.now(timezone.utc).isoformat()
    if not since:
        since = "1970-01-01T00:00:00+00:00"
    if not until:
        until = default_until
    return since, until


@router.get("/audit")
async def list_support_audit(
    org_id: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO timestamp lower bound"),
    until: Optional[str] = Query(None, description="ISO timestamp upper bound"),
    classifier_label: Optional[str] = Query(None),
    blocked_only: bool = Query(False),
    limit: int = Query(500, le=5000),
    user: dict = Depends(get_current_user),
) -> dict:
    """Filtered listing of `support_audit` rows for dashboard + CSV preview."""
    require_master_admin(user)
    since_iso, until_iso = _iso_bounds(since, until)
    rows = await _scan_audit(org_id or "", since_iso, until_iso, limit)
    if classifier_label:
        rows = [r for r in rows if r.get("classifier_label") == classifier_label]
    if blocked_only:
        rows = [r for r in rows if r.get("blocked")]
    return {"rows": rows, "total": len(rows), "since": since_iso, "until": until_iso}


_AUDIT_CSV_HEADERS = [
    "created_at", "org_id", "user_id", "session_id", "model", "latency_ms",
    "tokens_in", "tokens_out", "prompt_hash", "response_hash",
    "classifier_label", "classifier_confidence", "blocked", "block_reason",
    "tool_calls_proposed", "tool_calls_executed", "needs_human",
    "response_confidence", "pii_redaction_counts",
]


def _audit_row_to_csv(r: dict) -> list:
    return [
        r.get("created_at", ""), r.get("org_id", ""), r.get("user_id", ""),
        r.get("session_id", ""), r.get("model", ""), r.get("latency_ms", ""),
        r.get("tokens_in", "") or "", r.get("tokens_out", "") or "",
        r.get("prompt_hash", ""), r.get("response_hash", ""),
        r.get("classifier_label", ""), r.get("classifier_confidence", ""),
        "yes" if r.get("blocked") else "no", r.get("block_reason", "") or "",
        "|".join(r.get("tool_calls_proposed") or []),
        "|".join(r.get("tool_calls_executed") or []),
        "yes" if r.get("needs_human") else "no",
        r.get("response_confidence", ""),
        ",".join(f"{k}={v}" for k, v in (r.get("pii_redactions") or {}).items()),
    ]


@router.get("/audit/export")
async def export_support_audit(
    org_id: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """CSV export of the audit stream — one row per /ask request. Suitable for
    handing straight to a SOC 2 / ISO 27001 auditor."""
    require_master_admin(user)
    since_iso, until_iso = _iso_bounds(since, until)
    rows = await _scan_audit(org_id or "", since_iso, until_iso, 5000)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_AUDIT_CSV_HEADERS)
    for r in rows:
        writer.writerow(_audit_row_to_csv(r))
    buf.seek(0)
    filename = f"support-audit{'-' + org_id if org_id else ''}-{since_iso[:10]}-to-{until_iso[:10]}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/conversations/export")
async def export_support_conversations(
    org_id: str = Query(..., description="Required — export is per-org"),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Export the raw conversation transcripts for one org (not masked — intended
    for SAR / audit access). Caller accepts responsibility for handling the
    data; access is logged via `routes.master_admin.log_activity`."""
    require_master_admin(user)
    since_iso, until_iso = _iso_bounds(since, until)
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id is required for conversation export")

    query = {"org_id": org_id, "created_at": {"$gte": since_iso, "$lt": until_iso}}
    rows = await db.support_conversations.find(query, {"_id": 0}).sort("created_at", 1).limit(10000).to_list(length=10000)

    from routes.master_admin import log_activity
    await log_activity(
        "support_conversations_export",
        f"Exported {len(rows)} rows for org {org_id} ({since_iso}..{until_iso})",
        user["email"], "org", org_id,
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["created_at", "session_id", "user_id", "role", "text", "extra"])
    for r in rows:
        writer.writerow([
            r.get("created_at", ""), r.get("session_id", ""), r.get("user_id", ""),
            r.get("role", ""), (r.get("text") or "").replace("\n", " \\n ")[:4000],
            str(r.get("extra") or ""),
        ])
    buf.seek(0)
    filename = f"support-conversations-{org_id}-{since_iso[:10]}-to-{until_iso[:10]}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
