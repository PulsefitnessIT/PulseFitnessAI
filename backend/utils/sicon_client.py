"""
Sicon Service API Client
Handles all communication with the Sicon WebAPI (Sage 200 add-on).
Server-to-server only — credentials never exposed to frontend.

Field mappings aligned with /app/memory/SICON_INTEGRATION_SPEC.md v1.0
"""
import httpx
import logging
import base64
import os
import hashlib
from cryptography.fernet import Fernet
from datetime import datetime, timezone
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# Derive a stable Fernet key from JWT_SECRET (used to encrypt Sicon credentials at rest).
# Fail loudly if JWT_SECRET is unset — we must never fall back to a predictable
# default or an attacker can decrypt every stored Sicon credential.
_jwt_secret = (os.environ.get("JWT_SECRET") or "").strip()
if not _jwt_secret:
    raise RuntimeError(
        "JWT_SECRET must be set in the environment for Sicon credential encryption.",
    )
_key_bytes = hashlib.sha256(_jwt_secret.encode()).digest()
FERNET_KEY = base64.urlsafe_b64encode(_key_bytes)
_fernet = Fernet(FERNET_KEY)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string for storage in DB."""
    if not plaintext:
        return ""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a stored string."""
    if not ciphertext:
        return ""
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt value — may be stored unencrypted")
        return ciphertext


# ── HTTP Error class ──────────────────────────────────────────────

class SiconAPIError(Exception):
    """Raised for any Sicon API failure. Carries http_status for retry decisions."""
    def __init__(self, message: str, http_status: int = 0, payload: Optional[Dict] = None):
        super().__init__(message)
        self.http_status = http_status
        self.payload = payload or {}


def _extract_records(body) -> List:
    """Pull the record list out of a Sicon list envelope, tolerating the
    various array keys Sicon uses across endpoints (records/items/entities/
    data/results). Returns [] for anything unexpected."""
    if isinstance(body, list):
        return body
    if not isinstance(body, dict):
        return []
    for key in ("records", "items", "entities", "data", "results", "value"):
        val = body.get(key)
        if isinstance(val, list):
            return val
    return []


# ── Client ────────────────────────────────────────────────────────

class SiconClient:
    """
    Client for the Sicon Service WebAPI (R260200c).
    All calls are server-to-server over HTTPS with Basic auth.
    """

    def __init__(self, base_url: str, username: str, password: str, company_id: int = 0,
                 timeout: float = 30.0, allow_writes: bool = False, page_size: int = 50,
                 contract_base_url: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        # §26 — Sicon Contract Management is a SEPARATE WebAPI/plugin that may
        # sit on a different host/port. Falls back to the service base URL.
        self.contract_base_url = (contract_base_url or base_url).rstrip("/")
        self.company_id = company_id
        self.timeout = timeout
        self._auth = (username, password)
        self._username = username
        self._password = password
        self._bearer: Optional[str] = None
        # §18/§35 — writes stay OFF unless explicitly enabled server-side.
        # Enforced centrally in the request layer so NO write can slip through.
        self.allow_writes = allow_writes
        # §5 — Sicon paging size (default 50, matches the proven live tests).
        self.page_size = page_size or 50

    def _guard_write(self, method: str) -> None:
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE") and not self.allow_writes:
            raise SiconAPIError(
                "Sicon writes are disabled (SICON_ALLOW_WRITES=false). "
                "Refusing to send a write request.",
                http_status=403,
            )

    def _params(self, extra: Optional[Dict] = None) -> Dict:
        params = {}
        if self.company_id:
            params["companyId"] = self.company_id
        if extra:
            params.update(extra)
        return params

    def _parse_response(self, resp, method: str, path: str, json_body: Optional[Dict]) -> Dict:
        """Parse an HTTP response, raising SiconAPIError on failure."""
        if resp.status_code >= 400:
            raise SiconAPIError(
                f"Sicon {method} {path} → {resp.status_code}: {resp.text[:300]}",
                http_status=resp.status_code,
                payload=json_body or {},
            )
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return {"raw": resp.text}

    async def _request(self, method: str, path: str, params: Optional[Dict] = None, json_body: Optional[Dict] = None) -> Dict:
        self._guard_write(method)
        url = f"{self.base_url}{path}"
        merged_params = self._params(params)
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=True) as client:
                resp = await client.request(
                    method=method, url=url,
                    params=merged_params, json=json_body,
                    auth=self._auth,
                    headers={"Content-Type": "application/json", "Accept": "application/json"}
                )
                return self._parse_response(resp, method, path, json_body)
        except SiconAPIError:
            raise
        except httpx.ConnectError as e:
            raise SiconAPIError(f"Connection failed: {e}", http_status=0, payload=json_body or {})
        except httpx.TimeoutException as e:
            raise SiconAPIError(f"Timeout: {e}", http_status=408, payload=json_body or {})
        except Exception as e:
            raise SiconAPIError(f"Unknown error: {e}", http_status=0, payload=json_body or {})

    # ── Connectivity ──────────────────────────────────────────────
    async def ping(self) -> bool:
        try:
            await self._request("GET", "/api/SMConnectivity/Ping")
            return True
        except Exception:
            return False

    # ── Service WebAPI v1 (/api/v1/SiconService/*) ────────────────
    # Migrated surface per the customer's Bruno collection: JWT bearer auth,
    # camelCase full models, companyId query param. See utils.sicon_service_models.

    async def _authenticate_v1(self) -> None:
        """Fetch a JWT bearer token (POST /api/v1/authentication/authenticate)."""
        if self._bearer:
            return
        url = f"{self.base_url}/api/v1/authentication/authenticate"
        async with httpx.AsyncClient(timeout=self.timeout, verify=True) as client:
            resp = await client.post(url, json={"username": self._username, "password": self._password},
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
            if resp.status_code >= 400:
                raise SiconAPIError(f"Sicon auth → {resp.status_code}: {resp.text[:200]}",
                                    http_status=resp.status_code)
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            token = body.get("accessToken") or body.get("access_token") or body.get("token")
            if not token:
                raise SiconAPIError("Sicon auth returned no accessToken", http_status=resp.status_code)
            self._bearer = token

    async def _svc_request(self, method: str, path: str, json_body: Optional[Dict] = None,
                           params: Optional[Dict] = None, anon: bool = False) -> Dict:
        """Request against the v1 SiconService surface with bearer auth + companyId."""
        self._guard_write(method)
        if not anon:
            await self._authenticate_v1()
        url = f"{self.base_url}{path}"
        merged = self._params(params)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._bearer and not anon:
            headers["Authorization"] = f"Bearer {self._bearer}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=True) as client:
                resp = await client.request(method=method, url=url, params=merged,
                                            json=json_body, headers=headers)
                return self._parse_response(resp, method, path, json_body)
        except SiconAPIError:
            raise
        except httpx.ConnectError as e:
            raise SiconAPIError(f"Connection failed: {e}", http_status=0, payload=json_body or {})
        except httpx.TimeoutException as e:
            raise SiconAPIError(f"Timeout: {e}", http_status=408, payload=json_body or {})
        except Exception as e:
            raise SiconAPIError(f"Unknown error: {e}", http_status=0, payload=json_body or {})

    async def svc_ping(self) -> bool:
        try:
            await self._svc_request("GET", "/api/v1/SiconService/Ping", anon=True)
            return True
        except Exception:
            return False

    async def svc_create_case(self, model: Dict) -> Dict:
        return await self._svc_request("POST", "/api/v1/SiconService/Case", json_body=model)

    async def svc_update_case(self, case_id: int, model: Dict) -> Dict:
        return await self._svc_request("PUT", f"/api/v1/SiconService/Case/{case_id}", json_body=model)

    async def svc_create_appointment(self, model: Dict) -> Dict:
        return await self._svc_request("POST", "/api/v1/SiconService/Appointment", json_body=model)

    async def svc_update_appointment(self, appointment_id: int, model: Dict) -> Dict:
        return await self._svc_request("PUT", f"/api/v1/SiconService/Appointment/{appointment_id}", json_body=model)

    async def svc_appointment_time_booking(self, appointment_id: int, model: Dict) -> Dict:
        return await self._svc_request(
            "POST", f"/api/v1/SiconService/Appointment/{appointment_id}/TimeBooking", json_body=model)

    async def svc_create_equipment(self, model: Dict) -> Dict:
        return await self._svc_request("POST", "/api/v1/SiconService/Equipment", json_body=model)

    async def svc_update_equipment(self, equipment_id: int, model: Dict) -> Dict:
        return await self._svc_request("PUT", f"/api/v1/SiconService/Equipment/{equipment_id}", json_body=model)

    async def svc_create_tracking_note(self, case_id: int, model: Dict) -> Dict:
        return await self._svc_request(
            "POST", f"/api/v1/SiconService/Case/{case_id}/TrackingNote", json_body=model)

    async def svc_update_tracking_note(self, case_id: int, note_id: int, model: Dict) -> Dict:
        return await self._svc_request(
            "PUT", f"/api/v1/SiconService/Case/{case_id}/TrackingNote/{note_id}", json_body=model)

    # ══════════════════════════════════════════════════════════════════
    # PROVEN READ-SIDE (Sicon → Pulse). See PulseFitness-Sicon collection.
    # These are the ONLY read endpoints proven live; do not invent others.
    # ══════════════════════════════════════════════════════════════════

    async def _svc_get(self, path: str, raw_query: Optional[str] = None, anon: bool = False,
                       _retry_auth: bool = True) -> Dict:
        """GET against the v1 SiconService surface.

        `raw_query` is appended VERBATIM (already-encoded) after companyId, so
        Sicon's paging syntax `$skip=0%26$max=50` reaches the server intact —
        the internal `%26` must NOT be decoded into a second query parameter
        (spec §5/§30). We therefore set the URL query as raw bytes and never
        let httpx re-encode it.
        """
        if not anon:
            await self._authenticate_v1()
        parts = []
        if self.company_id:
            parts.append(f"companyId={self.company_id}")
        if raw_query:
            parts.append(raw_query)
        url = httpx.URL(f"{self.base_url}{path}")
        if parts:
            url = url.copy_with(query="&".join(parts).encode("ascii"))
        headers = {"Accept": "application/json"}
        if self._bearer and not anon:
            headers["Authorization"] = f"Bearer {self._bearer}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=True) as client:
                resp = await client.get(url, headers=headers)
                # Auto re-authenticate once if the token has expired (spec §3.5).
                if resp.status_code in (401, 403) and not anon and _retry_auth:
                    self._bearer = None
                    await self._authenticate_v1()
                    return await self._svc_get(path, raw_query=raw_query, anon=anon, _retry_auth=False)
                return self._parse_response(resp, "GET", path, None)
        except SiconAPIError:
            raise
        except httpx.ConnectError as e:
            raise SiconAPIError(f"Connection failed: {e}", http_status=0)
        except httpx.TimeoutException as e:
            raise SiconAPIError(f"Timeout: {e}", http_status=408)
        except Exception as e:
            raise SiconAPIError(f"Unknown error: {e}", http_status=0)

    @staticmethod
    def build_page_query(skip: int, max_: int) -> str:
        """The one place page syntax is built. Ampersand encoded as %26 so it
        stays INSIDE the single `query` parameter (spec §5)."""
        return f"query=$skip={skip}%26$max={max_}"

    # ── Reference data (GetMany) ──────────────────────────────────
    async def svc_get_case_types(self) -> Dict:
        return await self._svc_get("/api/v1/SiconService/CaseType")

    async def svc_get_priorities(self) -> Dict:
        return await self._svc_get("/api/v1/SiconService/Priority")

    async def svc_get_tracking_statuses(self) -> Dict:
        return await self._svc_get("/api/v1/SiconService/TrackingStatus")

    # ── Equipment ─────────────────────────────────────────────────
    async def svc_get_equipment_page(self, skip: int = 0, max_: Optional[int] = None) -> Dict:
        max_ = max_ or self.page_size
        return await self._svc_get("/api/v1/SiconService/Equipment",
                                   raw_query=self.build_page_query(skip, max_))

    async def svc_get_equipment_one(self, sicon_equipment_id: int) -> Dict:
        return await self._svc_get(f"/api/v1/SiconService/Equipment/{sicon_equipment_id}")

    # ── Case search ───────────────────────────────────────────────
    async def svc_get_casesearch_page(self, skip: int = 0, max_: Optional[int] = None) -> Dict:
        max_ = max_ or self.page_size
        return await self._svc_get("/api/v1/SiconService/CaseSearch",
                                   raw_query=self.build_page_query(skip, max_))

    async def svc_get_casesearch_one(self, si_sm_case_id: int) -> Dict:
        # Permanent key is siSMCaseId — never caseNumber (spec §12).
        return await self._svc_get(f"/api/v1/SiconService/CaseSearch/{si_sm_case_id}")

    # ── Case relationships (proven chain: Case→Equipment→Appointment→
    #    Resource→TimeBooking, with TrackingNotes on case history) §4/§11-16.
    #    Keyed on the permanent siSMCaseId. These are the ONLY proven v1
    #    relationship routes — do not fall back to legacy /api/Service/* here.
    async def svc_get_case_equipment(self, si_sm_case_id: int) -> Dict:
        return await self._svc_get(f"/api/v1/SiconService/Case/{si_sm_case_id}/Equipment")

    async def svc_get_case_appointments(self, si_sm_case_id: int) -> Dict:
        return await self._svc_get(f"/api/v1/SiconService/Case/{si_sm_case_id}/Appointment")

    async def svc_get_case_tracking_notes(self, si_sm_case_id: int) -> Dict:
        return await self._svc_get(f"/api/v1/SiconService/Case/{si_sm_case_id}/TrackingNote")

    async def svc_get_tracking_note_one(self, si_sm_case_id: int, note_id: int) -> Dict:
        return await self._svc_get(
            f"/api/v1/SiconService/Case/{si_sm_case_id}/TrackingNote/{note_id}")

    # ── Appointments (proven v1 GetOne + relationships) ───────────
    async def svc_get_appointment_one(self, appointment_id: int) -> Dict:
        return await self._svc_get(f"/api/v1/SiconService/Appointment/{appointment_id}")

    async def svc_get_appointment_resources(self, appointment_id: int) -> Dict:
        return await self._svc_get(f"/api/v1/SiconService/Appointment/{appointment_id}/Resource")

    async def svc_get_appointment_timebookings(self, appointment_id: int) -> Dict:
        return await self._svc_get(f"/api/v1/SiconService/Appointment/{appointment_id}/TimeBooking")

    # ── Contract Management plugin (SEPARATE WebAPI, §26) ─────────
    # Read-only capability probe. Known to 404 until Sicon enables the plugin
    # or confirms another host — callers must treat 404 as "Unavailable", never
    # rewrite these routes to make the 404 disappear.
    async def _contract_get(self, path: str, _retry_auth: bool = True) -> Dict:
        await self._authenticate_v1()
        url = f"{self.contract_base_url}{path}"
        headers = {"Accept": "application/json"}
        if self._bearer:
            headers["Authorization"] = f"Bearer {self._bearer}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code in (401, 403) and _retry_auth:
                    self._bearer = None
                    await self._authenticate_v1()
                    return await self._contract_get(path, _retry_auth=False)
                return self._parse_response(resp, "GET", path, None)
        except SiconAPIError:
            raise
        except httpx.ConnectError as e:
            raise SiconAPIError(f"Connection failed: {e}", http_status=0)
        except httpx.TimeoutException as e:
            raise SiconAPIError(f"Timeout: {e}", http_status=408)
        except Exception as e:
            raise SiconAPIError(f"Unknown error: {e}", http_status=0)

    async def svc_contract_available(self) -> bool:
        """Probe /api/v1/SiconContract/Ping. True only on 200; any error
        (incl. the expected 404) → False = plugin unavailable (§26)."""
        try:
            await self._contract_get("/api/v1/SiconContract/Ping")
            return True
        except Exception:
            return False

    async def svc_get_contracts(self) -> Dict:
        return await self._contract_get("/api/v1/SiconContract/Contract")

    async def svc_get_contract_one(self, contract_id: int) -> Dict:
        return await self._contract_get(f"/api/v1/SiconContract/Contract/{contract_id}")

    # ── Shared pager (iterate until nextPage is null) ─────────────
    async def svc_paginate(self, kind: str, page_size: Optional[int] = None, max_pages: int = 0):
        """Async generator yielding (page_meta, records) for 'equipment' or
        'cases'. Advances by skip=(page-1)*size and stops when Sicon reports
        nextPage == null (spec §5) rather than trusting a fixed totalPages."""
        size = page_size or self.page_size
        fetch = {"equipment": self.svc_get_equipment_page,
                 "cases": self.svc_get_casesearch_page}[kind]
        skip = 0
        page_no = 0
        while True:
            page_no += 1
            body = await fetch(skip, size)
            records = _extract_records(body)
            yield body, records
            next_page = body.get("nextPage")
            if next_page is None or not records:
                break
            if max_pages and page_no >= max_pages:
                break
            skip += size


    # ── Service Cases ─────────────────────────────────────────────
    async def get_case(self, case_id: int) -> Dict:
        return await self._request("GET", f"/api/service/cases/{case_id}")

    async def get_case_by_reference(self, case_reference: str) -> Dict:
        return await self._request("GET", "/api/service/cases", params={"casereference": case_reference})

    async def create_case(self, case_data: Dict) -> Dict:
        """Primary create — uses R260200c endpoint per spec §6.2."""
        return await self._request("POST", "/api/ServiceCase/CreateNewCase", json_body=case_data)

    async def amend_case(self, case_data: Dict) -> Dict:
        return await self._request("POST", "/api/ServiceCase/AmendCase", json_body=case_data)

    async def list_cases_updated_since(self, since_iso: str) -> Dict:
        """Poll for cases modified since given timestamp."""
        return await self._request("GET", "/api/service/cases", params={"modifiedsince": since_iso})

    # ── Case Types / Statuses ─────────────────────────────────────
    async def get_case_types(self) -> Dict:
        return await self._request("GET", "/api/service/case-types")

    async def get_tracking_statuses(self) -> Dict:
        return await self._request("GET", "/api/service/case-tracking-statuses")

    # NOTE: The Service WebAPI (R260200c) exposes NO priorities lookup endpoint.
    # Priorities are set on a case via PriorityID / PriorityName; the ID<->name
    # map is entered manually in the Sicon config (priority_mapping). Do not add a
    # get_priorities() call here — /api/service/priorities does not exist and 404s.
    # (Open question for Sicon: is a priorities lookup available on another route?)

    # ── Tracking Notes ────────────────────────────────────────────
    async def get_tracking_notes(self, case_id: int) -> Dict:
        return await self._request("GET", f"/api/Service/Cases/{case_id}/TrackingNotes")

    async def create_tracking_note(self, case_id: int, note_data: Dict) -> Dict:
        return await self._request("POST", f"/api/Service/Cases/{case_id}/TrackingNotes", json_body=note_data)

    # ── Appointments ──────────────────────────────────────────────
    # Per Service.R260200c the appointment CRUD operations live under Sicon's
    # generic-entity framework base "/~/api/v2/TEntity" (the "~" resolves to the
    # WebAPI site root server-side). This differs from TimeBookings / TrackingNotes
    # which are plain "/api/Service/..." routes. Paths below match the published spec.
    async def get_appointment(self, appointment_id: int) -> Dict:
        return await self._request("GET", f"/~/api/v2/TEntity/api/service/appointments/{appointment_id}")

    async def get_appointments_for_case(self, case_id: int) -> Dict:
        # NOTE: The spec exposes NO case-scoped appointment list. Appointments are
        # only listed via the paged generic-entity reader (GET /~/api/v2/TEntity).
        # We pass the case id as filterText as a best-effort; confirm the filter
        # semantics with Sicon (raised as a meeting question).
        return await self._request(
            "GET", "/~/api/v2/TEntity",
            params={"filterText": str(case_id), "pageNumber": 1, "pageSize": 200},
        )

    async def create_appointment(self, appointment_data: Dict) -> Dict:
        return await self._request("POST", "/~/api/v2/TEntity/api/Service/Appointments", json_body=appointment_data)

    async def update_appointment(self, appointment_id: int, appointment_data: Dict) -> Dict:
        return await self._request("PUT", f"/~/api/v2/TEntity/api/Service/Appointments/{appointment_id}", json_body=appointment_data)

    async def delete_appointment(self, appointment_id: int) -> Dict:
        return await self._request("DELETE", f"/~/api/v2/TEntity/{appointment_id}")

    # ── Appointment Resources (Engineers) ─────────────────────────
    async def get_resources(self) -> Dict:
        """Engineer directory (Phase C). One page at a time; callers may paginate."""
        return await self._request("GET", "/api/service/appointments/resources")

    async def get_resources_for_appointment(self, appointment_id: int) -> Dict:
        return await self._request("GET", f"/api/service/appointments/{appointment_id}/resources")

    # ── Time Bookings ─────────────────────────────────────────────
    async def get_time_bookings(self, appointment_id: int) -> Dict:
        return await self._request("GET", f"/api/Service/Appointments/{appointment_id}/TimeBookings")

    async def create_time_booking(self, appointment_id: int, booking_data: Dict) -> Dict:
        return await self._request("POST", f"/api/Service/Appointments/{appointment_id}/TimeBookings", json_body=booking_data)

    async def update_time_booking(self, appointment_id: int, booking_id: int, booking_data: Dict) -> Dict:
        return await self._request("PUT", f"/api/Service/Appointments/{appointment_id}/TimeBookings/{booking_id}", json_body=booking_data)

    # ── Contracts ─────────────────────────────────────────────────
    async def create_or_update_contract(self, contract_data: Dict) -> Dict:
        """Phase D — POST /api/Contract/CreateUpdateContract (upsert on ContractID)."""
        return await self._request("POST", "/api/Contract/CreateUpdateContract", json_body=contract_data)

    async def update_contract_customer_order_number(self, sicon_contract_id: int, customer_order_number: str) -> Dict:
        return await self._request(
            "POST", "/api/Contract/UpdateContractCustomerOrderNumber",
            params={"SiconContractID": sicon_contract_id, "CustomerOrderNumber": customer_order_number},
        )

    async def post_contract_line(self, line_data: Dict) -> Dict:
        """Phase D — POST /api/ContractLine/PostContractLine (create or update)."""
        return await self._request("POST", "/api/ContractLine/PostContractLine", json_body=line_data)

    # Back-compat aliases (older callers)
    async def create_contract(self, contract_data: Dict) -> Dict:
        return await self.create_or_update_contract(contract_data)

    async def update_contract(self, contract_id: int, contract_data: Dict) -> Dict:
        contract_data = {**contract_data, "ContractID": contract_id}
        return await self.create_or_update_contract(contract_data)

    # ── Stock (Sicon CoreWebAPI — Sage 200 stock) ─────────────────
    # The Service WebAPI exposes no parts/stock object on a case, so parts
    # used on a job are booked through the CoreWebAPI stock surface against
    # the engineer's van warehouse. See INTEGRATION_FIELD_MAPPING.md §33.13.
    async def get_stock_items_by_code(self, code: str) -> Dict:
        """Resolve a Sage stock item from our catalogue SKU (link picker)."""
        return await self._request("GET", "/api/StockItem/GetStockItemsByCode",
                                    params={"code": code})

    async def internal_issue(self, payload: Dict) -> Dict:
        """Book a part out of a warehouse/van (a 'parts used on job' event)."""
        return await self._request("POST", "/api/StockItem/InternalIssue", json_body=payload)

    async def transfer_stock(self, payload: Dict) -> Dict:
        """Move stock between two warehouses/bins (warehouse↔van transfer)."""
        return await self._request("POST", "/api/StockItem/TransferStock", json_body=payload)

    async def add_stock(self, payload: Dict) -> Dict:
        """Positive stock-take adjustment (count higher than expected)."""
        return await self._request("POST", "/api/StockItem/AddStock", json_body=payload)

    async def write_off_stock(self, payload: Dict) -> Dict:
        """Negative stock-take adjustment (count lower than expected)."""
        return await self._request("POST", "/api/StockItem/WriteOffStock", json_body=payload)


# ── Severity → Priority Lookup ────────────────────────────────────

SEVERITY_TO_PRIORITY_NAME = {
    "safety_critical": "Safety Critical",
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

FAULT_TYPE_TO_CASE_TYPE = {
    "standard": "Reactive",
    "safety_critical": "Safety Critical",
    "ppm": "Preventative Maintenance",
}


# ── Mappers: Pulse Fitness → Sicon ──────────────────────────────────────

def _extract_triage_fields(issue: Dict, fallback_severity: str) -> tuple[str, str, str]:
    """Extract AI triage summary, severity, and parts list from an issue."""
    triage = issue.get("ai_triage_parsed") or {}
    triage_summary = (
        triage.get("summary")
        or triage.get("diagnosis")
        or issue.get("ai_triage_summary", "")
    )[:250]
    ai_severity = triage.get("severity", fallback_severity)
    parts = triage.get("recommended_parts")
    ai_parts = ", ".join(parts) if isinstance(parts, list) else (parts or "")
    return triage_summary, ai_severity, ai_parts


def _apply_location(case_data: Dict, issue: Dict, fallback_addr: Dict) -> None:
    """Populate Location* fields on the Sicon case payload."""
    site_addr = issue.get("site_address") or fallback_addr
    if not site_addr:
        return
    case_data["LocationPostalName"] = site_addr.get("name") or issue.get("site_name", "")
    case_data["LocationAddressLine1"] = site_addr.get("line1", "")
    case_data["LocationAddressLine2"] = site_addr.get("line2", "")
    case_data["LocationAddressLine3"] = site_addr.get("line3", "")
    case_data["LocationAddressLine4"] = site_addr.get("line4", "")
    case_data["LocationCity"] = site_addr.get("city", "")
    case_data["LocationCounty"] = site_addr.get("county", "")
    case_data["LocationPostCode"] = site_addr.get("postcode", "")


def _build_contact_fields(issue: Dict) -> Dict:
    """Extract caller / customer contact fields."""
    return {
        "ContactName": issue.get("created_by_name", "") or issue.get("reporter_name", ""),
        "ContactEmail": issue.get("reporter_email", "") or issue.get("user_email", ""),
        "ContactPhoneNumber": issue.get("reporter_phone", "") or "",
        "CustomerReference": issue.get("sage_customer_reference", "") or issue.get("company_sage_ref", "") or "",
        "SLCustomerAccountID": issue.get("sage_customer_account_id", 0) or 0,
    }


def _build_assignment_fields(issue: Dict, config: Dict) -> Dict:
    """Extract Sicon contract/team assignment fields."""
    return {
        "AssignedToSageUserID": config.get("default_assigned_user_id", 0),
        "InternalTeamID": config.get("default_internal_team_id", 0),
        "ExternalTeamID": config.get("default_external_team_id", 0),
        "SiconContractID": issue.get("sicon_contract_id", 0) or config.get("default_contract_id", 0),
        "SiconContractNumber": issue.get("sicon_contract_number", ""),
        "SiconContractLineID": config.get("default_contract_line_id", 0),
        "SiJcJobID": 0,
        "SiconCRMPersonID": 0,
        "SiconCRMCompanyID": 0,
    }


def _build_analysis_fields(issue: Dict, triage_summary: str, ai_severity: str, ai_parts: str, org_name: str) -> Dict:
    """Per spec §10 — AI triage analytics fields (1-8 core)."""
    return {
        "AnalysisField1": triage_summary,
        "AnalysisField2": f"{ai_severity}".upper(),
        "AnalysisField3": ai_parts[:250],
        "AnalysisField4": issue.get("id", ""),
        "AnalysisField5": org_name[:100],
        "AnalysisField6": issue.get("sla_category") or issue.get("sla_tier") or "",
        "AnalysisField7": issue.get("ppm_schedule_id", ""),
        "AnalysisField8": issue.get("supplier_case_token", ""),
    }


def _build_extended_analysis_fields(issue: Dict, equipment: Optional[Dict] = None) -> Dict:
    """Phase A — AnalysisFields 9-20 (equipment lineage + provenance + CSAT).

    Equipment fields come from the linked equipment doc if provided (callers
    should look up equipment by serial_number before mapping)."""
    eq = equipment or {}
    return {
        "AnalysisField9":  (issue.get("fault_code") or "")[:50],
        "AnalysisField10": (issue.get("machine_type") or "")[:80],
        "AnalysisField11": (eq.get("make") or eq.get("manufacturer") or "")[:80],
        "AnalysisField12": (eq.get("model_code") or eq.get("model") or "")[:80],
        "AnalysisField13": (eq.get("install_date") or "")[:25],
        "AnalysisField14": (eq.get("warranty_expiry") or eq.get("warranty_end_date") or "")[:25],
        "AnalysisField15": (issue.get("id") or "")[:60],
        "AnalysisField16": (issue.get("ppm_schedule_id") or "")[:60],
        "AnalysisField17": (issue.get("ai_triage_summary") or "")[:200],
        "AnalysisField18": (issue.get("source") or "manual")[:30],
        "AnalysisField19": (issue.get("reporter_role") or issue.get("created_by_role") or "")[:30],
        "AnalysisField20": str(issue.get("csat_rating") or "")[:10],
    }


def _build_sub_location(issue: Dict, site: Optional[Dict] = None) -> Optional[Dict]:
    """Build a Sicon SubLocation object from a Pulse Fitness site doc.

    Falls back to issue.sicon_sub_location_id if no site was joined."""
    if site and site.get("sicon_sub_location_id"):
        return {
            "SiconSubLocationID": site["sicon_sub_location_id"],
            "CustDeliveryAddressID": site.get("sage_delivery_address_id", 0) or 0,
            "Description": (site.get("name") or site.get("label") or "")[:100],
            "Comment": (site.get("notes") or site.get("floor_or_zone") or "")[:250],
        }
    if issue.get("sicon_sub_location_id"):
        return {"SiconSubLocationID": issue["sicon_sub_location_id"]}
    return None


def _build_equipments_array(issue: Dict, config: Dict, equipment: Optional[Dict] = None) -> Optional[List[Dict]]:
    """Build the Equipments[] array with full objects (preferred over EquipmentIDs[])."""
    serial = issue.get("serial_number") or (equipment or {}).get("serial_number")
    sicon_eq_id = (config.get("equipment_id_mapping") or {}).get(serial) if serial else None
    if not sicon_eq_id:
        sicon_eq_id = (equipment or {}).get("sicon_equipment_id")
    if not sicon_eq_id:
        return None
    return [{
        "SiconEquipmentID": int(sicon_eq_id),
        "ItemID": (equipment or {}).get("sage_item_id", 0) or 0,
        "Name": (issue.get("machine_type") or (equipment or {}).get("display_name") or serial or "")[:120],
    }]


def map_gymaxis_to_sicon_case(issue: Dict, config: Dict, org_name: str = "",
                              equipment: Optional[Dict] = None,
                              site: Optional[Dict] = None,
                              crm_links: Optional[Dict] = None) -> Dict:
    """Build a Sicon Service Case payload from a Pulse Fitness issue.

    Phase A extends the original spec §3.1 mapping with:
    - AnalysisFields 9-20 (equipment lineage, provenance, CSAT)
    - Full SubLocation object from a joined site doc
    - SiconCRMPersonID / SiconCRMCompanyID from the org's cached CRM link
    - CaseNumber passthrough on amend
    - Full Equipments[] array (not just EquipmentIDs)
    - SiSMDocumentSubStatusID when set on the issue
    """
    severity = issue.get("severity", "medium")
    priority_id = (config.get("priority_mapping") or {}).get(severity) or config.get("default_priority_id", 0)
    priority_name = SEVERITY_TO_PRIORITY_NAME.get(severity, "Medium")

    fault_type = issue.get("fault_type", "standard")
    case_type_id = config.get("default_case_type_id", 0)
    case_type_name = config.get("default_case_type_name") or FAULT_TYPE_TO_CASE_TYPE.get(fault_type, "Reactive")

    triage_summary, ai_severity, ai_parts = _extract_triage_fields(issue, severity)
    crm = crm_links or {}

    case_data = {
        "SiSMCaseId": issue.get("sicon_case_id", 0) or 0,
        "CaseNumber": issue.get("sicon_case_number", ""),
        "CaseTypeID": case_type_id,
        "CaseTypeName": case_type_name,
        "FaultCode": (issue.get("fault_code") or "")[:50],
        "Description": issue.get("issue_description", "")[:4000],
        "Summary": f"{issue.get('machine_type', '')} — {issue.get('serial_number', '')}".strip(" —"),
        "CallDate": issue.get("created_at", datetime.now(timezone.utc).isoformat()),
        "PriorityID": priority_id,
        "PriorityName": priority_name,
        **_build_contact_fields(issue),
        **_build_assignment_fields(issue, config),
        **_build_analysis_fields(issue, triage_summary, ai_severity, ai_parts, org_name),
        **_build_extended_analysis_fields(issue, equipment),
    }

    # CRM cross-links (required on create per Sicon spec)
    case_data["SiconCRMPersonID"] = crm.get("crm_person_id") or config.get("default_crm_person_id", 0)
    case_data["SiconCRMCompanyID"] = crm.get("crm_company_id") or config.get("default_crm_company_id", 0)

    # Sub-status for richer progress tracking
    # Iter 216h7 — explicit field wins; otherwise resolve via per-org workflow_state map.
    sub_status_id = issue.get("sicon_sub_status_id")
    if not sub_status_id:
        workflow_state = (issue.get("workflow_state") or "").lower()
        sub_status_map = config.get("sub_status_mapping") or {}
        if workflow_state and workflow_state in sub_status_map:
            sub_status_id = sub_status_map[workflow_state]
    if sub_status_id:
        case_data["SiSMDocumentSubStatusID"] = int(sub_status_id)

    _apply_location(case_data, issue, config.get("location_address") or {})

    sub_loc = _build_sub_location(issue, site)
    if sub_loc:
        case_data["SubLocation"] = sub_loc

    eqs = _build_equipments_array(issue, config, equipment)
    if eqs:
        case_data["Equipments"] = eqs
        case_data["EquipmentIDs"] = [e["SiconEquipmentID"] for e in eqs]

    return case_data


def build_tracking_note_payload(note_text: str, created_by: str = "Pulse Fitness AI",
                                 visible_to_customer: bool = True,
                                 visible_to_engineer: bool = True,
                                 status_id: int = 0,
                                 sicon_appointment_id: int = 0,
                                 latitude: Optional[float] = None,
                                 longitude: Optional[float] = None,
                                 reassign_to_sage_user: int = 0) -> Dict:
    """Construct a Sicon tracking note payload (spec §3.4 + Phase B GPS/appointment link)."""
    payload: Dict = {
        "TrackingNote": note_text[:2000],
        "CaseTrackingStatusID": status_id,
        "VisibleToEngineer": visible_to_engineer,
        # Sicon's UpdateTrackingNoteRequest uses the plural key; the create
        # endpoint's published schema is empty so we send both to be safe.
        "VisibleToEngineers": visible_to_engineer,
        "VisibleToCustomer": visible_to_customer,
        "CreatedBy": created_by,
        "Time": datetime.now(timezone.utc).isoformat(),
    }
    if sicon_appointment_id:
        payload["SiconAppointmentID"] = int(sicon_appointment_id)
    if latitude is not None:
        payload["Latitude"] = float(latitude)
    if longitude is not None:
        payload["Longitude"] = float(longitude)
    if reassign_to_sage_user:
        payload["ReassignToSageUserNumber"] = int(reassign_to_sage_user)
    return payload


def _contract_spare_fields(contract: Dict) -> Dict:
    """Serialise Pulse Fitness metadata into Sicon Contract spare slots.

    Iter 216h7 — full coverage of Sicon's three spare-slot banks per contract
    header (each bank has 7 slots, type-strict on Sicon side):
      • SpareText1-7  ← strings (truncated at 250 chars)
      • SpareNum1-7   ← floats (financial signals: targets, uplift caps, % values)
      • SpareDate1-7  ← ISO date strings (renewal anchors, review dates, expiry)

    Three input shapes are honoured for backwards-compat:
      1. `contract.spare_text_map` / `spare_num_map` / `spare_date_map` —
         list of source keys; the resolver pulls from `contract[key]`.
      2. `contract.spare_text` / `spare_num` / `spare_date` — dict keyed by
         slot index (1..7) for direct overrides.
      3. Legacy: if only `spare_text_map` is set, behaviour is unchanged.
    """
    spare: Dict = {}
    # Text slots — pre-existing behaviour preserved.
    for i, key in enumerate(contract.get("spare_text_map") or [], start=1):
        if i > 7:
            break
        spare[f"SpareText{i}"] = str(contract.get(key, ""))[:250]
    for idx, val in (contract.get("spare_text") or {}).items():
        try:
            i = int(idx)
            if 1 <= i <= 7:
                spare[f"SpareText{i}"] = str(val)[:250]
        except (TypeError, ValueError):
            continue
    # Numeric slots — financial KPIs, uplift caps, % renewals, etc.
    for i, key in enumerate(contract.get("spare_num_map") or [], start=1):
        if i > 7:
            break
        val = contract.get(key)
        if val not in (None, ""):
            try:
                spare[f"SpareNum{i}"] = float(val)
            except (TypeError, ValueError):
                pass
    for idx, val in (contract.get("spare_num") or {}).items():
        try:
            i = int(idx)
            if 1 <= i <= 7 and val not in (None, ""):
                spare[f"SpareNum{i}"] = float(val)
        except (TypeError, ValueError):
            continue
    # Date slots — ISO strings; Sicon parses them server-side.
    for i, key in enumerate(contract.get("spare_date_map") or [], start=1):
        if i > 7:
            break
        val = contract.get(key)
        if val:
            spare[f"SpareDate{i}"] = str(val)[:25]
    for idx, val in (contract.get("spare_date") or {}).items():
        try:
            i = int(idx)
            if 1 <= i <= 7 and val:
                spare[f"SpareDate{i}"] = str(val)[:25]
        except (TypeError, ValueError):
            continue
    return spare


def map_gymaxis_contract_to_sicon(contract: Dict, sage_customer_id: int = 0) -> Dict:
    """Map a Pulse Fitness CRM contract to a Sicon Contract header (Contracts.R260200c §Contract)."""
    payload = {
        "ContractID": contract.get("sicon_contract_id", 0) or 0,
        "ContractNumber": contract.get("contract_number", ""),
        "CustomerNumber": contract.get("sage_customer_number") or str(sage_customer_id or contract.get("sage_customer_account_id", "") or ""),
        "Description": contract.get("description") or contract.get("title", ""),
        "SOPBillingDescription": contract.get("billing_description") or contract.get("title", ""),
        "CustomerOrderNumber": contract.get("customer_order_number") or contract.get("purchase_order_ref", ""),
    }
    payload.update(_contract_spare_fields(contract))
    return payload


def _contract_line_analysis_codes(line: Dict) -> Dict:
    """Pack SLA + Pulse Fitness custom metadata into Sicon's analysis-code slots.

    Uses CLAnalysisCode1-15 by convention (out of 150 available). Reserved:
    - CL1  = SLA tier (Gold / Platinum / Silver)
    - CL2  = Response-hours target
    - CL3  = Resolution-hours target
    - CL4  = OOS credit terms
    - CL5  = Safety-critical flag
    - CL6  = Pulse Fitness internal asset_id (for joins)
    - CL7  = Pulse Fitness site_id
    - CL8  = PPM frequency override (if different from VisitFrequency)
    - CL9  = Tender pack reference
    - CL10 = Renewal notice days

    Iter 216h7 — extended with five finance/governance signals so the
    Sicon side can drive automation (penalty calc, escalation, etc.):
    - CL11 = SLA penalty band ("0/5/10/25%" or absolute credit code)
    - CL12 = KPI breach flag ("OK"|"WARN"|"BREACH") set by Pulse Fitness SLA worker
    - CL13 = Finance approver email (last contract amend authoriser)
    - CL14 = Billing cycle override (e.g. "annual"|"semi-annual"|"quarterly")
    - CL15 = Holdback % (retention against final invoice, finance use)

    Any caller-supplied `analysis_codes` dict overrides these defaults.
    """
    sla = line.get("sla") or {}
    out = {
        "CLAnalysisCode1": (line.get("tier") or sla.get("tier") or "")[:50],
        "CLAnalysisCode2": str(sla.get("response_hours") or "")[:20],
        "CLAnalysisCode3": str(sla.get("resolution_hours") or "")[:20],
        "CLAnalysisCode4": str(sla.get("oos_credit_terms") or "")[:50],
        "CLAnalysisCode5": "YES" if line.get("safety_critical") else "NO",
        "CLAnalysisCode6": (line.get("asset_id") or line.get("equipment_id") or "")[:60],
        "CLAnalysisCode7": (line.get("site_id") or "")[:60],
        "CLAnalysisCode8": (line.get("ppm_frequency_override") or "")[:20],
        "CLAnalysisCode9": (line.get("tender_reference") or "")[:60],
        "CLAnalysisCode10": str(line.get("renewal_notice_days") or 90)[:10],
        # Iter 216h7 finance/governance extensions
        "CLAnalysisCode11": str(line.get("sla_penalty_band") or sla.get("penalty_band") or "")[:50],
        "CLAnalysisCode12": (line.get("kpi_breach_flag") or "OK")[:10].upper(),
        "CLAnalysisCode13": (line.get("finance_approver_email") or "")[:120],
        "CLAnalysisCode14": (line.get("billing_cycle_override") or "")[:30],
        "CLAnalysisCode15": str(line.get("holdback_pct") or "")[:10],
    }
    # Pass-through any caller-supplied overrides (analysis_codes dict)
    for k, v in (line.get("analysis_codes") or {}).items():
        if k.startswith("CLAnalysisCode") or k.startswith("AnalysisCode"):
            out[k] = str(v)[:250]
    return out


def _contract_line_dates_and_price(line: Dict) -> Dict:
    return {
        "ContractStartDate": line.get("start_date") or line.get("contract_start_date", ""),
        "ContractEndDate": line.get("end_date") or line.get("contract_end_date", ""),
        "Quantity": float(line.get("quantity") or 1),
        "UnitPrice": float(line.get("unit_price") or 0),
        "SOPUnitPrice": float(line.get("sop_unit_price") or line.get("unit_price") or 0),
        "PriceInterval": line.get("price_interval") or "years",
        "AmendedQuantity": float(line.get("amended_quantity") or 0),
        "AmendedUnitPrice": float(line.get("amended_unit_price") or 0),
        "BillCoverFrom": line.get("bill_cover_from") or line.get("start_date", ""),
        "OrderDate": line.get("order_date") or line.get("created_at", ""),
        "OriginalStartDate": line.get("original_start_date") or line.get("start_date", ""),
        "AnnualUnitCost": float(line.get("annual_unit_cost") or 0),
    }


def _contract_line_renewal(line: Dict) -> Dict:
    return {
        "RenewalQuantity": float(line.get("renewal_quantity") or line.get("quantity") or 1),
        "RenewalUnitPrice": float(line.get("renewal_unit_price") or line.get("unit_price") or 0),
        "RenewalFrequency": int(line.get("renewal_frequency") or 1),
        "RenewalPriceFreqInterval": line.get("renewal_price_freq_interval") or "years",
        "RenewalDuration": int(line.get("renewal_duration") or 0),
        "ContractExtended": bool(line.get("contract_extended", False)),
        "InitialContractDuration": int(line.get("initial_contract_duration") or 12),
        "ExtendedContractDuration": int(line.get("extended_contract_duration") or 0),
        "ContractDuration": int(line.get("contract_duration") or 0),
        "isRenewalUpdate": bool(line.get("is_renewal_update", False)),
        "ReasonCode": (line.get("reason_code") or "")[:50],
    }


def _contract_line_billing(line: Dict) -> Dict:
    return {
        "InvoiceFrequencyValue": int(line.get("invoice_frequency_value") or 1),
        "InvoiceFrequencyInterval": line.get("invoice_frequency_interval") or "months",
        "BillCoverDuration": int(line.get("bill_cover_duration") or 0),
        "BillMonthInAdvanceArrearsQty": int(line.get("bill_month_in_advance_arrears_qty") or 0),
        "BillInArrears": bool(line.get("bill_in_arrears", False)),
        "ProRata": bool(line.get("pro_rata", False)),
        "IsRolling": bool(line.get("is_rolling", False)),
    }


def _contract_line_discounts(line: Dict) -> Dict:
    return {
        "Discount1Percent": float(line.get("discount1_percent") or 0),
        "Discount1Value": float(line.get("discount1_value") or 0),
        "Discount2Percent": float(line.get("discount2_percent") or 0),
        "Discount2Value": float(line.get("discount2_value") or 0),
        "Discount3Percent": float(line.get("discount3_percent") or 0),
        "Discount3Value": float(line.get("discount3_value") or 0),
    }


def _contract_line_supplier(line: Dict) -> Dict:
    sla = line.get("sla") or {}
    return {
        "VisitFrequency": (line.get("visit_frequency") or sla.get("ppm_frequency") or "")[:30],
        "WhoSold": (line.get("who_sold") or "")[:60],
        "PLSupplierID": int(line.get("pl_supplier_id") or 0),
        "SupplierCode": (line.get("supplier_code") or "")[:30],
        "SupplierUnitPrice": float(line.get("supplier_unit_price") or 0),
    }


def map_gymaxis_contract_line_to_sicon(line: Dict, sicon_contract_id: int) -> Dict:
    """Map a Pulse Fitness CRM contract line to a Sicon ContractLine payload."""
    payload: Dict = {
        "SiconContractID": str(sicon_contract_id or line.get("sicon_contract_id", "") or ""),
        "SiconContractLineID": int(line.get("sicon_contract_line_id") or 0),
        "ItemCode": line.get("item_code") or line.get("equipment_item_code") or "",
        "SalesOrderDescription": (line.get("sop_description") or line.get("description") or "")[:250],
        "InternalDescription": (line.get("internal_description") or line.get("description") or "")[:500],
    }
    payload.update(_contract_line_dates_and_price(line))
    payload.update(_contract_line_renewal(line))
    payload.update(_contract_line_billing(line))
    payload.update(_contract_line_discounts(line))
    payload.update(_contract_line_supplier(line))
    payload.update(_contract_line_analysis_codes(line))
    return payload


def build_appointment_payload(issue: Dict, scheduled_start: str, scheduled_end: str,
                               employee_ids: List[int], work_briefing: str = "",
                               appointment_type: str = "Work",
                               parent_work_appointment_id: int = 0,
                               charge_rate_id: int = 0,
                               label_id: int = 0,
                               confirmed: bool = True) -> Dict:
    """Build an appointment payload for a Sicon Service Case (spec §3.2 + Phase B work/travel split)."""
    payload: Dict = {
        "SiconAppointmentID": 0,
        "SiSMCaseId": issue.get("sicon_case_id", 0) or 0,
        "SiSMCaseID": issue.get("sicon_case_id", 0) or 0,  # some endpoints use this casing
        "ScheduledStartDate": scheduled_start,
        "ScheduledEndDate": scheduled_end,
        "AppointmentType": appointment_type if appointment_type in ("Work", "Travel", "Other") else "Work",
        "Subject": f"{issue.get('machine_type', '')} — {issue.get('serial_number', '')}".strip(" —"),
        "WorkBriefing": work_briefing[:1000],
        "EmployeeIDs": employee_ids or [],
        "Confirmed": bool(confirmed),
    }
    if parent_work_appointment_id and appointment_type == "Travel":
        payload["ParentWorkAppointmentID"] = int(parent_work_appointment_id)
    if charge_rate_id:
        payload["ChargeRateID"] = int(charge_rate_id)
    if label_id:
        payload["LabelID"] = int(label_id)
    return payload


def build_appointment_completion_payload(work_done: str, further_action: str = "",
                                          arrival_signee: str = "", departure_signee: str = "",
                                          arrival_lat: Optional[float] = None,
                                          arrival_lon: Optional[float] = None,
                                          departure_lat: Optional[float] = None,
                                          departure_lon: Optional[float] = None,
                                          work_done_acknowledged: bool = False,
                                          further_action_acknowledged: bool = False) -> Dict:
    """Build an appointment-update payload used to close out a visit.

    Feeds the proof-of-work chain: signatures + GPS + work-done + follow-up.
    All fields optional — partial updates are safe."""
    payload: Dict = {
        "AppointmentComplete": bool(work_done),
        "WorkDoneDescription": (work_done or "")[:2000],
        "WorkDoneAcknowledged": bool(work_done_acknowledged),
        "FurtherAction": (further_action or "")[:2000],
        "FurtherActionAcknowledged": bool(further_action_acknowledged),
        "ArrivalSignee": (arrival_signee or "")[:120],
        "DepartureSignee": (departure_signee or "")[:120],
    }
    for k, v in (("ArrivalLatitude", arrival_lat), ("ArrivalLongitude", arrival_lon),
                 ("DepartureLatitude", departure_lat), ("DepartureLongitude", departure_lon)):
        if v is not None:
            payload[k] = float(v)
    return payload


def build_time_booking_payload(employee_ids: List[int], start_date: str, end_date: str,
                                actual_hours: float, charge_rate: int = 0) -> Dict:
    """Build a TimeBooking payload for POST /api/Service/Appointments/{id}/TimeBookings."""
    return {
        "EmployeeIDs": employee_ids or [],
        "StartDate": start_date,
        "EndDate": end_date,
        "ActualHours": float(actual_hours or 0),
        "ChargeRate": int(charge_rate or 0),
    }


# ── Mappers: Pulse Fitness stock → Sicon CoreWebAPI ─────────────────────
# Our parts system (svc_parts catalogue, svc_van_stock / svc_warehouse_stock,
# svc_part_movements) maps onto Sage stock through the CoreWebAPI surface.
# See INTEGRATION_FIELD_MAPPING.md §33.13 for the full table + open questions.

def build_internal_issue_payload(part_sku: str, qty, warehouse_name: str,
                                 *, bin_name: str = "", reference: str = "",
                                 second_ref: str = "", cover_category: str = "",
                                 narrative: str = "",
                                 issue_date: Optional[str] = None) -> Dict:
    """StockItem/InternalIssue — book a part out of the engineer's van/warehouse
    when it's consumed on a job (our ``consume`` movement)."""
    return {
        "ItemCode": (part_sku or "").strip().upper(),
        "WarehouseName": warehouse_name or "",
        "BinName": bin_name or "",
        "Reference": (reference or "")[:60],
        "SecondRef": (second_ref or "")[:60],
        "AnalysisCode1": (cover_category or "")[:50],
        "DefaultNarrative": (narrative or "")[:250],
        "Quantity": float(qty or 0),
        "IssueDate": issue_date or datetime.now(timezone.utc).isoformat(),
    }


def build_stock_transfer_payload(part_sku: str, qty, from_warehouse: str,
                                 to_warehouse: str, *, from_bin: str = "",
                                 to_bin: str = "", reference: str = "",
                                 second_reference: str = "",
                                 date: Optional[str] = None) -> Dict:
    """StockItem/TransferStock — warehouse↔van move (our paired
    ``transfer_out``/``transfer_in`` movements become one transfer)."""
    return {
        "ItemCode": (part_sku or "").strip().upper(),
        "FromWarehouse": from_warehouse or "",
        "FromBin": from_bin or "",
        "ToWarehouse": to_warehouse or "",
        "ToBin": to_bin or "",
        "Quantity": float(qty or 0),
        "Date": date or datetime.now(timezone.utc).isoformat(),
        "Reference": (reference or "")[:60],
        "SecondReference": (second_reference or "")[:60],
    }


def build_stock_adjustment_payload(part_sku: str, qty_delta, warehouse_name: str,
                                   *, bin_name: str = "", reference: str = "",
                                   narrative: str = "",
                                   write_off_category: str = "Stock take") -> tuple[str, Dict]:
    """Stock-take variance (our ``adjust`` movement). Positive delta →
    AddStock, negative → WriteOffStock (field names differ between the two
    Sage endpoints). Returns ``(operation, payload)`` where operation is
    ``"stock_add"`` or ``"stock_writeoff"``."""
    item = (part_sku or "").strip().upper()
    qty = abs(float(qty_delta or 0))
    if (qty_delta or 0) >= 0:
        return "stock_add", {
            "ItemCode": item,
            "WarehouseName": warehouse_name or "",
            "BinName": bin_name or "",
            "Reference": (reference or "")[:60],
            "SecondRef": "",
            "Quantity": qty,
            "MovementDate": datetime.now(timezone.utc).isoformat(),
        }
    return "stock_writeoff", {
        "WriteOffCategory": write_off_category,
        "ItemCode": item,
        "WarehouseName": warehouse_name or "",
        "BinName": bin_name or "",
        "Quantity": qty,
        "Reference": (reference or "")[:60],
        "SecondReference": "",
        "MovementDate": datetime.now(timezone.utc).isoformat(),
    }


# ── Mappers: Sicon → Pulse Fitness ──────────────────────────────────────

def _ci(entity: Optional[Dict]) -> Dict:
    """Return a case-insensitive (lower-cased-key) view of a Sicon entity.

    Sicon's Service WebAPI serialises responses in camelCase
    (siSMCaseId, siconAppointmentId, siSMTrackingStatusId, statusId, …)
    whereas our historical mappers used PascalCase (SiSMCaseId,
    SiconAppointmentID, …). Both fold to the same lower-cased key, so
    reading from this view makes us robust to whichever casing the live
    instance emits — the connectivity fix confirmed at the Sicon meeting.
    """
    if not isinstance(entity, dict):
        return {}
    return {str(k).lower(): v for k, v in entity.items()}


def map_sicon_case_to_gymaxis(sicon_case: Dict) -> Dict:
    """Extract Pulse Fitness-relevant fields from a Sicon case response (extended).

    Casing-agnostic: reads camelCase or PascalCase transparently, and resolves
    the id-link fields Sicon confirmed (appointmentId, statusId, tracking-status)."""
    raw = sicon_case.get("entity", sicon_case) if isinstance(sicon_case, dict) else {}
    e = _ci(raw)
    sub = _ci(e.get("sublocation"))
    ct = _ci(e.get("casetype"))
    pr = _ci(e.get("priority"))
    proj = e.get("project")
    proj_ci = _ci(proj)
    admin = e.get("caseadmin")
    admin_ci = _ci(admin)
    return {
        "sicon_case_id": e.get("sismcaseid"),
        "sicon_case_number": e.get("casenumber"),
        "sicon_status_id": e.get("sismdocumentstatusid"),
        "sicon_status": e.get("sismdocumentstatusname", "Unknown"),
        "sicon_sub_status_id": e.get("sismdocumentsubstatusid"),
        # Tracking-status link (Sicon confirmed): case.statusId / case.status
        "sicon_tracking_status_id": e.get("statusid"),
        "sicon_tracking_status": e.get("status"),
        "sicon_last_tracking_status": e.get("lasttrackingstatus"),
        "sicon_last_updated_at": e.get("lastupdateddate"),
        # Linked appointment + latest note ids (Sicon confirmed)
        "sicon_appointment_id": e.get("appointmentid"),
        "sicon_latest_note_id": e.get("sismcasetrackingnoteid"),
        "sicon_customer_order_number": e.get("customerorderno") or e.get("customerordernumber"),
        # Sicon meeting follow-up (2026-06) — now read into Pulse too
        "sicon_cover_type": e.get("covertype"),
        "sicon_fault_code": e.get("faultcode"),
        "sicon_sla": e.get("sla"),
        "sicon_latest_note": e.get("note"),
        "sicon_project_id": (proj_ci.get("id") or proj_ci.get("sijcprojectid")) if isinstance(proj, dict) else proj,
        "sicon_project_name": proj_ci.get("name") if isinstance(proj, dict) else None,
        "sicon_case_admin_id": (admin_ci.get("id") or admin_ci.get("sageuserid")) if isinstance(admin, dict) else admin,
        "sicon_case_admin_name": (admin_ci.get("name") or admin_ci.get("fullname")) if isinstance(admin, dict) else None,
        "sicon_description": e.get("description"),
        "sicon_summary": e.get("summary"),
        "sicon_priority_id": e.get("priorityid") or pr.get("sismpriorityid"),
        "sicon_priority": e.get("priorityname") or pr.get("name"),
        "sicon_assigned_to": e.get("assignedtosageuser"),
        "sicon_assigned_to_id": e.get("assignedtosageuserid"),
        "sicon_internal_team": e.get("internalteam"),
        "sicon_internal_team_id": e.get("internalteamid"),
        "sicon_external_team": e.get("externalteam"),
        "sicon_external_team_id": e.get("externalteamid"),
        "sicon_contact_name": e.get("contactname"),
        "sicon_contact_email": e.get("contactemail"),
        "sicon_contact_phone": e.get("contactphonenumber"),
        "sicon_call_date": e.get("calldate"),
        "sicon_customer_reference": e.get("customerreference"),
        "sicon_sl_customer_account_id": e.get("slcustomeraccountid"),
        "sicon_case_type_id": e.get("casetypeid") or ct.get("sismcasetypeid"),
        "sicon_case_type_name": e.get("casetypename") or ct.get("name"),
        "sicon_contract_id": e.get("siconcontractid"),
        "sicon_contract_number": e.get("siconcontractnumber"),
        "sicon_contract_line_id": e.get("siconcontractlineid"),
        "sicon_contract_line_number": e.get("siconcontractlinenumber"),
        "sicon_job_id": e.get("sijcjobid"),
        "sicon_crm_person_id": e.get("siconcrmpersonid"),
        "sicon_crm_company_id": e.get("siconcrmcompanyid"),
        "sicon_sub_location_id": sub.get("siconsublocationid") or sub.get("siconsublocationdbkey"),
        "sicon_sub_location_description": sub.get("description"),
        "sicon_sub_location_comment": sub.get("comment"),
        "sicon_equipment_ids": e.get("equipmentids") or [
            _ci(x).get("siconequipmentid") for x in (e.get("equipments") or [])
            if _ci(x).get("siconequipmentid")
        ],
    }


def map_sicon_appointment_to_gymaxis(appointment: Dict) -> Dict:
    """Extract Pulse Fitness-relevant fields from a Sicon appointment (spec §3.2). Casing-agnostic."""
    raw = appointment.get("entity", appointment) if isinstance(appointment, dict) else {}
    e = _ci(raw)
    return {
        "sicon_appointment_id": e.get("siconappointmentid") or e.get("appointmentid"),
        "sicon_case_id": e.get("sismcaseid"),
        "scheduled_start": e.get("scheduledstartdate"),
        "scheduled_end": e.get("scheduledenddate"),
        "appointment_type": e.get("appointmenttype"),
        "work_done_description": e.get("workdonedescription"),
        "further_action": e.get("furtheraction"),
        "arrival_signee": e.get("arrivalsignee"),
        "departure_signee": e.get("departuresignee"),
        "arrival_latitude": e.get("arrivallatitude"),
        "arrival_longitude": e.get("arrivallongitude"),
        "departure_latitude": e.get("departurelatitude"),
        "departure_longitude": e.get("departurelongitude"),
        "appointment_complete": e.get("appointmentcomplete", False),
        "confirmed": e.get("confirmed", False),
        "employee_ids": e.get("employeeids", []),
        "subject": e.get("subject"),
        "costing_hours": e.get("costinghours"),
        "charging_hours": e.get("charginghours"),
        "is_estimate": e.get("isestimate", False),
    }


def map_sicon_time_booking_to_gymaxis(booking: Dict) -> Dict:
    """Map a Sicon time booking (spec §3.3). Casing-agnostic."""
    raw = booking.get("entity", booking) if isinstance(booking, dict) else {}
    e = _ci(raw)
    return {
        "start_date": e.get("startdate"),
        "end_date": e.get("enddate"),
        "actual_hours": e.get("actualhours") or e.get("costinghours"),
        "costing_hours": e.get("costinghours"),
        "charging_hours": e.get("charginghours"),
        "charge_rate": e.get("chargerate"),
        "is_estimate": e.get("isestimate", False),
        "employee_ids": e.get("employeeids", []),
    }


def map_sicon_tracking_note_to_gymaxis(note: Dict) -> Dict:
    """Map a Sicon tracking note (spec §3.4). Casing-agnostic; resolves statusId variants."""
    raw = note.get("entity", note) if isinstance(note, dict) else {}
    e = _ci(raw)
    return {
        "sicon_note_id": e.get("sismcasetrackingnoteid") or e.get("id") or e.get("trackingnoteid"),
        "message": e.get("trackingnote") or e.get("note"),
        "timestamp": e.get("time"),
        "by": e.get("user") or e.get("createdby"),
        "case_tracking_status_id": e.get("casetrackingstatusid") or e.get("statusid") or e.get("sismtrackingstatusid"),
        "status": e.get("status"),
        "visible_to_engineer": e.get("visibletoengineer", True),
        "visible_to_customer": e.get("visibletocustomer", False),
        "sicon_appointment_id": e.get("siconappointmentid") or e.get("appointmentid"),
        "latitude": e.get("latitude"),
        "longitude": e.get("longitude"),
    }


def map_sicon_resource_to_engineer(entity: Dict) -> Dict:
    """Phase C — map a Sicon AppointmentResource to a Pulse Fitness-side engineer doc.

    Used by the nightly directory refresh. Filters leavers out upstream. Casing-agnostic."""
    e = _ci(entity)
    return {
        "sicon_employee_id": e.get("sijcempid"),
        "full_name": e.get("fullname") or f"{e.get('firstname', '')} {e.get('surname', '')}".strip(),
        "first_name": e.get("firstname"),
        "surname": e.get("surname"),
        "diary_colour": e.get("diarycolour"),
        "employee_number": e.get("employeenumber"),
        "payroll_reference": e.get("payrollreference"),
        "post_code_area": e.get("postcodearea"),
        "team_name": e.get("team"),
        "team_id": e.get("siconteamid"),
        "subcontractor_account_id": e.get("subcontractoraccountid"),
        "contract_expiry_date": e.get("contractexpirydate"),
        "warehouse_name": e.get("warehousename"),
        "warehouse_id": e.get("warehouseid"),
        "is_team_leader": bool(e.get("isteamleader", False)),
        "is_leaver": bool(e.get("isleaver", False)),
        "is_project_manager": bool(e.get("isprojectmanager", False)),
        "is_shop_floor_user": bool(e.get("isshopflooruser", False)),
        "start_date": e.get("startdate"),
        "address_line1": e.get("addressline1"),
        "city": e.get("city"),
        "postcode": e.get("postcode"),
        "mobile_no": e.get("mobileno"),
        "telephone_no": e.get("telephoneno"),
        "email": e.get("email"),
    }
