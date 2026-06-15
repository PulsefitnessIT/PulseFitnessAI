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
NODE_LABELS_BE = {"staff": "Staff", "vacancy": "Vacancy", "placeholder": "Placeholder", "contractor": "Contractor"}
EDGE_TYPES = {"dotted", "temporary", "project", "escalation"}
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
    "layout": "vertical",       # vertical | top-down | left-right
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


async def _audit(cid: str, org_id: str, actor: str, action: str, detail: str = "", old=None, new=None):
    """Append an immutable audit entry for a chart action."""
    try:
        await db.org_chart_audit.insert_one({
            "id": str(uuid4()), "chart_id": cid, "organization_id": org_id,
            "actor": actor, "action": action, "detail": detail,
            "old_value": old, "new_value": new, "at": _now().isoformat(),
        })
    except Exception:  # auditing must never break the primary action
        logger.exception("orgchart audit write failed")


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


# Vertical (stacked) layout — mirrors the frontend indented-tree algorithm so
# freshly seeded / imported charts arrive in the print-friendly stacked shape
# without the user having to hit "Auto-layout" first.
_V_INDENT = 56
_V_ROW = 144  # CARD_H (116) + 28


def _vertical_positions(nodes: list[dict]) -> dict[str, tuple[float, float]]:
    ids = {n["id"] for n in nodes}
    children: dict[str, list[str]] = {}
    for n in nodes:
        m = n.get("manager_node_id")
        key = m if (m in ids) else "__root__"
        children.setdefault(key, []).append(n["id"])
    pos: dict[str, tuple[float, float]] = {}
    seen: set[str] = set()
    row = {"i": 0}

    def visit(nid: str, depth: int):
        if nid in seen:
            return
        seen.add(nid)
        pos[nid] = (depth * _V_INDENT, row["i"] * _V_ROW)
        row["i"] += 1
        for k in children.get(nid, []):
            visit(k, depth + 1)

    for r in children.get("__root__", []):
        visit(r, 0)
    for n in nodes:
        if n["id"] not in pos:
            pos[n["id"]] = (0, row["i"] * _V_ROW)
            row["i"] += 1
    return pos


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
        # Fresh build (no pre-existing cards) → arrange vertically (stacked).
        if not existing:
            posmap = _vertical_positions(new_nodes)
            for n in new_nodes:
                n["x"], n["y"] = posmap[n["id"]]
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
    note_counts = {}
    for n in await db.org_chart_notes.find({"chart_id": cid, "organization_id": org_id}, {"_id": 0, "node_id": 1}).to_list(10000):
        note_counts[n["node_id"]] = note_counts.get(n["node_id"], 0) + 1
    for n in nodes:
        n["site_name"] = sites.get(n.get("site_id"))
        n["note_count"] = note_counts.get(n["id"], 0)
    edges = await db.org_chart_edges.find({"chart_id": cid, "organization_id": org_id}, {"_id": 0}).to_list(5000)
    return {"chart": chart, "nodes": nodes, "edges": edges,
            "sites": [{"id": k, "name": v} for k, v in sites.items()]}


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
    await _audit(cid, org_id, user.get("email"), "card_added", f"{NODE_LABELS_BE.get(doc.get('type'), doc.get('type'))}: {doc.get('full_name')}")
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
    if "manager_node_id" in patch and patch.get("manager_node_id") != node.get("manager_node_id"):
        mgr_name = "—"
        if patch.get("manager_node_id"):
            m = await db.org_chart_nodes.find_one({"id": patch["manager_node_id"], "chart_id": cid}, {"_id": 0, "full_name": 1})
            mgr_name = (m or {}).get("full_name", "—")
        await _audit(cid, org_id, user.get("email"), "reporting_changed", f"{node.get('full_name')} → {mgr_name}",
                     old=node.get("manager_node_id"), new=patch.get("manager_node_id"))
    else:
        await _audit(cid, org_id, user.get("email"), "card_edited", node.get("full_name"))

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
    await db.org_chart_edges.delete_many({"chart_id": cid, "organization_id": org_id,
                                          "$or": [{"from_node_id": nid}, {"to_node_id": nid}]})
    await _audit(cid, org_id, user.get("email"), "card_removed", nid)
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
        # Arrange the imported batch vertically (stacked) so it lands in the
        # print-friendly shape immediately.
        posmap = _vertical_positions(created)
        for n in created:
            n["x"], n["y"] = posmap[n["id"]]
        await db.org_chart_nodes.insert_many([n.copy() for n in created])
    await _audit(cid, org_id, user.get("email"), "import", f"{len(created)} cards imported")
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


# ───────────────────────── version history ─────────────────────────

class VersionCreate(BaseModel):
    label: str | None = None


async def _snapshot(cid: str, org_id: str, actor: str, label: str | None) -> dict:
    nodes = await db.org_chart_nodes.find({"chart_id": cid, "organization_id": org_id}, {"_id": 0}).to_list(5000)
    edges = await db.org_chart_edges.find({"chart_id": cid, "organization_id": org_id}, {"_id": 0}).to_list(5000)
    chart = await db.org_charts.find_one({"id": cid, "organization_id": org_id}, {"_id": 0, "settings": 1, "name": 1})
    n = await db.org_chart_versions.count_documents({"chart_id": cid, "organization_id": org_id})
    doc = {
        "id": str(uuid4()), "chart_id": cid, "organization_id": org_id,
        "version": n + 1, "label": label or f"Snapshot {n + 1}",
        "actor": actor, "created_at": _now().isoformat(),
        "nodes": nodes, "edges": edges, "settings": (chart or {}).get("settings"),
        "node_count": len(nodes),
    }
    await db.org_chart_versions.insert_one(doc.copy())
    return doc


@router.get("/staffing/orgchart/charts/{cid}/versions")
async def list_versions(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    rows = await db.org_chart_versions.find(
        {"chart_id": cid, "organization_id": org_id},
        {"_id": 0, "nodes": 0, "edges": 0}).sort("version", -1).to_list(200)
    return {"versions": rows}


@router.post("/staffing/orgchart/charts/{cid}/versions")
async def create_version(cid: str, body: VersionCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    doc = await _snapshot(cid, org_id, user.get("email"), body.label)
    await _audit(cid, org_id, user.get("email"), "version_saved", doc["label"])
    return {k: v for k, v in doc.items() if k not in ("nodes", "edges")}


@router.post("/staffing/orgchart/charts/{cid}/versions/{vid}/restore")
async def restore_version(cid: str, vid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    ver = await db.org_chart_versions.find_one({"id": vid, "chart_id": cid, "organization_id": org_id}, {"_id": 0})
    if not ver:
        raise HTTPException(404, "version not found")
    # safety snapshot of the current state before overwriting
    await _snapshot(cid, org_id, user.get("email"), "Auto-save before restore")
    await db.org_chart_nodes.delete_many({"chart_id": cid, "organization_id": org_id})
    await db.org_chart_edges.delete_many({"chart_id": cid, "organization_id": org_id})
    if ver.get("nodes"):
        await db.org_chart_nodes.insert_many([{**n} for n in ver["nodes"]])
    if ver.get("edges"):
        await db.org_chart_edges.insert_many([{**e} for e in ver["edges"]])
    if ver.get("settings"):
        await db.org_charts.update_one({"id": cid, "organization_id": org_id}, {"$set": {"settings": ver["settings"]}})
    await _audit(cid, org_id, user.get("email"), "version_restored", ver.get("label"))
    return {"ok": True}


# ───────────────────────── audit trail ─────────────────────────

@router.get("/staffing/orgchart/charts/{cid}/audit")
async def list_audit(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    rows = await db.org_chart_audit.find(
        {"chart_id": cid, "organization_id": org_id}, {"_id": 0}).sort("at", -1).to_list(300)
    return {"audit": rows}


# ───────────────────────── secondary / dotted reporting ─────────────────────────

class EdgeCreate(BaseModel):
    from_node_id: str      # the report (subordinate)
    to_node_id: str        # the secondary manager
    line_type: str = "dotted"


@router.post("/staffing/orgchart/charts/{cid}/edges")
async def create_edge(cid: str, body: EdgeCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    if body.line_type not in EDGE_TYPES:
        raise HTTPException(400, f"line_type must be one of {sorted(EDGE_TYPES)}")
    if body.from_node_id == body.to_node_id:
        raise HTTPException(400, "An edge needs two different cards")
    for nid in (body.from_node_id, body.to_node_id):
        if not await db.org_chart_nodes.find_one({"id": nid, "chart_id": cid}, {"_id": 0, "id": 1}):
            raise HTTPException(404, "node not found")
    doc = {"id": str(uuid4()), "chart_id": cid, "organization_id": org_id,
           "from_node_id": body.from_node_id, "to_node_id": body.to_node_id,
           "line_type": body.line_type, "created_at": _now().isoformat()}
    await db.org_chart_edges.insert_one(doc.copy())
    await _audit(cid, org_id, user.get("email"), "edge_added", body.line_type)
    return _clean(doc)


@router.delete("/staffing/orgchart/charts/{cid}/edges/{eid}")
async def delete_edge(cid: str, eid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.org_chart_edges.delete_one({"id": eid, "chart_id": cid, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "edge not found")
    return {"ok": True}


# ───────────────────────── notes / comments ─────────────────────────

class NoteCreate(BaseModel):
    node_id: str
    body: str
    confidential: bool = False


@router.get("/staffing/orgchart/charts/{cid}/nodes/{nid}/notes")
async def list_notes(cid: str, nid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    rows = await db.org_chart_notes.find(
        {"chart_id": cid, "organization_id": org_id, "node_id": nid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"notes": rows}


@router.post("/staffing/orgchart/charts/{cid}/nodes/{nid}/notes")
async def create_note(cid: str, nid: str, body: NoteCreate, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    if not (body.body or "").strip():
        raise HTTPException(400, "Note body required")
    doc = {"id": str(uuid4()), "chart_id": cid, "organization_id": org_id, "node_id": nid,
           "body": body.body.strip(), "confidential": bool(body.confidential),
           "author": user.get("email"), "created_at": _now().isoformat()}
    await db.org_chart_notes.insert_one(doc.copy())
    return _clean(doc)


@router.delete("/staffing/orgchart/charts/{cid}/notes/{note_id}")
async def delete_note(cid: str, note_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    res = await db.org_chart_notes.delete_one({"id": note_id, "chart_id": cid, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "note not found")
    return {"ok": True}


# ───────────────────────── starter templates ─────────────────────────

TEMPLATES = {
    "small_gym": {"name": "Small Independent Gym", "roles": [
        ("Gym Owner / Manager", "Management", None),
        ("Front of House", "Front of House", 0), ("Personal Trainer", "Personal Trainers", 0),
        ("Fitness Instructor", "Fitness Instructors", 0), ("Cleaner", "Cleaning", 0),
    ]},
    "boutique_studio": {"name": "Boutique Studio", "roles": [
        ("Studio Manager", "Management", None),
        ("Lead Instructor", "Instructors", 0), ("Instructor", "Instructors", 1),
        ("Reception", "Front of House", 0), ("Sales", "Sales", 0),
    ]},
    "multi_site": {"name": "Multi-Site Gym Operator", "roles": [
        ("Operations Director", "Leadership", None),
        ("Regional Manager", "Operations", 0), ("Site Manager", "Operations", 1),
        ("Head of Sales", "Sales", 0), ("Head of Marketing", "Marketing", 0),
        ("Finance Manager", "Finance", 0),
    ]},
    "service_company": {"name": "Fitness Equipment Service Company", "roles": [
        ("Managing Director", "Leadership", None),
        ("Service Manager", "Service & Aftersales", 0), ("Lead Engineer", "Field Engineers", 1),
        ("Field Engineer", "Field Engineers", 2), ("Service Admin", "Service Admin", 1),
        ("Contracts Manager", "Contracts", 0),
    ]},
    "pulse_internal": {"name": "Pulse Fitness Internal Structure", "roles": [
        ("Managing Director", "Leadership", None),
        ("Head of Service", "Service & Aftersales", 0), ("Field Engineer", "Field Engineers", 1),
        ("Service Admin", "Service Admin", 1), ("Contracts Manager", "Contracts", 0),
        ("Head of Sales", "Sales", 0), ("Head of Marketing", "Marketing", 0),
        ("Finance Manager", "Finance", 0), ("Warehouse Manager", "Warehouse / Stores", 0),
        ("Product Lead", "Product / Development", 0),
    ]},
    "enterprise_ops": {"name": "Enterprise Operations Team", "roles": [
        ("COO", "Leadership", None),
        ("Operations Manager", "Operations", 0), ("Team Lead", "Operations", 1),
        ("Coordinator", "Operations", 2), ("Quality Lead", "Operations", 0),
    ]},
    "engineer_team": {"name": "Engineer Service Team", "roles": [
        ("Service Director", "Leadership", None),
        ("Dispatch Lead", "Service Admin", 0), ("Senior Engineer", "Field Engineers", 0),
        ("Field Engineer", "Field Engineers", 2), ("Apprentice Engineer", "Field Engineers", 2),
    ]},
    "sales_cs": {"name": "Sales and Customer Success Team", "roles": [
        ("Commercial Director", "Leadership", None),
        ("Head of Sales", "Sales", 0), ("Account Executive", "Sales", 1),
        ("Customer Success Lead", "Customer Success", 0), ("CS Agent", "Customer Success", 3),
    ]},
}


@router.get("/staffing/orgchart/templates")
async def list_templates(user: dict = Depends(get_current_user)):
    _require_manager(user)
    return {"templates": [{"id": k, "name": v["name"], "roles": len(v["roles"])} for k, v in TEMPLATES.items()]}


@router.post("/staffing/orgchart/charts/{cid}/apply-template/{template_id}")
async def apply_template(cid: str, template_id: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    tpl = TEMPLATES.get(template_id)
    if not tpl:
        raise HTTPException(404, "template not found")
    base = await db.org_chart_nodes.count_documents({"chart_id": cid, "organization_id": org_id})
    created = []
    for i, (title, dept, mgr_idx) in enumerate(tpl["roles"]):
        col, row = (base + i) % 6, (base + i) // 6
        created.append({
            "id": str(uuid4()), "chart_id": cid, "organization_id": org_id,
            "type": "placeholder", "staff_id": None, "full_name": title, "job_title": title,
            "department": dept, "is_engineer": "engineer" in title.lower(),
            "manager_node_id": None, "status": "active",
            "x": col * 240, "y": row * 170, "created_at": _now().isoformat(),
            "_mgr_idx": mgr_idx,
        })
    for n in created:
        mi = n.pop("_mgr_idx", None)
        if mi is not None and mi < len(created):
            n["manager_node_id"] = created[mi]["id"]
    if created:
        await db.org_chart_nodes.insert_many([n.copy() for n in created])
    await _audit(cid, org_id, user.get("email"), "template_applied", tpl["name"])
    return {"ok": True, "added": len(created)}


# ───────────────────────── public share link ─────────────────────────
import secrets as _secrets  # noqa: E402


class PublishRequest(BaseModel):
    show_contact: bool = False


@router.post("/staffing/orgchart/charts/{cid}/publish")
async def publish_chart(cid: str, body: PublishRequest, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    chart = await _get_chart(cid, org_id)
    token = chart.get("public_token") or _secrets.token_urlsafe(32)
    await db.org_charts.update_one(
        {"id": cid, "organization_id": org_id},
        {"$set": {"is_public": True, "public_token": token,
                  "public_show_contact": bool(body.show_contact),
                  "updated_at": _now().isoformat()}})
    await _audit(cid, org_id, user.get("email"), "published", "Public link enabled")
    return {"ok": True, "public_token": token, "show_contact": bool(body.show_contact)}


@router.delete("/staffing/orgchart/charts/{cid}/publish")
async def unpublish_chart(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    await _get_chart(cid, org_id)
    await db.org_charts.update_one(
        {"id": cid, "organization_id": org_id},
        {"$set": {"is_public": False, "public_token": None, "updated_at": _now().isoformat()}})
    await _audit(cid, org_id, user.get("email"), "unpublished", "Public link disabled")
    return {"ok": True}


@router.post("/staffing/orgchart/charts/{cid}/publish/rotate")
async def rotate_public_token(cid: str, user: dict = Depends(get_current_user)):
    _require_manager(user)
    org_id = _org(user)
    chart = await _get_chart(cid, org_id)
    if not chart.get("is_public"):
        raise HTTPException(400, "Chart is not published")
    token = _secrets.token_urlsafe(32)
    await db.org_charts.update_one(
        {"id": cid, "organization_id": org_id},
        {"$set": {"public_token": token, "updated_at": _now().isoformat()}})
    await _audit(cid, org_id, user.get("email"), "link_rotated", "Public link regenerated")
    return {"ok": True, "public_token": token}


@router.get("/staffing/orgchart/public/{token}")
async def public_chart(token: str):
    """PUBLIC (no auth) read-only org chart by share token.

    Strips every sensitive field — never returns emails/phones (unless the
    publisher opted in), notes, salary bands, or the linked staff_id.
    """
    chart = await db.org_charts.find_one(
        {"public_token": token, "is_public": True}, {"_id": 0})
    if not chart:
        raise HTTPException(404, "This org chart link is no longer available")
    org_id = chart["organization_id"]
    show_contact = bool(chart.get("public_show_contact"))
    sites = await _site_names(org_id)
    raw = await db.org_chart_nodes.find(
        {"chart_id": chart["id"], "organization_id": org_id}, {"_id": 0}).to_list(5000)
    nodes = []
    for n in raw:
        safe = {
            "id": n["id"], "type": n.get("type"), "full_name": n.get("full_name"),
            "job_title": n.get("job_title"), "department": n.get("department"),
            "site_name": sites.get(n.get("site_id")), "is_engineer": bool(n.get("is_engineer")),
            "manager_node_id": n.get("manager_node_id"), "x": n.get("x", 0), "y": n.get("y", 0),
            "recruitment_stage": n.get("recruitment_stage") if n.get("type") == "vacancy" else None,
        }
        if show_contact:
            safe["email"] = n.get("email")
            safe["phone"] = n.get("phone")
        nodes.append(safe)
    edges = await db.org_chart_edges.find(
        {"chart_id": chart["id"], "organization_id": org_id},
        {"_id": 0, "from_node_id": 1, "to_node_id": 1, "line_type": 1}).to_list(5000)
    return {"name": chart.get("name"), "settings": chart.get("settings"),
            "show_contact": show_contact, "nodes": nodes, "edges": edges}
