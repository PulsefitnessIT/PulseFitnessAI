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


# ── Client ────────────────────────────────────────────────────────

class SiconClient:
    """
    Client for the Sicon Service WebAPI (R260200c).
    All calls are server-to-server over HTTPS with Basic auth.
    """

    def __init__(self, base_url: str, username: str, password: str, company_id: int = 0, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.company_id = company_id
        self.timeout = timeout
        self._auth = (username, password)

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

    # ── Case Types / Statuses / Priorities ────────────────────────
    async def get_case_types(self) -> Dict:
        return await self._request("GET", "/api/service/case-types")

    async def get_tracking_statuses(self) -> Dict:
        return await self._request("GET", "/api/service/case-tracking-statuses")

    async def get_priorities(self) -> Dict:
        return await self._request("GET", "/api/service/priorities")

    # ── Tracking Notes ────────────────────────────────────────────
    async def get_tracking_notes(self, case_id: int) -> Dict:
        return await self._request("GET", f"/api/Service/Cases/{case_id}/TrackingNotes")

    async def create_tracking_note(self, case_id: int, note_data: Dict) -> Dict:
        return await self._request("POST", f"/api/Service/Cases/{case_id}/TrackingNotes", json_body=note_data)

    # ── Appointments ──────────────────────────────────────────────
    async def get_appointment(self, appointment_id: int) -> Dict:
        return await self._request("GET", f"/api/service/appointments/{appointment_id}")

    async def get_appointments_for_case(self, case_id: int) -> Dict:
        return await self._request("GET", "/api/service/appointments", params={"caseid": case_id})

    async def create_appointment(self, appointment_data: Dict) -> Dict:
        return await self._request("POST", "/api/Service/Appointments", json_body=appointment_data)

    async def update_appointment(self, appointment_id: int, appointment_data: Dict) -> Dict:
        return await self._request("PUT", f"/api/Service/Appointments/{appointment_id}", json_body=appointment_data)

    async def delete_appointment(self, appointment_id: int) -> Dict:
        return await self._request("DELETE", f"/api/service/appointments/{appointment_id}")

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


# ── Mappers: GymAxis → Sicon ──────────────────────────────────────

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
    """Build a Sicon SubLocation object from a GymAxis site doc.

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
    """Build a Sicon Service Case payload from a GymAxis issue.

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


def build_tracking_note_payload(note_text: str, created_by: str = "GymAxis AI",
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
    """Serialise GymAxis metadata into Sicon Contract spare slots.

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
    """Map a GymAxis CRM contract to a Sicon Contract header (Contracts.R260200c §Contract)."""
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
    """Pack SLA + GymAxis custom metadata into Sicon's analysis-code slots.

    Uses CLAnalysisCode1-15 by convention (out of 150 available). Reserved:
    - CL1  = SLA tier (Gold / Platinum / Silver)
    - CL2  = Response-hours target
    - CL3  = Resolution-hours target
    - CL4  = OOS credit terms
    - CL5  = Safety-critical flag
    - CL6  = GymAxis internal asset_id (for joins)
    - CL7  = GymAxis site_id
    - CL8  = PPM frequency override (if different from VisitFrequency)
    - CL9  = Tender pack reference
    - CL10 = Renewal notice days

    Iter 216h7 — extended with five finance/governance signals so the
    Sicon side can drive automation (penalty calc, escalation, etc.):
    - CL11 = SLA penalty band ("0/5/10/25%" or absolute credit code)
    - CL12 = KPI breach flag ("OK"|"WARN"|"BREACH") set by GymAxis SLA worker
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
    """Map a GymAxis CRM contract line to a Sicon ContractLine payload."""
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


# ── Mappers: Sicon → GymAxis ──────────────────────────────────────

def map_sicon_case_to_gymaxis(sicon_case: Dict) -> Dict:
    """Extract GymAxis-relevant fields from a Sicon case response (extended)."""
    entity = sicon_case.get("entity", sicon_case) if isinstance(sicon_case, dict) else {}
    sub_loc = entity.get("SubLocation") or {}
    return {
        "sicon_case_id": entity.get("SiSMCaseId"),
        "sicon_case_number": entity.get("CaseNumber"),
        "sicon_status_id": entity.get("SiSMDocumentStatusID"),
        "sicon_status": entity.get("SiSMDocumentStatusName", "Unknown"),
        "sicon_sub_status_id": entity.get("SiSMDocumentSubStatusID"),
        "sicon_description": entity.get("Description"),
        "sicon_summary": entity.get("Summary"),
        "sicon_priority_id": entity.get("PriorityID"),
        "sicon_priority": entity.get("PriorityName"),
        "sicon_assigned_to": entity.get("AssignedToSageUser"),
        "sicon_assigned_to_id": entity.get("AssignedToSageUserID"),
        "sicon_internal_team": entity.get("InternalTeam"),
        "sicon_internal_team_id": entity.get("InternalTeamID"),
        "sicon_external_team": entity.get("ExternalTeam"),
        "sicon_external_team_id": entity.get("ExternalTeamID"),
        "sicon_contact_name": entity.get("ContactName"),
        "sicon_contact_email": entity.get("ContactEmail"),
        "sicon_contact_phone": entity.get("ContactPhoneNumber"),
        "sicon_call_date": entity.get("CallDate"),
        "sicon_customer_reference": entity.get("CustomerReference"),
        "sicon_sl_customer_account_id": entity.get("SLCustomerAccountID"),
        "sicon_case_type_id": entity.get("CaseTypeID"),
        "sicon_case_type_name": entity.get("CaseTypeName"),
        "sicon_contract_id": entity.get("SiconContractID"),
        "sicon_contract_number": entity.get("SiconContractNumber"),
        "sicon_contract_line_id": entity.get("SiconContractLineID"),
        "sicon_contract_line_number": entity.get("SiconContractLineNumber"),
        "sicon_job_id": entity.get("SiJcJobID"),
        "sicon_crm_person_id": entity.get("SiconCRMPersonID"),
        "sicon_crm_company_id": entity.get("SiconCRMCompanyID"),
        "sicon_sub_location_id": sub_loc.get("SiconSubLocationID"),
        "sicon_sub_location_description": sub_loc.get("Description"),
        "sicon_sub_location_comment": sub_loc.get("Comment"),
        "sicon_equipment_ids": entity.get("EquipmentIDs") or [
            e.get("SiconEquipmentID") for e in (entity.get("Equipments") or []) if e.get("SiconEquipmentID")
        ],
    }


def map_sicon_appointment_to_gymaxis(appointment: Dict) -> Dict:
    """Extract GymAxis-relevant fields from a Sicon appointment (spec §3.2)."""
    entity = appointment.get("entity", appointment) if isinstance(appointment, dict) else {}
    return {
        "sicon_appointment_id": entity.get("SiconAppointmentID"),
        "scheduled_start": entity.get("ScheduledStartDate"),
        "scheduled_end": entity.get("ScheduledEndDate"),
        "appointment_type": entity.get("AppointmentType"),
        "work_done_description": entity.get("WorkDoneDescription"),
        "further_action": entity.get("FurtherAction"),
        "arrival_signee": entity.get("ArrivalSignee"),
        "departure_signee": entity.get("DepartureSignee"),
        "arrival_latitude": entity.get("ArrivalLatitude"),
        "arrival_longitude": entity.get("ArrivalLongitude"),
        "departure_latitude": entity.get("DepartureLatitude"),
        "departure_longitude": entity.get("DepartureLongitude"),
        "appointment_complete": entity.get("AppointmentComplete", False),
        "confirmed": entity.get("Confirmed", False),
        "employee_ids": entity.get("EmployeeIDs", []),
        "subject": entity.get("Subject"),
    }


def map_sicon_time_booking_to_gymaxis(booking: Dict) -> Dict:
    """Map a Sicon time booking (spec §3.3)."""
    entity = booking.get("entity", booking) if isinstance(booking, dict) else {}
    return {
        "start_date": entity.get("StartDate"),
        "end_date": entity.get("EndDate"),
        "actual_hours": entity.get("ActualHours"),
        "employee_ids": entity.get("EmployeeIDs", []),
    }


def map_sicon_tracking_note_to_gymaxis(note: Dict) -> Dict:
    """Map a Sicon tracking note (spec §3.4)."""
    entity = note.get("entity", note) if isinstance(note, dict) else {}
    return {
        "sicon_note_id": entity.get("ID") or entity.get("TrackingNoteID"),
        "message": entity.get("TrackingNote"),
        "timestamp": entity.get("Time"),
        "by": entity.get("User") or entity.get("CreatedBy"),
        "case_tracking_status_id": entity.get("CaseTrackingStatusID"),
        "status": entity.get("Status"),
        "visible_to_engineer": entity.get("VisibleToEngineer", True),
        "visible_to_customer": entity.get("VisibleToCustomer", False),
        "sicon_appointment_id": entity.get("SiconAppointmentID"),
        "latitude": entity.get("Latitude"),
        "longitude": entity.get("Longitude"),
    }


def map_sicon_resource_to_engineer(entity: Dict) -> Dict:
    """Phase C — map a Sicon AppointmentResource to a GymAxis-side engineer doc.

    Used by the nightly directory refresh. Filters leavers out upstream."""
    return {
        "sicon_employee_id": entity.get("SIJCEMPID"),
        "full_name": entity.get("FullName") or f"{entity.get('FirstName', '')} {entity.get('Surname', '')}".strip(),
        "first_name": entity.get("FirstName"),
        "surname": entity.get("Surname"),
        "diary_colour": entity.get("DiaryColour"),
        "employee_number": entity.get("EmployeeNumber"),
        "payroll_reference": entity.get("PayrollReference"),
        "post_code_area": entity.get("PostCodeArea"),
        "team_name": entity.get("Team"),
        "team_id": entity.get("SiconTeamID"),
        "subcontractor_account_id": entity.get("SubContractorAccountID"),
        "contract_expiry_date": entity.get("ContractExpiryDate"),
        "warehouse_name": entity.get("WarehouseName"),
        "warehouse_id": entity.get("WarehouseID"),
        "is_team_leader": bool(entity.get("IsTeamLeader", False)),
        "is_leaver": bool(entity.get("IsLeaver", False)),
        "is_project_manager": bool(entity.get("IsProjectManager", False)),
        "is_shop_floor_user": bool(entity.get("IsShopFloorUser", False)),
        "start_date": entity.get("StartDate"),
        "address_line1": entity.get("AddressLine1"),
        "city": entity.get("City"),
        "postcode": entity.get("PostCode"),
        "mobile_no": entity.get("MobileNo"),
        "telephone_no": entity.get("TelephoneNo"),
        "email": entity.get("Email"),
    }
