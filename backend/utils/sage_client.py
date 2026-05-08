"""
Sage 200 UK · thin REST client (Phase 8 B · iter 215ea).

Wraps the existing OAuth2 config stored in `crm_integrations[type=sage200]`
and exposes per-kind dispatch methods used by the Sage outbox worker.

Entity coverage (per INTEGRATION_FIELD_MAPPING.md sections 18-21):
    SLInvoice (incl. SLInvoiceLine) — POST /sales-invoices    [kind="invoice"]
    SLQuote   (incl. SLQuoteLine)   — POST /sales-quotations  [kind="quote"]
    SLContract                       — POST /recurring-invoices [kind="contract"]
    Purchase orders                  — POST /purchase-orders   [kind="po"]

Auth model:
  Sage 200 UK uses OAuth2 (Confidential Client) — access tokens expire
  after 480 mins. The operator-facing config flow at
  `routes/crm_sage200.py` already stores access_token / refresh_token /
  token_expires_at on the config doc. This client reads that doc, refreshes
  the access_token if needed, and includes the X-Site / X-Company headers
  Sage 200 requires.

Endpoint mapping (per the credentials matrix in INTEGRATION_FIELD_MAPPING.md):

  invoice   → POST {base}/sales-invoices       (kind="invoice", status flow ready→submitted→posted)
  po        → POST {base}/purchase-orders      (kind="po",      status flow pending→submitted→posted)
  quote     → POST {base}/sales-quotations     (kind="quote",   currently unused; reserved for CRM CPQ Workstream B+)
  contract  → POST {base}/recurring-invoices   (kind="contract", reserved for CRM Contracts billing schedule)

Live HTTP only fires when the per-org config has `access_token` populated.
Otherwise the caller (sage_outbox_worker.tick) marks the row
`skipped_no_config` and leaves it pending.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from utils.database import db

logger = logging.getLogger(__name__)

SAGE_STANDARD_BASE = "https://api.columbus.sage.com/uk/sage200/accounts/v1"
SAGE_PROFESSIONAL_BASE = "https://api.columbus.sage.com/uk/sage200extra/accounts/v1"
SAGE_TOKEN_URL = "https://oauth.accounting.sage.com/token"

# Endpoint suffixes per kind. Override-able via `SAGE_ENDPOINT_OVERRIDE_<KIND>` env.
ENDPOINT_BY_KIND: dict[str, str] = {
    "invoice":  "/sales-invoices",
    "po":       "/purchase-orders",
    "quote":    "/sales-quotations",
    "contract": "/recurring-invoices",
}


class SageAPIError(Exception):
    def __init__(self, message: str, http_status: int = 0, payload: Optional[dict] = None):
        super().__init__(message)
        self.http_status = http_status
        self.payload = payload or {}


# ─────────────────────────────────────────────────────────────────
# Config + token management
# ─────────────────────────────────────────────────────────────────


async def get_sage_config(*, organization_id: Optional[str] = None) -> Optional[dict]:
    """Read the Sage 200 config doc.

    Today the existing CRM flow stores a single tenant-wide config keyed by
    {type:"sage200"}. If/when we go multi-tenant we'll switch to filtering
    by organization_id; the call sites already pass it through.
    """
    q: dict[str, Any] = {"type": "sage200"}
    if organization_id:
        q["organization_id"] = organization_id
    cfg = await db.crm_integrations.find_one(q, projection={"_id": 0})
    if cfg is None and organization_id:
        # Fall back to the global config (covers single-tenant deployments).
        cfg = await db.crm_integrations.find_one({"type": "sage200"}, projection={"_id": 0})
    return cfg


def _is_live_config(cfg: Optional[dict]) -> bool:
    """A Sage config is considered 'live' when it has an access_token AND
    either an explicit enabled flag OR no enabled flag at all (legacy)."""
    if not cfg:
        return False
    if not cfg.get("access_token"):
        return False
    if "enabled" in cfg:
        return bool(cfg["enabled"])
    return True  # legacy config without enabled flag — live if access_token present


def get_base_url(cfg: dict) -> str:
    edition = (cfg.get("edition") or cfg.get("tier") or "standard").lower()
    return SAGE_PROFESSIONAL_BASE if edition == "professional" else SAGE_STANDARD_BASE


async def _refresh_access_token(cfg: dict) -> dict:
    """Use the stored refresh_token to mint a fresh access_token.

    Persists the new tokens on the config doc and returns the updated doc.
    """
    if not cfg.get("refresh_token") or not cfg.get("client_id") or not cfg.get("client_secret"):
        raise SageAPIError("Cannot refresh Sage token — missing refresh_token / client_id / client_secret.", http_status=401)
    data = {
        "grant_type": "refresh_token",
        "refresh_token": cfg["refresh_token"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(SAGE_TOKEN_URL, data=data)
        if resp.status_code != 200:
            raise SageAPIError(f"Sage token refresh failed: {resp.status_code} {resp.text[:200]}",
                               http_status=resp.status_code)
        body = resp.json()
    expires_in = int(body.get("expires_in") or 3600)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    update = {
        "access_token": body.get("access_token"),
        "token_expires_at": expires_at,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.get("refresh_token"):
        update["refresh_token"] = body["refresh_token"]
    q: dict[str, Any] = {"type": "sage200"}
    if cfg.get("organization_id"):
        q["organization_id"] = cfg["organization_id"]
    await db.crm_integrations.update_one(q, {"$set": update})
    return {**cfg, **update}


def _is_token_stale(cfg: dict) -> bool:
    exp = cfg.get("token_expires_at")
    if not exp:
        return False
    try:
        dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
    except Exception:
        return False
    return dt <= datetime.now(timezone.utc) + timedelta(minutes=2)


async def _ensure_fresh_token(cfg: dict) -> dict:
    if _is_token_stale(cfg):
        return await _refresh_access_token(cfg)
    return cfg


def _build_headers(cfg: dict) -> dict:
    return {
        "Authorization": f"Bearer {cfg.get('access_token','')}",
        "X-Site": str(cfg.get("site_id", "")),
        "X-Company": str(cfg.get("company_id", "")),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ─────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────


async def post_payload(*, kind: str, payload: dict, organization_id: Optional[str] = None) -> dict:
    """POST a payload to the Sage 200 endpoint matching `kind`.

    Returns the parsed JSON response on 2xx; raises `SageAPIError` on
    config / network / 4xx-5xx failures.
    """
    if kind not in ENDPOINT_BY_KIND:
        raise SageAPIError(f"Unknown Sage outbox kind: {kind!r}", http_status=0)

    cfg = await get_sage_config(organization_id=organization_id)
    if not _is_live_config(cfg):
        raise SageAPIError("Sage 200 not configured for this organization", http_status=0)
    cfg = await _ensure_fresh_token(cfg)

    url = f"{get_base_url(cfg)}{ENDPOINT_BY_KIND[kind]}"
    headers = _build_headers(cfg)

    async with httpx.AsyncClient(timeout=30) as http:
        try:
            resp = await http.post(url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise SageAPIError(f"Sage transport error: {e}", http_status=0) from e

    if resp.status_code == 401:
        # Token may have just expired — refresh once and retry.
        cfg = await _refresh_access_token(cfg)
        headers = _build_headers(cfg)
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(url, json=payload, headers=headers)

    if resp.status_code >= 400:
        raise SageAPIError(
            f"Sage POST {kind} failed: {resp.status_code} {resp.text[:300]}",
            http_status=resp.status_code,
            payload=payload,
        )

    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


__all__ = [
    "SageAPIError",
    "ENDPOINT_BY_KIND",
    "get_sage_config",
    "get_base_url",
    "post_payload",
]
