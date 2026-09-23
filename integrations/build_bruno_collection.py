"""Generate the PulseFitness ↔ Sicon Service WebAPI v1 Bruno collection.
Read-first, write-safe. Run: python integrations/build_bruno_collection.py
→ integrations/PulseFitness-Sicon-WebAPI.zip  (bundles mapping.csv + FIELD_MAPPING.md)
"""
import json
import os
import shutil
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "bruno_sicon_v1")
BR = os.path.join(OUT_DIR, "PulseFitness Sicon WebAPI")

# Write guard — POST/PUT refuse to run unless ALLOW_WRITES=true.
WRITE_GUARD = (
    "script:pre-request {\n"
    "  if (String(bru.getEnvVar('ALLOW_WRITES')).toLowerCase() !== 'true') {\n"
    "    throw new Error('WRITE BLOCKED: initial mapping is READ-ONLY. Set ALLOW_WRITES=true to run POST/PUT.');\n"
    "  }\n}\n"
)


def capture(props):
    """post-response script: assert 200 + capture Sicon ids into runtime vars."""
    body = ["script:post-response {",
            "  test('status is 2xx', function () { if (res.getStatus() >= 300) throw new Error('HTTP ' + res.getStatus()); });",
            "  const b = res.getBody() || {};",
            "  const e = (b && b.entity) ? b.entity : b;",
            "  const first = Array.isArray(e) ? (e[0] || {}) : (Array.isArray(b.items) ? (b.items[0]||{}) : e);"]
    for sicon_prop, var in props:
        body.append(f"  if (first && first.{sicon_prop} !== undefined && first.{sicon_prop} !== null) "
                    f"bru.setVar('{var}', first.{sicon_prop});")
    body.append("}")
    return "\n".join(body) + "\n"


def tests_only(expected_props):
    checks = ["  test('status is 200', function () { if (res.getStatus() !== 200) throw new Error('HTTP ' + res.getStatus()); });"]
    for p in expected_props:
        checks.append(f"  test('has {p}', function () {{ const b=res.getBody()||{{}}; const e=Array.isArray(b)?(b[0]||{{}}):((b.entity)||b); if (e && e.{p} === undefined) throw new Error('missing {p}'); }});")
    return "script:post-response {\n" + "\n".join(checks) + "\n}\n"


def bru(name, seq, method, url, body=None, anon=False, query_extra=None,
        post=None, write_guard=False):
    lines = [f"meta {{\n  name: {name}\n  type: http\n  seq: {seq}\n}}\n"]
    lines.append(f"{method.lower()} {{\n  url: {url}\n  body: {'json' if body else 'none'}\n  auth: {'none' if anon else 'inherit'}\n}}\n")
    q = ["companyId: {{companyId}}"]
    if query_extra:
        q = query_extra + q
    lines.append("params:query {\n" + "\n".join("  " + x for x in q) + "\n}\n")
    if write_guard:
        lines.append(WRITE_GUARD)
    if body is not None:
        lines.append("headers {\n  Content-Type: application/json\n}\n")
        bj = json.dumps(body, indent=2).replace('"{{', '{{').replace('}}"', '}}')
        lines.append("body:json {\n" + "\n".join("  " + ln for ln in bj.splitlines()) + "\n}\n")
    if post:
        lines.append(post)
    return "\n".join(lines)


# ── Bodies (create = primary key 0 per Sicon create convention; optional FKs = null;
#    lookup ids reference {{vars}} sourced from the Lookups folder, never hardcoded) ──
CASE_BODY = {
    "siSMCaseId": 0, "caseNumber": "", "siSMDocumentStatusId": 0, "siSMDocumentStatusName": "",
    "siSMDocumentSubStatusId": 0, "summary": "Example", "description": "Example", "callDate": None,
    "contactName": "", "contactPhoneNumber": "", "contactEmail": "", "lastUpdatedDate": None,
    "isNonContract": False,
    "address": {"postalName": "", "addressLine1": "", "addressLine2": "", "addressLine3": "",
                "addressLine4": "", "city": "", "county": "", "postCode": "", "sopDelAddress": None},
    "customerOrderNo": "", "createdBy": "", **{f"analysisField{i}": "" for i in range(1, 21)},
    "siconCRMPersonId": "{{crmPersonId}}", "siconCRMCompanyId": "{{crmCompanyId}}",
    "caseType": {"siSMCaseTypeId": "{{caseTypeId}}", "name": "", "systemType": "",
                 "isPreventativeMaintenanceType": False, "isEnabled": True, "isCustom": False,
                 "defaultAppointmentLabel": None},
    "coverType": None, "sla": None, "faultCode": None, "skill": None,
    "priority": {"siSMPriorityId": "{{priorityId}}", "name": "", "colour": ""},
    "lastTrackingStatus": None, "contract": None, "contractLine": None, "project": None,
    "caseAdmin": None, "internalTeamId": "{{internalTeamId}}", "internalTeam": None,
    "externalTeamId": "{{externalTeamId}}", "externalTeam": None, "customer": None,
    "customerContact": None, "subLocation": None, "equipmentIds": [],
}
APPT_BODY = {
    "siconAppointmentId": 0, "siSMCaseId": "{{caseId}}", "appointmentType": "Work",
    "parentWorkAppointmentId": None, "subject": "Example", "description": "", "workBriefing": "",
    "employeeIds": ["{{employeeId}}"], "chargeRateId": None, "labelId": None, "colour": "",
    "confirmed": False, "scheduledStartDate": "2026-01-01T09:00:00", "scheduledEndDate": "2026-01-01T17:00:00",
    "appointmentComplete": False, "workDoneDescription": "", "workDoneAcknowledged": False,
    "furtherAction": "", "furtherActionAcknowledged": False, "arrivalSignee": "", "departureSignee": "",
    "arrivalLatitude": None, "arrivalLongitude": None, "departureLatitude": None, "departureLongitude": None,
}
TIMEBOOK_BODY = {"employeeIds": ["{{employeeId}}"], "startDate": "2026-01-01T09:00:00",
                 "endDate": "2026-01-01T17:00:00", "costingHours": None, "chargingHours": None,
                 "chargeRate": None, "isEstimate": False}
EQUIP_BODY = {"siconEquipmentId": 0, "itemId": None, "description": "Example", "serialNumber": "",
              "idNumber": "", "warrantyExpiry": None, "installDate": None, "serviceIntervalMeasurement": "",
              "serviceIntervalDuration": None, "notes": "", "customerId": None,
              "siconEquipmentGroupDbKey": None, "make": "", "model": "", "lastServiceDate": None,
              "nextServiceDate": None, "siconCrmCompanyId": None, "siconCrmPersonId": None,
              "siconCrmEndUserCompanyId": None, "siconCrmEndUserPersonId": None,
              "custDeliveryAddressDbKey": None, "siconSubLocationDbKey": None, "siconContactDbKey": None,
              **{f"analysisCode{i}": "" for i in range(1, 21)}}
NOTE_BODY = {"siSMCaseTrackingNoteId": 0, "note": "Example", "time": None, "status": "",
             "statusId": "{{statusId}}", "appointmentId": "{{appointmentId}}", "visibleToEngineer": True,
             "visibleToCustomer": False, "reassignedToCaseOwnerId": None, "reassignedToInternalTeamId": None,
             "reassignedToExternalTeamId": None, "latitude": None, "longitude": None}

PAGE = ["query: $skip={{skip}}&$max={{pageSize}}"]

ENV = (
    "vars {\n"
    "  baseUrl: https://YOUR-SICON-HOST\n"
    "  companyId: 2\n"                       # Pulse Fitness Sicon company
    "  username: \n"
    "  password: \n"
    "  ALLOW_WRITES: false\n"               # READ-ONLY until deliberately enabled
    "  pageSize: 200\n"
    "  skip: 0\n"
    "  BEARER_TOKEN: \n"
    # Lookup/runtime ids — editable for manual testing; captured at runtime from responses.
    "  caseId: \n  appointmentId: \n  trackingNoteId: \n  equipmentId: \n  timeBookingId: \n"
    "  caseNumber: \n  caseTypeId: \n  priorityId: \n  statusId: \n  employeeId: \n"
    "  internalTeamId: \n  externalTeamId: \n  crmPersonId: \n  crmCompanyId: \n"
    "}\n"
)

FILES = {
    "bruno.json": json.dumps({"version": "1", "name": "PulseFitness Sicon WebAPI",
                              "type": "collection", "ignore": ["node_modules", ".git"]}, indent=2),
    "collection.bru": (
        "headers {\n  Accept: application/json\n}\n\n"
        "auth {\n  mode: bearer\n}\n\n"
        "auth:bearer {\n  token: {{BEARER_TOKEN}}\n}\n\n"
        "docs {\n"
        "  PulseFitness.ai <> Sicon Service WebAPI v1.\n"
        "  Company: Pulse Fitness = companyId 2 (set in the environment).\n"
        "  READ-FIRST: ALLOW_WRITES defaults to false; POST/PUT refuse to run until it is true.\n"
        "  Milestone 1 (read-only): Auth -> Lookups -> Equipment/GetMany (paginate) -> map -> store siconEquipmentId.\n"
        "  Runtime ids (caseId, appointmentId, equipmentId, trackingNoteId, timeBookingId) are CAPTURED\n"
        "  from responses via each request's post-response script (bru.setVar) and are NOT reset to 0.\n"
        "  See mapping.csv and FIELD_MAPPING.md bundled at the collection root.\n"
        "}\n"),
    "environments/PulseFitness (Company 2).bru": ENV,

    "Core/Ping.bru": bru("Ping", 1, "GET", "{{baseUrl}}/api/v1/SiconService/Ping", anon=True,
                         post=tests_only([])),
    "Auth/Authenticate.bru": (bru("Authenticate", 1, "POST", "{{baseUrl}}/api/v1/authentication/authenticate",
                              body={"username": "{{username}}", "password": "{{password}}"}, anon=True)
                              + "\ndocs {\n  NOTE: this is the ONLY write-exempt POST — it carries no ALLOW_WRITES\n"
                                "  guard because you must authenticate before anything else (including enabling writes).\n"
                                "  All business POST/PUT requests DO enforce the ALLOW_WRITES guard.\n}\n"
                              + "\nscript:post-response {\n  const b = res.getBody() || {};\n"
                                "  const t = b.accessToken || b.token;\n"
                                "  if (t) bru.setEnvVar('BEARER_TOKEN', t);\n"
                                "  test('got token', function () { if (!t) throw new Error('no accessToken'); });\n}\n"),

    # ── Lookups / reference data (read-only) ──
    **{f"Lookups/{name}.bru": bru(name, i + 1, "GET",
                                  "{{baseUrl}}/api/v1/SiconService/" + path,
                                  query_extra=["query: $max={{pageSize}}"],
                                  post=tests_only([]))
       for i, (name, path) in enumerate([
           ("CaseTypes", "CaseType"), ("Priorities", "Priority"), ("TrackingStatuses", "TrackingStatus"),
           ("Employees", "Employee"), ("Contracts", "Contract"), ("CoverTypes", "CoverType"),
           ("SLAs", "SLA"), ("FaultCodes", "FaultCode"), ("Skills", "Skill"), ("Teams", "Team"),
           ("Customers", "Customer"), ("Contacts", "Contact"), ("SubLocations", "SubLocation")])},

    # ── Equipment (READ first for estate import, then writes) ──
    "Equipment/GetMany.bru": bru("GetMany", 1, "GET", "{{baseUrl}}/api/v1/SiconService/Equipment",
                                 query_extra=PAGE,
                                 post=("script:post-response {\n"
                                       "  test('status 200', function(){ if(res.getStatus()!==200) throw new Error('HTTP '+res.getStatus()); });\n"
                                       "  const b = res.getBody() || {};\n"
                                       "  const items = Array.isArray(b) ? b : (b.items || b.entities || []);\n"
                                       "  test('is a list', function(){ if(!Array.isArray(items)) throw new Error('not a list'); });\n"
                                       "  test('has siconEquipmentId', function(){ if(items.length && items[0].siconEquipmentId===undefined) throw new Error('missing siconEquipmentId'); });\n"
                                       "  if (items.length) bru.setVar('equipmentId', items[0].siconEquipmentId);\n"
                                       "  // PAGINATION: advance skip by pageSize and re-run until fewer than pageSize rows return.\n"
                                       "  if (items.length >= Number(bru.getEnvVar('pageSize')||200)) {\n"
                                       "    bru.setVar('skip', Number(bru.getVar('skip')||bru.getEnvVar('skip')||0) + items.length);\n"
                                       "  }\n}\n")),
    "Equipment/GetOne.bru": bru("GetOne", 2, "GET",
                                "{{baseUrl}}/api/v1/SiconService/Equipment/{{equipmentId}}",
                                post=tests_only(["siconEquipmentId", "serialNumber"])),
    "Equipment/SearchBySerial.bru": bru("SearchBySerial", 3, "GET",
                                        "{{baseUrl}}/api/v1/SiconService/Equipment",
                                        query_extra=["query: $filter=serialNumber eq '{{serialNumber}}'&$max={{pageSize}}"],
                                        post=tests_only([])),
    "Equipment/PostOne.bru": bru("PostOne", 4, "POST", "{{baseUrl}}/api/v1/SiconService/Equipment",
                                 body=EQUIP_BODY, write_guard=True,
                                 post=capture([("siconEquipmentId", "equipmentId")])),
    "Equipment/PutOne.bru": bru("PutOne", 5, "PUT", "{{baseUrl}}/api/v1/SiconService/Equipment/{{equipmentId}}",
                                body={**EQUIP_BODY, "siconEquipmentId": "{{equipmentId}}"}, write_guard=True,
                                post=capture([("siconEquipmentId", "equipmentId")])),

    # ── Cases ──
    "Cases/Case/GetMany.bru": bru("GetMany", 1, "GET", "{{baseUrl}}/api/v1/SiconService/CaseSearch",
                                  query_extra=PAGE, post=tests_only([])),
    "Cases/Case/GetOne.bru": bru("GetOne", 2, "GET", "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}",
                                 post=tests_only(["siSMCaseId"])),
    "Cases/Case/PostOne.bru": bru("PostOne", 3, "POST", "{{baseUrl}}/api/v1/SiconService/Case",
                                  body=CASE_BODY, write_guard=True,
                                  post=capture([("siSMCaseId", "caseId"), ("caseNumber", "caseNumber")])),
    "Cases/Case/PutOne.bru": bru("PutOne", 4, "PUT", "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}",
                                 body={**CASE_BODY, "siSMCaseId": "{{caseId}}"}, write_guard=True,
                                 post=capture([("siSMCaseId", "caseId"), ("caseNumber", "caseNumber")])),
    "Cases/CaseTrackingNote/GetMany.bru": bru("GetMany", 1, "GET",
        "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}/TrackingNote", query_extra=PAGE, post=tests_only([])),
    "Cases/CaseTrackingNote/PostOne.bru": bru("PostOne", 2, "POST",
        "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}/TrackingNote", body=NOTE_BODY, write_guard=True,
        post=capture([("siSMCaseTrackingNoteId", "trackingNoteId")])),
    "Cases/CaseTrackingNote/PutOne.bru": bru("PutOne", 3, "PUT",
        "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}/TrackingNote/{{trackingNoteId}}",
        body={**NOTE_BODY, "siSMCaseTrackingNoteId": "{{trackingNoteId}}"}, write_guard=True,
        post=capture([("siSMCaseTrackingNoteId", "trackingNoteId")])),

    # ── Appointments ──
    "Appointments/Appointment/GetOne.bru": bru("GetOne", 1, "GET",
        "{{baseUrl}}/api/v1/SiconService/Appointment/{{appointmentId}}", post=tests_only(["siconAppointmentId"])),
    "Appointments/Appointment/PostOne.bru": bru("PostOne", 2, "POST",
        "{{baseUrl}}/api/v1/SiconService/Appointment", body=APPT_BODY, write_guard=True,
        post=capture([("siconAppointmentId", "appointmentId")])),
    "Appointments/Appointment/PutOne.bru": bru("PutOne", 3, "PUT",
        "{{baseUrl}}/api/v1/SiconService/Appointment/{{appointmentId}}",
        body={**APPT_BODY, "siconAppointmentId": "{{appointmentId}}"}, write_guard=True,
        post=capture([("siconAppointmentId", "appointmentId")])),
    "Appointments/AppointmentTimeBooking/PostOne.bru": bru("PostOne", 1, "POST",
        "{{baseUrl}}/api/v1/SiconService/Appointment/{{appointmentId}}/TimeBooking", body=TIMEBOOK_BODY,
        write_guard=True, post=capture([("timeBookingId", "timeBookingId"), ("id", "timeBookingId")])),
}


def main():
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    # regenerate mapping artifacts and bundle them
    try:
        subprocess.run(["python", os.path.join(ROOT, "build_mapping_csv.py")], check=True, timeout=30)
    except Exception as exc:
        print("mapping build skipped:", exc)
    for rel, content in FILES.items():
        p = os.path.join(BR, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
    for extra, dest in [("Pulse-Sicon-Field-Mapping.csv", "mapping.csv"),
                        ("FIELD_MAPPING.md", "FIELD_MAPPING.md")]:
        src = os.path.join(ROOT, extra)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(BR, dest))
    zip_path = os.path.join(ROOT, "PulseFitness-Sicon-WebAPI.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, _dirs, files in os.walk(BR):
            for fn in files:
                fp = os.path.join(base, fn)
                zf.write(fp, os.path.relpath(fp, OUT_DIR))
    print("Wrote", zip_path, "with", len(FILES), "requests + mapping.csv + FIELD_MAPPING.md")


if __name__ == "__main__":
    main()
