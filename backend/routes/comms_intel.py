"""Pulse Fitness AI — Comms intelligence (Phase 2).

Engagement scoring, inactive detection, best-send-time, benchmarking,
campaign analytics (click map + bot filtering + conversions), the
Deliverability Centre and the AI assistant endpoints. All read-only over
the existing ``marketing_messages`` / ``marketing_campaigns`` data so the
intelligence reflects real sends; AI endpoints only return suggestions.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile

from utils.auth import get_current_user
from utils.database import db
from utils import comms_ai
from utils import email_ingest

logger = logging.getLogger("comms_intel")
from routes.marketing.helpers import _org_id, _now_iso
from routes.comms import _ANY_COMMS_MODULE, _get_owned, render_blocks_to_html

router = APIRouter(prefix="/comms")

# opens that fire within this many seconds of send are treated as bot/scanner
_BOT_OPEN_SECONDS = 8


def _parse(ts) -> Optional[datetime]:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _band(score: int) -> str:
    if score >= 75:
        return "highly_engaged"
    if score >= 50:
        return "engaged"
    if score >= 25:
        return "neutral"
    if score > 0:
        return "disengaged"
    return "inactive"


async def _campaign_module_ids(org_id: str, module: Optional[str]) -> Optional[set]:
    """Campaign ids belonging to a module (None = all)."""
    if not module or module == "all":
        return None
    docs = await db.marketing_campaigns.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "related_module": 1, "campaign_type": 1},
    ).to_list(length=2000)
    from routes.comms import _CAMPAIGN_TYPE_MODULE
    ids = set()
    for d in docs:
        rm = d.get("related_module") or _CAMPAIGN_TYPE_MODULE.get(d.get("campaign_type"), "marketing")
        if rm == module:
            ids.add(d["id"])
    return ids


def _event_flags(msg: dict):
    """Return (opened, clicked, is_bot_open) for a message, bot-aware."""
    sent = _parse(msg.get("sent_at"))
    opened_at = _parse(msg.get("opened_at"))
    events = msg.get("events") or []
    opened = bool(opened_at) or any(e.get("type") == "open" for e in events)
    clicked = bool(msg.get("clicked_at")) or any(e.get("type") == "click" for e in events)
    is_bot = False
    if opened and sent:
        first_open = opened_at
        for e in events:
            if e.get("type") == "open":
                eo = _parse(e.get("at"))
                if eo and (not first_open or eo < first_open):
                    first_open = eo
        if first_open and (first_open - sent).total_seconds() < _BOT_OPEN_SECONDS:
            is_bot = True
    return opened, clicked, is_bot


# ───────────────────────── Engagement scoring ─────────────────────────

@router.get("/engagement/contacts", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def engagement_contacts(
    module: Optional[str] = Query(None),
    days: int = Query(90, ge=1, le=730),
    bots: str = Query("exclude"),
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    cids = await _campaign_module_ids(org_id, module)
    q: dict = {"organization_id": org_id}
    if cids is not None:
        if not cids:
            return {"contacts": [], "bands": {}}
        q["campaign_id"] = {"$in": list(cids)}
    msgs = await db.marketing_messages.find(q, {"_id": 0}).to_list(length=20000)

    agg: dict = defaultdict(lambda: {"sent": 0, "opened": 0, "clicked": 0, "bounced": 0, "last_open": None})
    for m in msgs:
        email = (m.get("contact_email") or "").lower()
        if not email:
            continue
        a = agg[email]
        a["sent"] += 1
        opened, clicked, is_bot = _event_flags(m)
        if m.get("status") in ("bounced", "failed"):
            a["bounced"] += 1
        if opened and not (bots == "exclude" and is_bot):
            a["opened"] += 1
            oa = _parse(m.get("opened_at"))
            if oa and (not a["last_open"] or oa > a["last_open"]):
                a["last_open"] = oa
        if clicked:
            a["clicked"] += 1

    # unsubscribes penalise
    unsub = set()
    async for s in db.marketing_subscriptions.find(
        {"organization_id": org_id, "status": "unsubscribed"}, {"_id": 0, "email": 1, "contact_email": 1},
    ):
        unsub.add((s.get("email") or s.get("contact_email") or "").lower())

    now = _now()
    out = []
    bands_count: dict = defaultdict(int)
    for email, a in agg.items():
        score = a["opened"] * 8 + a["clicked"] * 20 - a["bounced"] * 12
        if a["last_open"]:
            age = (now - a["last_open"]).days
            score += max(0, 20 - age // 3)
        if email in unsub:
            score = min(score, 5)
        score = max(0, min(100, int(score)))
        band = _band(score)
        bands_count[band] += 1
        out.append({
            "email": email, "sent": a["sent"], "opened": a["opened"],
            "clicked": a["clicked"], "bounced": a["bounced"],
            "last_open": a["last_open"].isoformat() if a["last_open"] else None,
            "unsubscribed": email in unsub, "score": score, "band": band,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return {"contacts": out[:limit], "bands": dict(bands_count), "total": len(out)}


@router.get("/engagement/companies", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def engagement_companies(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    # map contact email -> company via crm2_contacts
    contacts = await db.crm2_contacts.find(
        {"organization_id": org_id}, {"_id": 0, "email": 1, "company_id": 1},
    ).to_list(length=10000)
    email_company = {(c.get("email") or "").lower(): c.get("company_id") for c in contacts if c.get("email")}
    companies = await db.crm2_companies.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(length=5000)
    cname = {c["id"]: c.get("name", "Unknown") for c in companies}

    scored = (await engagement_contacts.__wrapped__(  # reuse logic
        module=None, days=365, bots="exclude", limit=10000, user=user,
    )) if hasattr(engagement_contacts, "__wrapped__") else None
    # fallback: recompute inline if wrapper not available
    if not scored:
        msgs = await db.marketing_messages.find({"organization_id": org_id}, {"_id": 0}).to_list(length=20000)
        per: dict = defaultdict(lambda: {"opened": 0, "clicked": 0})
        for m in msgs:
            email = (m.get("contact_email") or "").lower()
            opened, clicked, is_bot = _event_flags(m)
            if opened and not is_bot:
                per[email]["opened"] += 1
            if clicked:
                per[email]["clicked"] += 1
        scored = {"contacts": [
            {"email": e, "score": max(0, min(100, v["opened"] * 8 + v["clicked"] * 20)),
             "opened": v["opened"], "clicked": v["clicked"]}
            for e, v in per.items()
        ]}

    comp_agg: dict = defaultdict(lambda: {"contacts": 0, "score_sum": 0, "opened": 0, "clicked": 0})
    for c in scored["contacts"]:
        comp_id = email_company.get(c["email"])
        if not comp_id:
            continue
        g = comp_agg[comp_id]
        g["contacts"] += 1
        g["score_sum"] += c["score"]
        g["opened"] += c.get("opened", 0)
        g["clicked"] += c.get("clicked", 0)

    out = []
    for comp_id, g in comp_agg.items():
        avg = int(g["score_sum"] / g["contacts"]) if g["contacts"] else 0
        out.append({
            "company_id": comp_id, "company_name": cname.get(comp_id, "Unknown"),
            "engaged_contacts": g["contacts"], "opened": g["opened"], "clicked": g["clicked"],
            "score": avg, "band": _band(avg),
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return {"companies": out, "total": len(out)}


# ───────────────────────── Inactive detection ─────────────────────────

@router.get("/insights/inactive", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def inactive_contacts(
    days: int = Query(60, ge=7, le=730),
    module: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    cids = await _campaign_module_ids(org_id, module)
    q: dict = {"organization_id": org_id}
    if cids is not None:
        if not cids:
            return {"inactive": [], "cutoff_days": days}
        q["campaign_id"] = {"$in": list(cids)}
    msgs = await db.marketing_messages.find(q, {"_id": 0}).to_list(length=20000)
    cutoff = _now() - timedelta(days=days)
    agg: dict = defaultdict(lambda: {"sent": 0, "last_open": None, "last_send": None})
    for m in msgs:
        email = (m.get("contact_email") or "").lower()
        if not email:
            continue
        a = agg[email]
        a["sent"] += 1
        sa = _parse(m.get("sent_at"))
        if sa and (not a["last_send"] or sa > a["last_send"]):
            a["last_send"] = sa
        opened, _, is_bot = _event_flags(m)
        if opened and not is_bot:
            oa = _parse(m.get("opened_at"))
            if oa and (not a["last_open"] or oa > a["last_open"]):
                a["last_open"] = oa
    out = []
    for email, a in agg.items():
        if a["sent"] >= 2 and (not a["last_open"] or a["last_open"] < cutoff):
            out.append({
                "email": email, "sent": a["sent"],
                "last_open": a["last_open"].isoformat() if a["last_open"] else None,
                "days_since_open": (_now() - a["last_open"]).days if a["last_open"] else None,
            })
    out.sort(key=lambda x: (x["days_since_open"] is None, -(x["days_since_open"] or 0)))
    return {"inactive": out[:500], "cutoff_days": days, "count": len(out)}


# ───────────────────────── Best send time ─────────────────────────

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@router.get("/insights/best-send-time", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def best_send_time(module: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    cids = await _campaign_module_ids(org_id, module)
    q: dict = {"organization_id": org_id, "opened_at": {"$nin": [None, ""]}}
    if cids is not None:
        if not cids:
            q = None
        else:
            q["campaign_id"] = {"$in": list(cids)}
    grid = [[0] * 24 for _ in range(7)]
    total = 0
    if q is not None:
        msgs = await db.marketing_messages.find(q, {"_id": 0, "opened_at": 1, "events": 1}).to_list(length=20000)
        for m in msgs:
            oa = _parse(m.get("opened_at"))
            if oa:
                grid[oa.weekday()][oa.hour] += 1
                total += 1
    if total < 20:
        # safe starter recommendation (industry norms) until enough data
        return {
            "enough_data": False, "samples": total, "grid": grid, "days": _DAYS,
            "recommendation": {"day": "Tue", "hour": 10, "label": "Tuesday around 10:00"},
            "note": "Not enough open data yet — using a safe starter recommendation. This will sharpen as you send more.",
        }
    best_day = best_hour = 0
    best_val = -1
    for d in range(7):
        for h in range(24):
            if grid[d][h] > best_val:
                best_val, best_day, best_hour = grid[d][h], d, h
    return {
        "enough_data": True, "samples": total, "grid": grid, "days": _DAYS,
        "recommendation": {"day": _DAYS[best_day], "hour": best_hour,
                           "label": f"{_DAYS[best_day]} around {best_hour:02d}:00"},
    }


# ───────────────────────── Benchmarking ─────────────────────────

@router.get("/insights/benchmarks", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def benchmarks(module: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    docs = await db.marketing_campaigns.find({"organization_id": org_id}, {"_id": 0}).to_list(length=2000)
    from routes.comms import _CAMPAIGN_TYPE_MODULE
    rows = []
    for d in docs:
        rm = d.get("related_module") or _CAMPAIGN_TYPE_MODULE.get(d.get("campaign_type"), "marketing")
        if module and module != "all" and rm != module:
            continue
        m = d.get("metrics") or {}
        sent = int(m.get("sent", 0) or 0)
        if sent <= 0:
            continue
        rows.append({
            "id": d["id"], "name": d.get("name"), "type": d.get("campaign_type"),
            "open_rate": round(int(m.get("opened", 0)) / sent * 100, 1),
            "click_rate": round(int(m.get("clicked", 0)) / sent * 100, 1),
            "unsub_rate": round(int(m.get("unsubscribed", 0)) / sent * 100, 2),
            "sent": sent,
        })
    if not rows:
        return {"campaigns": [], "averages": {"open_rate": 0, "click_rate": 0, "unsub_rate": 0}, "count": 0}
    avg = {
        "open_rate": round(sum(r["open_rate"] for r in rows) / len(rows), 1),
        "click_rate": round(sum(r["click_rate"] for r in rows) / len(rows), 1),
        "unsub_rate": round(sum(r["unsub_rate"] for r in rows) / len(rows), 2),
    }
    rows.sort(key=lambda r: r["open_rate"], reverse=True)
    return {"campaigns": rows, "averages": avg, "count": len(rows),
            "best": rows[0], "worst": rows[-1]}


# ───────────────────────── Campaign analytics (click map, bots, conv) ─────────

@router.get("/campaigns/{campaign_id}/analytics", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def campaign_analytics(
    campaign_id: str, bots: str = Query("exclude"), user: dict = Depends(get_current_user),
):
    org_id = await _org_id(user)
    camp = await _get_owned(campaign_id, org_id)
    msgs = await db.marketing_messages.find(
        {"organization_id": org_id, "campaign_id": campaign_id}, {"_id": 0},
    ).to_list(length=50000)

    sent = len(msgs)
    opened = clicked = bounced = bot_opens = 0
    click_map: dict = defaultdict(int)
    for m in msgs:
        op, cl, is_bot = _event_flags(m)
        if m.get("status") in ("bounced", "failed"):
            bounced += 1
        if op:
            if is_bot:
                bot_opens += 1
                if bots == "exclude":
                    continue
            opened += 1
        if cl:
            clicked += 1
        for e in (m.get("events") or []):
            if e.get("type") == "click" and e.get("url"):
                click_map[e["url"]] += 1

    # fall back to stored campaign metrics if no per-message rows yet
    if sent == 0:
        cm = camp.get("metrics") or {}
        sent = int(cm.get("sent", 0)); opened = int(cm.get("opened", 0))
        clicked = int(cm.get("clicked", 0)); bounced = int(cm.get("bounced", 0))

    rate = lambda n: round(n / sent * 100, 1) if sent else 0.0
    convs = await db.comms_conversions.find(
        {"organization_id": org_id, "campaign_id": campaign_id}, {"_id": 0},
    ).to_list(length=10000)
    by_type: dict = {}
    revenue = 0.0
    for c in convs:
        by_type[c.get("type", "other")] = by_type.get(c.get("type", "other"), 0) + 1
        revenue += float(c.get("value_gbp", 0) or 0)
    conversions = {
        "count": len(convs), "by_type": by_type, "revenue_gbp": round(revenue, 2),
        "conversion_rate": round(len(convs) / sent * 100, 1) if sent else 0.0,
    }
    return {
        "campaign_id": campaign_id, "name": camp.get("name"),
        "bot_filtering": bots, "bot_opens": bot_opens,
        "totals": {"sent": sent, "opened": opened, "clicked": clicked, "bounced": bounced},
        "rates": {"open_rate": rate(opened), "click_rate": rate(clicked),
                  "bounce_rate": rate(bounced), "ctor": round(clicked / opened * 100, 1) if opened else 0.0},
        "click_map": sorted(
            [{"url": u, "clicks": c} for u, c in click_map.items()],
            key=lambda x: x["clicks"], reverse=True,
        ),
        "conversions": conversions,
    }


# ───────────────────────── Deliverability Centre ─────────────────────────

@router.get("/deliverability", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def deliverability(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    from utils.email import _CATEGORY_SENDER_DEFAULT, _bare_addr, RESEND_API_KEY
    domains = []
    seen = set()
    for cat, sender in _CATEGORY_SENDER_DEFAULT.items():
        dom = _bare_addr(sender).split("@")[-1]
        if dom in seen:
            continue
        seen.add(dom)
        domains.append({
            "domain": dom, "category": cat, "sender": sender,
            "verified": bool(RESEND_API_KEY),
            "spf": "configured", "dkim": "configured", "dmarc": "configured",
        })

    msgs = await db.marketing_messages.find(
        {"organization_id": org_id}, {"_id": 0, "status": 1},
    ).to_list(length=50000)
    sent = len(msgs)
    bounced = sum(1 for m in msgs if m.get("status") in ("bounced", "failed"))
    unsub = await db.marketing_subscriptions.count_documents(
        {"organization_id": org_id, "status": "unsubscribed"})
    suppress = await db.marketing_subscriptions.count_documents(
        {"organization_id": org_id, "status": {"$in": ["unsubscribed", "bounced", "complained"]}})

    rate = lambda n: round(n / sent * 100, 2) if sent else 0.0
    bounce_rate = rate(bounced)
    unsub_rate = rate(unsub)
    warnings = []
    if not RESEND_API_KEY:
        warnings.append({"level": "error", "message": "No email provider key configured — sends will fail."})
    if bounce_rate > 5:
        warnings.append({"level": "warn", "message": f"Bounce rate is high ({bounce_rate}%). Clean your list before large sends."})
    if unsub_rate > 2:
        warnings.append({"level": "warn", "message": f"Unsubscribe rate is elevated ({unsub_rate}%). Review targeting & frequency."})
    health = "good"
    if any(w["level"] == "error" for w in warnings):
        health = "at_risk"
    elif warnings:
        health = "warning"
    return {
        "provider": "Resend", "health": health, "domains": domains,
        "rates": {"sent": sent, "bounce_rate": bounce_rate, "unsubscribe_rate": unsub_rate},
        "suppression_count": suppress, "warnings": warnings,
    }


# ───────────────────────── AI assistant ─────────────────────────

@router.post("/ai/subjects", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def ai_subjects(body: dict = Body(...), user: dict = Depends(get_current_user)):
    res = await comms_ai.generate_subjects(
        body.get("topic", ""), body.get("audience", ""), body.get("tone", ""), int(body.get("n", 5)))
    if res is None:
        raise HTTPException(503, "AI assistant is unavailable right now. Please try again.")
    return {"subjects": res}


@router.post("/ai/write", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def ai_write(body: dict = Body(...), user: dict = Depends(get_current_user)):
    res = await comms_ai.write_email(
        body.get("brief", ""), body.get("campaign_type", ""), body.get("tone", ""))
    if res is None:
        raise HTTPException(503, "AI assistant is unavailable right now. Please try again.")
    blocks = []
    for b in res.get("blocks", []):
        t = b.get("type")
        if t in ("heading", "text", "button"):
            blocks.append({"id": f"ai{len(blocks)}", "type": t, "props": b.get("props") or {}})
    return {"subject": res.get("subject", ""), "preview": res.get("preview", ""), "blocks": blocks}


_ALLOWED_IMPORT_BLOCKS = {"heading", "text", "button", "image", "divider", "spacer"}
_MAX_IMPORT_BYTES = 15 * 1024 * 1024


@router.post("/ai/import-email", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def ai_import_email(
    file: Optional[UploadFile] = File(default=None),
    text: str = Form(default=""),
    user: dict = Depends(get_current_user),
):
    """Rebuild a dropped/pasted email into editable template blocks.

    Accepts a file (.eml/.msg/.html/.txt/.pdf/image) or pasted text/HTML.
    """
    file_bytes, filename, content_type = None, "", ""
    if file is not None:
        file_bytes = await file.read()
        if file_bytes and len(file_bytes) > _MAX_IMPORT_BYTES:
            raise HTTPException(413, "File is too large — keep it under 15MB.")
        filename = file.filename or ""
        content_type = file.content_type or ""

    if not file_bytes and not (text or "").strip():
        raise HTTPException(400, "Drop an email file or paste the email content.")

    try:
        parsed = email_ingest.parse_email(file_bytes, filename, text, content_type)
    except Exception as exc:
        logger.warning("[comms-ai] email parse failed for %r: %s", filename, exc)
        raise HTTPException(422, "We couldn't read that email file. Try exporting it as .eml or pasting the email text/HTML instead.")

    try:
        res = await asyncio.wait_for(
            comms_ai.import_email_to_blocks(
                text_content=parsed.get("text", ""),
                available_images=parsed.get("images", []),
                image_b64=parsed.get("image_b64"),
                file_path=parsed.get("file_path"),
                file_mime=parsed.get("file_mime"),
            ),
            timeout=75,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "That email is taking too long to rebuild. Try a smaller email or paste just the body text.")
    except Exception as exc:
        logger.warning("[comms-ai] import rebuild failed: %s", exc)
        raise HTTPException(502, "Couldn't rebuild that email right now. Please try again or paste the text.")
    if res is None:
        raise HTTPException(422, "We couldn't extract any content from that email. Try pasting the email body or HTML instead.")

    notes = [str(n).strip() for n in (res.get("notes") or []) if str(n).strip()]
    blocks = []
    missing_imgs = 0
    for b in res.get("blocks", []):
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        props = b.get("props")
        # Tolerate the alternate {blocktype: {..props..}} shape the model sometimes emits.
        if t is None:
            for k, v in b.items():
                if k in _ALLOWED_IMPORT_BLOCKS and isinstance(v, dict):
                    t, props = k, v
                    break
        if t not in _ALLOWED_IMPORT_BLOCKS:
            continue
        props = props if isinstance(props, dict) else {}
        if t == "image" and not (props.get("src") or "").strip():
            missing_imgs += 1
        blocks.append({"id": f"imp{len(blocks)}", "type": t, "props": props})

    # If the source clearly had embedded images we couldn't host, make it explicit.
    embedded = parsed.get("embedded_image_count", 0)
    if (embedded or missing_imgs) and not any("image" in n.lower() for n in notes):
        notes.append(
            "Some images were embedded in the original and couldn't be pulled in automatically — "
            "placeholders were added so you can upload them.")

    return {
        "subject": res.get("subject", ""),
        "preview": res.get("preview", ""),
        "blocks": blocks,
        "notes": notes,
        "source_kind": parsed.get("kind", "text"),
    }


@router.post("/ai/improve", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def ai_improve(body: dict = Body(...), user: dict = Depends(get_current_user)):
    res = await comms_ai.improve_text(body.get("text", ""), body.get("goal", ""))
    if res is None:
        raise HTTPException(503, "AI assistant is unavailable right now. Please try again.")
    return {"text": res}


@router.post("/campaigns/{campaign_id}/ai-analyse", dependencies=[Depends(_ANY_COMMS_MODULE)])
async def ai_analyse(campaign_id: str, user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    camp = await _get_owned(campaign_id, org_id)
    analytics = await campaign_analytics(campaign_id, bots="exclude", user=user)
    bench = await benchmarks(module=camp.get("related_module"), user=user)
    context = {
        "name": camp.get("name"), "type": camp.get("campaign_type"),
        "goal": camp.get("conversion_goal"),
        "rates": analytics["rates"], "totals": analytics["totals"],
        "org_average": bench["averages"],
    }
    res = await comms_ai.analyse_campaign(context)
    if res is None:
        raise HTTPException(503, "AI assistant is unavailable right now. Please try again.")
    return {"analysis": res, "context": context}
