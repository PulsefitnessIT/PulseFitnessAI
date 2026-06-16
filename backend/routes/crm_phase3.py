"""CRM · Phase 3 polish — Iter 216h226.

Three companion endpoints that complete the "operational brain" loop:

  1. POST /crm/opportunities/{id}/ai/next-action
     Reads the deal + recent activities + stakeholder map, returns
     an AI-generated next-best-action with reasoning + a confidence
     score. Uses the existing Emergent LLM key path in
     `routes.crm_ai.call_llm`.

  2. POST /crm/companies/{id}/enrich-from-website
     Fetches the company's website, parses OG/meta tags + favicon,
     and updates name / description / logo_url / website. No external
     API — pure HTML scraping (BeautifulSoup4 already in requirements
     via inbound email parsing).

  3. GET  /crm/companies/{id}/timeline
     Cross-module activity feed — folds CRM activities + Operations
     issues (engineer visits) + Invoices into one chronological view.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urljoin

from fastapi import APIRouter, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm", tags=["CRM Phase 3"])


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────
# 1. AI Next-Best-Action
# ──────────────────────────────────────────────────────────────────


@router.post("/opportunities/{op_id}/ai/next-action")
async def ai_next_action(op_id: str, user=Depends(get_crm_user)) -> dict:
    """Suggest the next-best-action for this opportunity.

    Builds a compact context (stage, age, value, owner, last activity,
    stakeholders) and asks the LLM for: action verb, target contact,
    reasoning, confidence (high/med/low), and a draft email body if
    the action involves sending one.
    """
    opp = await db.crm2_opportunities.find_one({"id": op_id, **_of(user)}, {"_id": 0})
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    # Recent activities (last 10).
    activities = await db.crm2_activities.find(
        {"opportunity_id": op_id, **_of(user)}, {"_id": 0, "type": 1, "subject": 1, "body": 1, "created_at": 1},
    ).sort("created_at", -1).limit(10).to_list(10)

    # Stakeholder map.
    stakeholders = await db.crm_stakeholder_map.find(
        {"opportunity_id": op_id, **_of(user)}, {"_id": 0, "contact_id": 1, "influence_types": 1, "support_level": 1},
    ).to_list(20)

    # Compose a short prompt.
    days_in_stage = ""
    try:
        if opp.get("stage_changed_at"):
            delta = (datetime.now(timezone.utc) - datetime.fromisoformat(opp["stage_changed_at"].replace("Z", "+00:00"))).days
            days_in_stage = f" (in stage {delta} days)"
    except Exception:
        pass

    activity_lines = "\n".join(
        f"  - {a.get('created_at','')[:10]} {a.get('type','note')}: {a.get('subject','')}"
        for a in activities[:5]
    ) or "  (no recent activity)"

    stakeholder_lines = "\n".join(
        f"  - {s.get('contact_id','?')}: {', '.join(s.get('influence_types', []) or ['(none)'])} (support: {s.get('support_level','neutral')})"
        for s in stakeholders[:6]
    ) or "  (no stakeholders mapped)"

    prompt = f"""Suggest the single best next action for this CRM opportunity.

OPPORTUNITY:
  Title: {opp.get('title','-')}
  Stage: {opp.get('stage','-')}{days_in_stage}
  Value: £{opp.get('value', 0)}
  Owner: {opp.get('owner_name','-')}
  Created: {opp.get('created_at','-')[:10]}

RECENT ACTIVITY:
{activity_lines}

STAKEHOLDERS (Miller Heiman):
{stakeholder_lines}

Return JSON with this exact shape:
{{
  "action": "Call|Email|Meeting|Demo|Send Proposal|Send Quote|Schedule Follow-up|Find Champion|Address Blocker|Escalate to Manager",
  "target_role": "Economic Buyer|Champion|Coach|Technical Buyer|User Buyer|Blocker|Decision Maker|(any role from Miller Heiman)",
  "reasoning": "1-3 sentences why this is the right move now",
  "urgency": "high|medium|low",
  "confidence": "high|medium|low",
  "suggested_subject": "if action involves email/message, the subject line; else null",
  "suggested_body": "if action involves email/message, ~3-sentence draft body; else null"
}}

Be specific, fitness-industry-aware, and concise. Do NOT wrap in markdown fences."""

    try:
        from routes.crm_ai import call_llm, _parse_llm_json
        raw = await call_llm(prompt, max_tokens=800)
        parsed = _parse_llm_json(raw, {
            "action": "Call",
            "target_role": "Decision Maker",
            "reasoning": "AI response could not be parsed — defaulting to manual call.",
            "urgency": "medium",
            "confidence": "low",
            "suggested_subject": None,
            "suggested_body": None,
        })
    except Exception as e:
        logger.exception("ai_next_action failed")
        parsed = {
            "action": "Call",
            "target_role": "Decision Maker",
            "reasoning": f"AI unavailable ({type(e).__name__}). Default: contact the deal owner.",
            "urgency": "medium",
            "confidence": "low",
            "suggested_subject": None,
            "suggested_body": None,
        }

    # Persist as an activity so the suggestion shows up in the timeline.
    try:
        from routes.crm_v2 import _id as crm_id  # reuse uuid helper
        await db.crm2_activities.insert_one({
            "id": crm_id(),
            "organization_id": user.get("organization_id"),
            "type": "ai_suggestion",
            "subject": f"AI · Next best action: {parsed.get('action','?')}",
            "body": parsed.get("reasoning", ""),
            "opportunity_id": op_id,
            "company_id": opp.get("company_id"),
            "contact_id": None,
            "owner_id": user.get("id"),
            "owner_name": user.get("full_name", ""),
            "created_at": _now(),
            "updated_at": _now(),
            "meta": parsed,
        })
    except Exception:
        pass

    return parsed


# ──────────────────────────────────────────────────────────────────
# 2. Website-first enrichment
# ──────────────────────────────────────────────────────────────────


def _normalise_url(url: str) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _extract_meta(html: str, base_url: str) -> dict:
    """Pure-regex meta extractor (avoids the bs4 dependency for a
    handful of tags). Captures og:* + name=description + favicon
    link tag."""
    out: dict[str, Any] = {}

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        return (m.group(1).strip() if m else None)

    # OG tags.
    out["og_title"] = grab(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']')
    out["og_description"] = grab(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']')
    out["og_image"] = grab(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']')
    out["meta_description"] = grab(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']')
    out["title"] = grab(r'<title[^>]*>([^<]+)</title>')

    # Favicon (first match).
    fav = re.search(
        r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if fav:
        out["favicon"] = urljoin(base_url, fav.group(1))

    # Resolve og_image relative URL.
    if out.get("og_image"):
        out["og_image"] = urljoin(base_url, out["og_image"])

    return {k: v for k, v in out.items() if v}


@router.post("/companies/{company_id}/enrich-from-website")
async def enrich_from_website(company_id: str, user=Depends(get_crm_user)) -> dict:
    """Pull company metadata from its website (og:* + meta + favicon)
    and merge into the CRM company record. Only updates fields that
    are currently empty — never overwrites manually-curated data.
    """
    company = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0})
    if not company:
        raise HTTPException(404, "Company not found")
    base = _normalise_url(company.get("website") or "")
    if not base:
        raise HTTPException(422, "Company has no website to enrich from")

    try:
        import httpx
        with httpx.Client(follow_redirects=True, timeout=10.0, headers={"User-Agent": "PulseFitnessAI/1.0 (+https://www.pulsefitness.ai)"}) as client:
            resp = client.get(base)
            resp.raise_for_status()
            html = resp.text[:200_000]
    except Exception as e:
        raise HTTPException(502, f"Could not reach {base}: {type(e).__name__}")

    meta = _extract_meta(html, base)

    # Merge — only fill blanks.
    fill: dict[str, Any] = {}
    if meta.get("og_description") and not company.get("description"):
        fill["description"] = meta["og_description"]
    elif meta.get("meta_description") and not company.get("description"):
        fill["description"] = meta["meta_description"]
    if meta.get("og_image") and not company.get("logo_url"):
        fill["logo_url"] = meta["og_image"]
    elif meta.get("favicon") and not company.get("logo_url"):
        fill["logo_url"] = meta["favicon"]
    if meta.get("og_title") and not company.get("name_long"):
        fill["name_long"] = meta["og_title"]

    if fill:
        fill["enrichment_source"] = "website"
        fill["enriched_at"] = _now()
        fill["updated_at"] = _now()
        await db.crm2_companies.update_one(
            {"id": company_id, **_of(user)},
            {"$set": fill},
        )

    return {
        "enriched": list(fill.keys()),
        "values": fill,
        "source": base,
        "raw_meta": meta,
    }


# ──────────────────────────────────────────────────────────────────
# 3. Cross-module unified company timeline
# ──────────────────────────────────────────────────────────────────


@router.get("/companies/{company_id}/timeline")
async def company_timeline(
    company_id: str,
    limit: int = 50,
    user=Depends(get_crm_user),
) -> dict:
    """Unified chronological feed: CRM activities + Operations cases
    (engineer visits) + invoices. Each row carries a `module` tag so
    the FE can colour-code or filter.
    """
    org_id = user.get("organization_id")
    company = await db.crm2_companies.find_one({"id": company_id, **_of(user)}, {"_id": 0, "id": 1, "name": 1})
    if not company:
        raise HTTPException(404, "Company not found")

    rows: list[dict] = []

    # CRM activities.
    activities = await db.crm2_activities.find(
        {"company_id": company_id, **_of(user)},
        {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    for a in activities:
        rows.append({
            "module": "crm",
            "type": a.get("type", "note"),
            "title": a.get("subject") or a.get("body", "")[:80],
            "body": a.get("body", ""),
            "owner": a.get("owner_name", ""),
            "created_at": a.get("created_at"),
            "ref_id": a.get("id"),
        })

    # CRM cases (already linked).
    cases = await db.crm2_cases.find(
        {"company_id": company_id, **_of(user)},
        {"_id": 0, "id": 1, "title": 1, "status": 1, "case_number": 1, "created_at": 1, "owner_name": 1, "priority": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    for c in cases:
        rows.append({
            "module": "service",
            "type": "case",
            "title": f"{c.get('case_number','')} · {c.get('title','')}",
            "body": f"Status: {c.get('status','-')} · Priority: {c.get('priority','-')}",
            "owner": c.get("owner_name", ""),
            "created_at": c.get("created_at"),
            "ref_id": c.get("id"),
        })

    # Operations issues (engineer visits + faults) — join via company name.
    # `issues.company_name` or `issues.company_id` may be set; we accept either.
    issue_query = {
        "organization_id": org_id,
        "$or": [
            {"company_id": company_id},
            {"company_name": company.get("name")},
        ],
    }
    issues = await db.issues.find(
        issue_query,
        {"_id": 0, "id": 1, "title": 1, "status": 1, "equipment_name": 1, "created_at": 1, "engineer_name": 1, "completed_at": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    for it in issues:
        rows.append({
            "module": "operations",
            "type": "engineer_visit" if it.get("engineer_name") else "fault",
            "title": (it.get("title") or "Fault") + (f" · {it['equipment_name']}" if it.get("equipment_name") else ""),
            "body": f"Status: {it.get('status','-')}" + (f" · Engineer: {it.get('engineer_name')}" if it.get("engineer_name") else ""),
            "owner": it.get("engineer_name", ""),
            "created_at": it.get("created_at"),
            "ref_id": it.get("id"),
        })

    # Invoices — join via company name + org.
    invoices = await db.invoices.find(
        {"organization_id": org_id, "$or": [
            {"company_id": company_id},
            {"customer_name": company.get("name")},
        ]},
        {"_id": 0, "id": 1, "invoice_number": 1, "amount": 1, "status": 1, "created_at": 1, "due_date": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    for inv in invoices:
        rows.append({
            "module": "billing",
            "type": "invoice",
            "title": f"Invoice {inv.get('invoice_number','')} · £{inv.get('amount', 0)}",
            "body": f"Status: {inv.get('status','-')}",
            "owner": "",
            "created_at": inv.get("created_at"),
            "ref_id": inv.get("id"),
        })

    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    rows = rows[:limit]
    return {
        "company_id": company_id,
        "rows": rows,
        "count": len(rows),
        "modules_present": sorted({r["module"] for r in rows}),
    }
