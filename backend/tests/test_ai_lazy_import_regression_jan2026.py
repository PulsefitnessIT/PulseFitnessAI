"""
Regression test: after moving `emergentintegrations.llm` / `litellm` imports
to lazy (function-local) scope to fix the k8s deploy crash-loop, verify:
  1) Backend health is 200.
  2) AI-backed endpoints do NOT produce ImportError / NameError 500s.
     Any 200 OK, or graceful handled error (400/404/422/503/etc), is a PASS.
     Only 500 responses whose body mentions ImportError/NameError/
     "LlmChat is not defined"/"UserMessage is not defined" are FAILURES.
  3) Master-admin test-data purge endpoints are wired (200 with admin JWT,
     401 unauthenticated).
"""
import os
import re
import pytest
import requests

def _load_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ.setdefault("REACT_APP_BACKEND_URL", line.split("=", 1)[1].strip())
_load_env()
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASS = "C2s9yJ3YAhydB4d34-Bykg"
OPER_EMAIL = "owner@isodemo.com"
OPER_PASS = "IsoDemo123!"

IMPORT_ERR_RE = re.compile(
    r"(ImportError|NameError|is not defined|cannot import name|ModuleNotFoundError)",
    re.IGNORECASE,
)


def _is_import_regression(resp: requests.Response) -> tuple[bool, str]:
    if resp.status_code != 500:
        return False, ""
    body = resp.text or ""
    m = IMPORT_ERR_RE.search(body)
    return (bool(m), body[:400])


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
                      timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def oper_token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": OPER_EMAIL, "password": OPER_PASS},
                      timeout=30)
    assert r.status_code == 200, f"operator login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def crm_token():
    r = requests.post(f"{BASE}/api/crm/auth/login",
                      json={"email": OPER_EMAIL, "password": OPER_PASS},
                      timeout=30)
    if r.status_code != 200:
        pytest.skip(f"crm login unavailable ({r.status_code})")
    tok = r.json().get("token") or r.json().get("access_token")
    return tok


@pytest.fixture(scope="session")
def oper_headers(oper_token):
    return {"Authorization": f"Bearer {oper_token}"}


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def crm_headers(crm_token):
    return {"Authorization": f"Bearer {crm_token}"}


# -----------------------------
# 1. Core health
# -----------------------------
def test_health_ok():
    r = requests.get(f"{BASE}/api/health", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# -----------------------------
# 2. Master-admin test-data purge
# -----------------------------
class TestMasterAdminPurge:
    def test_candidates_unauth_401(self):
        r = requests.get(f"{BASE}/api/master-admin/test-data/candidates", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_purge_unauth_401(self):
        r = requests.post(f"{BASE}/api/master-admin/test-data/purge",
                          json={"dry_run": True}, timeout=15)
        assert r.status_code in (401, 403)

    def test_candidates_admin_200(self, admin_headers):
        r = requests.get(f"{BASE}/api/master-admin/test-data/candidates",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, dict) or isinstance(body, list)

    def test_purge_dry_run_admin_200(self, admin_headers):
        r = requests.post(f"{BASE}/api/master-admin/test-data/purge",
                          headers=admin_headers,
                          json={"dry_run": True},
                          timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        # per-collection counts expected
        assert isinstance(body, dict)


# -----------------------------
# 3. AI endpoint regression sweep — helpers to fetch entity ids
# -----------------------------
def _first(lst_or_dict, key=None):
    if isinstance(lst_or_dict, dict):
        for k in ("items", "results", "data", "equipment", "issues", "files"):
            if k in lst_or_dict and isinstance(lst_or_dict[k], list) and lst_or_dict[k]:
                lst_or_dict = lst_or_dict[k]
                break
    if isinstance(lst_or_dict, list) and lst_or_dict:
        item = lst_or_dict[0]
        if key:
            return item.get(key) or item.get("id") or item.get("_id")
        return item
    return None


@pytest.fixture(scope="session")
def equipment_id(oper_headers):
    r = requests.get(f"{BASE}/api/equipment", headers=oper_headers, timeout=30)
    if r.status_code != 200:
        return None
    item = _first(r.json())
    if not item:
        return None
    return item.get("id") or item.get("_id") or item.get("equipment_id")


@pytest.fixture(scope="session")
def issue_id(oper_headers):
    r = requests.get(f"{BASE}/api/issues", headers=oper_headers, timeout=30)
    if r.status_code != 200:
        return None
    item = _first(r.json())
    if not item:
        return None
    return item.get("id") or item.get("_id") or item.get("issue_id")


# Parameterised AI endpoint sweep. Each row = (method, path, json_body_factory, headers_fixture)
AI_ENDPOINTS = [
    # ai_diagnosis
    ("POST", "/api/chat/diagnose", lambda ctx: {"message": "Treadmill motor overheats after 20 min", "session_id": "test-lazy-import"}, "oper"),
    ("POST", "/api/audit/generate", lambda ctx: {"site_id": "iso-demo-site-a"}, "oper"),
    # svc/ai triage
    ("POST", "/api/svc/ai/triage", lambda ctx: {"description": "Squeaky belt on treadmill", "equipment_type": "treadmill"}, "oper"),
    ("POST", "/api/svc/ai/photo/classify", lambda ctx: {"image_base64": ""}, "oper"),
    # capex AI justification
    ("POST", "/api/capex/generate-justifications", lambda ctx: {"title": "Replace treadmill fleet", "amount": 25000, "reason": "End of life"}, "oper"),
    # risk assessment AI generate
    ("POST", "/api/risk-assessments/ai-generate", lambda ctx: {"activity": "Manual handling of gym plates", "context": "Free weights area"}, "oper"),
    # equipment predictive maintenance (POST, needs equipment_id)
    ("POST", "/api/equipment/{equipment_id}/predictive-maintenance", lambda ctx: {}, "oper"),
    # admin documents duplicate scan
    ("POST", "/api/ai-scan-duplicates", lambda ctx: {}, "admin"),
]


@pytest.mark.parametrize("method,path,body_fn,who", AI_ENDPOINTS)
def test_ai_endpoint_no_import_regression(
    method, path, body_fn, who, oper_headers, admin_headers, equipment_id, issue_id
):
    headers = oper_headers if who == "oper" else admin_headers
    if "{equipment_id}" in path:
        if not equipment_id:
            pytest.skip("no equipment_id available in preview data")
        path = path.replace("{equipment_id}", str(equipment_id))
    if "{issue_id}" in path:
        if not issue_id:
            pytest.skip("no issue_id available in preview data")
        path = path.replace("{issue_id}", str(issue_id))

    url = f"{BASE}{path}"
    body = body_fn({"equipment_id": equipment_id, "issue_id": issue_id}) if body_fn else None

    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=90)
        else:
            r = requests.post(url, headers=headers, json=body, timeout=90)
    except requests.RequestException as e:
        pytest.fail(f"network error on {method} {path}: {e}")

    bad, snippet = _is_import_regression(r)
    assert not bad, (
        f"IMPORT/NAMEERROR regression on {method} {path} → 500\n{snippet}"
    )
    # Log the outcome for report visibility
    print(f"[AI] {method} {path} -> {r.status_code}")


# -----------------------------
# 4. Issue creation triage path (routes/issues.py + issue_helpers.py)
# -----------------------------
def test_issue_create_triage_no_import_regression(oper_headers):
    """Creating an issue triggers lazily-imported LlmChat triage. Should not 500 on import."""
    # Try common endpoints — a 404/422/400 is fine, only import-500 is a failure.
    payloads = [
        ("/api/issues", {"title": "TEST_lazy_import regression",
                          "description": "Belt slipping intermittently",
                          "equipment_type": "treadmill",
                          "severity": "medium"}),
    ]
    for path, body in payloads:
        r = requests.post(f"{BASE}{path}", headers=oper_headers, json=body, timeout=90)
        bad, snippet = _is_import_regression(r)
        assert not bad, f"IMPORT regression on POST {path}: {snippet}"
        print(f"[issue] POST {path} -> {r.status_code}")


# -----------------------------
# 5. Files / documents Q&A endpoints (routes/files.py, admin_documents.py)
# -----------------------------
def test_admin_documents_endpoints_no_import_regression(admin_headers):
    """Hit doc extract / supplier detect / duplicate scan surfaces to verify no import failures."""
    candidates = [
        ("GET", "/api/admin-documents", None),
        ("POST", "/api/admin-documents/duplicate-scan", {}),
        ("POST", "/api/admin-documents/supplier-detect", {"text": "Invoice from Acme Fitness Ltd"}),
    ]
    for method, path, body in candidates:
        try:
            if method == "GET":
                r = requests.get(f"{BASE}{path}", headers=admin_headers, timeout=45)
            else:
                r = requests.post(f"{BASE}{path}", headers=admin_headers, json=body, timeout=60)
        except requests.RequestException:
            continue
        if r.status_code == 404:
            # Route may not be mounted under this exact path — not our concern here.
            print(f"[docs] {method} {path} -> 404 (skipping)")
            continue
        bad, snippet = _is_import_regression(r)
        assert not bad, f"IMPORT regression on {method} {path}: {snippet}"
        print(f"[docs] {method} {path} -> {r.status_code}")
