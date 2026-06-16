"""
Orbit4 API client + deep field mappers (Phase α-δ).

Phases:
- α  Inbound: full ticket + asset field capture with conversation + attachments
- β  Inbound: new event handlers (asset.created/updated/moved, note.created, media.created, user.created)
- γ  Outbound: mirror Pulse Fitness equipment + CRM contracts into Orbit4
- δ  Outbound: mirror Pulse Fitness faults (tickets) with status transitions
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ╭────────────────────── constants ──────────────────────╮

ORBIT4_LANG_ENUM = {"en", "es", "de", "bg", "pt", "fr", "jp", "tr", "ar", "zh",
                    "zh-Hant", "hi", "bn", "pl", "id", "th", "vi", "el"}

ORBIT4_SUPPORTED_EVENTS = {
    "ticket.created", "ticket.updated", "ticket.closed",
    "asset.created", "asset.updated", "asset.moved",
    "note.created", "media.created",
    "user.created", "user.updated",
}

# Our severity → Orbit4 ticket priority
GYMAXIS_SEVERITY_TO_ORBIT4 = {
    "safety_critical": "critical",
    "critical": "high",
    "high": "high",
    "medium": "normal",
    "low": "low",
}

# Orbit4 ticket priority → Pulse Fitness severity
ORBIT4_PRIORITY_TO_GYMAXIS = {
    "critical": "critical",
    "urgent": "critical",
    "high": "high",
    "normal": "medium",
    "medium": "medium",
    "low": "low",
}


# ╭────────────────────── exceptions ─────────────────────╮

class Orbit4APIError(Exception):
    """Raised on non-2xx responses from Orbit4."""


# ╭────────────────────── client ─────────────────────────╮

class Orbit4Client:
    """Thin async client over the Orbit4 REST API."""

    def __init__(self, base_url: str, api_token: str,
                 user_agent: str = "PulseFitness-ServiceBridge/1.0",
                 timeout: int = 30):
        self.base_url = (base_url or "https://api.orbit4.org/v1").rstrip("/")
        self.api_token = api_token
        self.user_agent = user_agent
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

    async def _request(self, method: str, path: str,
                       params: Optional[Dict] = None,
                       json_body: Optional[Dict] = None) -> Dict:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.request(
                method, url, headers=self._headers(),
                params=params, json=json_body,
            )
        if resp.status_code >= 400:
            raise Orbit4APIError(f"{method} {path} → {resp.status_code}: {resp.text[:250]}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # ── Assets ──────────────────────────────────────
    async def list_assets(self, **params) -> Dict:
        return await self._request("GET", "/assets", params=params)

    async def get_asset(self, asset_id: int) -> Dict:
        return await self._request("GET", f"/assets/{asset_id}")

    async def create_asset(self, payload: Dict) -> Dict:
        return await self._request("POST", "/assets", json_body=payload)

    async def update_asset(self, asset_id: int, payload: Dict) -> Dict:
        return await self._request("PUT", f"/assets/{asset_id}", json_body=payload)

    async def delete_asset(self, asset_id: int) -> Dict:
        return await self._request("DELETE", f"/assets/{asset_id}")

    # ── Contracts ───────────────────────────────────
    async def list_contracts(self, **params) -> Dict:
        return await self._request("GET", "/contracts", params=params)

    async def create_contract(self, payload: Dict) -> Dict:
        return await self._request("POST", "/contracts", json_body=payload)

    # ── Tickets ─────────────────────────────────────
    async def create_ticket(self, contract_id: int, payload: Dict) -> Dict:
        return await self._request("POST", f"/contracts/{contract_id}/tickets", json_body=payload)

    async def update_ticket(self, ticket_id: int, payload: Dict) -> Dict:
        return await self._request("PUT", f"/tickets/{ticket_id}", json_body=payload)

    async def close_ticket(self, ticket_id: int, payload: Optional[Dict] = None) -> Dict:
        return await self._request("POST", f"/tickets/{ticket_id}/close", json_body=payload or {})

    async def add_ticket_note(self, ticket_id: int, note: str, user_id: Optional[int] = None) -> Dict:
        body: Dict = {"note": note}
        if user_id:
            body["user_id"] = int(user_id)
        return await self._request("POST", f"/tickets/{ticket_id}/notes", json_body=body)

    # ── Users ───────────────────────────────────────
    async def create_user(self, payload: Dict) -> Dict:
        return await self._request("POST", "/users", json_body=payload)

    async def update_user(self, user_id: int, payload: Dict) -> Dict:
        return await self._request("PUT", f"/users/{user_id}", json_body=payload)

    async def link_user(self, parent_id: int, child_id: int) -> Dict:
        return await self._request("POST", f"/users/{parent_id}/link",
                                   json_body={"child_id": int(child_id)})


# ╭────────────────── Inbound mappers (Phase α) ─────────────────╮

def _iso_or_none(value: Any) -> Optional[str]:
    if not value:
        return None
    return str(value)


def _user_summary(user: Optional[Dict]) -> Dict:
    if not user:
        return {}
    return {
        "id": user.get("id"),
        "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
        "email": user.get("email"),
        "role": user.get("role"),
        "site_name": user.get("site_name"),
        "company_name": (user.get("company") or {}).get("name"),
    }


def map_orbit4_asset_to_gymaxis(asset: Dict) -> Dict:
    """Phase α — extract every mappable field from an Orbit4 asset."""
    return {
        "orbit4_asset_id": asset.get("id"),
        "orbit4_product_id": asset.get("product_id"),
        "orbit4_qr_code": asset.get("qr_code"),
        "serial_number": asset.get("serial_number") or "",
        "manufacturer": asset.get("brand") or "",
        "model": asset.get("range") or "",
        "equipment_type": asset.get("product") or "",
        "install_date": _iso_or_none(asset.get("installation_date")),
        "manufacturing_date": _iso_or_none(asset.get("manufacturing_date")),
        "warranty_expiry": _iso_or_none(asset.get("warranty_end_date")),
        "orbit4_deprecation_date": _iso_or_none(asset.get("deprecation_date")),
        "orbit4_current_spend": asset.get("current_spend"),
        "orbit4_max_spend": asset.get("max_spend"),
        "orbit4_residual_price": asset.get("residual_price"),
        "orbit4_fitness_product": bool(asset.get("fitness_product")),
        "orbit4_has_odometer": bool(asset.get("has_odometer")),
        "orbit4_image_url": asset.get("image"),
        "orbit4_metadata": asset.get("metadata") or {},
    }


def map_orbit4_contract_to_gymaxis(contract: Dict) -> Dict:
    return {
        "orbit4_contract_id": contract.get("id"),
        "contract_number": contract.get("number"),
        "contract_type": contract.get("type"),
        "active": bool(contract.get("active", False)),
        "start_date": _iso_or_none(contract.get("start_date")),
        "end_date": _iso_or_none(contract.get("end_date")),
        "orbit4_gym_operator": _user_summary(contract.get("gym_operator")),
        "orbit4_service_provider": _user_summary(contract.get("service_provider")),
        "orbit4_metadata": contract.get("metadata") or {},
    }


def _pluck_attachments(ticket: Dict) -> List[Dict]:
    """Flatten Orbit4's media[] / images[] / documents[] into a single list."""
    out: List[Dict] = []
    for bucket in ("media", "images", "documents"):
        for item in ticket.get(bucket) or []:
            out.append({
                "id": item.get("id"),
                "url": item.get("url"),
                "type": item.get("type") or bucket[:-1],
                "source": "orbit4",
                "created_at": item.get("created_at"),
            })
    return out


def _pluck_notes(ticket: Dict) -> List[Dict]:
    notes = ticket.get("notes") or []
    return [
        {
            "type": "orbit4_note",
            "message": n.get("note") or "",
            "by": _user_summary(n.get("user")).get("name") or "Orbit4",
            "is_system": bool(n.get("is_system")),
            "timestamp": n.get("created_at"),
        }
        for n in notes
    ]


def _contract_summary(ticket: Dict) -> Dict:
    contract = ticket.get("contract") or {}
    if not contract:
        return {}
    return {
        "id": contract.get("id"),
        "number": contract.get("number"),
        "type": contract.get("type"),
        "active": contract.get("active"),
        "start_date": contract.get("start_date"),
        "end_date": contract.get("end_date"),
    }


def _ticket_ids_block(ticket: Dict) -> Dict:
    return {
        "orbit4_ticket_id": str(ticket.get("id") or ""),
        "orbit4_ticket_number": ticket.get("number") or "",
        "orbit4_status": ticket.get("status") or "",
        "orbit4_type": ticket.get("type") or "",
        "orbit4_problem_type": ticket.get("problem_type") or "",
        "orbit4_priority": ticket.get("priority"),
        "orbit4_tags": ticket.get("tags") or [],
    }


def _ticket_lifecycle_block(ticket: Dict) -> Dict:
    return {
        "orbit4_engineer_deployed_at": _iso_or_none(ticket.get("engineer_deployed_at")),
        "orbit4_engineer_arrived_at": _iso_or_none(ticket.get("engineer_arrived_at")),
        "orbit4_closed_at": _iso_or_none(ticket.get("closed_at")),
        "orbit4_created_at": _iso_or_none(ticket.get("created_at")),
    }


def _ticket_parties_block(ticket: Dict) -> Dict:
    return {
        "orbit4_gym_operator": _user_summary(ticket.get("gym_operator")),
        "orbit4_service_provider": _user_summary(ticket.get("service_provider")),
        "orbit4_ticket_admin": _user_summary(ticket.get("ticket_admin")),
        "orbit4_engineer": _user_summary(ticket.get("engineer")),
        "orbit4_caretaker": _user_summary(ticket.get("caretaker")),
    }


def map_orbit4_ticket_full(ticket: Dict) -> Dict:
    """Phase α — capture every mappable field from an Orbit4 ticket payload."""
    asset = ticket.get("asset") or {}
    description = ticket.get("description") or ""
    payload: Dict = {
        "description": description,
        "issue_description": description,
        "subject": f"Orbit4 #{ticket.get('number', '')} — {asset.get('product', 'Unknown Equipment')}",
        **_ticket_ids_block(ticket),
        **_ticket_lifecycle_block(ticket),
        **_ticket_parties_block(ticket),
        "severity": ORBIT4_PRIORITY_TO_GYMAXIS.get(
            str(ticket.get("priority") or "normal").lower(), "medium",
        ),
        "orbit4_contract": _contract_summary(ticket),
        "orbit4_metadata": ticket.get("metadata") or {},
        "orbit4_attachments": _pluck_attachments(ticket),
        "orbit4_notes": _pluck_notes(ticket),
        "source": "orbit4",
    }
    # Asset fan-out — only include if an asset block was supplied
    if asset:
        payload["asset_serial"] = asset.get("serial_number") or ""
        payload["asset_name"] = (
            f"{asset.get('brand', '')} {asset.get('range', '')} {asset.get('product', '')}".strip()
        )
        payload["asset_qr_code"] = asset.get("qr_code") or ""
        payload["machine_type"] = asset.get("product") or ""
        payload.update(map_orbit4_asset_to_gymaxis(asset))
    return payload


# ╭────────────────── Outbound mappers (Phase γ-δ) ─────────────────╮

def _stringify_metadata(extra: Optional[Dict]) -> Optional[str]:
    if not extra:
        return None
    try:
        return json.dumps(extra, separators=(",", ":"))
    except TypeError:
        return None


def _equipment_date_fields(equipment: Dict) -> Dict:
    return {
        "installation_date": (equipment.get("install_date") or "")[:10] or None,
        "manufacturing_date": (equipment.get("manufacture_date") or "")[:10] or None,
        "warranty_end_date": (equipment.get("warranty_expiry") or "")[:10] or None,
        "deprecation_date": (equipment.get("deprecation_date") or "")[:10] or None,
    }


def map_gymaxis_equipment_to_orbit4(equipment: Dict, *,
                                     user_id: Optional[int] = None,
                                     product_id: Optional[int] = None) -> Dict:
    """Phase γ — build a POST /v1/assets payload from our equipment doc."""
    payload: Dict = {
        "qr_code": equipment.get("qr_code") or f"GA-{equipment.get('id', '')[:8]}",
        "serial_number": equipment.get("serial_number") or "",
        "brand": equipment.get("manufacturer") or equipment.get("make") or "",
        "range": equipment.get("model") or equipment.get("model_code") or "",
        "product": equipment.get("equipment_type") or equipment.get("name") or "",
    }
    payload.update(_equipment_date_fields(equipment))
    if user_id:
        payload["user_id"] = int(user_id)
    if product_id:
        payload["product_id"] = int(product_id)
    md = _stringify_metadata({
        "integration_id": equipment.get("id", ""),
        "organization_id": equipment.get("organization_id", ""),
    })
    if md:
        payload["metadata"] = md
    return {k: v for k, v in payload.items() if v not in (None, "")}


def map_gymaxis_contract_to_orbit4(contract: Dict, *,
                                    gym_operator_id: int,
                                    service_provider_id: int) -> Dict:
    """Phase γ — map a Pulse Fitness CRM contract header to /v1/contracts."""
    payload: Dict = {
        "gym_operator_id": int(gym_operator_id),
        "service_provider_id": int(service_provider_id),
        "number": contract.get("contract_number") or contract.get("id", ""),
        "type": contract.get("contract_type") or contract.get("tier") or "Full Annual",
        "start_date": (contract.get("start_date") or "")[:10],
        "end_date": (contract.get("end_date") or "")[:10],
        "active": contract.get("status", "active") == "active",
    }
    md = _stringify_metadata({
        "integration_id": contract.get("id", ""),
        "organization_id": contract.get("organization_id", ""),
    })
    if md:
        payload["metadata"] = md
    return {k: v for k, v in payload.items() if v not in (None, "")}


def _priority_for_orbit4(severity: str) -> str:
    return GYMAXIS_SEVERITY_TO_ORBIT4.get((severity or "").lower(), "normal")


def map_gymaxis_issue_to_orbit4_ticket(issue: Dict, *,
                                        asset_id: Optional[int] = None,
                                        gym_operator_id: Optional[int] = None,
                                        service_provider_id: Optional[int] = None,
                                        problem_type: str = "undefined") -> Dict:
    """Phase δ — build a POST /v1/contracts/{id}/tickets payload."""
    payload: Dict = {
        "description": issue.get("issue_description") or "",
        "priority": _priority_for_orbit4(issue.get("severity", "medium")),
        "problem_type": problem_type,
        "tags": issue.get("fault_tags") or [],
    }
    if asset_id:
        payload["asset_id"] = int(asset_id)
    if gym_operator_id:
        payload["gym_operator_id"] = int(gym_operator_id)
    if service_provider_id:
        payload["service_provider_id"] = int(service_provider_id)
    md = _stringify_metadata({
        "integration_id": issue.get("id", ""),
        "organization_id": issue.get("organization_id", ""),
        "supplier_case_token": issue.get("supplier_case_token", ""),
        "sicon_case_id": issue.get("sicon_case_id"),
    })
    if md:
        payload["metadata"] = md
    return {k: v for k, v in payload.items() if v not in (None, "")}


# Pulse Fitness fault status → Orbit4 ticket status (conservative — open/in_progress/closed only)
GYMAXIS_STATUS_TO_ORBIT4 = {
    "open": "open",
    "new": "open",
    "in_progress": "in_progress",
    "scheduled": "in_progress",
    "parts_on_order": "in_progress",
    "awaiting_parts": "in_progress",
    "engineer_assigned": "in_progress",
    "completed": "closed",
    "resolved": "closed",
    "closed": "closed",
    "archived": "closed",
}


def map_gymaxis_status_to_orbit4_patch(issue_status: str,
                                        resolution: Optional[str] = None) -> Dict:
    """Phase δ — body for PUT /v1/tickets/{id} mirroring a status change."""
    o4_status = GYMAXIS_STATUS_TO_ORBIT4.get((issue_status or "").lower(), "open")
    body: Dict = {"status": o4_status}
    if o4_status == "closed":
        body["closed_at"] = datetime.now(timezone.utc).isoformat()
        if resolution:
            body["resolution"] = resolution[:1000]
    return body


def map_gymaxis_user_to_orbit4(user: Dict, *, role: str = "gym_operator",
                                 site_name: Optional[str] = None) -> Dict:
    """Phase γ — provision a Pulse Fitness user onto Orbit4."""
    language = user.get("language", "en")
    if language not in ORBIT4_LANG_ENUM:
        language = "en"
    payload: Dict = {
        "first_name": (user.get("full_name", "").split(" ", 1) + [""])[0][:60] or user.get("email", ""),
        "last_name":  (user.get("full_name", "").split(" ", 1) + [""])[1][:60] or "-",
        "email": user.get("email", ""),
        "language": language,
        "role": role,
    }
    if site_name:
        payload["site_name"] = site_name[:120]
    md = _stringify_metadata({
        "integration_id": user.get("id", ""),
        "organization_id": user.get("organization_id", ""),
    })
    if md:
        payload["metadata"] = md
    return {k: v for k, v in payload.items() if v not in (None, "")}
