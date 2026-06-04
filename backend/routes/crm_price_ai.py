"""CRM · Master Price List — AI support enhancements (Iter 220 P1).

Three small, opt-in LLM helpers that reuse the established Emergent LLM
integration (Claude Sonnet via `emergentintegrations`):

  1. POST /crm/products/{id}/ai-clean-description
     Grammar-only clean-up of a product description. PRESERVES meaning,
     facts, specs, numbers and product names — never invents content.
     Returns a suggestion for the editor to review (does NOT auto-save).

  2. POST /crm/price-list/import/ai-error-summary
     Turns a preview validation summary (counts + row-level issues) into
     a plain-English summary plus the worst-offending flagged rows.

  3. GET  /crm/price-list/ai-bundle-suggestions
     Proposes 3-5 sensible product bundles from the live catalogue. These
     are SUGGESTIONS ONLY — the editor chooses what (if anything) to create.
"""
from __future__ import annotations

import json
import logging
import os
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_products import _is_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm", tags=["CRM Price List · AI"])


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _require_admin(user: dict) -> None:
    if not _is_admin(user):
        raise HTTPException(403, "Only Price List editors (admin / owner / manager) can use AI tools")


async def _llm_text(system: str, prompt: str, *, session_prefix: str) -> str:
    """Single-shot Claude Sonnet call. Raises 503 on missing key / failure."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, "AI is not configured")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=api_key,
            session_id=f"{session_prefix}-{uuid.uuid4()}",
            system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        return (resp or "").strip()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface a friendly error to the UI
        logger.warning("CRM AI call failed (%s): %s", session_prefix, exc)
        raise HTTPException(503, "AI is temporarily unavailable — please try again") from exc


def _extract_json(text: str) -> dict:
    t = (text or "").strip()
    if "```" in t:
        t = t.split("```")[1].replace("json", "", 1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return {}


# ── 1. Clean description ───────────────────────────────────────────

@router.post("/products/{product_id}/ai-clean-description")
async def ai_clean_description(product_id: str, body: dict = Body(default={}), user=Depends(get_crm_user)) -> dict:
    _require_admin(user)
    p = await db.crm_products.find_one({"id": product_id, **_of(user)}, {"_id": 0, "name": 1, "description": 1})
    if not p:
        raise HTTPException(404, "Product not found")
    # Prefer the (possibly unsaved) text from the editor, fall back to stored.
    original = (body.get("description") if body.get("description") is not None else p.get("description")) or ""
    original = str(original).strip()
    if not original:
        raise HTTPException(422, "There is no description to improve")

    system = (
        "You are a meticulous product copy editor for a B2B catalogue. "
        "Improve ONLY grammar, spelling, punctuation, capitalisation and clarity "
        "of the description text you are given. PRESERVE the original meaning "
        "exactly: keep every fact, specification, measurement, number, model name, "
        "product name and brand unchanged. Do NOT add new claims, features or "
        "marketing language. Do NOT remove information. Edit the description "
        "AS PROVIDED — even if it seems unrelated to the product name, the name is "
        "context only; never replace, contradict or comment on the description. "
        "Keep British English spelling. Return ONLY the improved description text "
        "— no preamble, no notes, no quotes, no commentary."
    )
    prompt = f"Product: {p.get('name', '')}\n\nDescription to improve:\n{original}"
    suggestion = await _llm_text(system, prompt, session_prefix="pdesc")
    # Strip wrapping quotes/backticks the model might add.
    suggestion = suggestion.strip().strip("`").strip()
    if suggestion.startswith('"') and suggestion.endswith('"') and len(suggestion) > 1:
        suggestion = suggestion[1:-1].strip()
    return {"original": original, "suggestion": suggestion, "changed": suggestion != original}


# ── 2. Summarise import errors ─────────────────────────────────────

@router.post("/price-list/import/ai-error-summary")
async def ai_import_error_summary(body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    _require_admin(user)
    preview = body.get("preview") or {}
    if not isinstance(preview, dict) or not preview:
        raise HTTPException(422, "A preview summary is required")

    # Compact the payload — counts + a capped sample of row issues.
    counts = {k: preview.get(k) for k in (
        "total", "ready", "warnings", "errors", "new", "updates",
        "duplicates_in_file", "missing_name", "missing_price", "missing_sage",
        "negative_price", "cost_gt_sell", "unmapped_columns_total",
    ) if preview.get(k) is not None}
    issues = (preview.get("issues") or [])[:40]

    if not issues and not counts.get("errors") and not counts.get("warnings"):
        return {
            "summary": "No problems were found — every row is ready to import.",
            "flagged": [], "next_steps": [], "severity": "ok",
        }

    system = (
        "You help a non-technical gym operations user understand problems found "
        "while importing a product price-list spreadsheet into their CRM. Be "
        "concise, friendly and practical. British English. "
        "Return ONLY JSON: {\"summary\": string (2-4 plain-English sentences "
        "explaining what's wrong and how many rows are affected), \"flagged\": "
        "array of up to 8 of the most important rows as {\"row\": number, "
        "\"sheet\": string, \"code\": string, \"reason\": short string}, "
        "\"next_steps\": array of up to 4 short actionable bullet strings, "
        "\"severity\": one of \"ok\"|\"info\"|\"warning\"|\"error\"}."
    )
    prompt = (
        f"Validation counts:\n{json.dumps(counts, ensure_ascii=False)}\n\n"
        f"Row-level issues (sample):\n{json.dumps(issues, ensure_ascii=False)}"
    )
    out = _extract_json(await _llm_text(system, prompt, session_prefix="imperr"))
    if not out.get("summary"):
        # Deterministic fallback if the model returns something unparseable.
        errs, warns = counts.get("errors", 0), counts.get("warnings", 0)
        out = {
            "summary": f"{errs} row(s) cannot be imported and {warns} row(s) need review out of {counts.get('total', 0)} total.",
            "flagged": [{"row": i.get("row"), "sheet": i.get("sheet"), "code": i.get("code", ""), "reason": i.get("msg", "")} for i in issues[:8]],
            "next_steps": ["Fix the flagged rows in your spreadsheet and re-upload, or proceed and skip them."],
            "severity": "error" if errs else "warning",
        }
    out["flagged"] = (out.get("flagged") or [])[:8]
    out["next_steps"] = (out.get("next_steps") or [])[:4]
    return out


# ── 3. Suggest bundles ─────────────────────────────────────────────

@router.get("/price-list/ai-bundle-suggestions")
async def ai_bundle_suggestions(user=Depends(get_crm_user)) -> dict:
    _require_admin(user)
    cur = db.crm_products.find(
        {**_of(user), "active": True, "is_bundle": {"$ne": True}},
        {"_id": 0, "id": 1, "sku": 1, "name": 1, "category": 1, "sell_price": 1},
    ).sort([("category", 1), ("name", 1)]).limit(120)
    products = await cur.to_list(120)
    if len(products) < 3:
        raise HTTPException(422, "Add at least 3 products before requesting bundle suggestions")

    by_id = {p["id"]: p for p in products}
    catalogue = [
        {"id": p["id"], "sku": p.get("sku") or "", "name": p.get("name", ""),
         "category": p.get("category", ""), "sell": round(float(p.get("sell_price") or 0), 2)}
        for p in products
    ]
    system = (
        "You are a B2B fitness-equipment sales strategist. From the catalogue "
        "provided, propose practical product bundles a sales rep could offer "
        "(e.g. equipment + installation + a maintenance plan, or complementary "
        "items often bought together). These are SUGGESTIONS only. "
        "Use ONLY product ids that appear in the catalogue. British English. "
        "Return ONLY JSON: {\"suggestions\": array of 3-5 objects "
        "{\"name\": short bundle name, \"rationale\": one short sentence on why "
        "it sells together, \"component_ids\": array of 2-5 product ids from the "
        "catalogue}}. Do not invent ids or prices."
    )
    prompt = f"Catalogue:\n{json.dumps(catalogue, ensure_ascii=False)}"
    out = _extract_json(await _llm_text(system, prompt, session_prefix="bundle"))

    suggestions = []
    for s in (out.get("suggestions") or [])[:5]:
        ids = [i for i in (s.get("component_ids") or []) if i in by_id]
        # De-dupe while preserving order, need 2+ valid components.
        seen, comps = set(), []
        for i in ids:
            if i in seen:
                continue
            seen.add(i)
            p = by_id[i]
            comps.append({"product_id": i, "sku": p.get("sku") or "",
                          "name": p.get("name", ""), "sell_price": round(float(p.get("sell_price") or 0), 2)})
        if len(comps) < 2:
            continue
        suggestions.append({
            "name": str(s.get("name") or "Suggested bundle").strip()[:120],
            "rationale": str(s.get("rationale") or "").strip()[:240],
            "components": comps,
            "total_sell_price": round(sum(c["sell_price"] for c in comps), 2),
        })
    return {"suggestions": suggestions, "catalogue_size": len(products)}
