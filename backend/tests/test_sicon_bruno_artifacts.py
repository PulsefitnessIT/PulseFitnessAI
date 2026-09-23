"""
Verification of PulseFitness Sicon WebAPI Bruno collection + mapping artifacts.
Independently validates the 12 acceptance criteria listed in the review request.
"""
import os
import re
import csv
import io
import zipfile
import pathlib
import pytest
import requests

ROOT = pathlib.Path("/app/integrations/bruno_sicon_v1/PulseFitness Sicon WebAPI")
CSV_PATH = pathlib.Path("/app/integrations/Pulse-Sicon-Field-Mapping.csv")
MD_PATH = pathlib.Path("/app/integrations/FIELD_MAPPING.md")
ZIP_PATH = pathlib.Path("/app/integrations/PulseFitness-Sicon-WebAPI.zip")

# Load backend URL for download endpoint tests
def _load_backend_url():
    env = pathlib.Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE_URL = _load_backend_url()


def _read(p):
    return pathlib.Path(p).read_text()


# ---------- (1) Company ID ----------
def test_environment_company_id_is_2():
    env_files = list((ROOT / "environments").glob("*.bru"))
    assert env_files, "No environment file found"
    txt = env_files[0].read_text()
    assert re.search(r"companyId:\s*2\b", txt), f"companyId != 2 in {env_files[0].name}"
    assert not re.search(r"companyId:\s*1\b", txt), "companyId 1 leaked"


# ---------- (2) Equipment reads + pagination ----------
def test_equipment_files_present():
    eq = ROOT / "Equipment"
    for f in ("GetMany.bru", "GetOne.bru", "SearchBySerial.bru", "PostOne.bru", "PutOne.bru"):
        assert (eq / f).exists(), f"Missing Equipment/{f}"


def test_equipment_getmany_pagination():
    t = _read(ROOT / "Equipment/GetMany.bru")
    assert "$skip={{skip}}" in t or "$skip={skip}" in t or "$skip=" in t and "{{skip}}" in t, "pagination $skip missing"
    assert "$max=" in t and ("{{pageSize}}" in t or "{pageSize}" in t), "pagination $max missing"
    # post-response script advancing skip
    assert re.search(r"script:post-response|tests\s*{", t), "no post-response script block"
    assert "skip" in t.lower() and ("setVar" in t or "setEnvVar" in t), "no skip advance via bru.setVar"


# ---------- (3) TrackingNote appointmentId mapped ----------
def test_tracking_note_appointment_id():
    for f in ("PostOne.bru", "PutOne.bru"):
        t = _read(ROOT / f"Cases/CaseTrackingNote/{f}")
        assert re.search(r'"appointmentId"\s*:\s*\{\{?appointmentId\}?\}', t), \
            f"appointmentId not templated in {f}: got mismatch"
        assert not re.search(r'"appointmentId"\s*:\s*null', t), f"appointmentId is null in {f}"


# ---------- (4) Automatic ID capture ----------
CAPTURES = [
    ("Cases/Case/PostOne.bru", ["siSMCaseId", "caseId", "caseNumber"]),
    ("Appointments/Appointment/PostOne.bru", ["siconAppointmentId", "appointmentId"]),
    ("Equipment/PostOne.bru", ["siconEquipmentId", "equipmentId"]),
    ("Cases/CaseTrackingNote/PostOne.bru", ["siSMCaseTrackingNoteId", "trackingNoteId"]),
    ("Appointments/AppointmentTimeBooking/PostOne.bru", ["timeBookingId"]),
]

@pytest.mark.parametrize("path,tokens", CAPTURES)
def test_post_one_id_capture(path, tokens):
    t = _read(ROOT / path)
    assert "bru.setVar" in t, f"no bru.setVar in {path}"
    for tok in tokens:
        assert tok in t, f"{tok} not captured in {path}"


# ---------- (5) No zero-reset ----------
def test_collection_no_zero_reset():
    t = _read(ROOT / "collection.bru")
    # There must be no vars:pre-request block resetting ids to 0
    m = re.search(r"vars:pre-request\s*{([^}]*)}", t, re.DOTALL)
    if m:
        block = m.group(1)
        # count `: 0`
        zeros = re.findall(r":\s*0\b", block)
        assert len(zeros) == 0, f"collection.bru vars:pre-request resets ids to 0: {block!r}"
    # else: block absent — good.


# ---------- (6) ALLOW_WRITES + guards ----------
def test_env_allow_writes_false():
    env_files = list((ROOT / "environments").glob("*.bru"))
    txt = env_files[0].read_text()
    assert re.search(r"ALLOW_WRITES:\s*false", txt), "ALLOW_WRITES not false in environment"


def test_write_guard_on_all_post_put_but_not_get():
    guard_re = re.compile(r"WRITE BLOCKED")
    prereq_re = re.compile(r"script:pre-request")
    for p in ROOT.rglob("*.bru"):
        if p.name in ("collection.bru",) or "environments" in p.parts:
            continue
        text = p.read_text()
        # detect verb
        verb_m = re.search(r"^(get|post|put|delete|patch)\s*{", text, re.MULTILINE)
        if not verb_m:
            continue
        verb = verb_m.group(1).lower()
        if verb in ("post", "put"):
            assert prereq_re.search(text), f"{p} missing script:pre-request"
            assert guard_re.search(text), f"{p} missing WRITE BLOCKED guard"
        elif verb == "get":
            assert not guard_re.search(text), f"{p} (GET) should not have WRITE BLOCKED guard"


# ---------- (7) Lookups folder ----------
EXPECTED_LOOKUPS = {
    "CaseTypes", "Priorities", "TrackingStatuses", "Employees", "Contracts",
    "CoverTypes", "SLAs", "FaultCodes", "Skills", "Teams", "Customers",
    "Contacts", "SubLocations",
}

def test_lookups_present():
    lu = ROOT / "Lookups"
    assert lu.is_dir(), "Lookups folder missing"
    names = {p.stem for p in lu.glob("*.bru")}
    missing = EXPECTED_LOOKUPS - names
    assert not missing, f"Missing lookups: {missing}"
    # each must be GET
    for p in lu.glob("*.bru"):
        t = p.read_text()
        assert re.search(r"^get\s*{", t, re.MULTILINE), f"{p.name} not GET"


# ---------- (8) GET response tests ----------
def test_get_requests_have_response_tests():
    # at least all GET files include a `tests {` post-response test block
    get_files = []
    for p in ROOT.rglob("*.bru"):
        if "environments" in p.parts or p.name == "collection.bru":
            continue
        text = p.read_text()
        if re.search(r"^get\s*{", text, re.MULTILINE):
            get_files.append((p, text))
    assert get_files, "no GET files scanned"
    for p, text in get_files:
        assert re.search(r"tests\s*{", text), f"{p} missing tests block"
        assert "expect" in text or "test(" in text or "res.status" in text, \
            f"{p} tests block has no assertions"


def test_equipment_getone_asserts_ids():
    t = _read(ROOT / "Equipment/GetOne.bru")
    assert "siconEquipmentId" in t and "serialNumber" in t, \
        "Equipment GetOne tests missing siconEquipmentId/serialNumber assertions"


# ---------- (9) Null-vs-zero on optional FKs ----------
def test_null_optional_fks_in_create_bodies():
    # Case PostOne, Appointment PostOne, Equipment PostOne
    for path in ("Cases/Case/PostOne.bru", "Appointments/Appointment/PostOne.bru",
                 "Equipment/PostOne.bru"):
        t = _read(ROOT / path)
        # optional FKs should be null (at least one of these depending on entity)
        # check that when the field is present, it is null OR a {{lookup}} var, not 0
        for fld in ("chargeRateId", "labelId", "parentWorkAppointmentId"):
            m = re.search(rf'"{fld}"\s*:\s*([^,\n]+)', t)
            if m:
                val = m.group(1).strip().rstrip(",").strip()
                assert val == "null", f"{path}: {fld}={val} (expected null)"
    # Reference vars like {{caseTypeId}}/{{priorityId}}/{{employeeId}} used instead of 0
    case_post = _read(ROOT / "Cases/Case/PostOne.bru")
    for tok in ("caseTypeId", "priorityId"):
        assert "{{" + tok + "}}" in case_post or "{" + tok + "}" in case_post, \
            f"Case PostOne doesn't reference {tok} lookup var"


# ---------- Mapping CSV ----------
EXPECTED_HEADER = ["Sicon Entity", "Sicon JSON Path", "Pulse Entity", "Pulse Field/Path",
                   "Direction", "Data Type", "Sicon Behaviour Status", "Notes"]

def test_mapping_csv_header_and_rows():
    with CSV_PATH.open(newline="") as f:
        rdr = csv.reader(f)
        rows = list(rdr)
    assert rows[0] == EXPECTED_HEADER, f"Header mismatch: {rows[0]}"
    data_rows = rows[1:]
    assert len(data_rows) == 164, f"expected 164 data rows, got {len(data_rows)}"
    # non-empty behaviour status
    for i, r in enumerate(data_rows, start=2):
        assert r[6].strip(), f"row {i} empty behaviour status"


def test_mapping_csv_no_unmapped_token():
    txt = CSV_PATH.read_text()
    assert "UNMAPPED" not in txt, "UNMAPPED token present in CSV"


def test_field_mapping_md_no_unmapped_label():
    txt = MD_PATH.read_text()
    # allow the single sentence describing nothing is unmapped
    hits = [l for l in txt.splitlines() if "UNMAPPED" in l]
    # only allowed to appear in a narrative sentence, not as a field label
    for h in hits:
        assert re.search(r"nothing|no fields|not.*unmapped|zero", h, re.I), \
            f"UNMAPPED label in FIELD_MAPPING.md: {h}"
    # must contain markdown tables
    assert "|" in txt and "---" in txt, "no markdown tables in FIELD_MAPPING.md"


# ---------- Download endpoints ----------
def test_download_zip_endpoint():
    r = requests.get(f"{BASE_URL}/api/downloads/sicon-bruno-collection.zip", timeout=30)
    assert r.status_code == 200, f"zip download {r.status_code}"
    assert "application/zip" in r.headers.get("content-type", ""), \
        f"content-type: {r.headers.get('content-type')}"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    # collection-root mapping.csv + FIELD_MAPPING.md
    assert any(n.endswith("mapping.csv") for n in names), "mapping.csv missing in zip"
    assert any(n.endswith("FIELD_MAPPING.md") for n in names), "FIELD_MAPPING.md missing in zip"
    # Equipment GetMany/GetOne
    assert any("Equipment/GetMany.bru" in n for n in names), "Equipment/GetMany.bru missing"
    assert any("Equipment/GetOne.bru" in n for n in names), "Equipment/GetOne.bru missing"
    # Lookups
    assert any("Lookups/CaseTypes.bru" in n for n in names), "Lookups/CaseTypes.bru missing"


def test_download_csv_endpoint():
    r = requests.get(f"{BASE_URL}/api/downloads/sicon-field-mapping.csv", timeout=30)
    assert r.status_code == 200, f"csv download {r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "text/csv" in ct, f"content-type: {ct}"
    first_line = r.text.splitlines()[0]
    got = next(csv.reader([first_line]))
    assert got == EXPECTED_HEADER, f"CSV header mismatch: {got}"


# ---------- Regression: imports ----------
def test_backend_imports_clean():
    import importlib
    mods = ["routes.public_downloads", "route_registry.features"]
    import sys
    sys.path.insert(0, "/app/backend")
    for m in mods:
        try:
            importlib.import_module(m)
        except ModuleNotFoundError as e:
            pytest.skip(f"module {m} not present: {e}")
