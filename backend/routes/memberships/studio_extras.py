"""Studio extras — waivers/PARQ + shareable OG preview cards.

Iter 215r. Two P1 features from the studio brief:

  1. Waivers — studios (esp. dance schools & kids classes) need a signed
     acknowledgement before a member first books. We add:
       POST /api/member/waivers              — member signs a plan waiver
       GET  /api/member/waivers/me           — list of signed waivers
     Plan authors set `waiver_required: bool` + `waiver_text: str` via
     the existing PUT /api/memberships/plans/{id} (fields pass through
     the Mongo update — the Plan router accepts extra fields).

  2. Per-class share card — an Instagram / WhatsApp friendly OG preview
     for each class occurrence. Re-uses the existing public class
     detail at /m/{slug}/c/{occId}. We add:
       GET /api/m/{slug}/c/{occ}/share      — HTML with OG meta tags
                                               (what IG scrapes)
       GET /api/m/{slug}/c/{occ}/og.png     — 1200x630 rendered card
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from utils.database import db, get_object, put_object

from routes.memberships.helpers import (
    _now_iso,
    _require_current_member,
    _uuid,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memberships-studio-extras"])


# ═══════════════════════════════ Waivers ═══════════════════════════════

class WaiverSignIn(BaseModel):
    plan_id: str
    signature_name: str = Field(min_length=2, max_length=120)
    acknowledged: bool = True


@router.post("/member/waivers")
async def member_sign_waiver(
    body: WaiverSignIn = Body(...),
    request: Request = None,  # type: ignore[assignment]
    member: dict = Depends(_require_current_member),
):
    """Member signs a plan's waiver. Idempotent — if they've already
    signed the same `(plan_id, text_hash)`, the existing record is
    returned unchanged so re-opening the modal doesn't duplicate."""
    if not body.acknowledged:
        raise HTTPException(400, "You must acknowledge the waiver to proceed.")

    plan = await db.membership_plans.find_one(
        {"id": body.plan_id, "organization_id": member["organization_id"]},
        {"_id": 0},
    )
    if not plan:
        raise HTTPException(404, "Plan not found.")
    if not plan.get("waiver_required"):
        # Signing a waiver that isn't required is harmless but we don't
        # manufacture a record. Return a soft ok.
        return {"ok": True, "skipped": True, "reason": "plan_waiver_not_required"}

    text = (plan.get("waiver_text") or "").strip()
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    existing = await db.waivers.find_one(
        {"member_id": member["id"], "plan_id": body.plan_id, "text_hash": text_hash},
        {"_id": 0},
    )
    if existing:
        return {"ok": True, "waiver_id": existing["id"], "already_signed": True}

    ua = (request.headers.get("user-agent") if request else "") or ""
    ip = (request.client.host if request and request.client else "") or ""

    waiver = {
        "id": _uuid(),
        "organization_id": member["organization_id"],
        "member_id": member["id"],
        "plan_id": body.plan_id,
        "plan_name": plan.get("name"),
        "text_hash": text_hash,
        "signature_name": body.signature_name.strip(),
        "signed_at": _now_iso(),
        "ip": ip[:64],
        "user_agent": ua[:250],
    }
    await db.waivers.insert_one({**waiver})
    return {"ok": True, "waiver_id": waiver["id"], "already_signed": False}


@router.get("/member/waivers/me")
async def member_list_waivers(member: dict = Depends(_require_current_member)):
    """Return everything this member has signed, most recent first."""
    rows = await db.waivers.find(
        {"member_id": member["id"]},
        {"_id": 0, "id": 1, "plan_id": 1, "plan_name": 1, "text_hash": 1, "signed_at": 1},
    ).sort("signed_at", -1).to_list(200)
    return {"waivers": rows}


# ─ Operator convenience: the share dialog needs the org's public slug
# so it can build the `/api/m/<slug>/c/<occ>/share` URL. We expose it
# separately from the big settings payload to keep the payload cheap.
from fastapi import Depends as _Depends  # noqa: E402
from utils.auth import get_current_user  # noqa: E402
from utils.module_guard import require_module  # noqa: E402


@router.get("/memberships/share/org-slug", dependencies=[_Depends(require_module("memberships"))])
async def operator_share_slug(user: dict = _Depends(get_current_user)):
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")},
        {"_id": 0, "membership_app_slug": 1, "slug": 1},
    )
    if not org:
        raise HTTPException(404, "Organization not found")
    return {"slug": org.get("membership_app_slug") or org.get("slug")}


# ═══════════════════════════════ Share card ═══════════════════════════════

async def _resolve_class(slug: str, occ_id: str) -> tuple[dict, dict, dict]:
    org = await db.organizations.find_one(
        {"membership_app_slug": slug.lower()},
        {"_id": 0, "id": 1, "name": 1, "logo_url": 1, "primary_color": 1, "secondary_color": 1, "modules": 1},
    )
    if not org or not (org.get("modules") or {}).get("memberships"):
        raise HTTPException(404, "Studio not found")
    occ = await db.class_occurrences.find_one(
        {"id": occ_id, "organization_id": org["id"]}, {"_id": 0},
    )
    if not occ:
        raise HTTPException(404, "Class not found")
    tpl = await db.class_templates.find_one(
        {"id": occ.get("template_id")}, {"_id": 0},
    ) or {}
    return org, occ, tpl


def _class_share_strings(org: dict, occ: dict, tpl: dict) -> dict:
    name = tpl.get("name") or occ.get("name") or "Class"
    starts_at = occ.get("starts_at") or ""
    try:
        dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        when = dt.strftime("%a %d %b · %H:%M")
    except Exception:  # noqa: BLE001
        when = starts_at
    capacity = int(occ.get("capacity") or 0)
    booked = int(occ.get("bookings_count") or 0)
    spots_left = max(capacity - booked, 0)
    spots_text = "Fully booked — join the waitlist" if spots_left == 0 and capacity else (
        f"{spots_left} spot{'s' if spots_left != 1 else ''} left" if capacity else "Book now"
    )
    desc = (tpl.get("description") or "").strip().split("\n", 1)[0][:140]
    return {
        "name": name,
        "when": when,
        "spots_text": spots_text,
        "org_name": org.get("name") or "Your studio",
        "description": desc or f"Join us for {name}",
        "primary_color": org.get("primary_color") or "#00B2C7",
    }


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "").lstrip("#")
    if len(h) != 6:
        return (0, 178, 199)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (0, 178, 199)


def _pick_font(size: int):
    """Try common system fonts; fall back to Pillow's default bitmap."""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _og_cache_key(org: dict, occ: dict, tpl: dict) -> str:
    """Stable fingerprint of everything that affects the rendered image.
    When any of these change, we re-render; otherwise the cached blob
    is valid forever. Saves re-rendering on every viral IG scrape."""
    parts = (
        str(occ.get("id") or ""),
        str(occ.get("name") or tpl.get("name") or ""),
        str(occ.get("starts_at") or ""),
        str(occ.get("capacity") or 0),
        str(occ.get("bookings_count") or 0),
        str(org.get("primary_color") or ""),
        str(org.get("name") or ""),
        # Bump this if _render_class_og layout/version changes.
        "v1",
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _og_storage_path(org_id: str, occ_id: str, key: str) -> str:
    return f"og-cache/{org_id}/{occ_id}/{key}.png"


def _render_class_og(org: dict, occ: dict, tpl: dict) -> bytes:
    """Pure Pillow render. Blocks — callers must run via asyncio.to_thread."""
    s = _class_share_strings(org, occ, tpl)

    W, H = 1200, 630
    fg = (255, 255, 255)
    primary = _hex_to_rgb(s["primary_color"])

    img = Image.new("RGB", (W, H), (10, 12, 16))
    d = ImageDraw.Draw(img)

    # Subtle top-to-bottom gradient toward the brand accent.
    for i in range(H):
        t = i / H
        r = int(10 + (primary[0] - 10) * t * 0.22)
        g = int(12 + (primary[1] - 12) * t * 0.22)
        b = int(16 + (primary[2] - 16) * t * 0.22)
        d.line([(0, i), (W, i)], fill=(r, g, b))

    # Brand stripe at top.
    d.rectangle([0, 0, W, 8], fill=primary)

    font_small = _pick_font(26)
    font_title = _pick_font(76)
    font_meta = _pick_font(36)
    font_cta = _pick_font(40)

    d.text((64, 52), s["org_name"].upper(), fill=(255, 255, 255, 200), font=font_small)

    title = s["name"]
    if len(title) > 22:
        words = title.split()
        line1, line2 = "", ""
        for w in words:
            if len(line1) + len(w) < 20:
                line1 = (line1 + " " + w).strip()
            else:
                line2 = (line2 + " " + w).strip()
        d.text((64, 130), line1, fill=fg, font=font_title)
        if line2:
            d.text((64, 220), line2, fill=fg, font=font_title)
    else:
        d.text((64, 150), title, fill=fg, font=font_title)

    d.text((64, 360), s["when"], fill=(255, 255, 255, 220), font=font_meta)
    d.text((64, 410), s["spots_text"], fill=primary, font=font_meta)

    cta = "Book now →"
    cta_w = int(d.textlength(cta, font=font_cta))
    px, py = 64, 520
    d.rounded_rectangle([px, py, px + cta_w + 60, py + 70], radius=35, fill=primary)
    d.text((px + 30, py + 14), cta, fill=(10, 12, 16), font=font_cta)

    d.text((W - 260, 572), "Powered by GymAxis", fill=(255, 255, 255, 140), font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def _get_or_render_og(org: dict, occ: dict, tpl: dict) -> tuple[bytes, str]:
    """Return the cached PNG bytes if the fingerprint still matches,
    otherwise render fresh, store it, and update the occurrence's
    `cached_og` record. Returns (bytes, source_tag) where source_tag is
    'cache' or 'fresh' — useful for response headers and observability."""
    key = _og_cache_key(org, occ, tpl)
    cache_meta = occ.get("cached_og") or {}
    path = cache_meta.get("path") or _og_storage_path(org["id"], occ["id"], key)

    if cache_meta.get("hash") == key:
        try:
            data, _ct = await asyncio.to_thread(get_object, path)
            if data:
                return data, "cache"
        except Exception as exc:  # noqa: BLE001
            logger.warning("og_cache: get failed %s — regenerating (%s)", path, exc)

    data = await asyncio.to_thread(_render_class_og, org, occ, tpl)
    try:
        fresh_path = _og_storage_path(org["id"], occ["id"], key)
        await asyncio.to_thread(put_object, fresh_path, data, "image/png")
        await db.class_occurrences.update_one(
            {"id": occ["id"]},
            {"$set": {"cached_og": {
                "hash": key,
                "path": fresh_path,
                "bytes": len(data),
                "stored_at": datetime.utcnow().isoformat() + "Z",
            }}},
        )
    except Exception as exc:  # noqa: BLE001
        # Storage hiccup shouldn't break the preview — return the fresh
        # bytes to the scraper and log for later.
        logger.warning("og_cache: put failed — serving fresh (%s)", exc)
    return data, "fresh"


@router.get("/m/{slug}/c/{occ_id}/og.png")
async def class_og_image(slug: str, occ_id: str):
    """Render (or fetch from cache) a 1200x630 OG preview PNG.

    The cache key is a hash of the fields that affect the image (name,
    time, capacity, bookings_count, brand colour). When any of those
    change the next request triggers a re-render. All other requests
    come from object storage — a single PIL render per class per
    version, no matter how viral the post goes."""
    org, occ, tpl = await _resolve_class(slug, occ_id)
    data, source = await _get_or_render_og(org, occ, tpl)
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=600",
            "X-GymAxis-OG-Cache": source,
        },
    )


@router.get("/m/{slug}/c/{occ_id}/share", response_class=HTMLResponse)
async def class_share_html(slug: str, occ_id: str, request: Request):
    """Minimal HTML page with OG meta that social platforms scrape.

    Humans get a meta-refresh into the SPA page so the URL is still
    useful to paste anywhere.
    """
    org, occ, tpl = await _resolve_class(slug, occ_id)
    s = _class_share_strings(org, occ, tpl)

    base = str(request.base_url).rstrip("/")
    og_image = f"{base}/api/m/{slug}/c/{occ_id}/og.png"
    spa_url = f"{base}/m/{slug}/c/{occ_id}"

    title = f"{s['name']} · {s['org_name']}"
    description = f"{s['when']} · {s['spots_text']}. {s['description']}"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{og_image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:url" content="{spa_url}">
  <meta property="og:site_name" content="{s['org_name']}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{og_image}">
  <meta http-equiv="refresh" content="0; url={spa_url}">
  <link rel="canonical" href="{spa_url}">
  <style>
    body {{ margin:0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#0A0C10; color:#fff; min-height:100vh; display:grid; place-items:center; padding:24px; }}
    a {{ color:{s['primary_color']}; font-weight:700; }}
  </style>
</head>
<body>
  <div style="max-width:560px; text-align:center">
    <p style="opacity:.6; font-size:11px; letter-spacing:.22em; text-transform:uppercase; margin:0">{s['org_name']}</p>
    <h1 style="font-size:40px; margin:12px 0">{s['name']}</h1>
    <p style="opacity:.8; font-size:18px">{s['when']}</p>
    <p style="font-size:18px; color:{s['primary_color']}; font-weight:700">{s['spots_text']}</p>
    <p style="margin-top:32px"><a href="{spa_url}">Open booking page →</a></p>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=300"})
