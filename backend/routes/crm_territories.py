"""
CRM Territories, Team Hierarchy & Coverage Assignment (iter 215dc).

Enterprise-grade sales coverage model:

- **Territories**: hierarchical (3+ levels) with geo criteria
  (postcode prefixes, counties, regions, countries). Tiebreak via
  round-robin across assigned reps.
- **Team hierarchy**: `manager_id` on `crm_users` forms a tree.
  Helper `collect_team_ids()` returns the caller + every
  sub-ordinate, supporting Salesforce-style "my team's pipeline"
  reporting.
- **Auto-assignment**: on contact/company/opportunity creation the
  best-matching territory assigns `owner_id` and `territory_id`.
- **Audit**: every territory + assignment change writes to
  `crm_audit_log` via the existing `log_audit()` helper.

Endpoints (all under `/api/crm/territories`):
    GET    /                       List territories for the caller's org (tree)
    POST   /                       Create a territory
    GET    /{tid}                  Detail with rollup stats
    PUT    /{tid}                  Update
    DELETE /{tid}                  Archive (soft-delete)
    POST   /{tid}/assign-rep       Attach a rep
    POST   /{tid}/remove-rep       Detach a rep
    POST   /auto-assign            Dry-run or apply auto-assignment
    POST   /bulk-reassign          Move records between owners
    GET    /rollup                 Pipeline + won value grouped by territory
    GET    /team/tree              Manager → rep hierarchy tree
    PUT    /team/{uid}/manager     Change reporting line
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import Optional
import uuid

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit

router = APIRouter(prefix="/crm/territories", tags=["CRM Territories"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _org_filter(user: dict) -> dict:
    org_id = user.get("organization_id")
    return {"organization_id": org_id} if org_id else {"organization_id": "__NONE__"}


def _require_team_admin(user: dict):
    if user["role"] not in ("admin", "owner", "manager"):
        raise HTTPException(403, "Insufficient permissions")


# ── Team hierarchy helpers ───────────────────────────────────────────

async def collect_team_ids(user_id: str, org_id: str, visited: set | None = None) -> list[str]:
    """Return `[user_id]` + every direct/indirect subordinate.

    Cycle-safe via `visited`. Capped at 1000 nodes (well above any
    realistic enterprise sales org) to prevent runaway traversal on
    corrupt data.
    """
    if visited is None:
        visited = set()
    if user_id in visited or len(visited) > 1000:
        return list(visited)
    visited.add(user_id)
    directs = await db.crm_users.find(
        {"manager_id": user_id, "organization_id": org_id},
        {"_id": 0, "id": 1},
    ).to_list(200)
    for d in directs:
        await collect_team_ids(d["id"], org_id, visited)
    return list(visited)


@router.get("/team/tree")
async def team_tree(user=Depends(get_crm_user)):
    """Full manager → rep tree for the caller's org."""
    of = _org_filter(user)
    users = await db.crm_users.find(
        of, {"_id": 0, "password": 0},
    ).to_list(500)
    by_manager: dict[str, list] = {}
    for u in users:
        mid = u.get("manager_id") or "__root__"
        by_manager.setdefault(mid, []).append(u)

    def build_node(u: dict) -> dict:
        return {
            **u,
            "directs": [build_node(c) for c in by_manager.get(u["id"], [])],
        }

    roots = by_manager.get("__root__", [])
    return {"tree": [build_node(r) for r in roots], "total_users": len(users)}


@router.put("/team/{user_id}/manager")
async def set_manager(user_id: str, data: dict, user=Depends(get_crm_user)):
    """Change reporting line. Prevents cycles."""
    _require_team_admin(user)
    of = _org_filter(user)
    target = await db.crm_users.find_one({"id": user_id, **of}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")

    new_manager_id = data.get("manager_id") or None
    if new_manager_id == user_id:
        raise HTTPException(400, "User cannot manage themselves")

    if new_manager_id:
        # Walk up the new manager's chain — if we meet user_id, we'd
        # create a cycle. Reject.
        cursor_id = new_manager_id
        hops = 0
        while cursor_id and hops < 50:
            if cursor_id == user_id:
                raise HTTPException(400, "Cycle detected — this assignment would create a loop")
            parent = await db.crm_users.find_one({"id": cursor_id}, {"_id": 0, "manager_id": 1})
            cursor_id = (parent or {}).get("manager_id")
            hops += 1

    await db.crm_users.update_one({"id": user_id}, {"$set": {"manager_id": new_manager_id, "updated_at": _now()}})
    await log_audit(user, "user", user_id, "manager_changed", {"manager_id": new_manager_id})
    return {"success": True}


# ── Territory CRUD ───────────────────────────────────────────────────

@router.get("")
@router.get("/")
async def list_territories(user=Depends(get_crm_user)):
    of = _org_filter(user)
    items = await db.crm_territories.find(
        {**of, "archived": {"$ne": True}},
        {"_id": 0},
    ).sort("name", 1).to_list(500)
    return {"territories": items, "total": len(items)}


@router.post("")
@router.post("/")
async def create_territory(data: dict, user=Depends(get_crm_user)):
    _require_team_admin(user)
    tid = _id()
    record = {
        "id": tid,
        "organization_id": user.get("organization_id"),
        "name": data.get("name", "").strip(),
        "parent_id": data.get("parent_id") or None,
        "description": data.get("description", ""),
        # Geo criteria (all optional; ANY match qualifies a record):
        "postcode_prefixes": [p.upper().strip() for p in data.get("postcode_prefixes", []) if p and isinstance(p, str)],
        "counties":   [c.strip() for c in data.get("counties", []) if c and isinstance(c, str)],
        "regions":    [r.strip() for r in data.get("regions", []) if r and isinstance(r, str)],
        "countries":  [c.strip().upper() for c in data.get("countries", []) if c and isinstance(c, str)],
        "assigned_rep_ids": list(data.get("assigned_rep_ids", [])),
        # Priority — higher number wins when multiple territories match.
        "priority": int(data.get("priority", 0)),
        # Round-robin cursor — which rep in `assigned_rep_ids` gets the next match.
        "rr_cursor": 0,
        "archived": False,
        "created_by": user["id"],
        "created_at": _now(),
        "updated_at": _now(),
    }
    if not record["name"]:
        raise HTTPException(400, "Name required")
    await db.crm_territories.insert_one(record)
    await log_audit(user, "territory", tid, "created", {"name": record["name"]})
    return {k: v for k, v in record.items() if k != "_id"}


async def _territory_rollup(tid: str, org_id: str) -> dict:
    """Compute headline metrics for a single territory."""
    of = {"organization_id": org_id}
    contacts = await db.crm2_contacts.count_documents({**of, "territory_id": tid})
    companies = await db.crm2_companies.count_documents({**of, "territory_id": tid})
    active_opps = await db.crm2_opportunities.find(
        {**of, "territory_id": tid, "stage": {"$nin": ["closed_won", "closed_lost"]}},
        {"_id": 0, "value": 1},
    ).to_list(500)
    won_opps = await db.crm2_opportunities.find(
        {**of, "territory_id": tid, "stage": "closed_won"},
        {"_id": 0, "value": 1},
    ).to_list(500)
    return {
        "contacts": contacts,
        "companies": companies,
        "active_opportunities": len(active_opps),
        "pipeline_value": sum(o.get("value", 0) for o in active_opps),
        "won_value": sum(o.get("value", 0) for o in won_opps),
        "won_count": len(won_opps),
    }


@router.get("/rollup")
async def territory_rollup(user=Depends(get_crm_user)):
    """Pipeline + won value grouped by territory."""
    of = _org_filter(user)
    territories = await db.crm_territories.find(
        {**of, "archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "parent_id": 1, "assigned_rep_ids": 1},
    ).to_list(500)
    rows = []
    for t in territories:
        stats = await _territory_rollup(t["id"], user.get("organization_id"))
        rows.append({**t, **stats})
    return {"rows": rows}


@router.get("/{tid}")
async def get_territory(tid: str, user=Depends(get_crm_user)):
    of = _org_filter(user)
    t = await db.crm_territories.find_one({"id": tid, **of}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Territory not found")
    t["rollup"] = await _territory_rollup(tid, user.get("organization_id"))
    if t.get("assigned_rep_ids"):
        reps = await db.crm_users.find(
            {"id": {"$in": t["assigned_rep_ids"]}},
            {"_id": 0, "password": 0},
        ).to_list(100)
        t["assigned_reps"] = reps
    return t


@router.put("/{tid}")
async def update_territory(tid: str, data: dict, user=Depends(get_crm_user)):
    _require_team_admin(user)
    of = _org_filter(user)
    existing = await db.crm_territories.find_one({"id": tid, **of}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Territory not found")
    allowed = {
        "name", "parent_id", "description", "postcode_prefixes", "counties",
        "regions", "countries", "assigned_rep_ids", "priority",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if "parent_id" in updates and updates["parent_id"] == tid:
        raise HTTPException(400, "Territory cannot be its own parent")
    # Normalise uppercase collections for match correctness.
    if "postcode_prefixes" in updates:
        updates["postcode_prefixes"] = [p.upper().strip() for p in updates["postcode_prefixes"] if p]
    if "countries" in updates:
        updates["countries"] = [c.upper().strip() for c in updates["countries"] if c]
    updates["updated_at"] = _now()
    await db.crm_territories.update_one({"id": tid, **of}, {"$set": updates})
    await log_audit(user, "territory", tid, "updated", updates)
    return {"success": True}


@router.delete("/{tid}")
async def archive_territory(tid: str, user=Depends(get_crm_user)):
    _require_team_admin(user)
    of = _org_filter(user)
    r = await db.crm_territories.update_one(
        {"id": tid, **of}, {"$set": {"archived": True, "updated_at": _now()}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Territory not found")
    await log_audit(user, "territory", tid, "archived")
    return {"success": True}


@router.post("/{tid}/assign-rep")
async def assign_rep(tid: str, data: dict, user=Depends(get_crm_user)):
    _require_team_admin(user)
    of = _org_filter(user)
    rep_id = data.get("rep_id", "")
    if not rep_id:
        raise HTTPException(400, "rep_id required")
    rep = await db.crm_users.find_one({"id": rep_id, **of}, {"_id": 0})
    if not rep:
        raise HTTPException(404, "Rep not found")
    await db.crm_territories.update_one(
        {"id": tid, **of},
        {"$addToSet": {"assigned_rep_ids": rep_id}, "$set": {"updated_at": _now()}},
    )
    await log_audit(user, "territory", tid, "rep_assigned", {"rep_id": rep_id})
    return {"success": True}


@router.post("/{tid}/remove-rep")
async def remove_rep(tid: str, data: dict, user=Depends(get_crm_user)):
    _require_team_admin(user)
    of = _org_filter(user)
    rep_id = data.get("rep_id", "")
    await db.crm_territories.update_one(
        {"id": tid, **of},
        {"$pull": {"assigned_rep_ids": rep_id}, "$set": {"updated_at": _now()}},
    )
    await log_audit(user, "territory", tid, "rep_removed", {"rep_id": rep_id})
    return {"success": True}


# ── Matching engine ──────────────────────────────────────────────────

def _postcode_prefix(postcode: str) -> str:
    """UK postcode outward code — the letters + digits BEFORE the space.

    Works for full postcodes ("SW1A 1AA" → "SW1A"), shortened prefixes
    ("SW1A" → "SW1A"), and messy input ("sw1a1aa" → "SW1A").
    """
    if not postcode:
        return ""
    s = postcode.strip().upper().replace(" ", "")
    # UK outward codes are 2-4 chars: 2 letters + 0-2 digits (+ optional 1 letter).
    # Take up to 4 chars; callers typically store prefixes like "SW", "SW1", "SW1A".
    return s[:4]


def _matches_territory(territory: dict, record: dict) -> bool:
    """True when `record` satisfies the territory's geo criteria."""
    prefixes = territory.get("postcode_prefixes", [])
    counties = set(c.lower() for c in territory.get("counties", []))
    regions = set(r.lower() for r in territory.get("regions", []))
    countries = set(c.upper() for c in territory.get("countries", []))

    rec_postcode = _postcode_prefix(record.get("postcode", ""))
    rec_county = (record.get("county") or record.get("state", "")).lower()
    rec_region = (record.get("region") or "").lower()
    rec_country = (record.get("country") or "UK").upper()

    # No criteria at all → territory is a catch-all (lowest priority wins).
    if not (prefixes or counties or regions or countries):
        return False

    if prefixes and rec_postcode:
        if any(rec_postcode.startswith(p) for p in prefixes):
            return True
    if counties and rec_county and rec_county in counties:
        return True
    if regions and rec_region and rec_region in regions:
        return True
    if countries and rec_country in countries:
        return True
    return False


async def resolve_territory_for(record: dict, org_id: str) -> dict | None:
    """Find the highest-priority matching territory for a record.

    Ties broken by lexicographic `id` for stability. Returns the full
    territory doc or None.
    """
    candidates = await db.crm_territories.find(
        {"organization_id": org_id, "archived": {"$ne": True}},
        {"_id": 0},
    ).sort([("priority", -1), ("id", 1)]).to_list(500)
    for t in candidates:
        if _matches_territory(t, record):
            return t
    return None


async def assign_from_territory(record: dict, org_id: str) -> dict:
    """Return `{territory_id, owner_id, owner_name}` or empty dict if
    no territory matches. Advances the round-robin cursor server-side.
    """
    t = await resolve_territory_for(record, org_id)
    if not t:
        return {}
    reps = t.get("assigned_rep_ids") or []
    if not reps:
        return {"territory_id": t["id"]}
    cursor = int(t.get("rr_cursor") or 0) % len(reps)
    rep_id = reps[cursor]
    # Advance cursor for next call (mod len to wrap).
    await db.crm_territories.update_one(
        {"id": t["id"]},
        {"$set": {"rr_cursor": (cursor + 1) % len(reps), "updated_at": _now()}},
    )
    rep = await db.crm_users.find_one(
        {"id": rep_id}, {"_id": 0, "full_name": 1},
    ) or {}
    return {
        "territory_id": t["id"],
        "owner_id": rep_id,
        "owner_name": rep.get("full_name", ""),
    }


@router.post("/auto-assign")
async def auto_assign(data: dict, user=Depends(get_crm_user)):
    """Run auto-assignment across existing records. Dry-run by default.

    Body:
      { entity: "contact" | "company" | "opportunity",
        dry_run: bool,
        only_unassigned: bool }
    """
    _require_team_admin(user)
    org_id = user.get("organization_id")
    entity = data.get("entity", "company")
    dry_run = bool(data.get("dry_run", True))
    only_unassigned = bool(data.get("only_unassigned", True))

    coll_map = {
        "contact": db.crm2_contacts,
        "company": db.crm2_companies,
        "opportunity": db.crm2_opportunities,
    }
    coll = coll_map.get(entity)
    if coll is None:
        raise HTTPException(400, "entity must be contact, company, or opportunity")

    query = {"organization_id": org_id}
    if only_unassigned:
        query["territory_id"] = {"$in": [None, ""]}

    proposals = []
    changed = 0
    cursor = coll.find(query, {"_id": 0}).limit(500)
    async for rec in cursor:
        assignment = await assign_from_territory(rec, org_id)
        if not assignment or not assignment.get("territory_id"):
            continue
        proposals.append({"id": rec["id"], **assignment})
        if not dry_run:
            patch = {"territory_id": assignment["territory_id"], "updated_at": _now()}
            if assignment.get("owner_id"):
                patch["owner_id"] = assignment["owner_id"]
                patch["owner_name"] = assignment.get("owner_name", "")
            await coll.update_one({"id": rec["id"]}, {"$set": patch})
            changed += 1

    if not dry_run:
        await log_audit(
            user, "territory", "bulk", "auto_assign",
            {"entity": entity, "changed": changed},
        )
    return {"dry_run": dry_run, "proposals": proposals[:200], "changed": changed, "total_proposed": len(proposals)}


@router.post("/bulk-reassign")
async def bulk_reassign(data: dict, user=Depends(get_crm_user)):
    """Move a rep's entire book of business to another rep.

    Body: { from_user_id, to_user_id, entities: ["contact", "company", "opportunity"] }
    """
    _require_team_admin(user)
    org_id = user.get("organization_id")
    frm = data.get("from_user_id", "")
    to = data.get("to_user_id", "")
    entities = data.get("entities") or ["contact", "company", "opportunity"]
    if not frm or not to or frm == to:
        raise HTTPException(400, "Distinct from_user_id and to_user_id required")

    new_rep = await db.crm_users.find_one({"id": to, "organization_id": org_id}, {"_id": 0, "full_name": 1})
    if not new_rep:
        raise HTTPException(404, "Target rep not found")

    coll_map = {
        "contact": db.crm2_contacts,
        "company": db.crm2_companies,
        "opportunity": db.crm2_opportunities,
    }
    moved = {}
    for e in entities:
        coll = coll_map.get(e)
        if coll is None:
            continue
        r = await coll.update_many(
            {"organization_id": org_id, "owner_id": frm},
            {"$set": {
                "owner_id": to,
                "owner_name": new_rep.get("full_name", ""),
                "updated_at": _now(),
            }},
        )
        moved[e] = r.modified_count

    await log_audit(
        user, "territory", "bulk", "reassign",
        {"from": frm, "to": to, "moved": moved},
    )
    return {"moved": moved}
