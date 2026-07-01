"""Machine Manual Library (Iter 376 + 379 enhancements).

Solves the "same manual uploaded hundreds of times" problem. A manual is
uploaded ONCE against a machine, stored in a shared library keyed by
**manufacturer + model**, and auto-linked to every machine in the org that
shares that make/model. Operators can also link an existing library manual
to additional machines.

Iter 379 enhancements:
  • **AI semantic de-dup** — beyond exact file-hash matching, a new upload's
    extracted text is fingerprinted and compared against existing manuals for
    the same make/model. Identical normalised content (e.g. the same manual
    re-saved as PDF vs DOCX, or re-scanned) is detected lexically, and the
    genuinely ambiguous middle ground is confirmed by an LLM. Duplicates are
    merged (links extended) instead of re-stored.
  • **Large-file object storage** — files above the inline threshold are kept
    in remote object storage (limit raised 5 MB → 50 MB) instead of inline
    base64. Small files stay inline for backward compatibility.
  • **Platform-curated global model manuals** — a Master Admin can upload (or
    promote an org manual to) a GLOBAL manual for a make/model. Global manuals
    surface to every org as one-click suggestions on matching machines and are
    cloned into the org's library when attached.

Master Admin sees the cross-org directory.

Collection ``machine_manuals``::

    {
        "id":              uuid,
        "organization_id": str | "__global__",
        "is_global":       bool,
        "manufacturer":    str,
        "model":           str,
        "make_model_key":  "<mfr lower>|<model lower>",
        "title":           str,
        "filename":        str,
        "content_type":    str,
        "size_bytes":      int,
        "sha256":          str,                 # exact-dup detection
        "content_fingerprint": str | None,      # normalised-text hash
        "text_excerpt":    str,                 # for semantic comparison
        "storage":         {"kind": "inline-base64", "data": b64}
                           | {"kind": "object", "path": key},
        "linked_equipment_ids": [str, ...],
        "cloned_from_global":   str | None,
        "uploaded_by":     user_id,
        "uploaded_at":     iso,
    }
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Form

from utils.auth import get_current_user
from utils.database import db, APP_NAME, EMERGENT_LLM_KEY, put_object, get_object
from utils.security_plus import safe_regex

router = APIRouter()
logger = logging.getLogger(__name__)

GLOBAL_ORG = "__global__"               # sentinel org for platform-curated manuals
MAX_BYTES = 25 * 1024 * 1024            # 25 MB hard limit (matches upload body-size tier)
INLINE_THRESHOLD = 2 * 1024 * 1024      # ≤2 MB stays inline; larger → object storage

# Semantic-dedup tuning.
_LEXICAL_DUP_RATIO = 0.90               # ≥ this lexical ratio → duplicate outright
_AI_REVIEW_FLOOR = 0.55                 # between floor & dup-ratio → ask the LLM


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(manufacturer: str, model: str) -> str:
    return f"{(manufacturer or '').strip().lower()}|{(model or '').strip().lower()}"


def _strip(doc: dict) -> dict:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k not in ("storage", "_id", "text_excerpt")}
    out["linked_count"] = len(doc.get("linked_equipment_ids") or [])
    out["has_body"] = bool((doc.get("storage") or {}).get("data")) or \
        bool((doc.get("storage") or {}).get("path"))
    out["is_global"] = bool(doc.get("is_global"))
    return out


# ───────────────────────── Text extraction + fingerprinting ─────────────────────────


def _extract_text(body: bytes, content_type: str, filename: str) -> str:
    """Best-effort plain-text extraction for semantic de-dup. Returns "" on
    any failure or for unsupported types (e.g. raw images)."""
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    try:
        if "pdf" in ct or name.endswith(".pdf"):
            import fitz  # PyMuPDF
            doc = fitz.open(stream=body, filetype="pdf")
            parts: list[str] = []
            for i, page in enumerate(doc):
                if i >= 30:  # cap pages — first 30 are plenty to fingerprint
                    break
                parts.append(page.get_text())
            doc.close()
            return "\n".join(parts)
        if name.endswith(".docx") or "wordprocessingml" in ct:
            import docx  # python-docx
            d = docx.Document(io.BytesIO(body))
            return "\n".join(p.text for p in d.paragraphs)
        if "text" in ct or name.endswith((".txt", ".md", ".rtf")):
            return body.decode("utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover
        logger.info("[manuals] text extraction failed (%s): %s", filename, exc)
    return ""


def _normalize_text(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _content_fingerprint(text: str) -> str | None:
    norm = _normalize_text(text)
    if len(norm) < 40:  # too little text to fingerprint reliably
        return None
    return hashlib.sha256(norm.encode()).hexdigest()


def _similarity(a: str, b: str) -> float:
    a2, b2 = _normalize_text(a)[:8000], _normalize_text(b)[:8000]
    if not a2 or not b2:
        return 0.0
    return SequenceMatcher(None, a2, b2).ratio()


async def _ai_same_manual(text_a: str, text_b: str) -> bool:
    """Ask the LLM whether two manual excerpts are the SAME document. Best
    effort — returns False on any failure / missing key."""
    if not EMERGENT_LLM_KEY or not text_a or not text_b:
        return False
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"manual-dedup-{uuid.uuid4().hex[:8]}",
            system_message=(
                "You compare two equipment-manual text excerpts and decide if "
                "they are the SAME manual (same document / content, possibly a "
                "different file format, scan, or revision). Reply with ONLY "
                "'yes' or 'no'."
            ),
        ).with_model("openai", "gpt-4o")
        prompt = (
            f"MANUAL A:\n{text_a[:2500]}\n\n"
            f"MANUAL B:\n{text_b[:2500]}\n\n"
            "Are these the same manual? Answer yes or no."
        )
        ans = await chat.send_message(UserMessage(text=prompt))
        return (ans or "").strip().lower().startswith("y")
    except Exception as exc:  # pragma: no cover
        logger.info("[manuals] AI dedup check skipped: %s", exc)
        return False


async def _find_semantic_duplicate(
    org_id: str, manufacturer: str, model: str,
    fingerprint: str | None, text: str,
) -> tuple[dict | None, str | None]:
    """Look for an existing manual (same org + make/model) whose content
    matches the new upload semantically. Returns (manual, method) or
    (None, None)."""
    if not text or len(_normalize_text(text)) < 40:
        return None, None
    candidates = await db.machine_manuals.find(
        {"organization_id": org_id, "make_model_key": _key(manufacturer, model)},
        {"_id": 0},
    ).to_list(length=50)
    if not candidates:
        return None, None

    # 1) Identical normalised-content fingerprint → exact semantic dup.
    if fingerprint:
        for c in candidates:
            if c.get("content_fingerprint") == fingerprint:
                return c, "semantic-exact"

    # 2) Lexical similarity on the stored excerpt; LLM confirms the middle.
    best, best_ratio = None, 0.0
    for c in candidates:
        cex = c.get("text_excerpt") or ""
        if not cex:
            continue
        r = _similarity(text, cex)
        if r > best_ratio:
            best_ratio, best = r, c
    if best is not None:
        if best_ratio >= _LEXICAL_DUP_RATIO:
            return best, f"semantic-lexical-{round(best_ratio, 2)}"
        if best_ratio >= _AI_REVIEW_FLOOR and await _ai_same_manual(text, best.get("text_excerpt") or ""):
            return best, "semantic-ai"
    return None, None


# ───────────────────────── Storage helpers ─────────────────────────


def _ext_for(filename: str, content_type: str) -> str:
    name = (filename or "").lower()
    if "." in name:
        return name.rsplit(".", 1)[-1][:8]
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return "pdf"
    if "word" in ct:
        return "docx"
    return "bin"


def _store_body(org_id: str, body: bytes, content_type: str, filename: str) -> dict:
    """Inline small files (base64) and offload large files to object storage."""
    if len(body) <= INLINE_THRESHOLD:
        return {"kind": "inline-base64", "data": base64.b64encode(body).decode()}
    path = f"{APP_NAME}/machine-manuals/{org_id}/{uuid.uuid4()}.{_ext_for(filename, content_type)}"
    put_object(path, body, content_type or "application/octet-stream")
    return {"kind": "object", "path": path}


def _read_body(manual: dict) -> bytes | None:
    storage = manual.get("storage") or {}
    if storage.get("kind") == "object" and storage.get("path"):
        data, _ct = get_object(storage["path"])
        return data
    if storage.get("data"):
        return base64.b64decode(storage["data"])
    return None


async def _matching_equipment_ids(org_id: str, manufacturer: str, model: str) -> list[str]:
    """All equipment in the org sharing this make+model (case-insensitive)."""
    if not manufacturer or not model:
        return []
    cursor = db.equipment.find(
        {
            "organization_id": org_id,
            "manufacturer": {"$regex": f"^{re.escape(manufacturer.strip())}$", "$options": "i"},
            "model": {"$regex": f"^{re.escape(model.strip())}$", "$options": "i"},
        },
        {"_id": 0, "id": 1},
    )
    return [e["id"] for e in await cursor.to_list(length=5000)]


async def _build_manual_doc(
    *, org_id: str, manufacturer: str, model: str, title: str,
    file: UploadFile, body: bytes, sha256: str, is_global: bool = False,
    link_ids: set[str] | None = None, uploaded_by: str | None = None,
    cloned_from_global: str | None = None,
) -> dict:
    text = _extract_text(body, file.content_type or "", file.filename or "")
    return {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "is_global": is_global,
        "manufacturer": manufacturer.strip()[:120],
        "model": model.strip()[:120],
        "make_model_key": _key(manufacturer, model),
        "title": (title.strip() or file.filename or "Manual")[:200],
        "filename": (file.filename or "manual")[:160],
        "content_type": file.content_type or "application/pdf",
        "size_bytes": len(body),
        "sha256": sha256,
        "content_fingerprint": _content_fingerprint(text),
        "text_excerpt": (text or "")[:6000],
        "storage": _store_body(org_id, body, file.content_type or "", file.filename or ""),
        "linked_equipment_ids": sorted(link_ids or set()),
        "cloned_from_global": cloned_from_global,
        "uploaded_by": uploaded_by,
        "uploaded_at": _now(),
    }


# ───────────────────────── Upload + de-dup ─────────────────────────


@router.post("/machine-manuals/upload")
async def upload_manual(
    file: UploadFile = File(...),
    manufacturer: str = Form(...),
    model: str = Form(...),
    title: str = Form(""),
    equipment_id: str = Form(""),
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload a manual against a machine. De-dupes by exact file hash AND by
    AI semantic content, auto-links to every machine in the org sharing the
    same manufacturer+model."""
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(400, "No organization context")
    if not manufacturer.strip() or not model.strip():
        raise HTTPException(400, "Manufacturer and model are required to file a manual")

    body = await file.read()
    if not body:
        raise HTTPException(400, "Empty upload")
    if len(body) > MAX_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_BYTES // 1024 // 1024} MB limit")

    sha256 = hashlib.sha256(body).hexdigest()
    auto_ids = await _matching_equipment_ids(org_id, manufacturer, model)
    link_ids = set(auto_ids)
    if equipment_id:
        link_ids.add(equipment_id)

    # 1) Exact-bytes dedup → reuse, just extend links.
    existing = await db.machine_manuals.find_one({"organization_id": org_id, "sha256": sha256})
    if existing:
        merged = sorted(set(existing.get("linked_equipment_ids") or []) | link_ids)
        await db.machine_manuals.update_one(
            {"id": existing["id"]}, {"$set": {"linked_equipment_ids": merged}}
        )
        existing["linked_equipment_ids"] = merged
        return {"manual": _strip(existing), "reused": True, "dedup_method": "exact-hash",
                "linked_count": len(merged)}

    # 2) AI semantic dedup → same content in a different file → reuse.
    text = _extract_text(body, file.content_type or "", file.filename or "")
    fingerprint = _content_fingerprint(text)
    dup, method = await _find_semantic_duplicate(org_id, manufacturer, model, fingerprint, text)
    if dup:
        merged = sorted(set(dup.get("linked_equipment_ids") or []) | link_ids)
        await db.machine_manuals.update_one(
            {"id": dup["id"]}, {"$set": {"linked_equipment_ids": merged}}
        )
        dup["linked_equipment_ids"] = merged
        return {"manual": _strip(dup), "reused": True, "dedup_method": method,
                "linked_count": len(merged)}

    # 3) New manual.
    doc = await _build_manual_doc(
        org_id=org_id, manufacturer=manufacturer, model=model, title=title,
        file=file, body=body, sha256=sha256, link_ids=link_ids,
        uploaded_by=user.get("id"),
    )
    await db.machine_manuals.insert_one(dict(doc))
    return {"manual": _strip(doc), "reused": False, "dedup_method": None,
            "linked_count": len(link_ids)}


@router.get("/machine-manuals")
async def list_manuals(
    equipment_id: str | None = None,
    q: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    """List the org's manuals. Filter to those linked to a specific machine
    (equipment_id) or fuzzy-search by manufacturer/model/title."""
    org_id = user.get("organization_id")
    query: dict[str, Any] = {"organization_id": org_id}
    if equipment_id:
        query["linked_equipment_ids"] = equipment_id
    if q:
        rx = safe_regex(q)
        query["$or"] = [{"manufacturer": rx}, {"model": rx}, {"title": rx}]
    cursor = db.machine_manuals.find(query, {"storage": 0, "text_excerpt": 0}).sort("uploaded_at", -1).limit(500)
    rows = await cursor.to_list(length=500)
    return {"manuals": [_strip(r) for r in rows]}


@router.get("/machine-manuals/global")
async def list_global_manuals(q: str | None = None, user: dict = Depends(get_current_user)) -> dict:
    """Browse the platform-curated global manual library (read-only for
    operators)."""
    query: dict[str, Any] = {"organization_id": GLOBAL_ORG, "is_global": True}
    if q:
        rx = safe_regex(q)
        query["$or"] = [{"manufacturer": rx}, {"model": rx}, {"title": rx}]
    rows = await db.machine_manuals.find(query, {"storage": 0, "text_excerpt": 0}).sort("uploaded_at", -1).limit(500).to_list(length=500)
    return {"manuals": [_strip(r) for r in rows]}


@router.get("/machine-manuals/suggestions")
async def suggest_manuals(equipment_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Library manuals (org + platform-global) that match this machine's
    make/model but are NOT yet linked to it — surfaced as one-click
    'attach existing' suggestions."""
    org_id = user.get("organization_id")
    eq = await db.equipment.find_one({"id": equipment_id, "organization_id": org_id}, {"_id": 0})
    if not eq:
        raise HTTPException(404, "Equipment not found")
    mk = _key(eq.get("manufacturer"), eq.get("model"))
    org_rows = await db.machine_manuals.find(
        {"organization_id": org_id, "make_model_key": mk},
        {"storage": 0, "text_excerpt": 0},
    ).to_list(length=100)
    out = [_strip(r) for r in org_rows if equipment_id not in (r.get("linked_equipment_ids") or [])]

    # Platform-curated globals for this make/model — exclude any the org has
    # already cloned.
    cloned = {r.get("cloned_from_global") for r in org_rows if r.get("cloned_from_global")}
    global_rows = await db.machine_manuals.find(
        {"organization_id": GLOBAL_ORG, "is_global": True, "make_model_key": mk},
        {"storage": 0, "text_excerpt": 0},
    ).to_list(length=100)
    for g in global_rows:
        if g["id"] not in cloned:
            out.append(_strip(g))

    return {"suggestions": out, "manufacturer": eq.get("manufacturer"), "model": eq.get("model")}


@router.post("/machine-manuals/{manual_id}/link")
async def link_manual(manual_id: str, payload: dict, user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    eq_ids = payload.get("equipment_ids") or []
    manual = await db.machine_manuals.find_one({"id": manual_id})
    if not manual:
        raise HTTPException(404, "Manual not found")

    # Linking a platform-global manual clones it into the org's library so the
    # org owns a normal, editable copy.
    if manual.get("is_global"):
        existing_clone = await db.machine_manuals.find_one(
            {"organization_id": org_id, "cloned_from_global": manual_id}
        )
        if existing_clone:
            merged = sorted(set(existing_clone.get("linked_equipment_ids") or []) | set(eq_ids))
            await db.machine_manuals.update_one(
                {"id": existing_clone["id"]}, {"$set": {"linked_equipment_ids": merged}}
            )
            return {"linked_count": len(merged), "cloned": False, "manual_id": existing_clone["id"]}
        clone = {k: v for k, v in manual.items() if k != "_id"}
        clone.update({
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "is_global": False,
            "cloned_from_global": manual_id,
            "linked_equipment_ids": sorted(set(eq_ids)),
            "uploaded_by": user.get("id"),
            "uploaded_at": _now(),
        })
        await db.machine_manuals.insert_one(dict(clone))
        return {"linked_count": len(eq_ids), "cloned": True, "manual_id": clone["id"]}

    if manual.get("organization_id") != org_id:
        raise HTTPException(404, "Manual not found")
    merged = sorted(set(manual.get("linked_equipment_ids") or []) | set(eq_ids))
    await db.machine_manuals.update_one({"id": manual_id}, {"$set": {"linked_equipment_ids": merged}})
    return {"linked_count": len(merged), "cloned": False, "manual_id": manual_id}


@router.post("/machine-manuals/{manual_id}/unlink")
async def unlink_manual(manual_id: str, payload: dict, user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    manual = await db.machine_manuals.find_one({"id": manual_id, "organization_id": org_id})
    if not manual:
        raise HTTPException(404, "Manual not found")
    eq_id = payload.get("equipment_id")
    remaining = [x for x in (manual.get("linked_equipment_ids") or []) if x != eq_id]
    await db.machine_manuals.update_one({"id": manual_id}, {"$set": {"linked_equipment_ids": remaining}})
    return {"linked_count": len(remaining)}


@router.get("/machine-manuals/{manual_id}/download")
async def download_manual(manual_id: str, user: dict = Depends(get_current_user)) -> Response:
    manual = await db.machine_manuals.find_one({"id": manual_id})
    if not manual:
        raise HTTPException(404, "Manual not found")
    # Access: master admin → any; global manuals → any authed user; otherwise
    # must belong to the requester's org.
    if not user.get("is_master_admin") and not manual.get("is_global") \
            and manual.get("organization_id") != user.get("organization_id"):
        raise HTTPException(404, "Manual not found")
    try:
        data = _read_body(manual)
    except Exception as exc:
        logger.warning("[manuals] body read failed for %s: %s", manual_id, exc)
        raise HTTPException(404, "Manual body unavailable") from exc
    if not data:
        raise HTTPException(404, "Manual body unavailable")
    return Response(
        content=data,
        media_type=manual.get("content_type", "application/pdf"),
        headers={"Content-Disposition": f'inline; filename="{manual.get("filename", "manual.pdf")}"'},
    )


@router.delete("/machine-manuals/{manual_id}")
async def delete_manual(manual_id: str, user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    # Global manuals can only be deleted by a master admin.
    manual = await db.machine_manuals.find_one({"id": manual_id})
    if not manual:
        raise HTTPException(404, "Manual not found")
    if manual.get("is_global") and not user.get("is_master_admin"):
        raise HTTPException(403, "Only a platform admin can delete a global manual")
    if not user.get("is_master_admin") and manual.get("organization_id") != org_id:
        raise HTTPException(404, "Manual not found")
    await db.machine_manuals.delete_one({"id": manual_id})
    return {"deleted": True}


# ───────────────────────── Master Admin: directory + globals ─────────────────────────


@router.get("/master-admin/machine-manuals/directory")
async def manuals_directory(user: dict = Depends(get_current_user)) -> dict:
    """Cross-org directory for Master Admin — includes platform-global manuals."""
    from utils.auth_guards import assert_platform_admin
    assert_platform_admin(user, "Master admin only")
    rows = await db.machine_manuals.find({}, {"storage": 0, "text_excerpt": 0}).sort("uploaded_at", -1).limit(2000).to_list(length=2000)
    org_ids = list({r.get("organization_id") for r in rows if r.get("organization_id") and r.get("organization_id") != GLOBAL_ORG})
    orgs = await db.organizations.find({"id": {"$in": org_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(length=2000)
    org_name = {o["id"]: o.get("name") for o in orgs}
    out = []
    for r in rows:
        s = _strip(r)
        s["organization_name"] = "🌐 Platform (global)" if r.get("is_global") \
            else org_name.get(r.get("organization_id"), "—")
        out.append(s)
    return {"manuals": out, "total": len(out)}


@router.post("/master-admin/machine-manuals/global/upload")
async def upload_global_manual(
    file: UploadFile = File(...),
    manufacturer: str = Form(...),
    model: str = Form(...),
    title: str = Form(""),
    user: dict = Depends(get_current_user),
) -> dict:
    """Master Admin uploads a platform-curated GLOBAL manual for a make/model.
    De-dupes globals by exact hash."""
    from utils.auth_guards import assert_platform_admin
    assert_platform_admin(user, "Master admin only")
    if not manufacturer.strip() or not model.strip():
        raise HTTPException(400, "Manufacturer and model are required")

    body = await file.read()
    if not body:
        raise HTTPException(400, "Empty upload")
    if len(body) > MAX_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_BYTES // 1024 // 1024} MB limit")

    sha256 = hashlib.sha256(body).hexdigest()
    existing = await db.machine_manuals.find_one(
        {"organization_id": GLOBAL_ORG, "is_global": True, "sha256": sha256}
    )
    if existing:
        return {"manual": _strip(existing), "reused": True}

    doc = await _build_manual_doc(
        org_id=GLOBAL_ORG, manufacturer=manufacturer, model=model, title=title,
        file=file, body=body, sha256=sha256, is_global=True,
        uploaded_by=user.get("id"),
    )
    await db.machine_manuals.insert_one(dict(doc))
    return {"manual": _strip(doc), "reused": False}


@router.post("/master-admin/machine-manuals/{manual_id}/promote-global")
async def promote_to_global(manual_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Promote an org-uploaded manual into the platform-global library (clones
    it; the org's original copy is left untouched)."""
    from utils.auth_guards import assert_platform_admin
    assert_platform_admin(user, "Master admin only")
    src = await db.machine_manuals.find_one({"id": manual_id})
    if not src:
        raise HTTPException(404, "Manual not found")
    if src.get("is_global"):
        return {"manual": _strip(src), "already_global": True}

    # Don't duplicate an identical global.
    existing = await db.machine_manuals.find_one(
        {"organization_id": GLOBAL_ORG, "is_global": True, "sha256": src.get("sha256")}
    )
    if existing:
        return {"manual": _strip(existing), "already_global": True}

    clone = {k: v for k, v in src.items() if k != "_id"}
    clone.update({
        "id": str(uuid.uuid4()),
        "organization_id": GLOBAL_ORG,
        "is_global": True,
        "cloned_from_global": None,
        "promoted_from": manual_id,
        "linked_equipment_ids": [],
        "uploaded_by": user.get("id"),
        "uploaded_at": _now(),
    })
    await db.machine_manuals.insert_one(dict(clone))
    return {"manual": _strip(clone), "already_global": False}


async def manuals_for_equipment(
    org_id: str, equipment_id: str | None = None, serial_number: str | None = None,
) -> list[dict]:
    """Compact list of manuals relevant to a machine, for AI triage / fault
    auto-attachment. Order: org manuals linked to the machine → org manuals
    matching its make/model → platform-global manuals matching make/model.
    De-duped, capped at 8."""
    if not org_id:
        return []
    eq = None
    if equipment_id:
        eq = await db.equipment.find_one(
            {"id": equipment_id, "organization_id": org_id},
            {"_id": 0, "id": 1, "manufacturer": 1, "model": 1},
        )
    if not eq and serial_number:
        eq = await db.equipment.find_one(
            {"organization_id": org_id,
             "$or": [{"serial_number": serial_number}, {"name": serial_number}]},
            {"_id": 0, "id": 1, "manufacturer": 1, "model": 1},
        )
    eq_id = (eq or {}).get("id") or equipment_id

    def _compact(m: dict) -> dict:
        return {
            "id": m["id"], "title": m.get("title"),
            "manufacturer": m.get("manufacturer"), "model": m.get("model"),
            "is_global": bool(m.get("is_global")),
            "linked_count": len(m.get("linked_equipment_ids") or []),
        }

    out: list[dict] = []
    seen: set[str] = set()
    proj = {"storage": 0, "text_excerpt": 0}

    if eq_id:
        async for m in db.machine_manuals.find(
            {"organization_id": org_id, "linked_equipment_ids": eq_id}, proj,
        ):
            if m["id"] not in seen:
                out.append(_compact(m)); seen.add(m["id"])

    if eq and eq.get("manufacturer") and eq.get("model"):
        mk = _key(eq.get("manufacturer"), eq.get("model"))
        async for m in db.machine_manuals.find(
            {"organization_id": org_id, "make_model_key": mk}, proj,
        ):
            if m["id"] not in seen:
                out.append(_compact(m)); seen.add(m["id"])
        async for m in db.machine_manuals.find(
            {"organization_id": GLOBAL_ORG, "is_global": True, "make_model_key": mk}, proj,
        ):
            if m["id"] not in seen:
                out.append(_compact(m)); seen.add(m["id"])

    return out[:8]


async def _ai_pinpoint(query: str, pages_map: dict[int, str]) -> dict | None:
    """One bounded LLM call: pick the most relevant page + section heading from
    a few candidate pages. Best-effort — returns None on any failure."""
    if not EMERGENT_LLM_KEY or not pages_map:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"pinpoint-{uuid.uuid4().hex[:8]}",
            system_message=(
                "You locate the single most relevant page/section in an equipment "
                "manual for a reported fault. Reply with ONLY compact JSON: "
                '{"page": <number>, "section": "<short section heading or topic>"}.'
            ),
        ).with_model("openai", "gpt-4o")
        body = (
            f"FAULT: {query[:400]}\n\nCANDIDATE PAGES:\n"
            + "\n".join(f"[page {k}]\n{v}" for k, v in pages_map.items())
            + "\n\nReturn ONLY the JSON object."
        )
        ans = await chat.send_message(UserMessage(text=body))
        import json as _j
        t = (ans or "").strip()
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            return _j.loads(t[i:j + 1])
    except Exception as exc:  # pragma: no cover
        logger.info("[manuals] AI pinpoint skipped: %s", exc)
    return None


def _extract_pdf_pages(body: bytes) -> list[str]:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=body, filetype="pdf")
        pages: list[str] = []
        for i, p in enumerate(doc):
            if i >= 80:
                break
            pages.append(p.get_text() or "")
        doc.close()
        return pages
    except Exception as exc:  # pragma: no cover
        logger.info("[manuals] pdf page extract failed: %s", exc)
        return []


def _query_terms(query: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (query or "").lower()) if len(t) >= 3]


def _lexical_best_page(pages: list[str], query: str) -> int | None:
    terms = _query_terms(query)
    if not terms or not pages:
        return None
    best_i, best_score = -1, 0.0
    for i, txt in enumerate(pages):
        low = (txt or "").lower()
        if not low:
            continue
        raw = sum(low.count(t) for t in terms)
        if raw <= 0:
            continue
        score = raw / (1 + len(low) / 4000.0)  # dampen very long pages
        if score > best_score:
            best_score, best_i = score, i
    return best_i if best_i >= 0 else None


def _snippet_around(text: str, query: str, width: int = 240) -> str:
    low = (text or "").lower()
    pos = -1
    for t in _query_terms(query):
        p = low.find(t)
        if p >= 0:
            pos = p
            break
    start = max(0, pos - 60) if pos >= 0 else 0
    return re.sub(r"\s+", " ", (text[start:start + width] or "").strip())


async def pinpoint_for_manual(manual_id: str, org_id: str, query: str) -> dict | None:
    """Find the most relevant PAGE + section of a (PDF) manual for a fault.
    Lexical pre-rank → one LLM call to refine. Best-effort; returns None when
    not a multi-page PDF or on any failure."""
    manual = await db.machine_manuals.find_one({"id": manual_id})
    if not manual:
        return None
    if not manual.get("is_global") and manual.get("organization_id") not in (org_id, GLOBAL_ORG):
        return None
    ct = (manual.get("content_type") or "").lower()
    fn = (manual.get("filename") or "").lower()
    if "pdf" not in ct and not fn.endswith(".pdf"):
        return None
    try:
        body = _read_body(manual)
    except Exception:
        return None
    if not body:
        return None
    pages = _extract_pdf_pages(body)
    if len(pages) < 2:
        return None
    best_i = _lexical_best_page(pages, query)
    if best_i is None:
        return None

    section, method = None, "lexical"
    cand_idxs = sorted({max(0, best_i - 1), best_i, min(len(pages) - 1, best_i + 1)})
    refined = await _ai_pinpoint(query, {i + 1: (pages[i] or "")[:1500] for i in cand_idxs})
    if refined:
        rp = refined.get("page")
        if isinstance(rp, int) and 1 <= rp <= len(pages):
            best_i = rp - 1
        section = (str(refined.get("section") or "").strip()[:120]) or None
        method = "ai"
    return {
        "page": best_i + 1,
        "page_count": len(pages),
        "section": section,
        "snippet": _snippet_around(pages[best_i], query)[:240],
        "method": method,
    }


async def ensure_machine_manuals_indexes() -> None:
    try:
        await db.machine_manuals.create_index([("organization_id", 1), ("uploaded_at", -1)])
        await db.machine_manuals.create_index([("organization_id", 1), ("sha256", 1)])
        await db.machine_manuals.create_index([("organization_id", 1), ("make_model_key", 1)])
        await db.machine_manuals.create_index([("is_global", 1), ("make_model_key", 1)])
        await db.machine_manuals.create_index([("linked_equipment_ids", 1)])
    except Exception:
        logger.exception("ensure_machine_manuals_indexes failed (non-fatal)")
