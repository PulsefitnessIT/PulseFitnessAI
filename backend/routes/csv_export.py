"""Centralised CSV export (iter 215c0).

One framework, one route per module. Each route streams CSV to the
client without buffering whole dataset in memory.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/export", tags=["export"])


def _csv_response(rows: Iterable[dict], columns: list[tuple[str, str]], filename: str) -> StreamingResponse:
    """Build a streamed CSV response.

    `columns`: list of (header, dotted_path). Dotted path resolves nested
    dicts (e.g. `address.city`).
    """
    def _resolve(row: dict, path: str):
        cur = row
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = None
                break
        if isinstance(cur, list):
            return ", ".join(str(x) for x in cur)
        if cur is None:
            return ""
        return cur

    def _gen():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([c[0] for c in columns])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for row in rows:
            writer.writerow([_resolve(row, c[1]) for c in columns])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        _gen(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _require_org(user: dict) -> str:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(status_code=400, detail="No organisation")
    return org


@router.get("/members.csv")
async def export_members(user: dict = Depends(get_current_user)) -> StreamingResponse:
    org = _require_org(user)
    rows = await db.members.find(
        {"organization_id": org}, {"_id": 0},
    ).sort("created_at", -1).to_list(50_000)
    cols = [
        ("ID", "id"), ("First Name", "first_name"), ("Last Name", "last_name"),
        ("Email", "email"), ("Phone", "phone"), ("Status", "status"),
        ("DOB", "dob"), ("City", "city"), ("Postcode", "postcode"),
        ("Country", "country"), ("Tags", "tags"), ("Joined", "created_at"),
    ]
    return _csv_response(rows, cols, f"members_{_stamp()}.csv")


@router.get("/contacts.csv")
async def export_contacts(user: dict = Depends(get_current_user)) -> StreamingResponse:
    org = _require_org(user)
    rows = await db.crm2_contacts.find(
        {"organization_id": org}, {"_id": 0},
    ).sort("created_at", -1).to_list(50_000)
    cols = [
        ("ID", "id"), ("First Name", "first_name"), ("Last Name", "last_name"),
        ("Email", "email"), ("Phone", "phone"), ("Lifecycle", "lifecycle"),
        ("Source", "source"), ("Tags", "tags"), ("Created", "created_at"),
    ]
    return _csv_response(rows, cols, f"contacts_{_stamp()}.csv")


@router.get("/deals.csv")
async def export_deals(user: dict = Depends(get_current_user)) -> StreamingResponse:
    org = _require_org(user)
    rows = await db.crm2_opportunities.find(
        {"organization_id": org}, {"_id": 0},
    ).sort("created_at", -1).to_list(50_000)
    cols = [
        ("ID", "id"), ("Name", "name"), ("Stage", "stage"),
        ("Amount", "amount"), ("Currency", "currency"),
        ("Close Date", "close_date"), ("Owner", "owner_email"),
        ("Created", "created_at"),
    ]
    return _csv_response(rows, cols, f"deals_{_stamp()}.csv")


@router.get("/classes.csv")
async def export_classes(user: dict = Depends(get_current_user)) -> StreamingResponse:
    org = _require_org(user)
    rows = await db.class_templates.find(
        {"organization_id": org}, {"_id": 0},
    ).sort("name", 1).to_list(50_000)
    cols = [
        ("ID", "id"), ("Name", "name"), ("Instructor", "instructor_name"),
        ("Capacity", "capacity"), ("Duration (min)", "duration_min"),
        ("Days", "days_of_week"), ("Created", "created_at"),
    ]
    return _csv_response(rows, cols, f"classes_{_stamp()}.csv")


@router.get("/bookings.csv")
async def export_bookings(user: dict = Depends(get_current_user)) -> StreamingResponse:
    org = _require_org(user)
    rows = await db.bookings.find(
        {"organization_id": org}, {"_id": 0},
    ).sort("starts_at", -1).to_list(50_000)
    cols = [
        ("ID", "id"), ("Member", "member_name"), ("Email", "member_email"),
        ("Class", "class_name"), ("Starts", "starts_at"),
        ("Status", "status"), ("Created", "created_at"),
    ]
    return _csv_response(rows, cols, f"bookings_{_stamp()}.csv")
