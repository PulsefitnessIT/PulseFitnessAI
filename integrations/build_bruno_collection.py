"""Generate a Bruno collection for the PulseFitness ↔ Sicon Service WebAPI v1
integration, reflecting the exact camelCase payloads our platform now sends.
Run: python integrations/build_bruno_collection.py  → integrations/PulseFitness-Sicon-WebAPI.zip
"""
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "bruno_sicon_v1")
BR = os.path.join(OUT_DIR, "PulseFitness Sicon WebAPI")

CASE_BODY = {
    "siSMCaseId": 0, "caseNumber": "", "siSMDocumentStatusId": 0, "siSMDocumentStatusName": "",
    "siSMDocumentSubStatusId": 0, "summary": "Example case summary", "description": "Example case description",
    "callDate": None, "contactName": "", "contactPhoneNumber": "", "contactEmail": "", "lastUpdatedDate": None,
    "isNonContract": False,
    "address": {"postalName": "", "addressLine1": "", "addressLine2": "", "addressLine3": "", "addressLine4": "",
                "city": "", "county": "", "postCode": "", "sopDelAddress": None},
    "customerOrderNo": "", "createdBy": "",
    **{f"analysisField{i}": "" for i in range(1, 21)},
    "siconCRMPersonId": 0, "siconCRMCompanyId": 0,
    "caseType": {"siSMCaseTypeId": "{{caseTypeId}}", "name": "", "systemType": "",
                 "isPreventativeMaintenanceType": False, "isEnabled": True, "isCustom": False,
                 "defaultAppointmentLabel": None},
    "coverType": None, "sla": None, "faultCode": None, "skill": None,
    "priority": {"siSMPriorityId": "{{priorityId}}", "name": "", "colour": ""},
    "lastTrackingStatus": None, "contract": None, "contractLine": None, "project": None, "caseAdmin": None,
    "internalTeamId": 0, "internalTeam": None, "externalTeamId": 0, "externalTeam": None,
    "customer": None, "customerContact": None, "subLocation": None, "equipmentIds": [],
}
APPT_BODY = {
    "siconAppointmentId": 0, "siSMCaseId": "{{caseId}}", "appointmentType": "Work",
    "parentWorkAppointmentId": None, "subject": "Example appointment", "description": "", "workBriefing": "",
    "employeeIds": ["{{employeeId}}"], "chargeRateId": None, "labelId": None, "colour": "", "confirmed": False,
    "scheduledStartDate": "2026-01-01T09:00:00", "scheduledEndDate": "2026-01-01T17:00:00",
    "appointmentComplete": False, "workDoneDescription": "", "workDoneAcknowledged": False,
    "furtherAction": "", "furtherActionAcknowledged": False, "arrivalSignee": "", "departureSignee": "",
    "arrivalLatitude": None, "arrivalLongitude": None, "departureLatitude": None, "departureLongitude": None,
}
TIMEBOOK_BODY = {"employeeIds": ["{{employeeId}}"], "startDate": "2026-01-01T09:00:00",
                 "endDate": "2026-01-01T17:00:00", "costingHours": None, "chargingHours": None,
                 "chargeRate": None, "isEstimate": False}
EQUIP_BODY = {"siconEquipmentId": 0, "itemId": None, "description": "Example equipment", "serialNumber": "",
              "idNumber": "EXAMPLE-001", "warrantyExpiry": None, "installDate": None,
              "serviceIntervalMeasurement": "", "serviceIntervalDuration": None, "notes": "", "customerId": None,
              "siconEquipmentGroupDbKey": None, "make": "", "model": "", "lastServiceDate": None,
              "nextServiceDate": None, "siconCrmCompanyId": None, "siconCrmPersonId": None,
              "siconCrmEndUserCompanyId": None, "siconCrmEndUserPersonId": None, "custDeliveryAddressDbKey": None,
              "siconSubLocationDbKey": None, "siconContactDbKey": None,
              **{f"analysisCode{i}": "" for i in range(1, 21)}}
NOTE_BODY = {"siSMCaseTrackingNoteId": 0, "note": "Example tracking note", "time": None, "status": "",
             "statusId": "{{statusId}}", "appointmentId": None, "visibleToEngineer": True,
             "visibleToCustomer": False, "reassignedToCaseOwnerId": None, "reassignedToInternalTeamId": None,
             "reassignedToExternalTeamId": None, "latitude": None, "longitude": None}


def body_str(obj):
    return json.dumps(obj, indent=2).replace('"{{', '{{').replace('}}"', '}}')


def bru(name, seq, method, url, body=None, anon=False, query=True):
    lines = [f"meta {{\n  name: {name}\n  type: http\n  seq: {seq}\n}}\n"]
    lines.append(f"{method.lower()} {{\n  url: {url}\n  body: {'json' if body else 'none'}\n  auth: {'none' if anon else 'inherit'}\n}}\n")
    if query:
        lines.append("params:query {\n  companyId: {{companyId}}\n}\n")
    if body:
        lines.append("headers {\n  Content-Type: application/json\n}\n")
        lines.append("body:json {\n" + "\n".join("  " + ln for ln in body_str(body).splitlines()) + "\n}\n")
    return "\n".join(lines)


FILES = {
    "bruno.json": json.dumps({"version": "1", "name": "PulseFitness Sicon WebAPI",
                              "type": "collection", "ignore": ["node_modules", ".git"]}, indent=2),
    "collection.bru": ("headers {\n  Accept: application/json\n}\n\nauth {\n  mode: bearer\n}\n\n"
                       "auth:bearer {\n  token: {{BEARER_TOKEN}}\n}\n\n"
                       "vars:pre-request {\n  caseId: 0\n  appointmentId: 0\n  timeBookingId: 0\n"
                       "  trackingNoteId: 0\n  equipmentId: 0\n  caseTypeId: 0\n  priorityId: 0\n"
                       "  statusId: 0\n  employeeId: 0\n}\n\ndocs {\n  PulseFitness → Sicon Service WebAPI v1.\n"
                       "  Set companyId + baseUrl in the environment; run Auth/Authenticate first.\n}\n"),
    "environments/Production.bru": ("vars {\n  baseUrl: https://YOUR-SICON-HOST\n  companyId: 1\n"
                                    "  username: \n  password: \n}\n"),
    "Core/Ping.bru": bru("Ping", 1, "GET", "{{baseUrl}}/api/v1/SiconService/Ping", anon=True, query=False),
    "Auth/Authenticate.bru": (bru("Authenticate", 1, "POST", "{{baseUrl}}/api/v1/authentication/authenticate",
                              body={"username": "{{username}}", "password": "{{password}}"}, anon=True, query=False)
                              + "\nscript:post-response {\n  const b = res.getBody();\n"
                                "  if (b && b.accessToken) bru.setEnvVar('BEARER_TOKEN', b.accessToken);\n}\n"),
    "Cases/Case/GetOne.bru": bru("GetOne", 1, "GET", "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}"),
    "Cases/Case/PostOne.bru": bru("PostOne", 2, "POST", "{{baseUrl}}/api/v1/SiconService/Case", body=CASE_BODY),
    "Cases/Case/PutOne.bru": bru("PutOne", 3, "PUT", "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}",
                                 body={**CASE_BODY, "siSMCaseId": "{{caseId}}"}),
    "Cases/CaseTrackingNote/PostOne.bru": bru("PostOne", 1, "POST",
        "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}/TrackingNote", body=NOTE_BODY),
    "Cases/CaseTrackingNote/PutOne.bru": bru("PutOne", 2, "PUT",
        "{{baseUrl}}/api/v1/SiconService/Case/{{caseId}}/TrackingNote/{{trackingNoteId}}",
        body={**NOTE_BODY, "siSMCaseTrackingNoteId": "{{trackingNoteId}}"}),
    "Appointments/Appointment/GetOne.bru": bru("GetOne", 1, "GET",
        "{{baseUrl}}/api/v1/SiconService/Appointment/{{appointmentId}}"),
    "Appointments/Appointment/PostOne.bru": bru("PostOne", 2, "POST",
        "{{baseUrl}}/api/v1/SiconService/Appointment", body=APPT_BODY),
    "Appointments/Appointment/PutOne.bru": bru("PutOne", 3, "PUT",
        "{{baseUrl}}/api/v1/SiconService/Appointment/{{appointmentId}}",
        body={**APPT_BODY, "siconAppointmentId": "{{appointmentId}}"}),
    "Appointments/AppointmentTimeBooking/PostOne.bru": bru("PostOne", 1, "POST",
        "{{baseUrl}}/api/v1/SiconService/Appointment/{{appointmentId}}/TimeBooking", body=TIMEBOOK_BODY),
    "Equipment/Equipment/PostOne.bru": bru("PostOne", 1, "POST",
        "{{baseUrl}}/api/v1/SiconService/Equipment", body=EQUIP_BODY),
    "Equipment/Equipment/PutOne.bru": bru("PutOne", 2, "PUT",
        "{{baseUrl}}/api/v1/SiconService/Equipment/{{equipmentId}}",
        body={**EQUIP_BODY, "siconEquipmentId": "{{equipmentId}}"}),
    "Metadata/CaseType/GetMany.bru": bru("GetMany", 1, "GET", "{{baseUrl}}/api/v1/SiconService/CaseType"),
    "Metadata/Priority/GetMany.bru": bru("GetMany", 1, "GET", "{{baseUrl}}/api/v1/SiconService/Priority"),
    "Tracking/TrackingStatus/GetMany.bru": bru("GetMany", 1, "GET",
        "{{baseUrl}}/api/v1/SiconService/TrackingStatus"),
}


def main():
    for rel, content in FILES.items():
        path = os.path.join(BR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
    zip_path = os.path.join(ROOT, "PulseFitness-Sicon-WebAPI.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, _dirs, files in os.walk(BR):
            for fn in files:
                fp = os.path.join(base, fn)
                zf.write(fp, os.path.relpath(fp, OUT_DIR))
    print("Wrote", zip_path, "with", len(FILES), "files")


if __name__ == "__main__":
    main()
