"""Iter 216h163 — Self-service per-site data export (JSON + ZIP/CSV).

HQ owners and managers of multi-site chains need a one-click way to
pull every record we hold for a single site — for board reviews,
ICO subject-access responses, vendor offboarding, and internal audit.

This file exposes three endpoints, mounted under the existing
`/api/account/...` namespace so they sit next to the rest of the
HQ-owner self-service surface (team admin, billing, branding):

    GET /api/account/data-export/sites
        → list of sites the caller is allowed to export.
    GET /api/account/data-export/site/{site_id}.json
        → one big JSON dump of every site-scoped record.
    GET /api/account/data-export/site/{site_id}.zip
        → ZIP containing one CSV per collection + manifest.json.

Authorization:
  • role must be owner / manager / master_admin (the same gate used
    by `/account/team` and the rest of HQ self-service);
  • site_id must belong to either a `db.sites` row of the caller's
    own organisation, OR (for MOD HQ users) a `mod_site` child org
    rooted under the caller's `mod_root_id` — anything else 403s.
  • Every export is `audit_log()`'d with action `site_data_export`
    so the Compliance trail viewer (iter 216h161) shows who pulled
    what, when, from which IP.

Format choice rationale: JSON is the "data portability" format ICO
prefers (Art. 20 — Right to Data Portability); CSV-in-ZIP is what
finance / procurement actually open in Excel. We ship both.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from utils.audit import audit_log
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Knobs ────────────────────────────────────────────────────────
AUDIT_WINDOW_DAYS = 365
MAX_AUDIT_ROWS = 50_000
MAX_PER_COLLECTION = 50_000  # defensive cap for memory safety


# ── Role / site authorisation helpers ────────────────────────────

def _require_owner_or_manager(user: dict) -> None:
    role = (user.get("role") or "").lower()
    if role in ("owner", "manager", "master_admin", "master") or user.get("is_master_admin"):
        return
    raise HTTPException(status_code=403, detail="Owner or manager role required")


async def _allowed_sites_for(user: dict) -> list[dict]:
    """Return [{id, name, org_id, kind}] for every site the caller can export.

    kind = "internal" → row in `db.sites` of the caller's own org.
    kind = "mod_child" → a `mod_site` child organisation (its own org_id).

    A master_admin's set is whatever org context they're acting on
    (resolved from their JWT — same as elsewhere in the platform).
    """
    org_id = user.get("organization_id")
    if not org_id:
        return []

    sites: list[dict] = []

    # 1) Internal sites — every row in db.sites for the caller's org.
    internal = await db.sites.find(
        {"organization_id": org_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "is_head_office": 1},
    ).to_list(500)
    for s in internal:
        sites.append({
            "id": s["id"],
            "name": s.get("name") or "Site",
            "org_id": org_id,
            "kind": "internal",
            "is_head_office": bool(s.get("is_head_office")),
        })

    # 2) MOD child organisations rooted under this HQ.
    at = (user.get("account_type") or "").lower()
    if at in ("mod_org", "mod_branch"):
        hq = await db.organizations.find_one(
            {"id": org_id},
            {"_id": 0, "id": 1, "mod_root_id": 1, "mod_branch": 1},
        ) or {}
        root = hq.get("mod_root_id") or org_id
        q = {
            "account_type": "mod_site", "is_mod": True,
            "status": {"$ne": "archived"},
            "mod_root_id": root,
        }
        if at == "mod_branch" and hq.get("mod_branch"):
            q["mod_branch"] = hq["mod_branch"]
        children = await db.organizations.find(
            q, {"_id": 0, "id": 1, "name": 1},
        ).to_list(1000)
        for c in children:
            sites.append({
                "id": c["id"],
                "name": c.get("name") or "MOD Site",
                "org_id": c["id"],
                "kind": "mod_child",
                "is_head_office": False,
            })

    sites.sort(key=lambda s: (not s["is_head_office"], s["name"].lower()))
    return sites


async def _resolve_site_for_export(user: dict, site_id: str) -> dict:
    """Verify the caller is allowed to export site_id; return its descriptor.
    Raises 403 on cross-tenant attempts."""
    allowed = await _allowed_sites_for(user)
    match = next((s for s in allowed if s["id"] == site_id), None)
    if not match:
        raise HTTPException(status_code=403, detail="You do not have access to that site")
    return match


# ── Data gather ──────────────────────────────────────────────────

def _strip_id(doc: dict) -> dict:
    """Defensive ObjectId scrub — every find() projection already
    excludes _id, but never trust the input dict."""
    if not isinstance(doc, dict):
        return doc
    return {k: v for k, v in doc.items() if k != "_id"}


async def _scoped_find(coll: str, *, org_id: str, site_id: str | None,
                       site_field: str | None, limit: int = MAX_PER_COLLECTION,
                       sort: tuple[str, int] | None = None) -> list[dict]:
    """Find rows in `coll` scoped to org (+ optional site field)."""
    q: dict = {"organization_id": org_id}
    if site_id and site_field:
        q[site_field] = site_id
    cur = db[coll].find(q, {"_id": 0})
    if sort:
        cur = cur.sort(sort[0], sort[1])
    rows = await cur.to_list(limit)
    return [_strip_id(r) for r in rows]


async def _gather_site_export(user: dict, site_desc: dict) -> dict:
    """Build the in-memory export payload for one site."""
    org_id = site_desc["org_id"]
    site_id = site_desc["id"]
    is_mod_child = site_desc["kind"] == "mod_child"

    # For MOD children the "site" IS the org → no site_id field needed
    # anywhere; the org_id alone fully scopes the data. For internal
    # sites we filter by site_id on every collection that carries it.
    site_scope = None if is_mod_child else site_id

    org = await db.organizations.find_one(
        {"id": org_id}, {"_id": 0, "password": 0},
    )
    site_doc = None
    if not is_mod_child:
        site_doc = await db.sites.find_one({"id": site_id}, {"_id": 0})

    # Collections that carry a `site_id` field on internal sites.
    equipment = await _scoped_find(
        "equipment", org_id=org_id, site_id=site_scope, site_field="site_id",
    )
    issues = await _scoped_find(
        "issues", org_id=org_id, site_id=site_scope, site_field="site_id",
    )
    svc_cases = await _scoped_find(
        "svc_cases", org_id=org_id, site_id=site_scope, site_field="site_id",
        sort=("created_at", -1),
    )
    case_ids = [c["id"] for c in svc_cases if c.get("id")]

    # Child collections live under their parent case — join by case_id.
    if case_ids:
        quotes_raw = await db.svc_quotes.find(
            {"organization_id": org_id, "case_id": {"$in": case_ids}}, {"_id": 0},
        ).to_list(MAX_PER_COLLECTION)
        invoices_raw = await db.svc_invoices.find(
            {"organization_id": org_id, "case_id": {"$in": case_ids}}, {"_id": 0},
        ).to_list(MAX_PER_COLLECTION)
        events_raw = await db.svc_case_events.find(
            {"organization_id": org_id, "case_id": {"$in": case_ids}}, {"_id": 0},
        ).sort("created_at", 1).to_list(MAX_PER_COLLECTION)
        visit_notes_raw = await db.svc_visit_notes.find(
            {"organization_id": org_id, "case_id": {"$in": case_ids}}, {"_id": 0},
        ).to_list(MAX_PER_COLLECTION)
    else:
        quotes_raw = invoices_raw = events_raw = visit_notes_raw = []

    svc_quotes = [_strip_id(d) for d in quotes_raw]
    svc_invoices = [_strip_id(d) for d in invoices_raw]
    svc_case_events = [_strip_id(d) for d in events_raw]
    svc_visit_notes = [_strip_id(d) for d in visit_notes_raw]

    # Audit log — last 365 days, scoped by users belonging to this org
    # (the audit_logs collection itself doesn't store organization_id,
    # so we resolve via users.organization_id).
    cutoff = (datetime.now(timezone.utc) - timedelta(days=AUDIT_WINDOW_DAYS)).isoformat()
    org_user_ids = [
        u["id"] async for u in db.users.find(
            {"organization_id": org_id}, {"_id": 0, "id": 1},
        )
    ]
    audit_query: dict = {"timestamp": {"$gte": cutoff}}
    if org_user_ids:
        audit_query["user_id"] = {"$in": org_user_ids}
    else:
        # No users → use resource_id match against site_id as a fallback.
        audit_query["resource_id"] = site_id
    audit_rows = await db.audit_logs.find(
        audit_query, {"_id": 0},
    ).sort("timestamp", -1).to_list(MAX_AUDIT_ROWS)
    audit_rows = [_strip_id(r) for r in audit_rows]

    # Org-level collections that are NOT site-segregable — only ship
    # them when exporting a MOD child (where the org IS the site). For
    # internal sites these belong to the whole org and would leak data
    # from sibling sites if included.
    members: list[dict] = []
    invoices: list[dict] = []
    suppliers: list[dict] = []
    if is_mod_child:
        members = [
            _strip_id(m) for m in
            await db.members.find(
                {"organization_id": org_id},
                {"_id": 0, "password": 0},
            ).to_list(MAX_PER_COLLECTION)
        ]
        invoices = [
            _strip_id(i) for i in
            await db.invoices.find({"organization_id": org_id}, {"_id": 0})
            .sort("issued_at", -1).to_list(MAX_PER_COLLECTION)
        ]
        suppliers = [
            _strip_id(s) for s in
            await db.suppliers.find({"organization_id": org_id}, {"_id": 0})
            .to_list(MAX_PER_COLLECTION)
        ]

    return {
        "export_generated_at": datetime.now(timezone.utc).isoformat(),
        "export_format_version": "1.0",
        "exported_by": {
            "user_id": user.get("id"),
            "email": user.get("email"),
            "role": user.get("role"),
            "account_type": user.get("account_type"),
        },
        "site": {
            "id": site_id,
            "name": site_desc["name"],
            "kind": site_desc["kind"],
            "is_head_office": site_desc["is_head_office"],
            "record": _strip_id(site_doc) if site_doc else None,
        },
        "organization": _strip_id(org) if org else None,
        "counts": {
            "equipment": len(equipment),
            "issues": len(issues),
            "svc_cases": len(svc_cases),
            "svc_quotes": len(svc_quotes),
            "svc_invoices": len(svc_invoices),
            "svc_case_events": len(svc_case_events),
            "svc_visit_notes": len(svc_visit_notes),
            "audit_logs": len(audit_rows),
            "members": len(members),
            "invoices": len(invoices),
            "suppliers": len(suppliers),
        },
        "equipment": equipment,
        "issues": issues,
        "svc_cases": svc_cases,
        "svc_quotes": svc_quotes,
        "svc_invoices": svc_invoices,
        "svc_case_events": svc_case_events,
        "svc_visit_notes": svc_visit_notes,
        "audit_logs": audit_rows,
        "members": members,
        "invoices": invoices,
        "suppliers": suppliers,
    }


# ── CSV / ZIP serialisation ──────────────────────────────────────

def _flatten_value(v):
    """Stringify nested values for CSV — lists/dicts → JSON, None → ''."""
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str, ensure_ascii=False)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _rows_to_csv_bytes(rows: list[dict]) -> bytes:
    """Convert a list of dicts to CSV bytes. Header is the union of
    keys across rows, sorted with common fields first."""
    if not rows:
        return b""
    # Union of keys, with id/name/created_at first if present.
    keys: list[str] = []
    seen = set()
    for preferred in ("id", "reference", "name", "title", "email", "status",
                      "created_at", "timestamp", "issued_at"):
        if any(preferred in r for r in rows) and preferred not in seen:
            keys.append(preferred)
            seen.add(preferred)
    for r in rows:
        for k in r:
            if k not in seen:
                keys.append(k)
                seen.add(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: _flatten_value(r.get(k)) for k in keys})
    return buf.getvalue().encode("utf-8")


def _build_zip(payload: dict) -> bytes:
    """Bundle the export payload as a ZIP — one CSV per list collection
    + manifest.json with the metadata header."""
    buf = io.BytesIO()
    csv_collections = [
        "equipment", "issues", "svc_cases", "svc_quotes", "svc_invoices",
        "svc_case_events", "svc_visit_notes", "audit_logs",
        "members", "invoices", "suppliers",
    ]
    # Manifest = everything that isn't a list collection (so JSON stays small).
    manifest = {
        k: v for k, v in payload.items()
        if k not in csv_collections
    }
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json",
                    json.dumps(manifest, indent=2, default=str))
        for coll in csv_collections:
            rows = payload.get(coll) or []
            if not rows:
                continue
            zf.writestr(f"{coll}.csv", _rows_to_csv_bytes(rows))
        # Also include the raw JSON dump for archivists.
        zf.writestr("full_export.json",
                    json.dumps(payload, indent=2, default=str))
    return buf.getvalue()


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/account/data-export/sites")
async def list_exportable_sites(user: dict = Depends(get_current_user)) -> dict:
    """List every site the caller is allowed to export."""
    _require_owner_or_manager(user)
    sites = await _allowed_sites_for(user)
    return {"sites": sites, "count": len(sites)}


@router.get("/account/data-export/site/{site_id}.json")
async def export_site_json(
    site_id: str, request: Request,
    user: dict = Depends(get_current_user),
) -> Response:
    _require_owner_or_manager(user)
    site_desc = await _resolve_site_for_export(user, site_id)
    payload = await _gather_site_export(user, site_desc)
    ip = request.client.host if request.client else ""
    await audit_log(
        "site_data_export", user.get("id"), user.get("email", ""),
        "site", site_id,
        f"JSON export · {sum(payload['counts'].values())} rows across "
        f"{len(payload['counts'])} collections",
        ip,
    )
    blob = json.dumps(payload, indent=2, default=str).encode("utf-8")
    safe_name = (site_desc["name"] or "site").replace(" ", "_").replace("/", "-")[:40]
    return Response(
        content=blob,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="site_export_{safe_name}_'
                f'{datetime.now(timezone.utc).strftime("%Y%m%d")}.json"'
            ),
        },
    )


@router.get("/account/data-export/site/{site_id}.zip")
async def export_site_zip(
    site_id: str, request: Request,
    user: dict = Depends(get_current_user),
) -> Response:
    _require_owner_or_manager(user)
    site_desc = await _resolve_site_for_export(user, site_id)
    payload = await _gather_site_export(user, site_desc)
    zip_bytes = _build_zip(payload)
    ip = request.client.host if request.client else ""
    await audit_log(
        "site_data_export", user.get("id"), user.get("email", ""),
        "site", site_id,
        f"ZIP/CSV export · {sum(payload['counts'].values())} rows across "
        f"{len(payload['counts'])} collections",
        ip,
    )
    safe_name = (site_desc["name"] or "site").replace(" ", "_").replace("/", "-")[:40]
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="site_export_{safe_name}_'
                f'{datetime.now(timezone.utc).strftime("%Y%m%d")}.zip"'
            ),
        },
    )


__all__ = ["router"]
