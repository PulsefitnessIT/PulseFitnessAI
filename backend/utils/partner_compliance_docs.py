"""Iter 216h283 — Partner Engineer compliance docs (DBS / RTW /
Safeguarding / Public Liability).

Closes Gap 4 from the BA audit: gym-entry compliance capture.

Design notes
------------
* **What we capture**: the 4 core docs gym operators ask for during
  procurement — DBS, Right to Work, Safeguarding training, Public
  Liability insurance.
* **Encryption**: certificate / share-code numbers are stored
  Fernet-encrypted at rest with the same `MFA_ENCRYPTION_KEY` (so a
  single key rotation covers both MFA and compliance). We also store
  the last 4 characters in cleartext so the engineer + admin can
  reference the doc without decryption on read.
* **Verification**: two-step. Engineer self-submits via
  `PUT /partners/me/compliance-docs`. AI checker runs automatically
  on every upload (GPT-4o vision via Emergent LLM Key). Master admin
  reviews the AI's output + the doc itself and signs off via
  `POST /master-admin/partners/{id}/verify-doc`.
* **Storage**: doc files use the same `put_object` flow as the
  existing application attachments — versioned per-doc-kind so the
  most recent upload is always queryable as
  `partner.compliance_docs[kind].file`.

Schema additions to `partner_engineers`
---------------------------------------

::

    compliance_docs: {
        dbs: {
            certificate_number_enc: str | null,
            certificate_last4: str | null,
            update_service_number_enc: str | null,
            update_service_last4: str | null,
            check_date: datetime | null,
            check_level: "basic"|"standard"|"enhanced"|"enhanced_barred" | null,
            expires_at: datetime | null,
            file: {storage_path, download_url, original_filename, ...} | null,
            ai_check: {confidence: float, document_type: str, extracted: {...}, checked_at} | null,
            verified_at: datetime | null,
            verified_by: str | null,  # admin user id
            uploaded_at: datetime | null,
        },
        rtw: { document_type, share_code_enc, share_code_last4, expires_at, file, ai_check, verified_at, verified_by, uploaded_at },
        safeguarding: { issuer, completed_at, expires_at, file, ai_check, verified_at, verified_by, uploaded_at },
        public_liability: { provider, policy_number_enc, policy_number_last4, cover_amount, expires_at, file, ai_check, verified_at, verified_by, uploaded_at },
    }
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from utils.mfa import encrypt_secret, decrypt_secret

logger = logging.getLogger(__name__)

# The four doc kinds we capture. Drives validation + sweep + UI.
DOC_KINDS = ("dbs", "rtw", "safeguarding", "public_liability")

DBS_LEVELS = {"basic", "standard", "enhanced", "enhanced_barred"}
RTW_DOC_TYPES = {
    "passport_uk",
    "passport_eu",
    "passport_other",
    "brp",                # biometric residence permit
    "share_code_settled", # EU Settled Status share code
    "share_code_other",
    "birth_cert",
    "naturalisation_cert",
}


# ── Encryption helpers (thin wrapper over MFA Fernet) ───────────────


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """Encrypt a sensitive reference number for at-rest storage. Returns
    None for empty input so we never store a meaningless ciphertext."""
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    return encrypt_secret(raw)


def decrypt_field(blob: Optional[str]) -> Optional[str]:
    """Reverse of :func:`encrypt_field`. Returns None on missing/bad input."""
    if not blob:
        return None
    try:
        return decrypt_secret(blob)
    except Exception as exc:  # noqa: BLE001
        logger.warning("compliance doc decrypt failed: %s", exc)
        return None


def last4(value: Optional[str]) -> Optional[str]:
    """Return the last 4 alphanumeric chars of a reference. Used as the
    cleartext companion to an encrypted field so the engineer/admin
    can identify a doc at a glance without paying the decrypt cost."""
    if not value:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(value))
    return cleaned[-4:] if len(cleaned) >= 4 else cleaned


# ── Doc-kind validation ────────────────────────────────────────────


def validate_kind(kind: str) -> str:
    """Raise if the doc kind isn't one we support."""
    if kind not in DOC_KINDS:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown doc kind '{kind}' — expected one of {sorted(DOC_KINDS)}")
    return kind


def default_doc_shell() -> dict:
    """Empty shell for a single doc kind. Stored once per kind so the
    UI never has to special-case "doc not started yet"."""
    return {
        "file": None,
        "ai_check": None,
        "verified_at": None,
        "verified_by": None,
        "uploaded_at": None,
    }


# ── AI verification ────────────────────────────────────────────────


_AI_SYSTEM = (
    "You are a compliance officer verifying a UK fitness-industry engineer's certificate. "
    "Look at the supplied image (or PDF first page) and return ONLY a single JSON object with: "
    "`document_type` (lowercase string — e.g. 'dbs_basic', 'dbs_enhanced', 'right_to_work', "
    "'safeguarding', 'public_liability', 'other'); "
    "`issuee_name` (string or null); "
    "`issuer` (string or null); "
    "`issue_date` (ISO date or null); "
    "`expiry_date` (ISO date or null); "
    "`certificate_number` (string or null); "
    "`confidence` (float 0.0-1.0 indicating how confident you are this looks genuine and matches the expected type); "
    "`notes` (short string, max 200 chars, of anything that looks off — blurriness, missing signature, mismatched name, etc). "
    "Do NOT wrap the JSON in markdown fences. Do NOT add commentary outside the JSON."
)


async def ai_check_document(
    file_bytes: bytes,
    content_type: str,
    expected_kind: str,
) -> dict:
    """Send an uploaded compliance doc image to OpenAI GPT-4o for OCR +
    legitimacy check. Returns a dict the route caller stores under
    ``compliance_docs[kind].ai_check`` and a ``matches_expected`` bool.

    On any failure (LLM down, parsing error, key missing) we return a
    structured "skipped" result rather than raising — the admin will
    still be able to verify manually.
    """
    result_skeleton: dict = {
        "checked_at": datetime.now(timezone.utc),
        "expected_kind": expected_kind,
        "confidence": 0.0,
        "document_type": None,
        "issuee_name": None,
        "issuer": None,
        "issue_date": None,
        "expiry_date": None,
        "certificate_number_last4": None,
        "matches_expected": False,
        "notes": "",
        "status": "skipped",
    }

    api_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not api_key:
        result_skeleton["notes"] = "EMERGENT_LLM_KEY not set — admin must verify manually."
        return result_skeleton

    # The Emergent integrations library is async-only and we use
    # GPT-4o for vision (4o-mini lacks image understanding consistency
    # for handwritten certs; 4o is worth the extra few cents per check).
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    except Exception as exc:  # noqa: BLE001
        result_skeleton["notes"] = f"emergentintegrations import failed: {exc}"
        return result_skeleton

    # PDFs are not supported by the vision API directly. The doc UI
    # rejects PDFs for now — but if one slips through we just bail.
    if not (content_type or "").startswith("image/"):
        result_skeleton["status"] = "unsupported"
        result_skeleton["notes"] = "AI check only runs on image uploads (PDFs need manual review)."
        return result_skeleton

    try:
        img_b64 = base64.b64encode(file_bytes).decode("ascii")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"compliance-{expected_kind}",
            system_message=_AI_SYSTEM,
        ).with_model("openai", "gpt-4o")
        user_msg = UserMessage(
            text=f"Check this {expected_kind.replace('_', ' ')} certificate.",
            file_contents=[ImageContent(image_base64=img_b64)],
        )
        raw = await chat.send_message(user_msg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI compliance check call failed: %s", exc)
        result_skeleton["notes"] = f"AI check error: {exc.__class__.__name__}"
        return result_skeleton

    # Try to parse the JSON the model returned. We don't trust the
    # model to skip code-fences so strip them defensively.
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        result_skeleton["notes"] = f"AI returned non-JSON: {exc.msg[:80]}"
        return result_skeleton

    # Map the model output to our skeleton, gating types defensively.
    doc_type_raw = (parsed.get("document_type") or "").strip().lower()
    confidence = parsed.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0

    # Build the "matches expected" rule per kind. We're conservative —
    # 0.6+ confidence AND the document type label has the kind name in
    # it.
    matches = confidence >= 0.6 and (
        expected_kind in doc_type_raw
        or {
            "dbs": "dbs" in doc_type_raw or "disclosure" in doc_type_raw,
            "rtw": "right_to_work" in doc_type_raw or "right to work" in doc_type_raw or "passport" in doc_type_raw,
            "safeguarding": "safeguard" in doc_type_raw or "child_protect" in doc_type_raw,
            "public_liability": "public_liability" in doc_type_raw or "liability" in doc_type_raw or "insurance" in doc_type_raw,
        }.get(expected_kind, False)
    )

    return {
        **result_skeleton,
        "status": "ok",
        "confidence": confidence,
        "document_type": doc_type_raw or None,
        "issuee_name": (parsed.get("issuee_name") or None),
        "issuer": (parsed.get("issuer") or None),
        "issue_date": parsed.get("issue_date") or None,
        "expiry_date": parsed.get("expiry_date") or None,
        "certificate_number_last4": last4(parsed.get("certificate_number")),
        "matches_expected": matches,
        "notes": (parsed.get("notes") or "")[:200],
    }


# ── Sanitisation for API responses ─────────────────────────────────


_SENSITIVE_SUFFIXES = ("_enc",)


def sanitise_docs_for_response(docs: dict | None) -> dict:
    """Strip every ``*_enc`` ciphertext field from the compliance_docs
    map before returning it to the engineer or admin. The cleartext
    last-4 companion fields remain so the UI can still display
    something useful."""
    if not docs:
        return {}
    cleaned: dict = {}
    for kind, blob in docs.items():
        if not isinstance(blob, dict):
            cleaned[kind] = blob
            continue
        cleaned[kind] = {k: v for k, v in blob.items() if not any(k.endswith(s) for s in _SENSITIVE_SUFFIXES)}
    return cleaned


def overall_status(docs: dict | None) -> dict:
    """Aggregate flag the dashboard reads to render a single traffic-
    light badge. Returns ``{verified_count, total: len(DOC_KINDS),
    blocked: bool}`` where ``blocked`` is True if any uploaded doc
    has expired."""
    if not docs:
        return {"verified_count": 0, "total": len(DOC_KINDS), "blocked": False, "complete": False}
    verified = 0
    blocked = False
    now = datetime.now(timezone.utc)
    for kind in DOC_KINDS:
        blob = docs.get(kind) or {}
        if blob.get("verified_at"):
            verified += 1
        # Check expiry
        exp = blob.get("expires_at")
        if isinstance(exp, datetime):
            exp_aware = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
            if exp_aware < now and blob.get("file"):
                blocked = True
    return {
        "verified_count": verified,
        "total": len(DOC_KINDS),
        "blocked": blocked,
        "complete": verified == len(DOC_KINDS),
    }
