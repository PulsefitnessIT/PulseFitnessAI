"""Single source of truth for MOD/BFPO engineer coverage (territories + explicit sites).

Used by MOD Operations (routes/bfpo.py) and Master Admin (routes/master_admin_mod_estate.py)
so both screens resolve, validate and describe the same `bfpo_territory_ids` / `bfpo_site_ids`.
"""
from fastapi import HTTPException

from utils.database import db

BFPO_ORG_ID = "bfpo-mod-org"


async def lookup() -> tuple[dict, dict]:
    """(territories by id, allocatable sites by id) — BFPO estate sites + MOD establishment orgs."""
    terrs = {t["id"]: t async for t in db.bfpo_territories.find(
        {"organization_id": BFPO_ORG_ID}, {"_id": 0, "id": 1, "name": 1, "country": 1})}
    sites = {s["id"]: {**s, "kind": "bfpo_site"} async for s in db.sites.find(
        {"organization_id": BFPO_ORG_ID}, {"_id": 0, "id": 1, "name": 1, "territory_id": 1, "country": 1})}
    async for o in db.organizations.find({"account_type": "mod_site"}, {"_id": 0, "id": 1, "name": 1, "country": 1}):
        sites.setdefault(o["id"], {**o, "kind": "mod_site"})
    return terrs, sites


def _dedupe(ids) -> list[str]:
    out = []
    for i in ids or []:
        i = (i or "").strip() if isinstance(i, str) else ""
        if i and i not in out:
            out.append(i)
    return out


async def validate_allocation(territory_ids, site_ids, existing_t=(), existing_s=()) -> tuple[list[str], list[str]]:
    """Dedupe and reject NEWLY submitted unknown territory/site ids (422). References already on the
    record are kept (and flagged by describe()) so unrelated edits are never blocked by stale data."""
    terrs, sites = await lookup()
    t_ids, s_ids = _dedupe(territory_ids), _dedupe(site_ids)
    bad_t = [t for t in t_ids if t not in terrs and t not in (existing_t or ())]
    bad_s = [s for s in s_ids if s not in sites and s not in (existing_s or ())]
    if bad_t or bad_s:
        parts = ([f"unknown territory {', '.join(bad_t)}"] if bad_t else []) + (
            [f"unknown site {', '.join(bad_s)}"] if bad_s else [])
        raise HTTPException(422, "Coverage not saved — " + "; ".join(parts))
    return t_ids, s_ids


def describe(u: dict, terrs: dict, sites: dict) -> dict:
    """Coverage summary for one engineer: territories and explicit sites kept separate."""
    t_rows = [{"id": t, "name": terrs[t]["name"], "country": terrs[t].get("country"), "missing": False}
              if t in terrs else {"id": t, "name": "Unknown territory", "country": None, "missing": True}
              for t in _dedupe(u.get("bfpo_territory_ids"))]
    s_rows = []
    for s in _dedupe(u.get("bfpo_site_ids")):
        site = sites.get(s)
        if site:
            terr = terrs.get(site.get("territory_id") or "")
            s_rows.append({"id": s, "name": site.get("name"), "kind": site["kind"], "missing": False,
                           "country": site.get("country") or (terr or {}).get("country"),
                           "in_territory": bool(site.get("territory_id") in (u.get("bfpo_territory_ids") or []))})
        else:
            s_rows.append({"id": s, "name": "Unknown site", "kind": None, "missing": True, "country": None, "in_territory": False})
    valid_t = [t for t in t_rows if not t["missing"]]
    valid_s = [s for s in s_rows if not s["missing"]]
    status = ("territory_and_sites" if valid_t and valid_s else "territory" if valid_t
              else "sites" if valid_s else "none")
    issues = []
    if any(t["missing"] for t in t_rows):
        issues.append("References a territory that no longer exists")
    if any(s["missing"] for s in s_rows):
        issues.append("References a site that no longer exists")
    if status == "none":
        issues.append("No territory or site allocated — this engineer cannot see any MOD jobs")
    if u.get("is_active") is False:
        issues.append("Account deactivated — cannot sign in")
    countries = sorted({c for c in [t["country"] for t in valid_t] + [s["country"] for s in valid_s] if c})
    return {"status": status, "territories": t_rows, "sites": s_rows, "countries": countries, "issues": issues}


async def covers_case(eng: dict, case: dict) -> bool:
    """Does the engineer's normal coverage include this job's site/territory?"""
    if (eng.get("bfpo_role") or "") == "lead":
        return True
    terr = set(eng.get("bfpo_territory_ids") or [])
    sites = set(eng.get("bfpo_site_ids") or [])
    if case.get("territory_id") in terr:
        return True
    for sid in (case.get("site_id"), case.get("organization_id")):
        if sid and sid in sites:
            return True
    if terr and case.get("site_id"):
        s = await db.sites.find_one({"id": case["site_id"], "organization_id": BFPO_ORG_ID}, {"_id": 0, "territory_id": 1})
        if s and s.get("territory_id") in terr:
            return True
    return False
