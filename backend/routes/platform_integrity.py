"""Master Admin · Platform Health / Self-Healing engine.

A registry of read-only data-integrity *checks*. Each check scans for a
class of "invisible data" anomaly — records that exist in the DB but do
not surface correctly in the product (the class of the "logged a fault
but it shows no faults" bug). Findings are persisted, AI-diagnosed in
plain English, and can be fixed with a single click. Every fix stores a
before-snapshot so it can be undone.

Design (Phase 1):
  * DETECT + AI-diagnose everything; NOTHING auto-heals — the master
    admin applies each fix explicitly.
  * On-demand scan (a nightly sweep is Phase 2).
  * Reversible: `POST …/findings/{id}/undo` restores the snapshot.

Endpoints (master-admin gated), all under /api/master-admin:
  GET  /platform-health/checks                  → registry metadata
  POST /platform-health/scan                    → run all checks, persist findings
  GET  /platform-health/findings?status=open    → list findings
  POST /platform-health/findings/{id}/fix       → apply fix (+ snapshot)
  POST /platform-health/findings/{id}/dismiss   → dismiss a finding
  POST /platform-health/findings/{id}/undo      → restore a fixed finding

Phase 1 checks:
  * site_less_records — equipment / issues in a MULTI-SITE org that carry
    no site_id, so they never appear in any per-site view.
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

# ── Check registry (metadata surfaced to the UI) ──────────────────────
CHECKS = [
    {
        "id": "site_less_records",
        "label": "Invisible records — missing site",
        "description": (
            "Equipment or faults in a multi-site organisation that carry no "
            "site. They exist in the database but won't appear in any per-site "
            "view — the class of the 'I logged a fault but the screen shows no "
            "faults' issue. Fix backfills them to the org's primary site."
        ),
        "severity": "medium",
        "fixable": True,
    },
]
_CHECK_BY_ID = {c["id"]: c for c in CHECKS}

_SITELESS_OR = [{"site_id": {"$exists": False}}, {"site_id": None}, {"site_id": ""}]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _multi_site_orgs() -> list[dict]:
    """Orgs with 2+ non-archived sites, with their resolved primary site."""
    by_org: dict[str, list[dict]] = {}
    async for s in db.sites.find(
        {"status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "organization_id": 1, "is_head_office": 1},
    ):
        oid = s.get("organization_id")
        if oid:
            by_org.setdefault(oid, []).append(s)
    out = []
    for oid, sites in by_org.items():
        if len(sites) < 2:
            continue
        primary = next((x for x in sites if x.get("is_head_office")), sites[0])
        org = await db.organizations.find_one({"id": oid}, {"_id": 0, "id": 1, "name": 1})
        out.append({
            "org_id": oid,
            "org_name": (org or {}).get("name") or oid,
            "site_count": len(sites),
            "primary_site_id": primary.get("id"),
            "primary_site_name": primary.get("name") or "primary site",
        })
    return out


async def _detect_site_less() -> list[dict]:
    """One finding per multi-site org that has site-less equipment/issues."""
    findings = []
    for org in await _multi_site_orgs():
        oid = org["org_id"]
        eq_q = {"organization_id": oid, "$or": _SITELESS_OR}
        iss_q = {"organization_id": oid, "$or": _SITELESS_OR}
        eq_n = await db.equipment.count_documents(eq_q)
        iss_n = await db.issues.count_documents(iss_q)
        if eq_n == 0 and iss_n == 0:
            continue
        findings.append({
            "check_id": "site_less_records",
            "severity": "medium",
            "org_id": oid,
            "org_name": org["org_name"],
            "title": f"{eq_n + iss_n} record(s) with no site in “{org['org_name']}”",
            "detail": (
                f"{eq_n} equipment item(s) and {iss_n} fault(s) have no site set. "
                f"This org has {org['site_count']} sites, so these records are hidden "
                f"from every per-site view."
            ),
            "affected_count": eq_n + iss_n,
            "breakdown": {"equipment": eq_n, "issues": iss_n},
            "fix_kind": "backfill_site_id",
            "fix_params": {
                "site_id": org["primary_site_id"],
                "site_name": org["primary_site_name"],
            },
            "fix_plan": (
                f"Stamp all {eq_n + iss_n} site-less record(s) with the primary site "
                f"“{org['primary_site_name']}”, so they appear in that site's views. Reversible."
            ),
        })
    return findings


_DETECTORS = {"site_less_records": _detect_site_less}


# ── AI diagnosis (Claude Sonnet 4.5 via Emergent key; safe fallback) ──
async def _ai_diagnose(finding: dict) -> dict:
    fallback = {
        "ai_diagnosis": finding.get("detail", ""),
        "ai_recommendation": finding.get("fix_plan", ""),
        "ai_risk": "low",
    }
    if not EMERGENT_LLM_KEY:
        return fallback
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        system = (
            "You are a platform reliability engineer for PulseFitness.ai, a multi-tenant gym "
            "operations SaaS. You are handed ONE data-integrity finding and must explain it to a "
            "non-technical platform administrator. Return ONLY valid JSON with keys: "
            "diagnosis (2-3 plain-English sentences: what's wrong and the user-facing symptom), "
            "recommendation (1-2 sentences: what the one-click fix will do), "
            "risk (one of: low, medium, high — the risk of APPLYING the proposed fix). "
            "No markdown, no code fences."
        )
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"integrity_{uuid.uuid4().hex[:8]}",
            system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        prompt = (
            f"Check: {finding.get('check_id')}\n"
            f"Organisation: {finding.get('org_name')}\n"
            f"Title: {finding.get('title')}\n"
            f"Detail: {finding.get('detail')}\n"
            f"Proposed fix: {finding.get('fix_plan')}\n"
        )
        raw = await chat.send_message(UserMessage(text=prompt))
        import json as _json
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = _json.loads(cleaned)
        risk = str(parsed.get("risk", "low")).lower()
        return {
            "ai_diagnosis": parsed.get("diagnosis") or fallback["ai_diagnosis"],
            "ai_recommendation": parsed.get("recommendation") or fallback["ai_recommendation"],
            "ai_risk": risk if risk in ("low", "medium", "high") else "low",
        }
    except Exception as e:  # pragma: no cover — never let AI block a scan
        logger.warning("[platform-health] AI diagnosis failed: %s", e)
        return fallback


# ── Endpoints ─────────────────────────────────────────────────────────
@router.get("/platform-health/checks")
async def list_checks(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    return {"checks": CHECKS}


@router.post("/platform-health/scan")
async def run_scan(user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    scan_id = str(uuid.uuid4())
    started = _now()

    raw_findings: list[dict] = []
    for check_id, detector in _DETECTORS.items():
        try:
            raw_findings.extend(await detector())
        except Exception as e:
            logger.error("[platform-health] detector %s failed: %s", check_id, e)

    # AI-diagnose all findings in parallel (bounded, with fallback).
    diagnoses = await asyncio.gather(*[_ai_diagnose(f) for f in raw_findings[:25]])
    for f, diag in zip(raw_findings, diagnoses):
        f.update(diag)
    for f in raw_findings[25:]:
        f["ai_diagnosis"] = f.get("detail", "")
        f["ai_recommendation"] = f.get("fix_plan", "")
        f["ai_risk"] = "low"

    # Refresh OPEN findings (keep fixed/dismissed history intact).
    await db[_FINDINGS].delete_many({"status": "open"})
    docs = []
    for f in raw_findings:
        docs.append({
            **f,
            "id": str(uuid.uuid4()),
            "scan_id": scan_id,
            "status": "open",
            "created_at": started,
            "fixed_at": None,
            "fixed_by": None,
        })
    if docs:
        await db[_FINDINGS].insert_many(docs)

    by_sev: dict[str, int] = {}
    for f in raw_findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1

    scan_doc = {
        "id": scan_id, "started_at": started, "finished_at": _now(),
        "by": user.get("email", ""), "checks_run": list(_DETECTORS.keys()),
        "findings_count": len(docs), "by_severity": by_sev,
    }
    await db[_SCANS].insert_one({**scan_doc})

    findings = await db[_FINDINGS].find({"status": "open"}, {"_id": 0}).to_list(500)
    return {"scan": scan_doc, "findings": findings, "summary": {"total": len(docs), "by_severity": by_sev}}


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

    if f.get("fix_kind") != "backfill_site_id":
        raise HTTPException(400, "No automatic fix available for this finding")

    site_id = (f.get("fix_params") or {}).get("site_id")
    if not site_id:
        raise HTTPException(400, "Fix target site is missing")
    oid = f["org_id"]

    # Capture the exact ids we're about to change → snapshot for undo.
    eq_ids = [d["id"] async for d in db.equipment.find(
        {"organization_id": oid, "$or": _SITELESS_OR}, {"_id": 0, "id": 1})]
    iss_ids = [d["id"] async for d in db.issues.find(
        {"organization_id": oid, "$or": _SITELESS_OR}, {"_id": 0, "id": 1})]

    stamp = {"site_id": site_id, "integrity_backfilled_at": _now()}
    eq_res = await db.equipment.update_many({"id": {"$in": eq_ids}}, {"$set": stamp}) if eq_ids else None
    iss_res = await db.issues.update_many({"id": {"$in": iss_ids}}, {"$set": stamp}) if iss_ids else None

    snapshot = {"kind": "backfill_site_id", "site_id": site_id,
                "equipment_ids": eq_ids, "issue_ids": iss_ids}
    await db[_FINDINGS].update_one({"id": finding_id}, {"$set": {
        "status": "fixed", "fixed_at": _now(), "fixed_by": user.get("email", ""),
        "snapshot": snapshot,
        "fix_result": {"equipment": len(eq_ids), "issues": len(iss_ids)},
    }})
    await log_activity(
        "platform_integrity_fix",
        f"Backfilled site '{(f.get('fix_params') or {}).get('site_name')}' onto "
        f"{len(eq_ids)} equipment + {len(iss_ids)} faults in '{f.get('org_name')}'",
        user.get("email", ""), "organization", oid,
    )
    return {"ok": True, "fixed": {"equipment": len(eq_ids), "issues": len(iss_ids)}}


@router.post("/platform-health/findings/{finding_id}/undo")
async def undo_finding(finding_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    f = await db[_FINDINGS].find_one({"id": finding_id}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Finding not found")
    if f.get("status") != "fixed":
        raise HTTPException(409, "Only a fixed finding can be undone")
    snap = f.get("snapshot") or {}
    if snap.get("kind") != "backfill_site_id":
        raise HTTPException(400, "This fix cannot be undone")

    # Restore site-less state ONLY on rows still stamped with our site_id
    # (so a later legitimate re-assignment isn't clobbered).
    site_id = snap.get("site_id")
    unset = {"$unset": {"site_id": "", "integrity_backfilled_at": ""}}
    eq_ids = snap.get("equipment_ids") or []
    iss_ids = snap.get("issue_ids") or []
    eq_n = (await db.equipment.update_many(
        {"id": {"$in": eq_ids}, "site_id": site_id}, unset)).modified_count if eq_ids else 0
    iss_n = (await db.issues.update_many(
        {"id": {"$in": iss_ids}, "site_id": site_id}, unset)).modified_count if iss_ids else 0

    await db[_FINDINGS].update_one({"id": finding_id}, {"$set": {
        "status": "open", "fixed_at": None, "fixed_by": None,
        "undone_at": _now(), "undone_by": user.get("email", ""),
    }})
    await log_activity(
        "platform_integrity_undo",
        f"Undid site backfill for '{f.get('org_name')}' ({eq_n} equipment + {iss_n} faults)",
        user.get("email", ""), "organization", f.get("org_id"),
    )
    return {"ok": True, "reverted": {"equipment": eq_n, "issues": iss_n}}


@router.post("/platform-health/findings/{finding_id}/dismiss")
async def dismiss_finding(finding_id: str, user: dict = Depends(get_current_user)) -> dict:
    require_master_admin(user)
    res = await db[_FINDINGS].update_one(
        {"id": finding_id, "status": "open"},
        {"$set": {"status": "dismissed", "dismissed_at": _now(), "dismissed_by": user.get("email", "")}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Open finding not found")
    return {"ok": True}
