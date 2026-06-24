"""Campaign builder, send + tracking pixel + click tracker.

Iter 230 — Email A/B testing layered on top of the original send loop.
A campaign may now define ``variants`` (max 4) and an ``ab_test`` config:

    {
      "ab_test": {
        "enabled": true,
        "winner_metric": "opens" | "clicks",
        "sample_pct": 30,                # % of audience used for the test
        "decide_after_minutes": 240      # cap for auto-decide
      },
      "variants": [
        {"id": "a", "name": "Subject A", "subject": "...", "body_html": "...", "weight": 1},
        {"id": "b", "name": "Subject B", "subject": "...", "body_html": "...", "weight": 1}
      ]
    }

Send flow when A/B is enabled:
  • Stage 1 — split ``sample_pct`` of the audience across variants by
    weight, record each `marketing_messages` row with `variant_id`.
  • Campaign status moves to ``ab_testing``; the remaining audience is
    parked on the campaign as ``pending_recipients``.
  • Stage 2 — operator (or a future scheduler) calls
    ``POST /campaigns/{id}/decide-winner`` to pick the winning variant,
    which sends the remaining audience that variant's body.

Without ``ab_test.enabled`` (default), behaviour is unchanged.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import (
    _new_id,
    _now_iso,
    _org_id,
    _org_site_filter,
    _stamp_site,
    logger,
)
from routes.marketing.audiences import _build_filter

router = APIRouter()


# ───────────────────────── Campaigns ─────────────────────────

_MAX_VARIANTS = 4


def _normalise_variants(raw: Optional[list], default_subject: str, default_body: str) -> list[dict]:
    """Return a clean variants list with stable ids and positive weights.

    A campaign with no `variants` synthesises a single default variant so
    the send loop can be uniform."""
    if not raw:
        return [{
            "id": "default",
            "name": "Default",
            "subject": default_subject,
            "body_html": default_body,
            "weight": 1,
        }]
    if len(raw) > _MAX_VARIANTS:
        raise HTTPException(400, f"Campaigns support up to {_MAX_VARIANTS} variants")
    cleaned: list[dict] = []
    seen_ids: set[str] = set()
    for idx, v in enumerate(raw):
        if not isinstance(v, dict):
            continue
        vid = (v.get("id") or "").strip().lower() or chr(ord("a") + idx)
        if vid in seen_ids:
            raise HTTPException(400, f"Duplicate variant id '{vid}'")
        seen_ids.add(vid)
        try:
            weight = float(v.get("weight") if v.get("weight") is not None else 1)
        except (TypeError, ValueError):
            weight = 1.0
        if weight <= 0:
            weight = 1.0
        cleaned.append({
            "id": vid,
            "name": (v.get("name") or vid.upper()).strip()[:60],
            "subject": (v.get("subject") or default_subject or "").strip()[:200],
            "body_html": v.get("body_html") or default_body or "",
            "weight": weight,
        })
    if not cleaned:
        raise HTTPException(400, "At least one variant required")
    return cleaned


def _validate_ab_test(raw: Optional[dict]) -> dict:
    if not raw or not raw.get("enabled"):
        return {"enabled": False}
    metric = (raw.get("winner_metric") or "opens").lower()
    if metric not in {"opens", "clicks"}:
        raise HTTPException(400, "winner_metric must be 'opens' or 'clicks'")
    try:
        sample_pct = int(raw.get("sample_pct") or 30)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "sample_pct must be an integer 5-90") from exc
    if not (5 <= sample_pct <= 90):
        raise HTTPException(400, "sample_pct must be between 5 and 90")
    try:
        decide_min = int(raw.get("decide_after_minutes") or 240)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "decide_after_minutes must be an integer") from exc
    if not (15 <= decide_min <= 7 * 24 * 60):
        raise HTTPException(400, "decide_after_minutes must be 15..10080 (7d)")
    return {
        "enabled": True,
        "winner_metric": metric,
        "sample_pct": sample_pct,
        "decide_after_minutes": decide_min,
    }


def _split_audience_for_variants(audience: list[dict], variants: list[dict]) -> dict[str, list[dict]]:
    """Distribute ``audience`` across variants by weight, deterministic
    by index so two send runs of the same audience produce the same
    bucketing (handy for re-tries)."""
    total_weight = sum(v["weight"] for v in variants) or 1.0
    cumulative = []
    acc = 0.0
    for v in variants:
        acc += v["weight"] / total_weight
        cumulative.append((v["id"], acc))
    buckets: dict[str, list[dict]] = {v["id"]: [] for v in variants}
    n = len(audience) or 1
    for i, contact in enumerate(audience):
        ratio = (i + 0.5) / n
        for vid, threshold in cumulative:
            if ratio <= threshold:
                buckets[vid].append(contact)
                break
        else:
            buckets[variants[-1]["id"]].append(contact)
    return buckets


async def _resolve_campaign_audience(campaign: dict) -> list[dict]:
    org_id = campaign["organization_id"]
    if campaign.get("dynamic_list_id"):
        # Iter 229 — campaigns can target a dynamic list. We resolve the
        # list inline so the send always uses the latest snapshot.
        from routes.marketing.dynamic_lists import _refresh_row, _is_stale
        row = await db.marketing_dynamic_lists.find_one(
            {"id": campaign["dynamic_list_id"], "organization_id": org_id}, {"_id": 0},
        )
        if not row:
            return []
        if _is_stale(row):
            await _refresh_row(row)
        ids = row.get("member_ids") or []
        if not ids:
            return []
        base = {"organization_id": org_id, "marketing_consent.email": {"$ne": False}, "id": {"$in": ids}}
        return await db.crm_contacts.find(
            base, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
        ).to_list(length=len(ids))
    if campaign.get("audience_id"):
        aud = await db.marketing_audiences.find_one(
            {"id": campaign["audience_id"], "organization_id": org_id}, {"_id": 0},
        )
        if not aud:
            return []
        rules = aud.get("rules") or {}
    else:
        rules = (campaign.get("audience_inline") or {}).get("rules", {})
    base = {"organization_id": org_id, "marketing_consent.email": {"$ne": False}}
    rule_filter = _build_filter(rules) if rules else {}
    full = {**base, **rule_filter} if rule_filter else base
    return await db.crm_contacts.find(
        full, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1},
    ).limit(50_000).to_list(length=50_000)


@router.get("/marketing/campaigns", dependencies=[Depends(require_module("marketing"))])
async def list_campaigns(user: dict = Depends(get_current_user)):
    items = await db.marketing_campaigns.find(
        await _org_site_filter(user), {"_id": 0},
    ).sort("created_at", -1).limit(200).to_list(length=200)
    return {"campaigns": items}


@router.post("/marketing/campaigns", dependencies=[Depends(require_module("marketing"))])
async def create_campaign(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    content = body.get("content") or {}
    variants = _normalise_variants(
        body.get("variants"),
        default_subject=content.get("subject") or "",
        default_body=content.get("body_html") or "",
    )
    ab_test = _validate_ab_test(body.get("ab_test"))
    doc = {
        "id": _new_id(), "organization_id": org_id, "site_id": await _stamp_site(user),
        "created_by": user["id"],
        "name": (body.get("name") or "Untitled Campaign").strip(),
        "status": "draft", "channel": body.get("channel", "email"),
        "audience_id": body.get("audience_id"),
        "audience_inline": body.get("audience_inline"),
        "dynamic_list_id": body.get("dynamic_list_id"),
        "content": content,
        "variants": variants,
        "ab_test": ab_test,
        "winner_variant_id": None,
        "winner_decided_at": None,
        "pending_recipients": [],
        "schedule": body.get("schedule") or {},
        "tracking": body.get("tracking") or {"utm_source": "pulsefitnessai"},
        "metrics": {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "bounced": 0,
                    "converted": 0, "revenue_gbp": 0},
        "metrics_by_variant": {v["id"]: {"sent": 0, "opened": 0, "clicked": 0, "bounced": 0} for v in variants},
        "created_at": _now_iso(), "updated_at": _now_iso(), "sent_at": None,
    }
    await db.marketing_campaigns.insert_one(doc)
    return {"campaign": {k: v for k, v in doc.items() if k != "_id"}}


async def _send_one(*, campaign_id: str, org_id: str, contact: dict, variant: dict) -> bool:
    """Send a single email. Returns True on success."""
    try:
        from utils.email import send_email  # type: ignore
    except ImportError:
        send_email = None  # type: ignore
    email = (contact.get("email") or "").strip()
    if not email:
        return False
    msg_id = _new_id()
    tracking_pixel = (
        f'<img src="{os.environ.get("APP_BASE_URL", "")}/api/marketing/track/open/{msg_id}" '
        'width="1" height="1" style="display:none" alt="">'
    )
    body_html = variant.get("body_html") or ""
    personalised = body_html.replace("{{first_name}}", contact.get("first_name") or "there")
    full_html = f"{personalised}{tracking_pixel}"
    ok = False
    if send_email:
        try:
            await send_email(to=email, subject=variant.get("subject") or "", html=full_html)
            ok = True
        except Exception as exc:  # pragma: no cover
            logger.info("[marketing] email failed for %s: %s", email, exc)
    await db.marketing_messages.insert_one({
        "id": msg_id, "campaign_id": campaign_id, "organization_id": org_id,
        "contact_id": contact.get("id"), "contact_email": email,
        "variant_id": variant["id"],
        "channel": "email", "status": "sent" if ok else "failed",
        "sent_at": _now_iso(), "events": [], "attribution": {"bookings": [], "revenue_gbp": 0},
    })
    return ok


@router.post("/marketing/campaigns/{campaign_id}/send", dependencies=[Depends(require_module("marketing"))])
async def send_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    """Dispatch the campaign. Phase 1 supports email via Resend.

    A/B-enabled campaigns send only the sample portion at this stage
    (status moves to `ab_testing`); everything else is the original
    behaviour."""
    org_id = await _org_id(user)
    campaign = await db.marketing_campaigns.find_one(
        {"id": campaign_id, "organization_id": org_id}, {"_id": 0},
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if campaign["status"] in ("sending", "sent", "ab_testing"):
        return {"ok": True, "already_sent": True, "status": campaign["status"]}

    audience = await _resolve_campaign_audience(campaign)
    variants = campaign.get("variants") or _normalise_variants(
        None,
        default_subject=(campaign.get("content") or {}).get("subject") or campaign["name"],
        default_body=(campaign.get("content") or {}).get("body_html") or "",
    )
    ab_test = campaign.get("ab_test") or {"enabled": False}

    # Determine which slice of the audience receives THIS dispatch.
    pending_recipients: list[dict] = []
    if ab_test.get("enabled") and len(variants) > 1 and audience:
        sample_count = max(len(variants), int(len(audience) * ab_test["sample_pct"] / 100))
        sample_count = min(sample_count, len(audience))
        sample = audience[:sample_count]
        pending_recipients = [
            {"id": c.get("id"), "email": (c.get("email") or "").strip(), "first_name": c.get("first_name") or ""}
            for c in audience[sample_count:]
        ]
        new_status = "ab_testing"
    else:
        sample = audience
        new_status = "sent"

    await db.marketing_campaigns.update_one(
        {"id": campaign_id}, {"$set": {"status": "sending"}},
    )

    sent = 0
    failed = 0
    per_variant_sent: dict[str, int] = {v["id"]: 0 for v in variants}
    if campaign["channel"] == "email":
        buckets = _split_audience_for_variants(sample, variants)
        for variant in variants:
            for contact in buckets.get(variant["id"], []):
                ok = await _send_one(
                    campaign_id=campaign_id, org_id=org_id, contact=contact, variant=variant,
                )
                if ok:
                    sent += 1
                    per_variant_sent[variant["id"]] += 1
                else:
                    failed += 1
    elif campaign["channel"] == "in_app":
        for c in sample:
            await db.marketing_messages.insert_one({
                "id": _new_id(), "campaign_id": campaign_id, "organization_id": org_id,
                "contact_id": c.get("id"), "channel": "in_app", "status": "queued",
                "variant_id": variants[0]["id"],
                "content": campaign.get("content"), "sent_at": _now_iso(),
            })
            sent += 1
            per_variant_sent[variants[0]["id"]] += 1

    update_fields: dict = {
        "status": new_status, "sent_at": _now_iso(),
        "metrics.sent": sent, "metrics.bounced": failed,
        "pending_recipients": pending_recipients,
    }
    for vid, n in per_variant_sent.items():
        update_fields[f"metrics_by_variant.{vid}.sent"] = n
    await db.marketing_campaigns.update_one({"id": campaign_id}, {"$set": update_fields})
    await db.marketing_subscriptions.update_one(
        {"organization_id": org_id},
        {"$inc": {f"usage_this_period.{'emails_sent' if campaign['channel'] == 'email' else 'sms_sent'}": sent}},
    )
    # Iter 216h227 — Marketing trial first-win milestone — fires the
    # FIRST time any campaign actually ships emails / in-app messages
    # for the org so the activation card celebrates the launch.
    if sent > 0:
        try:
            from routes.activation_events import record_activation_event
            await record_activation_event(
                org_id, "first_campaign_launched",
                trigger_user_id=user.get("id"),
                payload={"campaign_id": campaign_id, "sent": sent},
            )
        except Exception:  # best-effort — never block campaign dispatch
            pass
    return {
        "ok": True, "sent": sent, "failed": failed,
        "audience_size": len(audience),
        "sample_size": len(sample),
        "pending_recipients": len(pending_recipients),
        "status": new_status,
        "ab_testing": new_status == "ab_testing",
    }


@router.post(
    "/marketing/campaigns/{campaign_id}/decide-winner",
    dependencies=[Depends(require_module("marketing"))],
)
async def decide_winner(
    campaign_id: str,
    body: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Pick the winning variant and dispatch the remainder.

    body = {"winner_variant_id": "a"}  # explicit pick
    OR    {}                                # auto-pick by metric

    Auto-pick uses the campaign's `ab_test.winner_metric` (defaults to
    'opens') and selects the variant with the highest count, breaking
    ties by lower `sent` (most efficient)."""
    org_id = await _org_id(user)
    campaign = await db.marketing_campaigns.find_one(
        {"id": campaign_id, "organization_id": org_id}, {"_id": 0},
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not (campaign.get("ab_test") or {}).get("enabled"):
        raise HTTPException(400, "A/B test is not enabled on this campaign")
    if campaign["status"] != "ab_testing":
        raise HTTPException(400, f"Campaign is not in ab_testing state (status={campaign['status']})")

    variants = campaign.get("variants") or []
    chosen_id = (body.get("winner_variant_id") or "").strip().lower()
    if chosen_id:
        winner = next((v for v in variants if v["id"] == chosen_id), None)
        if not winner:
            raise HTTPException(400, "Unknown winner_variant_id")
    else:
        metric = (campaign.get("ab_test") or {}).get("winner_metric") or "opens"
        mbv = campaign.get("metrics_by_variant") or {}
        def score(v):
            row = mbv.get(v["id"]) or {}
            return (row.get(metric, 0), -row.get("sent", 0))
        winner = max(variants, key=score) if variants else None
        if not winner:
            raise HTTPException(400, "No variants to choose from")

    pending = campaign.get("pending_recipients") or []
    sent_count = 0
    failed_count = 0
    for r in pending:
        ok = await _send_one(
            campaign_id=campaign_id, org_id=org_id, contact=r, variant=winner,
        )
        if ok:
            sent_count += 1
        else:
            failed_count += 1

    update_fields: dict = {
        "status": "sent",
        "winner_variant_id": winner["id"],
        "winner_decided_at": _now_iso(),
        "pending_recipients": [],
        f"metrics_by_variant.{winner['id']}.sent": (
            (campaign.get("metrics_by_variant") or {}).get(winner["id"], {}).get("sent", 0) + sent_count
        ),
    }
    await db.marketing_campaigns.update_one({"id": campaign_id}, {
        "$set": update_fields,
        "$inc": {"metrics.sent": sent_count, "metrics.bounced": failed_count},
    })
    return {
        "ok": True, "winner_variant_id": winner["id"],
        "remainder_sent": sent_count, "remainder_failed": failed_count,
    }


# ───────────────────────── Tracking pixel + click ─────────────────────────

@router.get("/marketing/track/open/{message_id}")
async def track_open(message_id: str):
    """1x1 PNG tracker — records the open event + bumps per-variant metrics."""
    msg = await db.marketing_messages.find_one(
        {"id": message_id}, {"_id": 0, "campaign_id": 1, "variant_id": 1, "opened_at": 1},
    )
    await db.marketing_messages.update_one(
        {"id": message_id, "opened_at": {"$in": [None, ""]}},
        {"$set": {"status": "opened", "opened_at": _now_iso()},
         "$push": {"events": {"type": "open", "at": _now_iso()}}},
    )
    if msg:
        inc: dict = {"metrics.opened": 1}
        vid = msg.get("variant_id")
        if vid:
            inc[f"metrics_by_variant.{vid}.opened"] = 1
        await db.marketing_campaigns.update_one({"id": msg["campaign_id"]}, {"$inc": inc})
    from fastapi.responses import Response
    pixel = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cb\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    return Response(content=pixel, media_type="image/png")
