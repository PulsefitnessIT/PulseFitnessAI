"""GymAxis Staffing — Org Chart Builder (Phase 1).

A focused, visual organisation-chart builder that lives at
Operations → Staffing → Org Chart. It LINKS to existing
``staff_members`` records rather than duplicating them, and lets
managers map reporting lines, departments, sites and vacancies.

Data model
----------
- ``org_charts``       — chart metadata + settings (one org can own many).
- ``org_chart_nodes``  — a card on a chart. Either links to a real
  ``staff_members`` row (``staff_id``) or is a standalone vacancy /
  placeholder / contractor card. ``manager_node_id`` forms the
  reporting-line tree.

Everything is scoped to the caller's ``organization_id`` — a partner
engineer or a different tenant can never read another org's chart.

Write-back safety
-----------------
Moving a card under a new manager only updates the underlying
``staff_members`` record when the client explicitly passes
``write_back_staff=true`` (the UI shows a confirm dialog first). We
store reporting + department on the staff row under ``manager_staff_id``
and ``department`` so the data survives outside the chart.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from routes.staffing import _org, _require_manager, _now, _clean

logger = logging.getLogger(__name__)
router = APIRouter()

NODE_TYPES = {"staff", "vacancy", "placeholder", "contractor"}
VACANCY_STAGES = {
    "Planned", "Approved", "Recruiting", "Interviewing",
    "Offer Made", "Filled", "On Hold", "Cancelled",
}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_SETTINGS = {
    "field_toggles": {
        "photo": True, "department": True, "site": True, "email": False,
        "phone": False, "reports_count": True, "status": True,
        "employment_type": False,
    },
    "layout": "top-down",       # top-down | left-right
    "group_by": "none",         # none | department | site
    "show_grid": True,
}


# ───────────────────────── schemas ─────────────────────────

class ChartCreate(BaseModel):
    name: str = "Organisation Chart"
    auto_build: bool = True       # seed nodes from current staff_members


class ChartUpdate(BaseModel):
    name: str | None = None
    settings: dict | None = None


class NodeCreate(BaseModel):
    type: str = "staff"
    staff_id: str | None = None
    full_name: str | None = None
    job_title: str | None = None
    department: str | None = None
    site_id: str | None = None
    employment_type: str | None = None     # full_time | part_time | contractor | casual
    status: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    manager_node_id: str | None = None
    x: float = 0.0
    y: float = 0.0
    # vacancy-only
    recruitment_stage: str | None = None
    target_start_date: str | None = None
    salary_band: str | None = None
    priority: str | None = None


class NodeUpdate(BaseModel):
    full_name: str | None = None
    job_title: str | None = None
    department: str | None = None
    site_id: str | None = None
    employment_type: str | None = None
    status: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None
    manager_node_id: str | None = None
    x: float | None = None
    y: float | None = None
    recruitment_stage: str | None = None
    target_start_date: str | None = None
    salary_band: str | None = None
    priority: str | None = None
    # when true, mirror manager/department/site onto the linked staff record
    write_back_staff: bool = False


class ImportRequest(BaseModel):
    rows: list[dict] = Field(default_factory=list)   # already-mapped rows
    options: dict = Field(default_factory=dict)       # link_existing, create_vacancies, ...


# ───────────────────────── helpers ─────────────────────────

async def _get_chart(cid: str, org_id: str) -> dict:
    chart = await db.org_charts.find_one({"id": cid, "organization_id": org_id}, {"_id": 0})
    if not chart:
        raise HTTPException(404, "Org chart not found")
    return chart


async def _staff_index(org_id: str) -> dict:
    """All active staff for the org, indexed by id."""
    rows = await db.staff_members.find(
        {"organization_id": org_id, "active": True}, {"_id": 0},
    ).to_list(5000)
    return {r["id"]: r for r in rows}


async def _site_names(org_id: str) -> dict:
    rows = await db.sites.find({"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    return {r["id"]: r.get("name") for r in rows}


def _node_from_staff(chart_id: str, org_id: str, s: dict, x: float = 0, y: float = 0) -> dict:
    role = (s.get("primary_role") or "").lower()
    is_eng = "engineer" in role or "technician" in role
    return {
        "id": str(uuid4()),
        "chart_id": chart_id,
        "organization_id": org_id,
        "type": "staff",
        "staff_id": s["id"],
        "full_name": s.get("full_name") or "Unnamed",
        "job_title": s.get("primary_role"),
        "department": s.get("department"),
        "site_id": (s.get("site_ids") or [None])[0],
        "employment_type": s.get("contract_type"),
        "status": "active" if s.get("active", True) else "inactive",
        "email": s.get("email"),
        "phone": s.get("phone"),
        "is_engineer": is_eng,
        "manager_node_id": None,
        "x": x,
        "y": y,
        "created_at": _now().isoformat(),
    }


# ───────────────────────── charts ─────────────────────────

@router.get("/staffing/orgchart/charts")
async def list_charts(user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    charts = await db.org_charts.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("created_at", 1).to_list(200)
    for c in charts:
        c["node_count"] = await db.org_chart_nodes.count_documents(
            {"chart_id": c["id"], "organization_id": org_id})
    return {"charts": charts}


@router.post("/staffing/orgchart/charts")
async def create_chart(body: ChartCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    cid = str(uuid4())
    doc = {
        "id": cid,
        "organization_id": org_id,
        "name": body.name.strip() or "Organisation Chart",
        "settings": DEFAULT_SETTINGS,
        "created_by": user.get("email"),
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    await db.org_charts.insert_one(doc.copy())
    added = 0
    if body.auto_build:
        added = await _seed_from_staff(cid, org_id)
    return {**_clean(doc), "node_count": added}


async def _seed_from_staff(chart_id: str, org_id: str) -> int:
    staff = await db.staff_members.find(
        {"organization_id": org_id, "active": True}, {"_id": 0},
    ).to_list(5000)
    existing = await db.org_chart_nodes.find(
        {"chart_id": chart_id}, {"_id": 0, "staff_id": 1, "id": 1}).to_list(5000)
    linked = {n.get("staff_id") for n in existing if n.get("staff_id")}
    sid_to_node = {n.get("staff_id"): n.get("id") for n in existing if n.get("staff_id")}
    new_nodes, i = [], 0
    for s in staff:
        if s["id"] in linked:
            continue
        col, row = i % 6, i // 6
        new_nodes.append(_node_from_staff(chart_id, org_id, s, x=col * 240, y=row * 170))
        i += 1
    if new_nodes:
        for n in new_nodes:
            sid_to_node[n["staff_id"]] = n["id"]
        for s in staff:
            n = next((x for x in new_nodes if x["staff_id"] == s["id"]), None)
            if n and s.get("manager_staff_id") and s["manager_staff_id"] in sid_to_node:
                n["manager_node_id"] = sid_to_node[s["manager_staff_id"]]
        await db.org_chart_nodes.insert_many([n.copy() for n in new_nodes])
    return len(new_nodes)


@router.get("/staffing/orgchart/charts/{cid}")
async def get_chart(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    chart = await _get_chart(cid, org_id)
    nodes = await db.org_chart_nodes.find(
        {"chart_id": cid, "organization_id": org_id}, {"_id": 0}).to_list(5000)
    sites = await _site_names(org_id)
    for n in nodes:
        n["site_name"] = sites.get(n.get("site_id"))
    return {"chart": chart, "nodes": nodes, "sites": [{"id": k, "name": v} for k, v in sites.items()]}


@router.patch("/staffing/orgchart/charts/{cid}")
async def update_chart(cid: str, body: ChartUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    patch = {"updated_at": _now().isoformat()}
    if body.name is not None:
        patch["name"] = body.name.strip() or "Organisation Chart"
    if body.settings is not None:
        patch["settings"] = body.settings
    await db.org_charts.update_one({"id": cid, "organization_id": org_id}, {"$set": patch})
    return await _get_chart(cid, org_id)


@router.delete("/staffing/orgchart/charts/{cid}")
async def delete_chart(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    await db.org_chart_nodes.delete_many({"chart_id": cid, "organization_id": org_id})
    await db.org_charts.delete_one({"id": cid, "organization_id": org_id})
    return {"ok": True}


@router.post("/staffing/orgchart/charts/{cid}/sync-staff")
async def sync_staff(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    added = await _seed_from_staff(cid, org_id)
    return {"ok": True, "added": added}


# ───────────────────────── nodes ─────────────────────────

@router.post("/staffing/orgchart/charts/{cid}/nodes")
async def create_node(cid: str, body: NodeCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    if body.type not in NODE_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(NODE_TYPES)}")
    doc = {
        "id": str(uuid4()),
        "chart_id": cid,
        "organization_id": org_id,
        "is_engineer": False,
        "created_at": _now().isoformat(),
        **body.dict(),
    }
    if body.staff_id:
        idx = await _staff_index(org_id)
        s = idx.get(body.staff_id)
        if not s:
            raise HTTPException(404, "staff_id not found in this org")
        doc["full_name"] = doc.get("full_name") or s.get("full_name")
        doc["job_title"] = doc.get("job_title") or s.get("primary_role")
        doc["email"] = doc.get("email") or s.get("email")
        role = (s.get("primary_role") or "").lower()
        doc["is_engineer"] = "engineer" in role or "technician" in role
    if not doc.get("full_name"):
        doc["full_name"] = "New role" if body.type in ("vacancy", "placeholder") else "Unnamed"
    if body.type == "vacancy" and not doc.get("recruitment_stage"):
        doc["recruitment_stage"] = "Planned"
    await db.org_chart_nodes.insert_one(doc.copy())
    sites = await _site_names(org_id)
    doc["site_name"] = sites.get(doc.get("site_id"))
    return _clean(doc)


@router.patch("/staffing/orgchart/charts/{cid}/nodes/{nid}")
async def update_node(cid: str, nid: str, body: NodeUpdate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    node = await db.org_chart_nodes.find_one({"id": nid, "chart_id": cid, "organization_id": org_id}, {"_id": 0})
    if not node:
        raise HTTPException(404, "node not found")
    data = body.dict()
    write_back = data.pop("write_back_staff", False)
    patch = {k: v for k, v in data.items() if v is not None}
    if "manager_node_id" in body.__fields_set__:
        patch["manager_node_id"] = body.manager_node_id
    if patch.get("manager_node_id"):
        if patch["manager_node_id"] == nid:
            raise HTTPException(400, "A card cannot report to itself")
        if await _would_create_cycle(cid, org_id, nid, patch["manager_node_id"]):
            raise HTTPException(400, "That move would create a circular reporting line")
    patch["updated_at"] = _now().isoformat()
    await db.org_chart_nodes.update_one(
        {"id": nid, "chart_id": cid, "organization_id": org_id}, {"$set": patch})

    if write_back and node.get("staff_id"):
        sp = {}
        if "manager_node_id" in patch:
            mgr = None
            if patch["manager_node_id"]:
                mgr = await db.org_chart_nodes.find_one(
                    {"id": patch["manager_node_id"], "chart_id": cid}, {"_id": 0, "staff_id": 1})
            sp["manager_staff_id"] = (mgr or {}).get("staff_id")
        if "department" in patch:
            sp["department"] = patch["department"]
        if "site_id" in patch and patch["site_id"]:
            sp["site_ids"] = [patch["site_id"]]
        if sp:
            sp["updated_at"] = _now().isoformat()
            await db.staff_members.update_one(
                {"id": node["staff_id"], "organization_id": org_id}, {"$set": sp})

    doc = await db.org_chart_nodes.find_one({"id": nid, "chart_id": cid}, {"_id": 0})
    sites = await _site_names(org_id)
    doc["site_name"] = sites.get(doc.get("site_id"))
    return doc


async def _would_create_cycle(cid: str, org_id: str, node_id: str, new_mgr_id: str) -> bool:
    """Walk up from the proposed manager; if we hit node_id, it's a cycle."""
    nodes = {n["id"]: n.get("manager_node_id") for n in
             await db.org_chart_nodes.find({"chart_id": cid, "organization_id": org_id},
                                           {"_id": 0, "id": 1, "manager_node_id": 1}).to_list(5000)}
    cur, seen = new_mgr_id, set()
    while cur and cur not in seen:
        if cur == node_id:
            return True
        seen.add(cur)
        cur = nodes.get(cur)
    return False


@router.delete("/staffing/orgchart/charts/{cid}/nodes/{nid}")
async def delete_node(cid: str, nid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.org_chart_nodes.delete_one({"id": nid, "chart_id": cid, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "node not found")
    await db.org_chart_nodes.update_many(
        {"chart_id": cid, "organization_id": org_id, "manager_node_id": nid},
        {"$set": {"manager_node_id": None}})
    return {"ok": True}


# ───────────────────────── insights ─────────────────────────

@router.get("/staffing/orgchart/charts/{cid}/insights")
async def insights(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    nodes = await db.org_chart_nodes.find(
        {"chart_id": cid, "organization_id": org_id}, {"_id": 0}).to_list(5000)
    reports = {}
    for n in nodes:
        m = n.get("manager_node_id")
        if m:
            reports[m] = reports.get(m, 0) + 1
    people = [n for n in nodes if n.get("type") in ("staff", "contractor")]
    vacancies = [n for n in nodes if n.get("type") == "vacancy"]
    managers = [n for n in nodes if reports.get(n["id"], 0) > 0]
    engineers = [n for n in nodes if n.get("is_engineer")]
    overloaded = [{"id": n["id"], "name": n.get("full_name"), "reports": reports[n["id"]]}
                  for n in managers if reports.get(n["id"], 0) > 8]
    no_mgr = [n for n in people if not n.get("manager_node_id")]
    no_site = [n for n in people if not n.get("site_id")]
    depts = {}
    for n in nodes:
        d = n.get("department") or "Unassigned"
        depts.setdefault(d, {"total": 0})
        depts[d]["total"] += 1
    avg_reports = round(sum(reports.values()) / len(managers), 1) if managers else 0
    return {
        "total_people": len(people),
        "total_managers": len(managers),
        "total_engineers": len(engineers),
        "open_vacancies": len([v for v in vacancies if v.get("recruitment_stage") not in ("Filled", "Cancelled")]),
        "total_vacancies": len(vacancies),
        "avg_direct_reports": avg_reports,
        "departments": len([d for d in depts if d != "Unassigned"]),
        "staff_without_manager": len(no_mgr),
        "staff_without_site": len(no_site),
        "overloaded_managers": overloaded,
        "dept_breakdown": [{"name": k, **v} for k, v in sorted(depts.items())],
    }


# ───────────────────────── import / export ─────────────────────────

@router.post("/staffing/orgchart/charts/{cid}/import/preview")
async def import_preview(cid: str, body: ImportRequest, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    staff = await _staff_index(org_id)
    by_email = {(s.get("email") or "").lower(): s for s in staff.values() if s.get("email")}
    by_name = {(s.get("full_name") or "").lower(): s for s in staff.values()}
    valid, warnings = [], []
    seen_emails = set()
    for i, raw in enumerate(body.rows):
        name = (raw.get("full_name") or "").strip()
        email = (raw.get("email") or "").strip().lower()
        issues = []
        if not name:
            issues.append("Missing name")
        if email and not _EMAIL_RE.match(email):
            issues.append("Invalid email")
        if email and email in seen_emails:
            issues.append("Duplicate in file")
        if email:
            seen_emails.add(email)
        match = by_email.get(email) or by_name.get(name.lower())
        valid.append({
            "row": i + 1, "full_name": name, "email": email,
            "job_title": raw.get("job_title"), "department": raw.get("department"),
            "manager_name": raw.get("manager_name") or raw.get("manager"),
            "is_vacancy": str(raw.get("vacancy") or "").lower() in ("yes", "true", "1"),
            "matched_staff_id": match.get("id") if match else None,
            "matched_staff_name": match.get("full_name") if match else None,
            "issues": issues,
        })
        if issues:
            warnings.append({"row": i + 1, "issues": issues})
    return {
        "total": len(body.rows),
        "matched": len([r for r in valid if r["matched_staff_id"]]),
        "new": len([r for r in valid if not r["matched_staff_id"] and not r["is_vacancy"]]),
        "vacancies": len([r for r in valid if r["is_vacancy"]]),
        "rows": valid,
        "warnings": warnings,
    }


@router.post("/staffing/orgchart/charts/{cid}/import/apply")
async def import_apply(cid: str, body: ImportRequest, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    opts = body.options or {}
    link_existing = opts.get("link_existing", True)
    staff = await _staff_index(org_id)
    by_email = {(s.get("email") or "").lower(): s for s in staff.values() if s.get("email")}
    by_name = {(s.get("full_name") or "").lower(): s for s in staff.values()}

    created, name_to_node = [], {}
    base = await db.org_chart_nodes.count_documents({"chart_id": cid, "organization_id": org_id})
    for i, raw in enumerate(body.rows):
        name = (raw.get("full_name") or "").strip()
        if not name:
            continue
        email = (raw.get("email") or "").strip().lower()
        is_vac = str(raw.get("vacancy") or "").lower() in ("yes", "true", "1")
        match = (by_email.get(email) or by_name.get(name.lower())) if link_existing else None
        col, row = (base + i) % 6, (base + i) // 6
        node = {
            "id": str(uuid4()), "chart_id": cid, "organization_id": org_id,
            "type": "vacancy" if is_vac else ("staff" if match else "placeholder"),
            "staff_id": match.get("id") if match else None,
            "full_name": name, "email": email or (match.get("email") if match else None),
            "job_title": raw.get("job_title") or (match.get("primary_role") if match else None),
            "department": raw.get("department"),
            "phone": raw.get("phone"),
            "employment_type": raw.get("employment_type"),
            "status": "active",
            "is_engineer": "engineer" in (raw.get("job_title") or "").lower(),
            "manager_node_id": None,
            "recruitment_stage": "Planned" if is_vac else None,
            "x": col * 240, "y": row * 170,
            "created_at": _now().isoformat(),
            "_manager_name": (raw.get("manager_name") or raw.get("manager") or "").strip().lower(),
        }
        created.append(node)
        name_to_node[name.lower()] = node["id"]
    for n in created:
        mn = n.pop("_manager_name", "")
        if mn and mn in name_to_node and name_to_node[mn] != n["id"]:
            n["manager_node_id"] = name_to_node[mn]
    if created:
        await db.org_chart_nodes.insert_many([n.copy() for n in created])
    return {"ok": True, "imported": len(created)}


@router.get("/staffing/orgchart/charts/{cid}/export.csv")
async def export_csv(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    nodes = await db.org_chart_nodes.find(
        {"chart_id": cid, "organization_id": org_id}, {"_id": 0}).to_list(5000)
    by_id = {n["id"]: n for n in nodes}
    sites = await _site_names(org_id)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Name", "Job title", "Type", "Department", "Site", "Manager",
                "Employment type", "Status", "Email", "Phone", "Linked staff"])
    for n in nodes:
        mgr = by_id.get(n.get("manager_node_id"))
        w.writerow([
            n.get("full_name"), n.get("job_title"), n.get("type"),
            n.get("department"), sites.get(n.get("site_id")),
            mgr.get("full_name") if mgr else "",
            n.get("employment_type"), n.get("status"),
            n.get("email"), n.get("phone"),
            "yes" if n.get("staff_id") else "no",
        ])
    return Response(
        content=out.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=org_chart.csv"})
