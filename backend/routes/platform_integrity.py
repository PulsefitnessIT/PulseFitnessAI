"""Master Admin · Platform Health / Self-Healing engine.

A registry of read-only data-integrity *checks*. Each check scans for a
class of "invisible / broken data" — records that exist in the DB but do
not surface correctly, dangle, or duplicate. Findings are persisted,
AI-diagnosed in plain English, and (where safe) fixed with one click.
Every fix stores a before-snapshot so it can be undone.

Policy: DETECT + AI-diagnose everything; NOTHING auto-heals — the master
admin applies each fix explicitly. On-demand scan + a nightly sweep.

Endpoints (master-admin gated) under /api/master-admin:
  GET  /platform-health/checks
  POST /platform-health/scan
  GET  /platform-health/findings?status=open|fixed|dismissed|all
  POST /platform-health/findings/{id}/fix
  POST /platform-health/findings/{id}/undo
  POST /platform-health/findings/{id}/dismiss

Checks:
  * site_less_records   — equipment/faults in a multi-site org with no site.        (fix: backfill primary site)
  * broken_site_refs    — equipment/faults whose site_id points at a deleted site.  (fix: reassign primary site)
  * orphaned_users      — users with no org / a deleted org.                         (fix: delete, reversible)
  * orphaned_issues     — OPEN faults whose machine no longer exists in the register. (report only)
  * duplicate_records   — duplicate org names / equipment serials / user emails.      (report only)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db, EMERGENT_LLM_KEY
from utils.auth import get_current_user
from routes.master_admin import require_master_admin, log_activity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master-admin", tags=["Master Admin"])

_FINDINGS = "platform_integrity_findings"
_SCANS = "platform_integrity_scans"

CHECKS = [
    {"id": "site_less_records", "label": "Invisible records — missing site", "severity": "medium", "fixable": True,
     "description": "Equipment or faults in a multi-site org with no site — they exist but never appear in a per-site view. Fix backfills the org's primary site."},
    {"id": "broken_site_refs", "label": "Broken site references", "severity": "medium", "fixable": True,
     "description": "Equipment or faults whose site points at a site that has been deleted, so they vanish from every view. Fix reassigns them to the org's primary site."},
    {"id": "orphaned_users", "label": "Orphaned users", "severity": "high", "fixable": True,
     "description": "User accounts with no organisation, or pointing at a deleted org — they cause 'organisation not found' errors. Fix deletes them (reversible)."},
    {"id": "orphaned_issues", "label": "Faults on missing equipment", "severity": "low", "fixable": False,
     "description": "Open faults logged against a machine that is no longer in the equipment register. Review manually — the machine may have been deleted in error."},
    {"id": "duplicate_records", "label": "Duplicate data", "severity": "low", "fixable": False,
     "description": "Duplicate organisation names, duplicate equipment serials within an org, or duplicate user emails. Review and merge manually — automatic merge is unsafe."},
]
_CHECK_BY_ID = {c["id"]: c for c in CHECKS}
_SITELESS_OR = [{"site_id": {"$exists": False}}, {"site_id": None}, {"site_id": ""}]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _org_name(oid: str) -> str:
    o = await db.organizations.find_one({"id": oid}, {"_id": 0, "name": 1})
    return (o or {}).get("name") or oid


async def _primary_site_map() -> dict[str, dict]:
    """org_id → {'site_id','site_name','count'} for every org with >=1 non-archived site."""
    by_org: dict[str, list[dict]] = {}
    async for s in db.sites.find({"status": {"$ne": "archived"}},
                                 {"_id": 0, "id": 1, "name": 1, "organization_id": 1, "is_head_office": 1}):
        oid = s.get("organization_id")
        if oid:
            by_org.setdefault(oid, []).append(s)
    out = {}
    for oid, sites in by_org.items():
        primary = next((x for x in sites if x.get("is_head_office")), sites[0])
        out[oid] = {"site_id": primary.get("id"), "site_name": primary.get("name") or "primary site", "count": len(sites)}
    return out


async def _valid_site_ids() -> set[str]:
    return {s["id"] async for s in db.sites.find({}, {"_id": 0, "id": 1}) if s.get("id")}


# ── Detectors ─────────────────────────────────────────────────────────
async def _detect_site_less() -> list[dict]:
    findings = []
    primaries = await _primary_site_map()
    for oid, p in primaries.items():
        if p["count"] < 2:
            continue
        eq_n = await db.equipment.count_documents({"organization_id": oid, "$or": _SITELESS_OR})
        iss_n = await db.issues.count_documents({"organization_id": oid, "$or": _SITELESS_OR})
        if eq_n == 0 and iss_n == 0:
            continue
        name = await _org_name(oid)
        findings.append({
            "check_id": "site_less_records", "severity": "medium", "org_id": oid, "org_name": name,
            "title": f"{eq_n + iss_n} record(s) with no site in “{name}”",
            "detail": f"{eq_n} equipment and {iss_n} fault(s) have no site. This org has {p['count']} sites, so these records are hidden from every per-site view.",
            "affected_count": eq_n + iss_n, "breakdown": {"equipment": eq_n, "issues": iss_n},
            "fix_kind": "backfill_site_id", "fix_params": {"site_id": p["site_id"], "site_name": p["site_name"]},
            "fix_plan": f"Stamp all {eq_n + iss_n} site-less record(s) with the primary site “{p['site_name']}”. Reversible.",
        })
    return findings


async def _detect_broken_site_refs() -> list[dict]:
    valid = await _valid_site_ids()
    primaries = await _primary_site_map()
    per_org: dict[str, dict] = {}
    for coll in ("equipment", "issues"):
        async for d in db[coll].find(
            {"site_id": {"$nin": [None, ""], "$exists": True}}, {"_id": 0, "id": 1, "site_id": 1, "organization_id": 1}):
            sid = d.get("site_id")
            if not sid or sid in valid:
                continue
            oid = d.get("organization_id")
            slot = per_org.setdefault(oid, {"equipment": 0, "issues": 0})
            slot[coll] += 1
    findings = []
    for oid, counts in per_org.items():
        total = counts["equipment"] + counts["issues"]
        name = await _org_name(oid)
        p = primaries.get(oid)
        base = {
            "check_id": "broken_site_refs", "severity": "medium", "org_id": oid, "org_name": name,
            "title": f"{total} record(s) point at a deleted site in “{name}”",
            "detail": f"{counts['equipment']} equipment and {counts['issues']} fault(s) reference a site that no longer exists, so they don't appear anywhere.",
            "affected_count": total, "breakdown": counts,
        }
        if p:
            base.update({
                "fix_kind": "reassign_site_id", "fix_params": {"site_id": p["site_id"], "site_name": p["site_name"]},
                "fix_plan": f"Reassign all {total} record(s) to the org's primary site “{p['site_name']}”. Reversible.",
            })
        else:
            base.update({"fix_kind": None, "fix_plan": "This org has no valid site to reassign to — review manually."})
        findings.append(base)
    return findings


async def _detect_orphaned_users() -> list[dict]:
    org_ids = await _valid_site_ids.__wrapped__() if False else {  # placeholder guard (never taken)
        o["id"] async for o in db.organizations.find({}, {"_id": 0, "id": 1}) if o.get("id")}
    orphans = []
    async for u in db.users.find({}, {"_id": 0, "id": 1, "email": 1, "organization_id": 1, "is_master_admin": 1}):
        if u.get("is_master_admin"):
            continue
        oid = u.get("organization_id")
        if not oid or oid not in org_ids:
            orphans.append({"id": u.get("id"), "email": u.get("email"),
                            "reason": "no_organization_id" if not oid else "org_doc_missing"})
    if not orphans:
        return []
    return [{
        "check_id": "orphaned_users", "severity": "high", "org_id": None, "org_name": "—",
        "title": f"{len(orphans)} orphaned user account(s)",
        "detail": "These users have no organisation (or point at a deleted org). They can trigger 'organisation not found' errors when they log in.",
        "affected_count": len(orphans), "breakdown": {"users": len(orphans)},
        "sample": [o["email"] for o in orphans[:8]],
        "fix_kind": "delete_orphan_users", "fix_params": {"user_ids": [o["id"] for o in orphans]},
        "fix_plan": f"Delete {len(orphans)} orphaned user account(s). Reversible — the records are snapshotted and can be restored.",
    }]


async def _detect_orphaned_issues() -> list[dict]:
    per_org: dict[str, int] = {}
    async for iss in db.issues.find(
        {"status": {"$ne": "resolved"}, "serial_unknown": {"$ne": True},
         "serial_number": {"$nin": [None, ""], "$exists": True}},
        {"_id": 0, "serial_number": 1, "organization_id": 1}):
        oid = iss.get("organization_id"); sn = iss.get("serial_number")
        exists = await db.equipment.find_one(
            {"organization_id": oid, "serial_number": sn}, {"_id": 0, "id": 1})
        if not exists:
            per_org[oid] = per_org.get(oid, 0) + 1
    findings = []
    for oid, n in per_org.items():
        if n == 0:
            continue
        name = await _org_name(oid)
        findings.append({
            "check_id": "orphaned_issues", "severity": "low", "org_id": oid, "org_name": name,
            "title": f"{n} open fault(s) on missing equipment in “{name}”",
            "detail": f"{n} open fault(s) reference a serial number that is not in the equipment register — the machine may have been deleted in error.",
            "affected_count": n, "breakdown": {"issues": n},
            "fix_kind": None, "fix_plan": "Review manually — re-add the machine to the register or resolve the fault.",
        })
    return findings


async def _detect_duplicate_records() -> list[dict]:
    findings = []
    # Duplicate org names (case-insensitive), non-archived.
    org_pipe = [{"$match": {"status": {"$ne": "archived"}}},
                {"$group": {"_id": {"$toLower": "$name"}, "n": {"$sum": 1}, "names": {"$addToSet": "$name"}}},
                {"$match": {"n": {"$gt": 1}}}]
    dup_orgs = [d async for d in db.organizations.aggregate(org_pipe)]
    if dup_orgs:
        total = sum(d["n"] for d in dup_orgs)
        findings.append({
            "check_id": "duplicate_records", "severity": "low", "org_id": None, "org_name": "—",
            "title": f"{len(dup_orgs)} duplicated organisation name(s)",
            "detail": "Organisations sharing the same name (case-insensitive): "
                      + "; ".join(", ".join(d.get("names", [])) for d in dup_orgs[:6]),
            "affected_count": total, "breakdown": {"org_name_groups": len(dup_orgs)},
            "fix_kind": None, "fix_plan": "Review and merge via Organisations → Cleanup & operator (automatic merge is unsafe).",
        })
    # Duplicate equipment serials within an org.
    eq_pipe = [{"$match": {"serial_number": {"$nin": [None, ""]}}},
               {"$group": {"_id": {"org": "$organization_id", "sn": "$serial_number"}, "n": {"$sum": 1}}},
               {"$match": {"n": {"$gt": 1}}}]
    dup_eq = [d async for d in db.equipment.aggregate(eq_pipe)]
    if dup_eq:
        findings.append({
            "check_id": "duplicate_records", "severity": "low", "org_id": None, "org_name": "—",
            "title": f"{len(dup_eq)} duplicated equipment serial(s)",
            "detail": f"{len(dup_eq)} serial number(s) appear more than once within the same organisation — likely double-imports.",
            "affected_count": sum(d["n"] for d in dup_eq), "breakdown": {"serial_groups": len(dup_eq)},
            "fix_kind": None, "fix_plan": "Review the register and remove the duplicate rows (automatic de-dupe is unsafe).",
        })
    # Duplicate user emails.
    usr_pipe = [{"$match": {"email": {"$nin": [None, ""]}}},
                {"$group": {"_id": {"$toLower": "$email"}, "n": {"$sum": 1}}},
                {"$match": {"n": {"$gt": 1}}}]
    dup_usr = [d async for d in db.users.aggregate(usr_pipe)]
    if dup_usr:
        findings.append({
            "check_id": "duplicate_records", "severity": "medium", "org_id": None, "org_name": "—",
            "title": f"{len(dup_usr)} duplicated user email(s)",
            "detail": f"{len(dup_usr)} email address(es) are used by more than one user account — this can cause login ambiguity.",
            "affected_count": sum(d["n"] for d in dup_usr), "breakdown": {"email_groups": len(dup_usr)},
            "fix_kind": None, "fix_plan": "Review the accounts in People → Directory and remove/merge the duplicate.",
        })
    return findings


_DETECTORS = {
    "site_less_records": _detect_site_less,
    "broken_site_refs": _detect_broken_site_refs,
    "orphaned_users": _detect_orphaned_users,
    "orphaned_issues": _detect_orphaned_issues,
    "duplicate_records": _detect_duplicate_records,
}


# ── AI diagnosis ──────────────────────────────────────────────────────
async def _ai_diagnose(finding: dict) -> dict:
    fallback = {"ai_diagnosis": finding.get("detail", ""),
                "ai_recommendation": finding.get("fix_plan", ""),
                "ai_risk": "low"}
    if not EMERGENT_LLM_KEY:
        return fallback
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        system = (
            "You are a platform reliability engineer for PulseFitness.ai, a multi-tenant gym operations SaaS. "
            "You are handed ONE data-integrity finding and must explain it to a non-technical platform "
            "administrator. Return ONLY valid JSON with keys: diagnosis (2-3 plain-English sentences: what's "
            "wrong and the user-facing symptom), recommendation (1-2 sentences: what to do / what the fix does), "
            "risk (one of: low, medium, high — risk of APPLYING the proposed fix). No markdown, no code fences."
        )
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"integrity_{uuid.uuid4().hex[:8]}",
                       system_message=system).with_model("anthropic", "claude-sonnet-4-5-20250929")
        prompt = (f"Check: {finding.get('check_id')}\nOrganisation: {finding.get('org_name')}\n"
                  f"Title: {finding.get('title')}\nDetail: {finding.get('detail')}\n"
                  f"Proposed fix: {finding.get('fix_plan')}\nHas one-click fix: {bool(finding.get('fix_kind'))}\n")
        raw = await chat.send_message(UserMessage(text=prompt))
        import json as _json
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = _json.loads(cleaned)
        risk = str(parsed.get("risk", "low")).lower()
        return {"ai_diagnosis": parsed.get("diagnosis") or fallback["ai_diagnosis"],
                "ai_recommendation": parsed.get("recommendation") or fallback["ai_recommendation"],
                "ai_risk": risk if risk in ("low", "medium", "high") else "low"}
    except Exception as e:  # pragma: no cover
        logger.warning("[platform-health] AI diagnosis failed: %s", e)
        return fallback


# ── Core scan (shared by endpoint + nightly loop) ─────────────────────
async def run_scan_internal(by: str) -> dict:
    scan_id = str(uuid.uuid4())
    started = _now()
    raw: list[dict] = []
    for check_id, detector in _DETECTORS.items():
        try:
            raw.extend(await detector())
        except Exception as e:
            logger.error("[platform-health] detector %s failed: %s", check_id, e)

    diagnoses = await asyncio.gather(*[_ai_diagnose(f) for f in raw[:25]])
    for f, diag in zip(raw, diagnoses):
        f.update(diag)
    for f in raw[25:]:
        f.update({"ai_diagnosis": f.get("detail", ""), "ai_recommendation": f.get("fix_plan", ""), "ai_risk": "low"})

    await db[_FINDINGS].delete_many({"status": "open"})
    docs = [{**f, "id": str(uuid.uuid4()), "scan_id": scan_id, "status": "open",
             "created_at": started, "fixed_at": None, "fixed_by": None} for f in raw]
    if docs:
        await db[_FINDINGS].insert_many(docs)

    by_sev: dict[str, int] = {}
    for f in raw:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
    scan_doc = {"id": scan_id, "started_at": started, "finished_at": _now(), "by": by,
                "checks_run": list(_DETECTORS.keys()), "findings_count": len(docs), "by_severity": by_sev}
    await db[_SCANS].insert_one({**scan_doc})
    return {"scan": scan_doc, "summary": {"total": len(docs), "by_severity": by_sev}}


async def run_forever(hours: int = 24):
    """Nightly integrity sweep. Idempotent (refreshes OPEN findings each run)."""
    interval = max(1, hours) * 3600
    while True:
        try:
            await asyncio.sleep(interval)
            res = await run_scan_internal(by="scheduler:nightly")
            logger.info("[platform-health] nightly sweep complete: %s", res.get("summary"))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("[platform-health] nightly sweep failed: %s", e)


# ── Endpoints ─────────────────────────────────────────────────────────
@router.get("/platform-health/checks")
async def list_checks(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    return {"checks": CHECKS}


@router.post("/platform-health/scan")
async def run_scan(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    res = await run_scan_internal(by=user.get("email", "manual"))
    findings = await db[_FINDINGS].find({"status": "open"}, {"_id": 0}).to_list(500)
    return {**res, "findings": findings}


@router.get("/platform-health/findings")
async def list_findings(status: str = "open", user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    q = {} if status == "all" else {"status": status}
    findings = await db[_FINDINGS].find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    last_scan = await db[_SCANS].find({}, {"_id": 0}).sort("started_at", -1).to_list(1)
    return {"findings": findings, "last_scan": (last_scan or [None])[0]}


@router.post("/platform-health/findings/{finding_id}/fix")
async def fix_finding(finding_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    f = await db[_FINDINGS].find_one({"id": finding_id}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Finding not found")
    if f.get("status") != "open":
        raise HTTPException(409, f"Finding already {f.get('status')}")
    kind = f.get("fix_kind")
    if not kind:
        raise HTTPException(400, "This finding is review-only — no automatic fix available")

    result: dict = {}
    snapshot: dict = {"kind": kind}

    if kind in ("backfill_site_id", "reassign_site_id"):
        site_id = (f.get("fix_params") or {}).get("site_id")
        if not site_id:
            raise HTTPException(400, "Fix target site is missing")
        oid = f["org_id"]
        stamp_extra = {"integrity_backfilled_at": _now()}
        eq_snap, iss_snap = [], []
        if kind == "backfill_site_id":
            match = {"organization_id": oid, "$or": _SITELESS_OR}
            eq_snap = [{"id": d["id"], "old": None} async for d in db.equipment.find(match, {"_id": 0, "id": 1})]
            iss_snap = [{"id": d["id"], "old": None} async for d in db.issues.find(match, {"_id": 0, "id": 1})]
        else:  # reassign_site_id — capture per-row old site_id
            valid = await _valid_site_ids()
            async for d in db.equipment.find({"organization_id": oid, "site_id": {"$nin": [None, ""], "$exists": True}},
                                             {"_id": 0, "id": 1, "site_id": 1}):
                if d.get("site_id") not in valid:
                    eq_snap.append({"id": d["id"], "old": d.get("site_id")})
            async for d in db.issues.find({"organization_id": oid, "site_id": {"$nin": [None, ""], "$exists": True}},
                                          {"_id": 0, "id": 1, "site_id": 1}):
                if d.get("site_id") not in valid:
                    iss_snap.append({"id": d["id"], "old": d.get("site_id")})
        eq_ids = [x["id"] for x in eq_snap]
        iss_ids = [x["id"] for x in iss_snap]
        if eq_ids:
            await db.equipment.update_many({"id": {"$in": eq_ids}}, {"$set": {"site_id": site_id, **stamp_extra}})
        if iss_ids:
            await db.issues.update_many({"id": {"$in": iss_ids}}, {"$set": {"site_id": site_id, **stamp_extra}})
        snapshot.update({"site_id": site_id, "equipment": eq_snap, "issues": iss_snap})
        result = {"equipment": len(eq_ids), "issues": len(iss_ids)}
        await log_activity("platform_integrity_fix",
                           f"{kind} on {len(eq_ids)} equipment + {len(iss_ids)} faults in '{f.get('org_name')}'",
                           user.get("email", ""), "organization", oid)

    elif kind == "delete_orphan_users":
        user_ids = (f.get("fix_params") or {}).get("user_ids") or []
        # Re-verify each is still an orphan and not a master admin before deleting.
        org_ids = {o["id"] async for o in db.organizations.find({}, {"_id": 0, "id": 1}) if o.get("id")}
        removed_docs = []
        for uid in user_ids:
            doc = await db.users.find_one({"id": uid}, {"_id": 0})
            if not doc or doc.get("is_master_admin"):
                continue
            oid = doc.get("organization_id")
            if oid and oid in org_ids:
                continue  # no longer an orphan
            removed_docs.append(doc)
            await db.users.delete_one({"id": uid})
        snapshot.update({"users": removed_docs})
        result = {"users": len(removed_docs)}
        await log_activity("platform_integrity_fix",
                           f"Deleted {len(removed_docs)} orphaned user(s)", user.get("email", ""), "user", "")
    else:
        raise HTTPException(400, f"Unknown fix kind: {kind}")

    await db[_FINDINGS].update_one({"id": finding_id}, {"$set": {
        "status": "fixed", "fixed_at": _now(), "fixed_by": user.get("email", ""),
        "snapshot": snapshot, "fix_result": result}})
    return {"ok": True, "fixed": result}


@router.post("/platform-health/findings/{finding_id}/undo")
async def undo_finding(finding_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    f = await db[_FINDINGS].find_one({"id": finding_id}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Finding not found")
    if f.get("status") != "fixed":
        raise HTTPException(409, "Only a fixed finding can be undone")
    snap = f.get("snapshot") or {}
    kind = snap.get("kind")
    reverted: dict = {}

    if kind in ("backfill_site_id", "reassign_site_id"):
        site_id = snap.get("site_id")
        eq_n = iss_n = 0
        for row in snap.get("equipment", []):
            old = row.get("old")
            op = {"$unset": {"site_id": "", "integrity_backfilled_at": ""}} if old in (None, "") \
                else {"$set": {"site_id": old}, "$unset": {"integrity_backfilled_at": ""}}
            eq_n += (await db.equipment.update_one({"id": row["id"], "site_id": site_id}, op)).modified_count
        for row in snap.get("issues", []):
            old = row.get("old")
            op = {"$unset": {"site_id": "", "integrity_backfilled_at": ""}} if old in (None, "") \
                else {"$set": {"site_id": old}, "$unset": {"integrity_backfilled_at": ""}}
            iss_n += (await db.issues.update_one({"id": row["id"], "site_id": site_id}, op)).modified_count
        reverted = {"equipment": eq_n, "issues": iss_n}

    elif kind == "delete_orphan_users":
        docs = snap.get("users", [])
        restored = 0
        for doc in docs:
            if not await db.users.find_one({"id": doc.get("id")}, {"_id": 0, "id": 1}):
                await db.users.insert_one({**doc})
                restored += 1
        reverted = {"users": restored}
    else:
        raise HTTPException(400, "This fix cannot be undone")

    await db[_FINDINGS].update_one({"id": finding_id}, {"$set": {
        "status": "open", "fixed_at": None, "fixed_by": None,
        "undone_at": _now(), "undone_by": user.get("email", "")}})
    await log_activity("platform_integrity_undo",
                       f"Undid {kind} for '{f.get('org_name')}' ({reverted})",
                       user.get("email", ""), "organization", f.get("org_id") or "")
    return {"ok": True, "reverted": reverted}


@router.post("/platform-health/findings/{finding_id}/dismiss")
async def dismiss_finding(finding_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    res = await db[_FINDINGS].update_one(
        {"id": finding_id, "status": "open"},
        {"$set": {"status": "dismissed", "dismissed_at": _now(), "dismissed_by": user.get("email", "")}})
    if res.matched_count == 0:
        raise HTTPException(404, "Open finding not found")
    return {"ok": True}
