"""AI Creative Studio (Gemini Nano Banana) + asset upload/list/delete.

Extracted from the legacy single-file routes/marketing.py during the
Pass 2 split. Endpoints, models, and helpers in this module retain
their original behaviour and tests.
"""
from __future__ import annotations

import base64
import os

import asyncio

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Response, UploadFile

from utils.auth import get_current_user
from utils.database import db
from utils.module_guard import require_module

from routes.marketing.helpers import (
    _get_entitlement,
    _new_id,
    _now_iso,
    _org_id,
    _require_feature,
    logger,
)
from routes.marketing.creative_storage import (
    can_create,
    migrate_assets,
    require_creator,
    store_data_url,
    store_image,
    variant_b64,
)
from utils.database import get_object

router = APIRouter()


# ───────────────────────── AI Creative Studio ─────────────────────────

RESOLUTION_PRESETS = {
    "instagram_square":    {"label": "Instagram square",    "width": 1080, "height": 1080, "aspect": "1:1"},
    "instagram_story":     {"label": "Instagram story",     "width": 1080, "height": 1920, "aspect": "9:16"},
    "facebook_feed":       {"label": "Facebook feed",       "width": 1200, "height": 630,  "aspect": "1.91:1"},
    "poster_vertical":     {"label": "Poster (4:5)",        "width": 1080, "height": 1350, "aspect": "4:5"},
    "poster_a4_portrait":  {"label": "A4 print portrait",   "width": 2480, "height": 3508, "aspect": "A4 portrait"},
    "poster_a4_landscape": {"label": "A4 print landscape",  "width": 3508, "height": 2480, "aspect": "A4 landscape"},
    "email_hero":          {"label": "Email hero (16:9)",   "width": 1600, "height": 900,  "aspect": "16:9"},
    "email_banner_wide":   {"label": "Email wide banner",   "width": 1600, "height": 600,  "aspect": "8:3"},
    "linkedin_post":       {"label": "LinkedIn post",       "width": 1200, "height": 1200, "aspect": "1:1"},
    "twitter_card":        {"label": "X / Twitter card",    "width": 1200, "height": 675,  "aspect": "16:9"},
    "youtube_thumb":       {"label": "YouTube thumbnail",   "width": 1280, "height": 720,  "aspect": "16:9"},
}


def _resolve_dimensions(body: dict) -> tuple[int, int, str]:
    """Return (width, height, descriptor). Custom dims override presets."""
    custom_w = body.get("custom_width")
    custom_h = body.get("custom_height")
    if custom_w and custom_h:
        try:
            w = max(256, min(int(custom_w), 4096))
            h = max(256, min(int(custom_h), 4096))
            return w, h, f"custom {w}x{h}"
        except (TypeError, ValueError):
            pass
    preset_id = body.get("resolution_preset") or "instagram_square"
    preset = RESOLUTION_PRESETS.get(preset_id) or RESOLUTION_PRESETS["instagram_square"]
    return preset["width"], preset["height"], preset["aspect"]


@router.get("/marketing/creative/resolutions")
async def list_resolutions(_: dict = Depends(get_current_user)):
    """Return the canonical list of resolution presets the UI offers."""
    return {"presets": [{"id": k, **v} for k, v in RESOLUTION_PRESETS.items()]}


def _public(asset: dict) -> dict:
    """Asset as returned to clients — never exposes raw storage paths."""
    out = {k: v for k, v in asset.items() if k != "_id"}
    out["variants"] = [{k: v for k, v in x.items() if k != "storage_path"} for x in out.get("variants") or []]
    return out


@router.post("/marketing/creative/generate", dependencies=[Depends(require_module("marketing"))])
async def generate_creative(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Generate marketing imagery via OpenAI gpt-image-1 through the
    emergentintegrations stack. Falls back to a placeholder gradient if the
    integration is unavailable so the UX still works in dev mode.

    DEFERRED: True multi-image pixel composition (where uploaded logos, faces,
    and equipment shots are baked into the output verbatim) requires the
    OpenAI Image Edits API with multiple `image[]` inputs. The
    emergentintegrations SDK currently only exposes single-prompt
    `generate_images()`. When multi-image input lands we will:
      • call `image_gen.edit_images(prompt=..., images=[logo, face, equip])`
      • drop the descriptive `Composition references` block from the prompt
    For now we describe each reference asset's category + label in the
    prompt itself — gpt-image-1 honours these fairly well for style/subject
    cues.

    Extended fields:
      • headline                  poster text overlay
      • subheadline               sub-line for the poster
      • call_to_action            CTA button label (e.g. "Join free this week")
      • resolution_preset         key from RESOLUTION_PRESETS, OR
      • custom_width/height       arbitrary integer dims (256–4096)
      • reference_asset_ids       list of marketing_creative_assets IDs that
                                  should inform the composition (logos, faces,
                                  equipment shots etc.). They are described in
                                  the prompt so gpt-image-1 incorporates the
                                  style, since the SDK doesn't yet take
                                  multi-image inputs.
      • mood                      free-form (e.g. "energetic", "calm")
      • style                     visual style (photorealistic, illustrated…)
    """
    require_creator(user)
    org_id = await _org_id(user)
    entitlement = await _get_entitlement(user)
    _require_feature(entitlement, "ai_creative_studio")

    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "Prompt is required")
    asset_type = body.get("type") or "social_post"
    n = max(1, min(int(body.get("n") or 1), 4))
    headline = (body.get("headline") or "").strip()
    subheadline = (body.get("subheadline") or "").strip()
    cta = (body.get("call_to_action") or "").strip()
    mood = (body.get("mood") or "").strip()
    style = (body.get("style") or "photorealistic").strip()
    width, height, aspect_descriptor = _resolve_dimensions(body)

    ref_ids = body.get("reference_asset_ids") or []
    if isinstance(ref_ids, list) and ref_ids:
        ref_ids = [str(x) for x in ref_ids if x][:6]  # cap to 6 references
    else:
        ref_ids = []
    refs = []
    if ref_ids:
        refs = await db.marketing_creative_assets.find(
            {"organization_id": org_id, "id": {"$in": ref_ids}},
            {"_id": 0, "id": 1, "category": 1, "prompt": 1, "filename": 1,
             "label": 1, "variants": 1},
        ).to_list(10)

    # Extract base64 image data from reference asset variants so we can
    # pass them as actual visual inputs to Gemini Nano Banana (not just
    # text descriptors).
    reference_b64s: list[str] = []
    for r in refs:
        data = await variant_b64((r.get("variants") or [{}])[0] or {})
        if data:
            reference_b64s.append(data)

    # Compose brand-aware + multi-input prompt
    brand_kit = await db.marketing_brand_kit.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    brand_lock = bool(body.get("brand_lock"))
    primary_logo_url = None
    if brand_lock:
        # Find this org's primary logo (first user_upload tagged as logo).
        logo_asset = await db.marketing_creative_assets.find_one(
            {"organization_id": org_id, "category": "logo", "type": "user_upload"},
            {"_id": 0, "filename": 1, "label": 1},
            sort=[("created_at", 1)],
        )
        if logo_asset:
            primary_logo_url = logo_asset.get("label") or logo_asset.get("filename") or "primary brand logo"
    ref_lines = []
    for r in refs:
        cat = (r.get("category") or "asset").lower()
        descriptor = r.get("label") or r.get("prompt") or r.get("filename") or "uploaded asset"
        ref_lines.append(f"- {cat}: {descriptor}")
    ref_block = ("Composition references (incorporate the look of):\n" + "\n".join(ref_lines)) if ref_lines else ""
    text_block_parts = []
    if headline:
        text_block_parts.append(f'main headline "{headline}"')
    if subheadline:
        text_block_parts.append(f'subheadline "{subheadline}"')
    if cta:
        text_block_parts.append(f'call-to-action button "{cta}"')
    text_block = (
        "Render this exact text on the poster as crisp typographic overlay: "
        + "; ".join(text_block_parts) + "."
    ) if text_block_parts else "No text overlays."
    framing = {
        "poster": f"{aspect_descriptor} poster composition, dramatic lighting",
        "email_hero": f"{aspect_descriptor} email hero, light background, headline space at top",
        "social_post": f"{aspect_descriptor} social feed image, vibrant",
    }.get(asset_type, f"{aspect_descriptor} composition")
    full_prompt = (
        f"{prompt}. {framing}. "
        f"Visual style: {style}. {f'Mood: {mood}.' if mood else ''} "
        f"Brand palette: primary {brand_kit.get('primary_color', '#0055FF')}, secondary {brand_kit.get('secondary_color', '#66CCFF')}. "
        f"{('BRAND LOCK: every poster MUST feature the brand primary logo (' + (primary_logo_url or 'brand logo') + ') in the top-left or bottom-right corner with a subtle protective shadow, must use ONLY the palette above (no other accent colours), and must use the brand typography style (modern bold sans-serif).') if brand_lock else ''}"
        f"{ref_block}\n{text_block} Professional fitness marketing. Print-quality, sharp."
    ).strip()

    variants: list[dict] = []
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "Image generation is not configured")
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent  # type: ignore
    file_contents = [ImageContent(b) for b in reference_b64s]
    model_id = "gemini-3.1-flash-image-preview"

    async def _one_variant() -> list[dict]:
        # Fresh chat per variant — Nano Banana is non-deterministic, giving natural variation.
        chat = LlmChat(
            api_key=api_key,
            session_id=f"creative-{org_id}-{_new_id()}",
            system_message="You are a senior fitness brand art director. Output a high-impact poster image.",
        )
        chat.with_model("gemini", model_id).with_params(modalities=["image", "text"])
        msg = UserMessage(text=full_prompt, file_contents=file_contents or None)
        try:
            _text, images = await chat.send_message_multimodal_response(msg)
        except Exception as exc:  # noqa: BLE001
            logger.info("[marketing] nano banana variant failed: %s", exc)
            return []
        out = []
        for img in (images or []):
            b64_data = img.get("data") if isinstance(img, dict) else None
            if b64_data:
                out.append(await store_image(org_id, base64.b64decode(b64_data),
                                             img.get("mime_type") or "image/png", model_id))
        return out

    for chunk in await asyncio.gather(*[_one_variant() for _ in range(n)]):
        variants.extend(chunk)
    if not variants:
        raise HTTPException(502, "The image AI couldn't create an image this time — please try again or simplify the prompt.")

    asset = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "type": asset_type, "prompt": prompt,
        "headline": headline or None, "subheadline": subheadline or None,
        "call_to_action": cta or None, "mood": mood or None, "style": style,
        "width": width, "height": height, "aspect": aspect_descriptor,
        "reference_asset_ids": ref_ids,
        "reference_count": len(reference_b64s),
        "brand_lock": brand_lock,
        "brand_kit_applied": bool(brand_kit),
        "source": model_id,
        "variants": variants,
        "used_by_campaign_ids": [], "used_by_post_ids": [],
        "created_at": _now_iso(),
    }
    await db.marketing_creative_assets.insert_one(asset)
    await db.marketing_subscriptions.update_one(
        {"organization_id": org_id}, {"$inc": {"usage_this_period.ai_generations": len(variants)}},
    )
    return {"asset": _public(asset)}


@router.post("/marketing/creative/import-brand-asset", dependencies=[Depends(require_module("marketing"))])
async def import_brand_library_asset(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Import a master-admin curated image from the shared Marketing
    library into the operator's own asset library so it can be selected
    as a composition reference.

    Iter 238g — completes the round-trip wire-up of
    `/api/marketing/image-library` into the Creative Studio picker.
    """
    require_creator(user)
    org_id = await _org_id(user)
    entitlement = await _get_entitlement(user)
    _require_feature(entitlement, "ai_creative_studio")

    library_id = (body.get("library_id") or "").strip()
    if not library_id:
        raise HTTPException(400, "library_id required")

    lib_row = await db.marketing_image_library.find_one(
        {"id": library_id, "enabled": True}, {"_id": 0},
    )
    if not lib_row:
        raise HTTPException(404, "Brand library image not found or disabled")

    # Avoid duplicating: if this org has already imported this library
    # asset, just return the existing copy.
    existing = await db.marketing_creative_assets.find_one(
        {"organization_id": org_id, "source": "brand_library", "library_id": library_id},
        {"_id": 0},
    )
    if existing:
        return {"asset": _public(existing), "reused": True}

    src_url = (lib_row.get("url") or "").strip()
    data_url = src_url
    # Convert remote URLs into a `data:` URL so the existing reference
    # pipeline (which only handles base64) works without changes.
    if src_url.startswith(("http://", "https://")):
        try:
            import httpx  # local import — keeps optional dep cheap
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(src_url)
            if resp.status_code != 200:
                raise HTTPException(502, f"Brand library image fetch failed: {resp.status_code}")
            mime = resp.headers.get("content-type", "image/jpeg").split(";", 1)[0].strip()
            if not mime.startswith("image/"):
                raise HTTPException(502, "Brand library URL did not return an image")
            data_url = f"data:{mime};base64," + base64.b64encode(resp.content).decode()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"Could not download brand library image: {exc}") from exc

    asset = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "type": "user_upload", "category": (lib_row.get("category") or "photo"),
        "prompt": lib_row.get("label") or "Brand library image",
        "filename": lib_row.get("label") or "brand_library_image",
        "label": lib_row.get("label"),
        "tags": lib_row.get("tags") or [],
        "brand_kit_applied": False,
        "source": "brand_library",
        "library_id": library_id,
        "variants": [await store_data_url(org_id, data_url, "brand_library")],
        "used_by_campaign_ids": [], "used_by_post_ids": [],
        "created_at": _now_iso(),
    }
    await db.marketing_creative_assets.insert_one(asset.copy())
    return {"asset": _public(asset), "reused": False}


@router.post("/marketing/creative/upload", dependencies=[Depends(require_module("marketing"))])
async def upload_creative(
    file: UploadFile = File(...),
    category: str = Form("other"),
    label: str = Form(""),
    user: dict = Depends(get_current_user),
):
    """Upload the user's own image so it appears alongside AI-generated assets
    in the Creative Studio gallery.

    Categories help the poster builder reason about the asset:
      • logo       — brand or partner logo (will be respected as-is)
      • face       — a person whose look should appear in generated imagery
      • equipment  — a piece of equipment to feature
      • photo      — a general photo (default)
      • other
    """
    require_creator(user)
    org_id = await _org_id(user)
    entitlement = await _get_entitlement(user)
    _require_feature(entitlement, "ai_creative_studio")

    if file.content_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        raise HTTPException(400, "Unsupported image type — use PNG, JPEG, WebP, or GIF")
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image too large — max 5 MB")
    stored = await store_image(org_id, raw, file.content_type, "user_upload")
    cat = (category or "other").strip().lower()
    if cat not in ("logo", "face", "equipment", "photo", "other"):
        cat = "other"
    asset = {
        "id": _new_id(), "organization_id": org_id, "created_by": user["id"],
        "type": "user_upload", "category": cat,
        "prompt": file.filename or "Uploaded image",
        "filename": file.filename,
        "label": (label or "").strip() or None,
        "brand_kit_applied": False, "source": "user_upload",
        "variants": [stored],
        "used_by_campaign_ids": [], "used_by_post_ids": [],
        "created_at": _now_iso(),
    }
    await db.marketing_creative_assets.insert_one(asset)
    return {"asset": _public(asset)}


@router.delete("/marketing/creative/{asset_id}", dependencies=[Depends(require_module("marketing"))])
async def delete_creative(asset_id: str, user: dict = Depends(get_current_user)):
    require_creator(user)
    org_id = await _org_id(user)
    res = await db.marketing_creative_assets.delete_one({"id": asset_id, "organization_id": org_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Asset not found")
    return {"deleted": True}


@router.get("/marketing/creative", dependencies=[Depends(require_module("marketing"))])
async def list_creative(user: dict = Depends(get_current_user)):
    org_id = await _org_id(user)
    items = await db.marketing_creative_assets.find(
        {"organization_id": org_id}, {"_id": 0},
    ).sort("created_at", -1).limit(60).to_list(length=60)
    await migrate_assets(items)  # lazily move legacy base64 images into storage
    return {"assets": [_public(a) for a in items], "can_create": can_create(user)}


@router.get("/marketing/creative/file/{token}")
async def creative_file(token: str, download: bool = Query(False)):
    """Serve a stored Creative Studio image by its unguessable token."""
    asset = await db.marketing_creative_assets.find_one(
        {"variants.token": token}, {"_id": 0, "id": 1, "variants": 1})
    v = next((x for x in (asset or {}).get("variants") or [] if x.get("token") == token), None)
    if not v or not v.get("storage_path"):
        raise HTTPException(404, "Image not found")
    data, ctype = await asyncio.to_thread(get_object, v["storage_path"])
    mime = v.get("mime") or ctype
    headers = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"}
    if download:
        ext = (v["storage_path"].rsplit(".", 1) + ["png"])[1]
        headers["Content-Disposition"] = f'attachment; filename="creative-{asset["id"][:8]}.{ext}"'
    return Response(content=data, media_type=mime, headers=headers)
