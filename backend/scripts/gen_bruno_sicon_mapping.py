#!/usr/bin/env python3
"""Build THE single, importable Sicon Service Bruno collection + field-map pack.

This is the one generator for the consolidated Sicon integration hand-over.
It reads the verbatim Sicon-provided Bruno collections (persisted in-repo under
integrations/sicon/_source) and the platform mapping table
(routes/sicon_mapping.py), and emits into integrations/sicon/:

  bruno/                       importable Bruno collection (bruno.json + requests
                               + environments) — merges the Platform Auth request
                               with the full Service WebAPI plugin so ONE import
                               authenticates AND drives every Service entity.
  bruno/environments/          Local + Production env templates (secrets blank).
  FIELD_MAPPING.md, mapping.csv  Sicon Service field -> Pulse field, per entity.
  README.md                    single-location index.
  Sicon-Service-Pulse.bruno.zip  ready to import into Bruno.

Auto-mapping: entity ids (caseId, equipmentId, appointmentId, caseTypeId,
priorityId, trackingStatusId, statusId, trackingNoteId, timeBookingId) live as
ENVIRONMENT vars and are captured by post-response scripts, so running Auth ->
metadata GetMany -> Case PostOne -> Appointment/TrackingNote/Equipment chains
without any manual id copying.

No credentials are ever written. password is a blank secret env var; the user
pastes it in Bruno locally.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # /app
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "integrations" / "sicon"
SRC_SERVICE = OUT / "_source" / "service"
SRC_PLATFORM = OUT / "_source" / "platform"
COLL = OUT / "bruno"

sys.path.insert(0, str(ROOT / "backend"))
from routes.sicon_mapping import SICON_FIELD_MAPPING  # noqa: E402


# ── field-map join helpers ─────────────────────────────────────────
def _leaf(sicon_field: str) -> str:
    return re.sub(r"[^a-z0-9]", "", sicon_field.split(".")[-1].lower())


# nested-Sicon-key -> table-leaf aliases (the Service wire nests what the
# platform mapping table records as flat Location*/caseType/priority fields).
ALIASES = {
    "postalname": "locationpostalname",
    "addressline1": "locationaddressline1",
    "addressline2": "locationaddressline2",
    "addressline3": "locationaddressline3",
    "addressline4": "locationaddressline4",
    "city": "locationcity",
    "county": "locationcounty",
    "postcode": "locationpostcode",
    "sismcasetypeid": "casetypeid",
    "sismpriorityid": "priorityid",
    "sismdocumentstatusid": "sismdocumentstatusid",
    "sismdocumentstatusname": "sismdocumentstatusname",
    "sismdocumentsubstatusid": "sismdocumentsubstatusid",
    "siconcrmpersonid": "siconcrmpersonid",
    "siconcrmcompanyid": "siconcrmcompanyid",
    "sopdeladdress": "address",
}

# Sicon-owned / display-only fields confirmed at the 2026-06 meeting as
# Sicon-side concerns — surfaced read-only, no Pulse mapping required.
# These are reported as SICON-OWNED (not gaps) so coverage reflects reality.
SICON_OWNED = frozenset({
    "isenabled", "iscustom", "colour", "defaultappointmentlabel", "systemtype",
    "isnoncontract", "ispreventativemaintenancetype", "skill",
    "reassignedtocaseownerid", "reassignedtointernalteamid", "reassignedtoexternalteamid",
})

by_leaf: dict[str, list[dict]] = {}
for r in SICON_FIELD_MAPPING:
    by_leaf.setdefault(_leaf(r["sicon_field"]), []).append(r)


def _lookup(key: str) -> list[dict]:
    lf = _leaf(key)
    if lf in by_leaf:
        return by_leaf[lf]
    if lf in ALIASES and ALIASES[lf] in by_leaf:
        return by_leaf[ALIASES[lf]]
    # analysisField1 / analysisCode3 -> the "1-20" catch-all rows
    m = re.match(r"^(analysisfield|analysiscode|clanalysiscode|sparetext|sparenum|sparedate)(\d+)$", lf)
    if m:
        for cand in by_leaf:
            if cand.startswith(m.group(1)) and re.search(r"\d+.*\d+", cand):
                return by_leaf[cand]
    return []


def parse_bru_body_keys(text: str) -> list[str]:
    m = re.search(r"body:json\s*\{(.*)\n\}", text, re.S)
    if not m:
        return []
    seen, out = set(), []
    for k in re.findall(r'"([A-Za-z0-9_]+)"\s*:', m.group(1)):
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


# ── authoritative Sicon Sage 200 Service WebAPI routes ─────────────
# The Sicon-provided collection used a fabricated "/api/v1/SiconService/{Entity}"
# scheme that the live WebAPI rejects ("no Api Controller or Action matching the
# Uri Provided"). These are the real routes our production client (sicon_client.py)
# + the audited spec use. path -> corrected URL (None = keep source URL + WARN).
ROUTE_MAP = {
    "Core/Ping/Ping.bru": "{{baseUrl}}/api/SMConnectivity/Ping",

    "Cases/Case/GetOne_ById.bru": "{{baseUrl}}/api/service/cases/{{caseId}}",
    "Cases/Case/GetOne_ByCaseNumber.bru": "{{baseUrl}}/api/service/cases?caseNumber={{caseNumber}}",
    "Cases/Case/PostOne.bru": "{{baseUrl}}/api/ServiceCase/CreateNewCase",
    "Cases/Case/PutOne.bru": "{{baseUrl}}/api/ServiceCase/AmendCase",
    "Cases/CaseSearch/GetMany.bru": "{{baseUrl}}/api/service/cases",
    "Cases/CaseSearch/GetOne_ById.bru": "{{baseUrl}}/api/service/cases/{{caseId}}",
    "Cases/CaseSearch/GetOne_ByCaseNumber.bru": "{{baseUrl}}/api/service/cases?caseNumber={{caseNumber}}",
    "Cases/CaseTrackingNote/GetMany.bru": "{{baseUrl}}/api/Service/Cases/{{caseId}}/TrackingNotes",
    "Cases/CaseTrackingNote/GetOne.bru": "{{baseUrl}}/api/Service/Cases/{{caseId}}/TrackingNotes/{{trackingNoteId}}",
    "Cases/CaseTrackingNote/PostOne.bru": "{{baseUrl}}/api/Service/Cases/{{caseId}}/TrackingNotes",
    "Cases/CaseTrackingNote/PutOne.bru": "{{baseUrl}}/api/Service/Cases/{{caseId}}/TrackingNotes/{{trackingNoteId}}",
    "Cases/CaseAppointment/GetMany.bru": "{{baseUrl}}/~/api/v2/TEntity/api/service/appointments",
    "Cases/CaseEquipment/GetMany.bru": "{{baseUrl}}/api/service/cases/{{caseId}}",

    "Appointments/Appointment/GetOne.bru": "{{baseUrl}}/~/api/v2/TEntity/api/service/appointments/{{appointmentId}}",
    "Appointments/Appointment/PostOne.bru": "{{baseUrl}}/~/api/v2/TEntity/api/Service/Appointments",
    "Appointments/Appointment/PutOne.bru": "{{baseUrl}}/~/api/v2/TEntity/api/Service/Appointments/{{appointmentId}}",
    "Appointments/AppointmentResource/GetMany.bru": "{{baseUrl}}/api/service/appointments/resources",
    "Appointments/AppointmentTimeBooking/GetMany.bru": "{{baseUrl}}/api/Service/Appointments/{{appointmentId}}/TimeBookings",
    "Appointments/AppointmentTimeBooking/PostOne.bru": "{{baseUrl}}/api/Service/Appointments/{{appointmentId}}/TimeBookings",
    "Appointments/AppointmentTimeBooking/PutOne.bru": "{{baseUrl}}/api/Service/Appointments/{{appointmentId}}/TimeBookings/{{timeBookingId}}",

    "Metadata/CaseType/GetMany.bru": "{{baseUrl}}/api/service/case-types",
    "Metadata/CaseType/GetOne.bru": "{{baseUrl}}/api/service/case-types/{{caseTypeId}}",
    "Tracking/TrackingStatus/GetMany.bru": "{{baseUrl}}/api/service/case-tracking-statuses",
    "Tracking/TrackingStatus/GetOne.bru": "{{baseUrl}}/api/service/case-tracking-statuses/{{trackingStatusId}}",
    # Priority + Equipment: no authoritative Service WebAPI route (see WARN below).
}

# path -> WARNING appended to the request docs (unverified / endpoint may not exist)
WARN = {
    "Metadata/Priority/GetMany.bru": "UNVERIFIED: the Service WebAPI (audit R260200c) exposes NO priorities lookup endpoint. PriorityID is config-mapped in Pulse. Confirm with Sicon if a live route now exists; otherwise this request will 404.",
    "Metadata/Priority/GetOne.bru": "UNVERIFIED: no priorities endpoint in the Service WebAPI. PriorityID is config-mapped. Confirm with Sicon.",
    "Equipment/Equipment/GetMany.bru": "UNVERIFIED: historically the Service WebAPI has NO standalone Equipment endpoint (equipment is referenced via EquipmentIDs on a case). Confirm the live route with Sicon before use.",
    "Equipment/Equipment/GetOne.bru": "UNVERIFIED: no confirmed standalone Equipment route. Confirm with Sicon.",
    "Equipment/Equipment/PostOne.bru": "UNVERIFIED: no confirmed standalone Equipment route. Confirm with Sicon.",
    "Equipment/Equipment/PutOne.bru": "UNVERIFIED: no confirmed standalone Equipment route. Confirm with Sicon.",
    "Cases/CaseEquipment/GetMany.bru": "Equipment is embedded on the case as EquipmentIDs; this points at the case read. Confirm a dedicated route with Sicon if you need the expanded equipment list.",
    "Cases/CaseAppointment/GetMany.bru": "No case-scoped appointment filter exists; this uses the paged TEntity appointments feed. Filter client-side by siSMCaseId.",
    "Appointments/Appointment/GetOne.bru": "Appointment routes go via the TEntity v2 gateway (/~/api/v2/TEntity/...) per the current production client. Confirm against your instance.",
    "Appointments/Appointment/PostOne.bru": "Appointment create via TEntity v2 gateway per production client. Confirm against your instance.",
    "Appointments/Appointment/PutOne.bru": "Appointment update via TEntity v2 gateway per production client. Confirm against your instance.",
    "Cases/Case/PutOne.bru": "Case amend is POST /api/ServiceCase/AmendCase (not a REST PUT) per the Service WebAPI.",
    "Cases/Case/PostOne.bru": "Case create is POST /api/ServiceCase/CreateNewCase per the Service WebAPI.",
}


def _rewrite_url(text: str, new_url: str) -> str:
    return re.sub(r"(?m)^(\s*url:\s*).*$", lambda m: m.group(1) + new_url, text, count=1)


def _append_docs(text: str, note: str) -> str:
    line = f"  \u26a0 {note}"
    m = re.search(r"(?ms)^docs\s*\{.*?^\}", text)
    if m:
        block = m.group(0)
        new_block = block[:-1].rstrip() + "\n" + line + "\n}"
        return text[:m.start()] + new_block + text[m.end():]
    return text.rstrip() + "\n\ndocs {\n" + line + "\n}\n"




# ── auto-chaining post-response capture scripts ─────────────────────
# path -> list of (sicon_body_key, env_var) captured from a SINGLE object body
CAPTURE_ONE = {
    "Cases/Case/PostOne.bru": [("siSMCaseId", "caseId"), ("caseNumber", "caseNumber")],
    "Cases/Case/PutOne.bru": [("siSMCaseId", "caseId")],
    "Cases/Case/GetOne_ById.bru": [("siSMCaseId", "caseId"), ("caseNumber", "caseNumber")],
    "Cases/Case/GetOne_ByCaseNumber.bru": [("siSMCaseId", "caseId"), ("caseNumber", "caseNumber")],
    "Cases/CaseTrackingNote/PostOne.bru": [("siSMCaseTrackingNoteId", "trackingNoteId")],
    "Equipment/Equipment/PostOne.bru": [("siconEquipmentId", "equipmentId")],
    "Equipment/Equipment/PutOne.bru": [("siconEquipmentId", "equipmentId")],
    "Equipment/Equipment/GetOne.bru": [("siconEquipmentId", "equipmentId")],
    "Appointments/Appointment/PostOne.bru": [("siconAppointmentId", "appointmentId")],
    "Appointments/Appointment/PutOne.bru": [("siconAppointmentId", "appointmentId")],
    "Appointments/Appointment/GetOne.bru": [("siconAppointmentId", "appointmentId")],
}
# path -> list of (sicon_body_key, env_var) captured from the FIRST list item
# Metadata auto-capture REMOVED — do not auto-use the first CaseType/Priority/
# TrackingStatus row. Operators pick explicitly via selectedCaseTypeId /
# selectedPriorityId / selectedTrackingStatusId from the lookup responses.
CAPTURE_LIST = {}

# GET requests get response-tests that assert these fields exist + record types.
GET_TEST_FIELDS = {
    "Cases": ["siSMCaseId", "caseNumber", "statusId", "appointmentId"],
    "Appointments": ["siconAppointmentId", "siSMCaseId", "scheduledStartDate"],
    "Equipment": ["siconEquipmentId", "serialNumber", "description"],
}
# Metadata lists: path -> (env var to set manually, id field, label field)
METADATA_LIST = {
    "Metadata/CaseType/GetMany.bru": ("selectedCaseTypeId", "siSMCaseTypeId", "name"),
    "Metadata/Priority/GetMany.bru": ("selectedPriorityId", "siSMPriorityId", "name"),
    "Tracking/TrackingStatus/GetMany.bru": ("selectedTrackingStatusId", "siSMTrackingStatusId", "name"),
}
# Extra Sicon reference/lookup requests: (name, route, needs_confirmation, note)
LOOKUPS = [
    ("Employees", "/api/service/appointments/resources", False,
     "Engineers / resources -> Pulse engineer (map_sicon_resource_to_engineer). Sicon field SIJCEMPID <-> Pulse engineer.sicon_employee_id. Direction: Sicon->Pulse."),
    ("Contracts", "/api/service/contracts", True,
     "Contracts lookup -> Pulse contract.sicon_contract_id. SICON CONFIRMATION REQUIRED: GET route unconfirmed (the Contract API is POST-only for create/update)."),
    ("CoverTypes", "/api/service/cover-types", True,
     "Cover types -> Pulse issue.cover_type. Direction: Sicon metadata. SICON CONFIRMATION REQUIRED: route unconfirmed."),
    ("SLAs", "/api/service/slas", True,
     "SLA bands -> Pulse issue.sla_category. Direction: Sicon metadata. SICON CONFIRMATION REQUIRED: route unconfirmed."),
    ("FaultCodes", "/api/service/fault-codes", True,
     "Fault codes -> Pulse issue.fault_code. Direction: Sicon metadata. SICON CONFIRMATION REQUIRED: route unconfirmed."),
    ("Skills", "/api/service/skills", True,
     "Engineer skills -> Pulse engineer.skills. Direction: Sicon metadata. SICON CONFIRMATION REQUIRED: route unconfirmed."),
    ("Teams", "/api/service/teams", True,
     "Internal / external teams -> Pulse config team ids. Direction: Sicon metadata. SICON CONFIRMATION REQUIRED: route unconfirmed."),
]


def _capture_block(pairs, is_list: bool) -> str:
    lines = ["script:post-response {", "  const b = res.getBody() || {};"]
    if is_list:
        lines.append("  const arr = Array.isArray(b) ? b : (b.data || b.items || b.results || b.records || []);")
        lines.append("  const item = (arr && arr.length) ? arr[0] : null;")
    else:
        lines.append("  const item = (b && b.data && !Array.isArray(b)) ? b.data : b;")
    lines.append("  if (item) {")
    for src, env in pairs:
        lines.append(f"    if (item.{src} != null) bru.setEnvVar('{env}', item.{src});")
        lines.append(f"    else if (item.id != null) bru.setEnvVar('{env}', item.id);")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


# ── environment / root files ────────────────────────────────────────
ID_VARS = [
    ("caseId", "0"), ("caseNumber", "0"), ("appointmentId", "0"),
    ("timeBookingId", "0"), ("trackingNoteId", "0"), ("equipmentId", "0"),
    ("employeeId", "0"),
]
# Control + explicit-selection vars (NOT auto-populated).
CONTROL_VARS = [
    ("ALLOW_WRITES", "false"), ("pageSize", "200"), ("page", "1"),
    ("selectedCaseTypeId", ""), ("selectedPriorityId", ""), ("selectedTrackingStatusId", ""),
]


def _env_file(base_url: str, company_id: str) -> str:
    lines = ["vars {",
             f"  baseUrl: {base_url}",
             "  username: Administrator",
             f"  companyId: {company_id}",
             "  BEARER_TOKEN: "]
    for k, v in ID_VARS + CONTROL_VARS:
        lines.append(f"  {k}: {v}")
    lines.append("}")
    lines.append("")
    lines.append("vars:secret [")
    lines.append("  password")
    lines.append("]")
    lines.append("")
    lines.append("docs {")
    lines.append("  Set baseUrl + companyId (Sage company) and paste the secret 'password'.")
    lines.append("  Run Auth > Authenticate first (captures BEARER_TOKEN).")
    lines.append("  SAFETY: ALLOW_WRITES defaults to false — POST/PUT/PATCH/DELETE are blocked")
    lines.append("  until you set ALLOW_WRITES=true (Auth is exempt).")
    lines.append("  SELECTION: choose selectedCaseTypeId / selectedPriorityId / selectedTrackingStatusId")
    lines.append("  from the Metadata lookup responses — they are NOT auto-selected.")
    lines.append("  Entity ids (caseId/appointmentId/...) are captured from create/get responses.")
    lines.append("}")
    return "\n".join(lines) + "\n"


ROOT_BRUNO_JSON = json.dumps({
    "version": "1",
    "name": "Sicon Service - Pulse Fitness",
    "type": "collection",
    "ignore": ["node_modules", ".git"],
}, indent=2) + "\n"

ROOT_COLLECTION_BRU = """auth {
  mode: bearer
}

auth:bearer {
  token: {{BEARER_TOKEN}}
}

headers {
  Accept: application/json
}

script:pre-request {
  // SAFETY GUARD: block writes unless ALLOW_WRITES=true (Auth is exempt).
  const m = (req.getMethod() || '').toUpperCase();
  const url = (req.getUrl() || '').toLowerCase();
  const allow = String(bru.getEnvVar('ALLOW_WRITES') || bru.getVar('ALLOW_WRITES') || 'false').toLowerCase() === 'true';
  if (['POST', 'PUT', 'PATCH', 'DELETE'].indexOf(m) !== -1 && url.indexOf('authenticate') === -1 && !allow) {
    throw new Error('Writes are disabled. Set ALLOW_WRITES=true in the environment to enable ' + m + ' requests.');
  }
}

docs {
  Sicon Service WebAPI - PulseFitness.ai consolidated collection.
  Package also contains FIELD_MAPPING.md + mapping.csv (Sicon field -> Pulse field, per entity).
  SAFETY: POST/PUT are blocked unless ALLOW_WRITES=true. Metadata (CaseType/Priority/
  TrackingStatus) is NOT auto-selected — set the selected* vars manually.
  All Service requests inherit the bearer token from Auth > Authenticate.
  companyId (Sage company) is passed as ?companyId={{companyId}} on every request.
}
"""

AUTH_BRU = """meta {
  name: Authenticate
  type: http
  seq: 1
}

post {
  url: {{baseUrl}}/api/v1/authentication/authenticate
  body: json
  auth: none
}

headers {
  Content-Type: application/json
}

body:json {
  {
    "username": "{{username}}",
    "password": "{{password}}"
  }
}

script:post-response {
  const b = res.getBody() || {};
  const tok = b.accessToken || b.token || b.access_token;
  if (tok) { bru.setEnvVar('BEARER_TOKEN', tok); }
}

tests {
  test("Status code is 200", function () {
    expect(res.getStatus()).to.equal(200);
  });
  test("Token captured", function () {
    const b = res.getBody() || {};
    expect(b.accessToken || b.token || b.access_token).to.be.ok;
  });
}

docs {
  Platform JWT authentication (AuthenticationApiController). On success the
  post-response script stores accessToken into the BEARER_TOKEN environment var,
  which every Service request inherits (collection-level bearer auth).
}
"""


def direction_word(d: str, entity: str) -> str:
    if entity == "Metadata":
        return "Sicon metadata"
    return {"→": "Pulse→Sicon", "←": "Sicon→Pulse", "↔": "Bidirectional"}.get(d, "Sicon metadata")


def _confirm_flag(entity: str, warn, leaf: str, nulled: set) -> str:
    if warn or entity == "Equipment" or leaf in nulled:
        return "SICON CONFIRMATION REQUIRED"
    return ""


_ID0_RE = re.compile(r'("(?:[A-Za-z0-9_]*?(?:[Ii][Dd]|[Ii][Dd]s))")(\s*:\s*)0(\s*[,}\n])')
_ARR0_RE = re.compile(r'(:\s*)\[\s*0\s*\]')


def _transform_body(text: str, key: str):
    """id:0 -> null, [0] -> [], and CaseTrackingNote appointmentId -> {{appointmentId}}.

    Do not send default database id 0 unless Sicon confirms it (prefer null)."""
    m = re.search(r"(body:json\s*\{)(.*?)(\n\})", text, re.S)
    if not m:
        return text, set()
    body = m.group(2)
    nulled: set = set()
    if key.startswith("Cases/CaseTrackingNote"):
        body = re.sub(r'("appointmentId"\s*:\s*)(?:0|null)', r"\g<1>{{appointmentId}}", body)
    body = _ARR0_RE.sub(r"\g<1>[]", body)
    # never default employeeIds to [0]/[{{employeeId}}] — leave empty until chosen
    body = re.sub(r'("employeeIds"\s*:\s*)\[[^\]]*\]', r"\g<1>[]", body)

    def _repl(mm):
        leaf = re.sub(r"[^a-z0-9]", "", mm.group(1).strip('"').lower())
        if leaf == "companyid":
            return mm.group(0)
        nulled.add(leaf)
        return mm.group(1) + mm.group(2) + "null" + mm.group(3)

    body = _ID0_RE.sub(_repl, body)
    return text[: m.start(2)] + body + text[m.end(2):], nulled


def _strip_docs(text: str) -> str:
    return re.sub(r"(?ms)^docs[ \t]*\{.*?^\}[ \t]*\n?", "", text).rstrip() + "\n"


def _is_get(text: str) -> bool:
    return re.search(r"(?m)^\s*get\s*\{", text) is not None


def _tests_block(entity: str, add_fields: bool, add_pagination: bool, meta) -> str:
    lines = ['  test("HTTP status is success", function () { expect(res.getStatus()).to.be.within(200, 299); });',
             "  const b = res.getBody() || {};",
             "  const arr = Array.isArray(b) ? b : (b.data || b.items || b.results || b.records || []);",
             "  const item = arr.length ? arr[0] : (Array.isArray(b) ? {} : b);"]
    if add_fields:
        for f in GET_TEST_FIELDS.get(entity, []):
            lines.append(f'  test("field {f} present", function () {{ expect(item).to.have.property("{f}"); }});')
            lines.append(f'  bru.setVar("_type_{f}", item ? typeof item["{f}"] : "undefined");')
    if add_pagination:
        lines.append('  bru.setVar("_equipmentPageCount", arr.length);')
        lines.append('  test("pagination returns a page (pageSize>10 proves full-estate retrieval)", function () { expect(arr.length).to.be.a("number"); });')
    if meta:
        var, idf, namef = meta
        lines.append(f'  console.log("{var} options (set manually, do NOT auto-select):", arr.map(function (x) {{ return {{ id: x.{idf} != null ? x.{idf} : x.id, name: x.{namef} }}; }}));')
    return "tests {\n" + "\n".join(lines) + "\n}\n"


def build_docs(entity: str, key: str, body_keys, warn, nulled: set, meta) -> str:
    L: list = []
    if warn:
        L += ["\u26a0 " + warn, ""]
    if meta:
        var, idf, namef = meta
        L += ["Selection lookup — do NOT auto-select the first row.",
              f"Pick a value from the response ({idf} = id, {namef} = label) and set {{{{{var}}}}} in the environment.",
              ""]
    if body_keys:
        L += ["### Field mapping — this request body",
              "Legend: Bruno var `{{appointmentId}}` | Sicon field `siconAppointmentId` | Pulse field `appointment.sicon_appointment_id`",
              "",
              "| Sicon field | Pulse field (PulseFitness.ai) | Direction | Confirmation |",
              "|---|---|---|---|"]
        for k in body_keys:
            rows = _lookup(k)
            leaf = re.sub(r"[^a-z0-9]", "", k.split(".")[-1].lower())
            if rows:
                pulse, d, ent = rows[0]["gymaxis_field"], rows[0]["direction"], rows[0]["entity"]
            else:
                pulse = "(Sicon-owned metadata)" if leaf in SICON_OWNED else "(unmapped — confirm with Sicon)"
                d, ent = "←", ("Metadata" if leaf in SICON_OWNED else entity)
            L.append(f"| `{k}` | `{pulse}` | {direction_word(d, ent)} | {_confirm_flag(entity, warn, leaf, nulled)} |")
        L.append("")
    if not (warn or meta or body_keys):
        L += [f"See FIELD_MAPPING.md / mapping.csv for the full {entity} field map "
              "(Bruno var vs Sicon field vs Pulse field, with direction).", ""]
    return "docs {\n" + "\n".join("  " + x for x in L) + "\n}\n"


def main():
    if not SRC_SERVICE.exists():
        sys.exit(f"missing source: {SRC_SERVICE}")
    if COLL.exists():
        shutil.rmtree(COLL)
    COLL.mkdir(parents=True)

    # 1. copy Service plugin requests verbatim (skip its root meta files;
    #    we write our own root bruno.json + collection.bru).
    skip = {"bruno.json", "collection.bru", "README.md"}
    for p in SRC_SERVICE.rglob("*"):
        rel = p.relative_to(SRC_SERVICE)
        if p.is_file() and str(rel) not in skip and ".git" not in rel.parts:
            dest = COLL / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            text = p.read_text(encoding="utf-8-sig", errors="ignore")
            key = str(rel).replace("\\", "/")
            entity = rel.parts[0] if len(rel.parts) > 1 else "Core"
            if key in ROUTE_MAP and ROUTE_MAP[key]:
                text = _rewrite_url(text, ROUTE_MAP[key])
            text = text.replace("$max=10", "$max={{pageSize}}")
            text, nulled = _transform_body(text, key)
            body_keys = parse_bru_body_keys(text)
            meta = METADATA_LIST.get(key)
            add_fields = _is_get(text) and entity in GET_TEST_FIELDS
            add_pagination = key == "Equipment/Equipment/GetMany.bru"
            if add_fields or add_pagination or meta:
                text = text.rstrip() + "\n\n" + _tests_block(entity, add_fields, add_pagination, meta)
            if key in CAPTURE_ONE:
                text = text.rstrip() + "\n\n" + _capture_block(CAPTURE_ONE[key], False) + "\n"
            text = _strip_docs(text) + "\n" + build_docs(entity, key, body_keys, WARN.get(key), nulled, meta)
            dest.write_text(text, encoding="utf-8")

    # 2. root meta + auth + environments
    (COLL / "bruno.json").write_text(ROOT_BRUNO_JSON, encoding="utf-8")
    # Collection-level defaults so {{caseId}}/{{appointmentId}}/etc. always resolve
    # (render green) even before an environment is picked. Environment scope
    # OVERRIDES collection scope in Bruno, so the ids captured at runtime (via
    # bru.setEnvVar) always win — these defaults never clobber a real value.
    coll_vars = "vars:pre-request {\n  BEARER_TOKEN: \n" + "".join(
        f"  {k}: {v}\n" for k, v in (ID_VARS + CONTROL_VARS)) + "}\n\n"
    (COLL / "collection.bru").write_text(coll_vars + ROOT_COLLECTION_BRU, encoding="utf-8")
    (COLL / "Auth").mkdir(exist_ok=True)
    (COLL / "Auth" / "Authenticate.bru").write_text(AUTH_BRU, encoding="utf-8")
    envdir = COLL / "environments"
    envdir.mkdir(exist_ok=True)
    (envdir / "Sicon Local.bru").write_text(_env_file("http://localhost:51080", "2"), encoding="utf-8")
    (envdir / "Sicon Production.bru").write_text(
        _env_file("https://YOUR-SAGE200-HOST:51080", "1"), encoding="utf-8")
    (COLL / ".gitignore").write_text(".env\n", encoding="utf-8")

    # 2b. Sicon reference/lookup requests (Employees, Contracts, Cover Types, SLA,
    #     Fault Codes, Skills, Teams) needed to map ID-based relationships.
    for name, route, needs, note in LOOKUPS:
        d = COLL / "Lookups" / name
        d.mkdir(parents=True, exist_ok=True)
        flag = "\u26a0 " if needs else ""
        bru = (
            f"meta {{\n  name: {name}\n  type: http\n  seq: 1\n}}\n\n"
            f"get {{\n  url: {{{{baseUrl}}}}{route}\n  body: none\n  auth: inherit\n}}\n\n"
            f"params:query {{\n  companyId: {{{{companyId}}}}\n  $max: {{{{pageSize}}}}\n}}\n\n"
            'tests {\n'
            '  test("HTTP status is success", function () { expect(res.getStatus()).to.be.within(200, 299); });\n'
            "  const b = res.getBody() || {};\n"
            "  const arr = Array.isArray(b) ? b : (b.data || b.items || b.results || []);\n"
            f'  console.log("{name} lookup count:", arr.length);\n'
            "}\n\n"
            f"docs {{\n  {flag}{note}\n}}\n"
        )
        (d / "GetMany.bru").write_text(bru, encoding="utf-8")

    # 3. field-map join (Sicon Service body fields -> Pulse fields)
    rows_out, seen = [], set()
    for bru in sorted(SRC_SERVICE.rglob("*.bru")):
        rel = bru.relative_to(SRC_SERVICE)
        entity = rel.parts[0] if len(rel.parts) > 1 else "Core"
        for k in parse_bru_body_keys(bru.read_text(encoding="utf-8-sig", errors="ignore")):
            matches = _lookup(k)
            if matches:
                for mrow in matches:
                    dedup = (str(rel), k, mrow["gymaxis_field"])
                    if dedup in seen:
                        continue
                    seen.add(dedup)
                    rows_out.append({
                        "sicon_entity": entity, "sicon_request": str(rel),
                        "sicon_field": k, "pulse_field": mrow["gymaxis_field"],
                        "direction": mrow["direction"], "type": mrow["type"],
                        "status": "MAPPED", "notes": mrow["notes"],
                    })
            else:
                dedup = (str(rel), k, "")
                if dedup in seen:
                    continue
                seen.add(dedup)
                if _leaf(k) in SICON_OWNED:
                    rows_out.append({
                        "sicon_entity": entity, "sicon_request": str(rel),
                        "sicon_field": k, "pulse_field": "(Sicon-owned)", "direction": "←",
                        "type": "", "status": "SICON-OWNED",
                        "notes": "Sicon-owned / display field — read-only, no Pulse mapping required.",
                    })
                else:
                    rows_out.append({
                        "sicon_entity": entity, "sicon_request": str(rel),
                        "sicon_field": k, "pulse_field": "", "direction": "",
                        "type": "", "status": "UNMAPPED", "notes": "No Pulse mapping - confirm with Sicon",
                    })

    with (OUT / "mapping.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sicon_entity", "sicon_request", "sicon_field",
                                          "pulse_field", "direction", "type", "status", "notes"])
        w.writeheader()
        w.writerows(rows_out)

    total = len(rows_out)
    mapped = sum(1 for r in rows_out if r["status"] == "MAPPED")
    sicon_owned = sum(1 for r in rows_out if r["status"] == "SICON-OWNED")
    unmapped = total - mapped - sicon_owned
    ents: dict[str, list] = {}
    for r in rows_out:
        ents.setdefault(r["sicon_entity"], []).append(r)

    md = [
        "# Sicon Service WebAPI  <->  PulseFitness.ai — field mapping",
        "",
        "Auto-generated by `backend/scripts/gen_bruno_sicon_mapping.py`.",
        "",
        "**Three layers (do not confuse):**",
        "- Bruno variable — e.g. `{{appointmentId}}` (collection/environment placeholder used in URLs & bodies)",
        "- Sicon field — e.g. `siconAppointmentId` (JSON key on the Sicon WebAPI)",
        "- Pulse field — e.g. `appointment.sicon_appointment_id` (PulseFitness.ai model path)",
        "",
        "**Direction:** Pulse→Sicon (write) · Sicon→Pulse (read) · Bidirectional · Sicon metadata (lookup).",
        "Fields whose Sicon write behaviour is unconfirmed are labelled **SICON CONFIRMATION REQUIRED**.",
        "",
        f"**Coverage: {mapped} MAPPED + {sicon_owned} Sicon metadata = {mapped + sicon_owned}/{total} accounted "
        f"({round((mapped + sicon_owned) / total * 100) if total else 0}%). {unmapped} open.**",
        "",
    ]
    for ent in sorted(ents):
        md.append(f"## {ent}")
        md.append("| Sicon field | Pulse field (PulseFitness.ai) | Direction | Status | Confirmation | Notes |")
        md.append("|---|---|---|---|---|---|")
        for r in sorted(ents[ent], key=lambda x: (x["status"] == "MAPPED", x["status"] == "SICON-OWNED", x["sicon_field"])):
            dword = direction_word(r["direction"], r["sicon_entity"])
            conf = "SICON CONFIRMATION REQUIRED" if (r["sicon_entity"] == "Equipment" or r["status"] == "UNMAPPED") else ""
            md.append(f"| `{r['sicon_field']}` | `{r['pulse_field']}` | {dword} | {r['status']} | {conf} | {r['notes']} |")
        md.append("")
    md.append("> Bruno variables (caseId, appointmentId, equipmentId, …) are NOT Sicon fields — they are")
    md.append("> environment placeholders; the real Sicon JSON key is the `Sicon field` column above.")
    (OUT / "FIELD_MAPPING.md").write_text("\n".join(md), encoding="utf-8")

    # 4. package: docs travel inside the collection AND at the zip root.
    shutil.copy(OUT / "FIELD_MAPPING.md", COLL / "FIELD_MAPPING.md")
    shutil.copy(OUT / "mapping.csv", COLL / "mapping.csv")
    zip_path = OUT / "Sicon-Service-Pulse.bruno.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(COLL.rglob("*")):
            if p.is_file():
                z.write(p, arcname=str(Path("bruno") / p.relative_to(COLL)))
        for extra in ("FIELD_MAPPING.md", "mapping.csv", "README.md"):
            fp = OUT / extra
            if fp.exists():
                z.write(fp, arcname=extra)

    print(f"OUT: {OUT}")
    print(f"collection files: {sum(1 for _ in COLL.rglob('*') if _.is_file())}")
    print(f"Sicon Service body fields: {total} | mapped: {mapped} | sicon-owned: {sicon_owned} | unmapped: {unmapped}")
    print(f"entities: {sorted(ents)}")
    print(f"zip: {zip_path} ({zip_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
