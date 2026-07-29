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
import uuid

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit, sync_staffing_to_crm_users

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

async def covered_territory_ids(user: dict) -> list[str]:
    """Territory ids where this user is an assigned rep — i.e. their 'area'.

    Used to scope the global appointments/calendar so regional staff only
    see what's happening in the patch they cover. Empty list = the user
    isn't assigned to any territory (treated as 'not regional staff').
    """
    org = user.get("organization_id")
    uid = user.get("id")
    if not org or not uid:
        return []
    cur = db.crm_territories.find(
        {"organization_id": org, "assigned_rep_ids": uid, "archived": {"$ne": True}},
        {"_id": 0, "id": 1},
    )
    return [t["id"] async for t in cur]


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
    # Cross-module flow: mirror Operations Staffing field staff (engineers /
    # sales managers set up in HR) into CRM so they appear as reps here AND
    # become assignable on the Territory map. Without this the map showed
    # "No CRM users yet" even though HR had staff. Idempotent + best-effort.
    await sync_staffing_to_crm_users(user.get("organization_id"))
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


@router.get("/tree")
async def territory_tree(user=Depends(get_crm_user)):
    """Iter 216h265 — hierarchical territory tree.

    Returns territories nested by `parent_id` (UK → Scotland → North…)
    plus a flat list so the UI can pick whichever shape it needs.
    Roots are nodes with no `parent_id` (or a `parent_id` that doesn't
    resolve inside the org — defensive against stale data).
    """
    of = _org_filter(user)
    items = await db.crm_territories.find(
        {**of, "archived": {"$ne": True}},
        {"_id": 0},
    ).sort("name", 1).to_list(1000)

    by_id = {t["id"]: t for t in items}
    # Cheap headline rollups so the tree can show counts without N+1
    # round-trips on the client side.
    children_by_parent: dict[str | None, list[dict]] = {}
    for t in items:
        pid = t.get("parent_id") if t.get("parent_id") in by_id else None
        children_by_parent.setdefault(pid, []).append(t)

    def build(node: dict) -> dict:
        kids = children_by_parent.get(node["id"], [])
        return {
            **node,
            "children": sorted(
                (build(c) for c in kids),
                key=lambda n: (n.get("name") or "").lower(),
            ),
        }

    roots = children_by_parent.get(None, [])
    tree = sorted(
        (build(r) for r in roots),
        key=lambda n: (n.get("name") or "").lower(),
    )
    return {"tree": tree, "flat": items, "total": len(items)}


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


# ── Iter 216h278: Interactive UK Territory Map ───────────────────────
#
# A visual map of the UK (counties + postcode areas) where the admin
# can colour regions and assign Sales Managers + Engineers. The map
# UI reads/writes via the endpoints below; under the hood every
# region becomes a row in `crm_territories` so the existing
# auto-assign engine + rollup keep working unchanged.
#
# Postcode-area territories carry priority 100; county territories
# carry priority 10 — so a single postcode override always beats a
# broad county sweep, which is the "cross-over" model the customer
# explicitly asked for.

REGION_TYPES = {"county", "postcode_area"}
_REGION_PRIORITY = {"county": 10, "postcode_area": 100}


def _normalise_role(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if v in {"sales_manager", "engineer", "both"} else "sales_manager"


def _normalise_colour(value: str | None) -> str:
    """Accept '#RRGGBB' / 'RRGGBB' / 'rgb()'. Fall back to a neutral grey."""
    v = (value or "").strip()
    if not v:
        return "#94A3B8"
    if not v.startswith("#"):
        v = "#" + v
    # very lightweight hex validation
    hex_part = v[1:]
    if len(hex_part) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in hex_part):
        return v.upper() if len(hex_part) == 6 else v.upper()
    return "#94A3B8"


@router.get("/staff-palette")
async def staff_palette(user=Depends(get_crm_user)):
    """List every CRM user with their assigned map colour + role.

    Used by the Territory Map sidebar so admins can pick who to drop
    onto a region. Adds a `colour_hex` and `territory_role` to each
    record (with sensible defaults if the user hasn't been styled yet).
    """
    of = _org_filter(user)
    # Cross-module flow: mirror Operations Staffing field staff into CRM so
    # engineers / sales managers set up in Staffing are assignable here.
    await sync_staffing_to_crm_users(user.get("organization_id"))
    users = await db.crm_users.find(
        of, {"_id": 0, "password": 0},
    ).sort("full_name", 1).to_list(500)
    palette = []
    for u in users:
        palette.append({
            "id": u["id"],
            "full_name": u.get("full_name", ""),
            "email": u.get("email", ""),
            "role": u.get("role", "rep"),
            "manager_id": u.get("manager_id"),
            "colour_hex": _normalise_colour(u.get("colour_hex")),
            "territory_role": _normalise_role(u.get("territory_role")),
        })
    return {"staff": palette, "total": len(palette)}


@router.put("/staff/{uid}/style")
async def update_staff_style(uid: str, data: dict, user=Depends(get_crm_user)):
    """Save a CRM user's map colour + territory role.

    Self-service: the user editing themselves is allowed; otherwise
    requires admin/owner/manager.
    """
    of = _org_filter(user)
    if uid != user["id"]:
        _require_team_admin(user)
    target = await db.crm_users.find_one({"id": uid, **of}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(404, "User not found")
    updates: dict = {"updated_at": _now()}
    if "colour_hex" in data:
        updates["colour_hex"] = _normalise_colour(data.get("colour_hex"))
    if "territory_role" in data:
        updates["territory_role"] = _normalise_role(data.get("territory_role"))
    if len(updates) == 1:
        raise HTTPException(400, "Nothing to update — pass colour_hex or territory_role")
    await db.crm_users.update_one({"id": uid, **of}, {"$set": updates})
    await log_audit(user, "user", uid, "style_updated", {k: v for k, v in updates.items() if k != "updated_at"})
    return {"success": True, **{k: v for k, v in updates.items() if k != "updated_at"}}


def _region_territory_name(region_type: str, region_code: str) -> str:
    if region_type == "postcode_area":
        return f"Postcode {region_code}"
    return region_code


async def _region_territory_doc(org_id: str, region_type: str, region_code: str) -> dict | None:
    return await db.crm_territories.find_one(
        {
            "organization_id": org_id,
            "region_type": region_type,
            "region_code": region_code,
            "archived": {"$ne": True},
        },
        {"_id": 0},
    )


@router.put("/region/{region_type}/{region_code}")
async def upsert_region_assignment(
    region_type: str,
    region_code: str,
    data: dict,
    user=Depends(get_crm_user),
):
    """Assign N reps to a county or postcode area on the map.

    Body: `{ assigned_rep_ids: [uid, ...], colour_hex?: "#RRGGBB" }`.
    Pass an empty `assigned_rep_ids` list to clear the region.
    Creates the underlying territory on first assignment, updates in
    place thereafter, archives when the list goes empty.
    """
    _require_team_admin(user)
    if region_type not in REGION_TYPES:
        raise HTTPException(400, "region_type must be 'county' or 'postcode_area'")
    region_code = (region_code or "").strip()
    if not region_code:
        raise HTTPException(400, "region_code required")
    org_id = user.get("organization_id")
    assigned = list(data.get("assigned_rep_ids") or [])

    # Validate reps belong to the org (silently drops strays).
    if assigned:
        valid = await db.crm_users.find(
            {"id": {"$in": assigned}, "organization_id": org_id},
            {"_id": 0, "id": 1},
        ).to_list(500)
        assigned = [r["id"] for r in valid]

    existing = await _region_territory_doc(org_id, region_type, region_code)
    if not assigned:
        # Empty list → archive the region's territory (if any).
        if existing:
            await db.crm_territories.update_one(
                {"id": existing["id"]},
                {"$set": {"archived": True, "assigned_rep_ids": [], "updated_at": _now()}},
            )
            await log_audit(user, "territory", existing["id"], "region_cleared",
                            {"region_type": region_type, "region_code": region_code})
        return {"success": True, "cleared": True}

    colour = _normalise_colour(data.get("colour_hex")) if "colour_hex" in data else None
    if existing:
        patch: dict = {
            "assigned_rep_ids": assigned,
            "archived": False,
            "updated_at": _now(),
        }
        if colour:
            patch["colour_hex"] = colour
        await db.crm_territories.update_one({"id": existing["id"]}, {"$set": patch})
        await log_audit(user, "territory", existing["id"], "region_updated",
                        {"assigned_rep_ids": assigned, "region_code": region_code})
        return {"success": True, "territory_id": existing["id"]}

    tid = _id()
    record = {
        "id": tid,
        "organization_id": org_id,
        "name": _region_territory_name(region_type, region_code),
        "parent_id": None,
        "description": f"Auto-created from map ({region_type}: {region_code})",
        "postcode_prefixes": [region_code.upper()] if region_type == "postcode_area" else [],
        "counties": [region_code] if region_type == "county" else [],
        "regions": [],
        "countries": [],
        "assigned_rep_ids": assigned,
        "priority": _REGION_PRIORITY[region_type],
        "rr_cursor": 0,
        "region_type": region_type,
        "region_code": region_code,
        "colour_hex": colour,
        "archived": False,
        "created_by": user["id"],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.crm_territories.insert_one(record)
    await log_audit(user, "territory", tid, "region_created", {
        "region_type": region_type, "region_code": region_code,
        "assigned_rep_ids": assigned,
    })
    return {"success": True, "territory_id": tid, "created": True}


@router.get("/coverage-map")
async def coverage_map(user=Depends(get_crm_user)):
    """Compact payload the map UI reads to paint every region.

    Returns:
        {
          counties:        { '<county name>': [{user_id, full_name, colour_hex, role}] },
          postcode_areas:  { '<area code>':   [{user_id, full_name, colour_hex, role}] },
          updated_at:      ISO ts,
        }
    """
    org_id = user.get("organization_id")
    territories = await db.crm_territories.find(
        {
            "organization_id": org_id,
            "archived": {"$ne": True},
            "region_type": {"$in": list(REGION_TYPES)},
        },
        {"_id": 0},
    ).to_list(1000)
    # Collect every rep id so we can resolve names + colours in one batch query.
    rep_ids: set[str] = set()
    for t in territories:
        for rid in t.get("assigned_rep_ids") or []:
            rep_ids.add(rid)
    rep_lookup: dict[str, dict] = {}
    if rep_ids:
        reps = await db.crm_users.find(
            {"id": {"$in": list(rep_ids)}, "organization_id": org_id},
            {"_id": 0, "password": 0},
        ).to_list(500)
        for r in reps:
            rep_lookup[r["id"]] = {
                "user_id": r["id"],
                "full_name": r.get("full_name", ""),
                "colour_hex": _normalise_colour(r.get("colour_hex")),
                "role": _normalise_role(r.get("territory_role")),
            }

    counties: dict[str, list[dict]] = {}
    postcodes: dict[str, list[dict]] = {}
    for t in territories:
        bucket = counties if t.get("region_type") == "county" else postcodes
        members = [rep_lookup[rid] for rid in t.get("assigned_rep_ids") or [] if rid in rep_lookup]
        bucket[t.get("region_code", "")] = members
    return {
        "counties": counties,
        "postcode_areas": postcodes,
        "updated_at": _now(),
    }


@router.get("/coverage-for")
async def coverage_for(
    postcode: str = "",
    county: str = "",
    company_id: str = "",
    user=Depends(get_crm_user),
):
    """Resolve who covers a location — used by Tenders + Companies
    to render a 'Covered by' badge.

    Postcode-area match wins over county match (priority 100 vs 10).
    Pass `company_id` to look up the company's stored postcode/county
    without a round-trip from the caller.
    """
    org_id = user.get("organization_id")
    # If the caller passed a company_id, resolve its postcode/county.
    if company_id and not (postcode or county):
        comp = await db.crm2_companies.find_one(
            {"id": company_id, "organization_id": org_id},
            {"_id": 0, "postcode": 1, "county": 1},
        )
        if comp:
            postcode = comp.get("postcode") or ""
            county = comp.get("county") or ""
    record = {"postcode": postcode or "", "county": county or ""}
    t = await resolve_territory_for(record, org_id)
    if not t:
        return {"covered": False}
    rep_ids = t.get("assigned_rep_ids") or []
    if not rep_ids:
        return {"covered": True, "territory_id": t["id"], "territory_name": t.get("name"), "reps": []}
    reps = await db.crm_users.find(
        {"id": {"$in": rep_ids}, "organization_id": org_id},
        {"_id": 0, "password": 0},
    ).to_list(100)
    return {
        "covered": True,
        "territory_id": t["id"],
        "territory_name": t.get("name"),
        "region_type": t.get("region_type"),
        "region_code": t.get("region_code"),
        "reps": [
            {
                "user_id": r["id"],
                "full_name": r.get("full_name", ""),
                "colour_hex": _normalise_colour(r.get("colour_hex")),
                "role": _normalise_role(r.get("territory_role")),
            }
            for r in reps
        ],
    }


@router.get("/coverage-report")
async def coverage_report(user=Depends(get_crm_user)):
    """Pipeline + tender £ value per rep, grouped by their territories.

    The CRM Tenders module asked for a visual indicator of who covers
    what; this endpoint feeds the "Territory Coverage" panel on the
    Tenders page (£ value of tenders inside each rep's patch).
    """
    org_id = user.get("organization_id")
    territories = await db.crm_territories.find(
        {
            "organization_id": org_id,
            "archived": {"$ne": True},
            "region_type": {"$in": list(REGION_TYPES)},
        },
        {"_id": 0},
    ).to_list(1000)
    if not territories:
        return {"rows": [], "totals": {"tenders": 0, "value": 0}}

    rep_to_regions: dict[str, list[dict]] = {}
    for t in territories:
        for rid in t.get("assigned_rep_ids") or []:
            rep_to_regions.setdefault(rid, []).append({
                "id": t["id"],
                "name": t.get("name"),
                "region_type": t.get("region_type"),
                "region_code": t.get("region_code"),
            })

    # Resolve rep meta in one batch.
    rep_ids = list(rep_to_regions.keys())
    reps_meta: dict[str, dict] = {}
    if rep_ids:
        reps = await db.crm_users.find(
            {"id": {"$in": rep_ids}, "organization_id": org_id},
            {"_id": 0, "password": 0},
        ).to_list(500)
        for r in reps:
            reps_meta[r["id"]] = {
                "full_name": r.get("full_name", ""),
                "colour_hex": _normalise_colour(r.get("colour_hex")),
                "role": _normalise_role(r.get("territory_role")),
            }

    # Tender + opportunity counts per territory.
    rows = []
    total_tenders = 0
    total_value = 0.0
    for rep_id, regions in rep_to_regions.items():
        meta = reps_meta.get(rep_id, {"full_name": "?", "colour_hex": "#94A3B8", "role": "sales_manager"})
        tender_count = 0
        tender_value = 0.0
        opp_value = 0.0
        for r in regions:
            tenders = await db.crm_v2_tenders.find(
                {"organization_id": org_id, "territory_id": r["id"]},
                {"_id": 0, "value": 1},
            ).to_list(500)
            tender_count += len(tenders)
            tender_value += sum(t.get("value") or 0 for t in tenders)
            opps = await db.crm2_opportunities.find(
                {"organization_id": org_id, "territory_id": r["id"], "stage": {"$nin": ["closed_won", "closed_lost"]}},
                {"_id": 0, "value": 1},
            ).to_list(500)
            opp_value += sum(o.get("value") or 0 for o in opps)
        rows.append({
            "user_id": rep_id,
            **meta,
            "region_count": len(regions),
            "regions": regions,
            "tender_count": tender_count,
            "tender_value": round(tender_value, 2),
            "pipeline_value": round(opp_value, 2),
        })
        total_tenders += tender_count
        total_value += tender_value
    rows.sort(key=lambda r: r["tender_value"], reverse=True)
    return {
        "rows": rows,
        "totals": {"tenders": total_tenders, "value": round(total_value, 2)},
    }


@router.get("/coverage-heatmap")
async def coverage_heatmap(user=Depends(get_crm_user)):
    """Per-region open pipeline + tender £ — used by the Map heatmap overlay.

    Returns a flat `{counties:{code:£}, postcode_areas:{code:£}}` so the
    Map UI can recolour each polygon's opacity in O(1). Picks the
    MAX(tender_value, pipeline_value) per region so the heatmap stays
    legible even when one stream is dwarfing the other.
    """
    org_id = user.get("organization_id")
    territories = await db.crm_territories.find(
        {
            "organization_id": org_id,
            "archived": {"$ne": True},
            "region_type": {"$in": list(REGION_TYPES)},
        },
        {"_id": 0, "id": 1, "region_type": 1, "region_code": 1},
    ).to_list(1000)
    counties: dict[str, float] = {}
    postcodes: dict[str, float] = {}
    for t in territories:
        tenders = await db.crm_v2_tenders.find(
            {"organization_id": org_id, "territory_id": t["id"]},
            {"_id": 0, "value": 1},
        ).to_list(500)
        opps = await db.crm2_opportunities.find(
            {"organization_id": org_id, "territory_id": t["id"], "stage": {"$nin": ["closed_won", "closed_lost"]}},
            {"_id": 0, "value": 1},
        ).to_list(500)
        v = max(
            sum(x.get("value") or 0 for x in tenders),
            sum(x.get("value") or 0 for x in opps),
        )
        bucket = counties if t.get("region_type") == "county" else postcodes
        bucket[t.get("region_code", "")] = round(float(v), 2)
    return {"counties": counties, "postcode_areas": postcodes}


@router.post("/map-auto-assign")
async def map_auto_assign(data: dict, user=Depends(get_crm_user)):
    """One-click apply: push every region's coverage onto unassigned
    companies, opportunities, and tenders.

    Wraps the existing `assign_from_territory` per record and skips
    anything that already has a `territory_id`. Returns a summary so
    the Map sidebar can render a confirmation toast.

    Body: `{ dry_run?: bool, only_unassigned?: bool }`
    """
    _require_team_admin(user)
    org_id = user.get("organization_id")
    dry_run = bool(data.get("dry_run", False))
    only_unassigned = bool(data.get("only_unassigned", True))

    coll_map = {
        "company": db.crm2_companies,
        "opportunity": db.crm2_opportunities,
        "tender": db.crm_v2_tenders,
    }
    totals = {"company": 0, "opportunity": 0, "tender": 0}
    for entity, coll in coll_map.items():
        query = {"organization_id": org_id}
        if only_unassigned:
            query["territory_id"] = {"$in": [None, ""]}
        cursor = coll.find(query, {"_id": 0}).limit(2000)
        async for rec in cursor:
            assignment = await assign_from_territory(rec, org_id)
            if not assignment or not assignment.get("territory_id"):
                continue
            if not dry_run:
                patch = {"territory_id": assignment["territory_id"], "updated_at": _now()}
                if assignment.get("owner_id"):
                    patch["owner_id"] = assignment["owner_id"]
                    patch["owner_name"] = assignment.get("owner_name", "")
                await coll.update_one({"id": rec["id"]}, {"$set": patch})
            totals[entity] += 1
    if not dry_run:
        await log_audit(
            user, "territory", "map", "auto_assign", {"totals": totals},
        )
    return {"dry_run": dry_run, "totals": totals, "total": sum(totals.values())}


# ── Office locations (map markers) ───────────────────────────────────
#
# Physical offices/depots the org wants pinned on the coverage map so
# planners can see how field staff patches sit relative to their bases.
# Stored in their own `crm_offices` collection (kept out of
# `crm_territories` so they never interfere with the auto-assign engine).

def _num_or_none(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def _geocode_postcode(postcode: str) -> dict | None:
    """Resolve a UK postcode to {lat, lng} via the free postcodes.io API.

    Returns None on any failure (bad postcode, network, timeout) so
    callers can fall back to manual coordinates.
    """
    pc = (postcode or "").strip().replace(" ", "")
    if not pc:
        return None
    import httpx
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.get(f"https://api.postcodes.io/postcodes/{pc}")
            if r.status_code != 200:
                return None
            res = (r.json() or {}).get("result") or {}
            lat = res.get("latitude")
            lng = res.get("longitude")
            if lat is None or lng is None:
                return None
            return {"lat": float(lat), "lng": float(lng), "county": res.get("admin_county") or res.get("region") or ""}
    except Exception:
        return None


@router.get("/geocode")
async def geocode_postcode(postcode: str = "", user=Depends(get_crm_user)):
    """Look up lat/lng for a UK postcode so the Offices form can pin by
    postcode instead of manual coordinates."""
    g = await _geocode_postcode(postcode)
    if not g:
        raise HTTPException(404, "Could not resolve that postcode")
    return g


@router.get("/offices")
async def list_offices(user=Depends(get_crm_user)):
    of = _org_filter(user)
    items = await db.crm_offices.find(
        {**of, "archived": {"$ne": True}}, {"_id": 0},
    ).sort("name", 1).to_list(500)
    return {"offices": items, "total": len(items)}


@router.post("/offices")
async def create_office(data: dict, user=Depends(get_crm_user)):
    _require_team_admin(user)
    lat = _num_or_none(data.get("lat"))
    lng = _num_or_none(data.get("lng"))
    postcode = (data.get("postcode") or "").strip().upper()
    # Auto-geocode from the postcode when no coordinates were supplied.
    if (lat is None or lng is None) and postcode:
        g = await _geocode_postcode(postcode)
        if g:
            lat, lng = g["lat"], g["lng"]
    if lat is None or lng is None:
        raise HTTPException(400, "Provide a valid UK postcode or lat/lng")
    oid = _id()
    record = {
        "id": oid,
        "organization_id": user.get("organization_id"),
        "name": (data.get("name") or "").strip() or "Office",
        "address": (data.get("address") or "").strip(),
        "postcode": postcode,
        "lat": lat,
        "lng": lng,
        "colour_hex": _normalise_colour(data.get("colour_hex") or "#0F172A"),
        "kind": (data.get("kind") or "office").strip().lower(),
        "archived": False,
        "created_by": user["id"],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.crm_offices.insert_one(record)
    await log_audit(user, "office", oid, "created", {"name": record["name"]})
    return {k: v for k, v in record.items() if k != "_id"}


@router.put("/offices/{oid}")
async def update_office(oid: str, data: dict, user=Depends(get_crm_user)):
    _require_team_admin(user)
    of = _org_filter(user)
    existing = await db.crm_offices.find_one({"id": oid, **of}, {"_id": 0, "id": 1})
    if not existing:
        raise HTTPException(404, "Office not found")
    updates: dict = {"updated_at": _now()}
    if "name" in data:
        updates["name"] = (data.get("name") or "").strip() or "Office"
    if "address" in data:
        updates["address"] = (data.get("address") or "").strip()
    if "postcode" in data:
        updates["postcode"] = (data.get("postcode") or "").strip().upper()
    if "colour_hex" in data:
        updates["colour_hex"] = _normalise_colour(data.get("colour_hex"))
    if "kind" in data:
        updates["kind"] = (data.get("kind") or "office").strip().lower()
    if "lat" in data:
        lat = _num_or_none(data.get("lat"))
        if lat is None:
            raise HTTPException(400, "Invalid lat")
        updates["lat"] = lat
    if "lng" in data:
        lng = _num_or_none(data.get("lng"))
        if lng is None:
            raise HTTPException(400, "Invalid lng")
        updates["lng"] = lng
    await db.crm_offices.update_one({"id": oid, **of}, {"$set": updates})
    await log_audit(user, "office", oid, "updated", {k: v for k, v in updates.items() if k != "updated_at"})
    return {"success": True}


@router.delete("/offices/{oid}")
async def delete_office(oid: str, user=Depends(get_crm_user)):
    _require_team_admin(user)
    of = _org_filter(user)
    r = await db.crm_offices.update_one(
        {"id": oid, **of}, {"$set": {"archived": True, "updated_at": _now()}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Office not found")
    await log_audit(user, "office", oid, "archived")
    return {"success": True}


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


