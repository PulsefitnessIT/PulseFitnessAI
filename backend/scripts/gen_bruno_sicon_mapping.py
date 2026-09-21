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
}

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
CAPTURE_LIST = {
    "Cases/CaseSearch/GetMany.bru": [("siSMCaseId", "caseId")],
    "Metadata/CaseType/GetMany.bru": [("siSMCaseTypeId", "caseTypeId")],
    "Metadata/Priority/GetMany.bru": [("siSMPriorityId", "priorityId")],
    "Tracking/TrackingStatus/GetMany.bru": [
        ("siSMTrackingStatusId", "trackingStatusId"), ("siSMTrackingStatusId", "statusId"),
    ],
}


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
    ("caseTypeId", "0"), ("priorityId", "0"), ("trackingStatusId", "0"),
    ("statusId", "0"), ("employeeId", "0"),
]


def _env_file(base_url: str, company_id: str) -> str:
    lines = ["vars {",
             f"  baseUrl: {base_url}",
             "  username: Administrator",
             f"  companyId: {company_id}",
             "  BEARER_TOKEN: "]
    for k, v in ID_VARS:
        lines.append(f"  {k}: {v}")
    lines.append("}")
    lines.append("")
    lines.append("vars:secret [")
    lines.append("  password")
    lines.append("]")
    lines.append("")
    lines.append("docs {")
    lines.append("  Set baseUrl to your Sicon Sage200 WebAPI host and companyId to the Sage company.")
    lines.append("  Paste the Sicon password into the secret 'password' var in Bruno (never committed).")
    lines.append("  Run Auth > Authenticate first — it captures accessToken into BEARER_TOKEN.")
    lines.append("  Entity ids auto-populate from post-response scripts as you run requests.")
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

docs {
  Sicon Service WebAPI - Pulse Fitness consolidated collection.
  Single source of truth: /app/integrations/sicon/ (FIELD_MAPPING.md + mapping.csv).
  All Service entity requests inherit the bearer token set by Auth > Authenticate.
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
            if key in CAPTURE_ONE:
                text = text.rstrip() + "\n\n" + _capture_block(CAPTURE_ONE[key], False) + "\n"
            elif key in CAPTURE_LIST:
                text = text.rstrip() + "\n\n" + _capture_block(CAPTURE_LIST[key], True) + "\n"
            dest.write_text(text, encoding="utf-8")

    # 2. root meta + auth + environments
    (COLL / "bruno.json").write_text(ROOT_BRUNO_JSON, encoding="utf-8")
    (COLL / "collection.bru").write_text(ROOT_COLLECTION_BRU, encoding="utf-8")
    (COLL / "Auth").mkdir(exist_ok=True)
    (COLL / "Auth" / "Authenticate.bru").write_text(AUTH_BRU, encoding="utf-8")
    envdir = COLL / "environments"
    envdir.mkdir(exist_ok=True)
    (envdir / "Sicon Local.bru").write_text(_env_file("http://localhost:51080", "1"), encoding="utf-8")
    (envdir / "Sicon Production.bru").write_text(
        _env_file("https://YOUR-SAGE200-HOST:51080", "1"), encoding="utf-8")
    (COLL / ".gitignore").write_text(".env\n", encoding="utf-8")

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
    ents: dict[str, list] = {}
    for r in rows_out:
        ents.setdefault(r["sicon_entity"], []).append(r)

    md = [
        "# Sicon Service WebAPI <-> Pulse Fitness - field mapping",
        "",
        "Auto-generated by `backend/scripts/gen_bruno_sicon_mapping.py` from the",
        "Sicon-provided Bruno collection bodies (integrations/sicon/_source) joined to",
        "the platform mapping table (`backend/routes/sicon_mapping.py`).",
        "`->` push (Pulse->Sicon) &middot; `<-` pull &middot; `<->` bi-directional.",
        "",
        f"**Coverage: {mapped}/{total} Sicon Service body fields have a Pulse mapping "
        f"({round(mapped / total * 100) if total else 0}%).**",
        "",
    ]
    for ent in sorted(ents):
        md.append(f"## {ent}")
        md.append("| Sicon field | Pulse field | Dir | Status | Notes |")
        md.append("|---|---|---|---|---|")
        for r in sorted(ents[ent], key=lambda x: (x["status"] != "UNMAPPED", x["sicon_field"])):
            md.append(f"| `{r['sicon_field']}` | `{r['pulse_field']}` | {r['direction']} "
                      f"| {r['status']} | {r['notes']} |")
        md.append("")
    (OUT / "FIELD_MAPPING.md").write_text("\n".join(md), encoding="utf-8")

    # 4. zip the importable collection (top-level folder = bruno/)
    zip_path = OUT / "Sicon-Service-Pulse.bruno.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(COLL.rglob("*")):
            if p.is_file():
                z.write(p, arcname=str(Path("bruno") / p.relative_to(COLL)))

    print(f"OUT: {OUT}")
    print(f"collection files: {sum(1 for _ in COLL.rglob('*') if _.is_file())}")
    print(f"Sicon Service body fields: {total} | mapped: {mapped} | unmapped: {total - mapped}")
    print(f"entities: {sorted(ents)}")
    print(f"zip: {zip_path} ({zip_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
