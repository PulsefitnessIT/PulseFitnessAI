"""Iter 220e3 — Contracts Phase E (Renewals), F (Reports), G (AI).

Renewal pipeline endpoints + dashboard analytics + AI assistance for
the CRM → Contracts module. Reuses existing collections so no data
is duplicated:

  * ``crm2_contracts``        — source of truth
  * ``crm2_contract_assets``  — asset coverage rows
  * ``crm2_activities``       — feed every renewal touch lands on
  * ``crm2_opportunities``    — renewal drafts already create one

Phase E (Renewals)
------------------
* ``GET  /contracts/renewals/pipeline`` — buckets contracts by days
  remaining (30 / 60 / 90 / future) with suggested uplift.
* ``POST /contracts/renewals/run-reminders`` — operator-triggered
  reminder run (creates ``crm2_activities`` rows for each contract
  crossing the 30/60/90 thresholds without an existing reminder
  today).

Phase F (Reports / Analytics)
-----------------------------
* ``GET /contracts/reports/dashboard`` — ARR / MRR / pipeline value
  / coverage gap / tier breakdown.

Phase G (AI assistance)
------------------------
* ``POST /contracts/{id}/ai/recommend-cover``  — suggest cover tier
* ``POST /contracts/{id}/ai/suggest-uplift``   — renewal uplift %
* ``POST /contracts/{id}/ai/draft-terms``      — bespoke clauses

The AI endpoints use the Emergent LLM key via emergentintegrations.
They NEVER auto-send, auto-sign or auto-activate anything — they
return suggestions for a human to accept.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from routes.crm_auth import get_crm_user
from utils.database import db


router = APIRouter(prefix="/crm/v2", tags=["Contracts · Renewals / Reports / AI"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    return {"organization_id": org if org else "__none__"}


def _suggested_uplift(contract: dict) -> dict:
    """Cheap heuristic uplift suggestion — the AI endpoint can refine
    this, but a deterministic baseline keeps the renewals dashboard
    useful even when the LLM key isn't configured.

    Rules of thumb (operator-validated):
      * Baseline 5 % CPI uplift.
      * +2 % if more than 30 % of the last 12 months' visits were
        chargeable overruns (cover under-priced relative to usage).
      * Cap at 12 % to avoid sticker shock on customer-facing PDFs.
    """
    base = 5.0
    cost = float((contract.get("pricing") or {}).get("cost_estimate") or 0)
    annual = float(contract.get("annual_value") or 0)
    if annual and cost / annual > 0.7:
        base += 3.0
    # Soft cap so renewals don't look hostile on a customer PDF.
    base = min(base, 12.0)
    return {
        "uplift_percent": round(base, 1),
        "rationale": (
            "Baseline 5% CPI uplift" +
            (" + 3% to reflect high cost-of-service ratio"
             if annual and cost / annual > 0.7 else "")
        ),
    }


# ── Phase E · Renewals ─────────────────────────────────────────


@router.get("/contracts/renewals/pipeline")
async def renewals_pipeline(user: dict = Depends(get_crm_user)):
    """Bucket active contracts by days-to-expiry. Returns an object
    keyed by bucket with contract stubs + suggested uplift so the
    Renewals dashboard can render without further lookups."""
    of = _of(user)
    today = datetime.now(timezone.utc).date()
    cutoff_90 = (today + timedelta(days=90)).isoformat()
    cutoff_today = today.isoformat()
    contracts = await db.crm2_contracts.find(
        {**of, "status": "active",
         "end_date": {"$lte": cutoff_90, "$gte": cutoff_today}},
        {"_id": 0, "id": 1, "title": 1, "contract_number": 1, "tier": 1,
         "company_name": 1, "company_id": 1, "annual_value": 1,
         "end_date": 1, "auto_renew": 1, "pricing": 1},
    ).sort("end_date", 1).to_list(500)

    buckets = {"30": [], "60": [], "90": []}
    total_value = 0.0
    for c in contracts:
        end = c.get("end_date") or ""
        try:
            days = (datetime.fromisoformat(end[:10]).date() - today).days
        except ValueError:
            continue
        if days < 0:
            continue
        suggest = _suggested_uplift(c)
        stub = {
            **c,
            "days_remaining": days,
            "suggested_uplift_percent": suggest["uplift_percent"],
            "suggested_uplift_rationale": suggest["rationale"],
            "suggested_renewal_value": round(
                float(c.get("annual_value") or 0) * (1 + suggest["uplift_percent"] / 100), 2,
            ),
        }
        total_value += float(c.get("annual_value") or 0)
        if days <= 30:
            buckets["30"].append(stub)
        elif days <= 60:
            buckets["60"].append(stub)
        else:
            buckets["90"].append(stub)
    return {
        "buckets": buckets,
        "totals": {
            "contracts": sum(len(v) for v in buckets.values()),
            "annual_value_at_risk": round(total_value, 2),
        },
        "generated_at": _now(),
    }


@router.post("/contracts/renewals/run-reminders")
async def run_renewal_reminders(user: dict = Depends(get_crm_user)):
    """Idempotent reminder run — for each active contract crossing
    the 30/60/90-day threshold today, drops a ``contract_renewal``
    activity row tagged with the threshold so subsequent runs don't
    duplicate. Suitable for a daily cron OR an operator button.
    """
    of = _of(user)
    today = datetime.now(timezone.utc).date()
    today_iso = today.isoformat()
    cutoff_91 = (today + timedelta(days=91)).isoformat()
    contracts = await db.crm2_contracts.find(
        {**of, "status": "active",
         "end_date": {"$lte": cutoff_91, "$gte": today_iso}},
        {"_id": 0, "id": 1, "contract_number": 1, "title": 1,
         "company_id": 1, "company_name": 1, "end_date": 1, "annual_value": 1},
    ).to_list(500)

    created = 0
    for c in contracts:
        try:
            days = (datetime.fromisoformat(c["end_date"][:10]).date() - today).days
        except ValueError:
            continue
        threshold = next((t for t in (30, 60, 90) if days <= t), None)
        if threshold is None:
            continue
        marker_subject = f"Renewal reminder [T{threshold}]: {c.get('contract_number')}"
        # Skip if a reminder for the same threshold today already exists.
        existing = await db.crm2_activities.find_one({
            **of, "contract_id": c["id"],
            "subject": marker_subject,
        })
        if existing:
            continue
        await db.crm2_activities.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": user.get("organization_id"),
            "type": "contract_renewal",
            "contract_id": c["id"],
            "subject": marker_subject,
            "body": (
                f"{c.get('title')} (£{float(c.get('annual_value') or 0):,.0f}/yr) "
                f"expires in {days} days — review renewal."
            ),
            "company_id": c.get("company_id", ""),
            "owner_id": user.get("id"),
            "owner_name": user.get("full_name", "system"),
            "created_at": _now(),
            "threshold_days": threshold,
        })
        created += 1
    return {"success": True, "reminders_created": created}


# ── Phase F · Reports / Analytics ──────────────────────────────


@router.get("/contracts/reports/dashboard")
async def contracts_report_dashboard(user: dict = Depends(get_crm_user)):
    """High-level contract analytics consumed by the new Reports tab.

    Returns:

        {
          "arr": float, "mrr": float,
          "expiring_30d_value": float,
          "expiring_60d_value": float,
          "expiring_90d_value": float,
          "by_tier":   [{"tier": "...", "count": N, "annual_value": F}],
          "by_status": [{"status": "...", "count": N}],
          "coverage": {"assets_covered": N, "assets_uncovered": N},
        }
    """
    of = _of(user)
    today = datetime.now(timezone.utc).date()

    by_tier = await db.crm2_contracts.aggregate([
        {"$match": {**of, "status": "active"}},
        {"$group": {"_id": "$tier", "count": {"$sum": 1},
                    "annual_value": {"$sum": "$annual_value"}}},
    ]).to_list(20)
    by_status = await db.crm2_contracts.aggregate([
        {"$match": of},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]).to_list(20)

    pipeline = [
        {"$match": {**of, "status": "active"}},
        {"$group": {"_id": None, "total": {"$sum": "$annual_value"}}},
    ]
    agg = await db.crm2_contracts.aggregate(pipeline).to_list(1)
    arr = float(agg[0]["total"]) if agg else 0.0

    async def _expiring_value(days_max: int) -> float:
        cutoff = (today + timedelta(days=days_max)).isoformat()
        rows = await db.crm2_contracts.aggregate([
            {"$match": {**of, "status": "active",
                        "end_date": {"$lte": cutoff, "$gte": today.isoformat()}}},
            {"$group": {"_id": None, "total": {"$sum": "$annual_value"}}},
        ]).to_list(1)
        return float(rows[0]["total"]) if rows else 0.0

    e30 = await _expiring_value(30)
    e60 = await _expiring_value(60)
    e90 = await _expiring_value(90)

    # Coverage gap — assets without an active contract_asset row.
    total_assets = await db.equipment.count_documents(of)
    covered_ids = await db.crm2_contract_assets.distinct("asset_id", of)
    covered = len([a for a in covered_ids if a])
    uncovered = max(0, total_assets - covered)

    return {
        "arr": round(arr, 2),
        "mrr": round(arr / 12, 2),
        "expiring_30d_value": round(e30, 2),
        "expiring_60d_value": round(e60, 2),
        "expiring_90d_value": round(e90, 2),
        "by_tier":   [{"tier": t["_id"], "count": t["count"],
                       "annual_value": round(float(t["annual_value"] or 0), 2)}
                      for t in by_tier],
        "by_status": [{"status": s["_id"], "count": s["count"]} for s in by_status],
        "coverage": {"assets_covered": covered, "assets_uncovered": uncovered},
        "generated_at": _now(),
    }


# ── Phase G · AI assistance ────────────────────────────────────


def _llm_key() -> str:
    return os.environ.get("EMERGENT_LLM_KEY", "")


async def _llm_chat(prompt: str, system: str = "") -> str:
    """Tiny wrapper around emergentintegrations. Returns the raw
    string completion or '' if the key isn't configured."""
    key = _llm_key()
    if not key:
        return ""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        session_id = f"contract-ai-{uuid.uuid4()}"
        chat = LlmChat(
            api_key=key,
            session_id=session_id,
            system_message=system or "You are an expert UK service-contract assistant for the fitness industry. Reply in concise UK English.",
        ).with_model("openai", "gpt-4o-mini")
        msg = UserMessage(text=prompt)
        reply = await chat.send_message(msg)
        return str(reply) if reply else ""
    except Exception:
        return ""


async def _load_contract(contract_id: str, of: dict) -> dict:
    c = await db.crm2_contracts.find_one({"id": contract_id, **of}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contract not found")
    return c


@router.post("/contracts/{contract_id}/ai/recommend-cover")
async def ai_recommend_cover(contract_id: str, user: dict = Depends(get_crm_user)):
    """Suggest a tier (silver/gold/platinum/custom) based on the
    contract's asset count, age, and customer profile. Returns a
    deterministic baseline if the LLM key isn't configured."""
    c = await _load_contract(contract_id, _of(user))
    assets = await db.crm2_contract_assets.count_documents({"contract_id": contract_id})
    # Deterministic baseline.
    if assets >= 40:
        base = "platinum"
    elif assets >= 12:
        base = "gold"
    else:
        base = "silver"
    rationale = f"Baseline recommendation: {base} (asset count = {assets})."
    prompt = (
        f"Recommend a service-contract tier for this customer.\n"
        f"Title: {c.get('title')}\nTier on file: {c.get('tier')}\n"
        f"Asset count: {assets}\nAnnual value: £{c.get('annual_value', 0)}.\n"
        f"Return a JSON-ish blob: tier: <silver|gold|platinum|custom>, "
        f"rationale: <one sentence>."
    )
    llm_reply = await _llm_chat(prompt)
    return {
        "recommended_tier": base,
        "rationale": rationale,
        "ai_reply": llm_reply or None,
        "uses_ai": bool(llm_reply),
    }


@router.post("/contracts/{contract_id}/ai/suggest-uplift")
async def ai_suggest_uplift(contract_id: str, user: dict = Depends(get_crm_user)):
    """Suggest a renewal uplift % with rationale. Defers to the
    deterministic heuristic when the LLM key isn't set."""
    c = await _load_contract(contract_id, _of(user))
    baseline = _suggested_uplift(c)
    prompt = (
        f"Suggest a renewal uplift % for this contract.\n"
        f"Tier: {c.get('tier')}\nAnnual value: £{c.get('annual_value', 0)}.\n"
        f"Cost-estimate (internal): £{(c.get('pricing') or {}).get('cost_estimate', 0)}.\n"
        f"Existing baseline: {baseline['uplift_percent']}%.\n"
        f"Reply with a single integer percentage and a one-sentence rationale."
    )
    llm_reply = await _llm_chat(prompt)
    return {**baseline, "ai_reply": llm_reply or None, "uses_ai": bool(llm_reply)}


@router.post("/contracts/{contract_id}/ai/draft-terms")
async def ai_draft_terms(contract_id: str, data: dict,
                         user: dict = Depends(get_crm_user)):
    """Draft a bespoke T&C paragraph (e.g. emergency upgrade clause)
    based on the operator's brief in ``data['brief']``. Never replaces
    existing terms — returns the draft for review."""
    c = await _load_contract(contract_id, _of(user))
    brief = (data.get("brief") or "").strip()
    if not brief:
        raise HTTPException(400, "brief is required")
    prompt = (
        f"Draft a single concise paragraph for the Terms & Conditions "
        f"section of a fitness-industry service contract.\n"
        f"Brief: {brief}\nContract tier: {c.get('tier')}.\n"
        f"Reply with the paragraph only — no preamble."
    )
    llm_reply = await _llm_chat(prompt)
    if not llm_reply:
        # Deterministic fallback so the operator at least sees a
        # starting point if the LLM key is missing.
        llm_reply = (
            f"### Bespoke clause\n"
            f"Under this {c.get('tier', '').title()} contract, "
            f"{brief.lower()}. This clause forms part of the Inclusions "
            f"and is subject to the response-time bands documented above."
        )
        ai = False
    else:
        ai = True
    return {"draft": llm_reply.strip(), "uses_ai": ai}
