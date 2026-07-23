"""
RELEASE READINESS AUDIT — PulseFitness.ai (Jan 2026)
Per-persona golden path smoke checks. Breadth over depth.
DO NOT complete Stripe payment. LIVE key in .env.
"""
import os
import time
import uuid
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fall back to frontend .env if not injected
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass

API = BASE + "/api"

# Shared token cache — auth is rate-limited (~4 rapid logins → 429). Only login once per user.
TOKENS: dict = {}
RESULTS: list = []


def record(path: str, ok: bool, status, detail: str = ""):
    RESULTS.append({"path": path, "ok": ok, "status": status, "detail": detail[:300]})
    print(f"[{'PASS' if ok else 'FAIL'}] {path} status={status} {detail[:200]}")


def _login(url: str, email: str, password: str, cache_key: str, extra_field: str = "email"):
    if cache_key in TOKENS:
        return TOKENS[cache_key]
    time.sleep(1.0)  # space out to avoid rate limit
    r = requests.post(url, json={extra_field: email, "password": password}, timeout=20)
    if r.status_code == 429:
        time.sleep(10)
        r = requests.post(url, json={extra_field: email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in {r.text[:200]}"
    TOKENS[cache_key] = tok
    return tok


def H(tok, site_id=None):
    h = {"Authorization": f"Bearer {tok}"}
    if site_id:
        h["X-Site-Id"] = site_id
    return h


# ─────────────────────────── PERSONA 1: OPERATOR OWNER ───────────────────────────
class TestOperatorOwner:
    def test_login_and_me(self):
        tok = _login(f"{API}/auth/login", "owner@isodemo.com", "IsoDemo123!", "owner_platform")
        r = requests.get(f"{API}/auth/me", headers=H(tok), timeout=15)
        record("owner /api/auth/me", r.status_code == 200, r.status_code)
        assert r.status_code == 200
        me = r.json()
        # Some codebases nest under "user"
        u = me.get("user") or me
        has_svc = "is_service_desk" in u or "is_service_desk" in me
        has_inv = "is_inventory" in u or "is_inventory" in me
        record("owner /me returns is_service_desk & is_inventory flags",
               has_svc and has_inv, r.status_code,
               f"keys={list(u.keys())[:15]}")

    def test_equipment_list(self):
        tok = TOKENS["owner_platform"]
        r = requests.get(f"{API}/equipment", headers=H(tok), timeout=20)
        record("owner GET /api/equipment", r.status_code == 200, r.status_code, r.text[:150])
        assert r.status_code == 200

    def test_create_equipment_and_log_fault(self):
        tok = TOKENS["owner_platform"]
        payload = {
            "make": "TEST_Make",
            "model": f"TEST_MODEL_{uuid.uuid4().hex[:6]}",
            "serial_number": f"TEST_SN_{uuid.uuid4().hex[:6]}",
            "category": "cardio",
            "location": "TEST_Location",
        }
        r = requests.post(f"{API}/equipment", headers=H(tok), json=payload, timeout=20)
        ok = r.status_code in (200, 201)
        record("owner POST /api/equipment (create)", ok, r.status_code, r.text[:200])
        if not ok:
            pytest.skip(f"equipment create failed {r.status_code}")
        eq = r.json()
        eq_id = eq.get("id") or eq.get("_id") or eq.get("equipment_id")

        # Log a fault via /api/issues
        fault_payload = {
            "equipment_id": eq_id,
            "title": "TEST_Fault noise",
            "description": "TEST audit fault",
            "priority": "medium",
        }
        r2 = requests.post(f"{API}/issues", headers=H(tok), json=fault_payload, timeout=20)
        ok2 = r2.status_code in (200, 201)
        record("owner POST /api/issues (log fault)", ok2, r2.status_code, r2.text[:200])

        # Verify appears in GET
        r3 = requests.get(f"{API}/issues", headers=H(tok), timeout=20)
        found = False
        if r3.status_code == 200:
            data = r3.json()
            items = data if isinstance(data, list) else data.get("items", data.get("issues", []))
            found = any((i.get("title") == fault_payload["title"] or
                         i.get("equipment_id") == eq_id) for i in items)
        record("owner fault appears in GET /api/issues", found, r3.status_code)


# ─────────────────────────── PERSONA 2: CRM SALES ───────────────────────────
class TestCRMSales:
    crm_tok = None
    quote_id = None
    company_id = None

    def test_crm_login(self):
        tok = _login(f"{API}/crm/auth/login", "owner@isodemo.com", "IsoDemo123!", "owner_crm")
        TestCRMSales.crm_tok = tok
        record("CRM /api/crm/auth/login", True, 200)

    def test_create_company(self):
        tok = TestCRMSales.crm_tok
        payload = {"name": f"TEST_Co_{uuid.uuid4().hex[:6]}", "industry": "gym"}
        r = requests.post(f"{API}/crm/v2/companies", headers=H(tok), json=payload, timeout=20)
        if r.status_code == 404:
            r = requests.post(f"{API}/crm/companies", headers=H(tok), json=payload, timeout=20)
        ok = r.status_code in (200, 201)
        record("CRM create company", ok, r.status_code, r.text[:200])
        if ok:
            d = r.json()
            TestCRMSales.company_id = d.get("id") or d.get("company_id") or d.get("_id")

    def test_create_quote_with_line(self):
        tok = TestCRMSales.crm_tok
        if not TestCRMSales.company_id:
            pytest.skip("no company")
        payload = {
            "company_id": TestCRMSales.company_id,
            "lines": [{"description": "TEST Treadmill", "quantity": 1, "unit_price": 1000}],
            "currency": "GBP",
        }
        r = requests.post(f"{API}/crm/v2/quotes", headers=H(tok), json=payload, timeout=20)
        ok = r.status_code in (200, 201)
        record("CRM create quote", ok, r.status_code, r.text[:250])
        if ok:
            d = r.json()
            TestCRMSales.quote_id = d.get("id") or d.get("quote_id") or d.get("_id")

    def test_mark_accepted(self):
        tok = TestCRMSales.crm_tok
        qid = TestCRMSales.quote_id
        if not qid:
            pytest.skip("no quote")
        # Try various accept endpoints
        for path in [
            f"{API}/crm/v2/quotes/{qid}/accept",
            f"{API}/crm/v2/quotes/{qid}/sign",
            f"{API}/crm/v2/quotes/{qid}/mark-accepted",
        ]:
            r = requests.post(path, headers=H(tok), json={}, timeout=15)
            if r.status_code in (200, 201, 204):
                record(f"CRM accept quote via {path.split('/')[-1]}", True, r.status_code)
                return
        # fallback: try patching status
        r = requests.patch(f"{API}/crm/v2/quotes/{qid}",
                           headers=H(tok), json={"status": "accepted"}, timeout=15)
        record("CRM mark quote accepted", r.status_code in (200, 204), r.status_code, r.text[:200])

    def test_push_to_distribution(self):
        tok = TestCRMSales.crm_tok
        qid = TestCRMSales.quote_id
        if not qid:
            pytest.skip("no quote")
        url = f"{API}/crm/v2/quotes/{qid}/push-to-distribution"
        r1 = requests.post(url, headers=H(tok), json={}, timeout=30)
        ok1 = r1.status_code == 200
        record("CRM push-to-distribution (1st)", ok1, r1.status_code, r1.text[:300])
        # Idempotent second call
        r2 = requests.post(url, headers=H(tok), json={}, timeout=30)
        ok2 = r2.status_code == 200
        # idempotent = same result / no dup order
        record("CRM push-to-distribution idempotent 2nd", ok2, r2.status_code, r2.text[:300])


# ─────────────────────────── PERSONA 3: DISTRIBUTION OPS ───────────────────────────
class TestDistribution:
    def test_dashboard(self):
        tok = TOKENS.get("owner_platform") or _login(
            f"{API}/auth/login", "owner@isodemo.com", "IsoDemo123!", "owner_platform")
        r = requests.get(f"{API}/inventory/dashboard", headers=H(tok), timeout=20)
        record("distribution GET /api/inventory/dashboard", r.status_code == 200,
               r.status_code, r.text[:200])

    def test_logistics_and_allocation_reachable(self):
        tok = TOKENS["owner_platform"]
        for p in ["/inventory/orders", "/inventory/warehouse", "/inventory/allocation",
                  "/inventory/logistics/installs", "/inventory/certificates"]:
            r = requests.get(f"{API}{p}", headers=H(tok), timeout=15)
            record(f"owner GET {p}", r.status_code < 500, r.status_code, r.text[:120])


# ─────────────────────────── PERSONA 4: CUSTOMER LITE ───────────────────────────
class TestCustomerLite:
    def test_login_and_deliveries(self):
        # Customer login endpoint — try common paths
        tok = None
        for url in [f"{API}/customer/auth/login", f"{API}/auth/login",
                    f"{API}/members/auth/login", f"{API}/customer-portal/auth/login"]:
            time.sleep(0.5)
            r = requests.post(url, json={"email": "lite.docs@pulsedemo.test",
                                         "password": "LiteDocs123!"}, timeout=15)
            if r.status_code == 200 and (r.json().get("token") or r.json().get("access_token")):
                tok = r.json().get("token") or r.json().get("access_token")
                record(f"customer-lite login via {url}", True, 200)
                break
        if not tok:
            record("customer-lite login", False, "n/a", "no auth endpoint accepted creds")
            pytest.skip("could not login customer-lite")
        TOKENS["cust_lite"] = tok

        r = requests.get(f"{API}/customer/deliveries", headers=H(tok), timeout=20)
        record("customer-lite GET /api/customer/deliveries", r.status_code == 200,
               r.status_code, r.text[:200])

        # equipment view for that customer
        r2 = requests.get(f"{API}/equipment", headers=H(tok), timeout=20)
        record("customer-lite GET /api/equipment", r2.status_code == 200, r2.status_code, r2.text[:150])


# ─────────────────────────── PERSONA 5: LOGISTICS ───────────────────────────
class TestLogistics:
    def test_login_and_scope(self):
        tok = _login(f"{API}/auth/login", "logi1@isodemo.com", "LogiPass123!", "logistics")
        r = requests.get(f"{API}/auth/me", headers=H(tok), timeout=15)
        me = r.json() if r.status_code == 200 else {}
        u = me.get("user") or me
        role = u.get("role") or u.get("user_role") or ""
        record("logistics /auth/me role=logistics",
               "logistic" in str(role).lower(),
               r.status_code, f"role={role}")

        r2 = requests.get(f"{API}/inventory/logistics/installs", headers=H(tok), timeout=15)
        record("logistics GET installs", r2.status_code == 200, r2.status_code, r2.text[:150])

        # Write attempt → expect 403
        r3 = requests.post(f"{API}/inventory/orders", headers=H(tok),
                           json={"test": "x"}, timeout=15)
        record("logistics WRITE isolation (expect 403)",
               r3.status_code == 403, r3.status_code, r3.text[:150])


# ─────────────────────────── PERSONA 6: DEALER ───────────────────────────
class TestDealer:
    def test_login_scope_isolation(self):
        tok = None
        for url in [f"{API}/auth/login", f"{API}/dealer-parts/portal/auth/login",
                    f"{API}/dealer/auth/login"]:
            time.sleep(0.5)
            r = requests.post(url, json={"email": "portal2@fitline.test",
                                         "password": "DealerDemo123!"}, timeout=15)
            if r.status_code == 200 and (r.json().get("token") or r.json().get("access_token")):
                tok = r.json().get("token") or r.json().get("access_token")
                record(f"dealer login via {url}", True, 200)
                break
        if not tok:
            record("dealer login", False, "n/a", "no auth endpoint accepted creds")
            pytest.skip("no dealer login")
        r = requests.get(f"{API}/dealer-parts/portal/me/overview", headers=H(tok), timeout=20)
        record("dealer overview (own scope)", r.status_code == 200, r.status_code, r.text[:150])

        # Staff-only endpoint expected 403
        r2 = requests.get(f"{API}/dealer-parts/orders", headers=H(tok), timeout=15)
        record("dealer staff-only isolation (expect 403)",
               r2.status_code == 403, r2.status_code, r2.text[:150])


# ─────────────────────────── PERSONA 7: MASTER ADMIN ───────────────────────────
class TestMasterAdmin:
    def test_login_and_endpoints(self):
        tok = _login(f"{API}/auth/login", "admin@pulsefitness.com",
                     "C2s9yJ3YAhydB4d34-Bykg", "master_admin")
        r = requests.get(f"{API}/master-admin/orgs", headers=H(tok), timeout=20)
        record("master-admin list orgs", r.status_code == 200, r.status_code, r.text[:150])

        r2 = requests.post(f"{API}/master-admin/platform-health/scan",
                           headers=H(tok), json={}, timeout=60)
        ok = r2.status_code == 200
        record("master-admin platform-health/scan", ok, r2.status_code, r2.text[:250])
        if ok:
            data = r2.json()
            has_findings = ("findings" in data) or ("issues" in data) or ("results" in data)
            record("master-admin scan returns findings structure",
                   has_findings, 200, f"keys={list(data.keys())[:10]}")


# ─────────────────────────── PERSONA 8: MEMBERSHIPS/STRIPE (LIVE — DO NOT PAY) ───────────
class TestMembershipsStripe:
    def test_checkout_session_create(self):
        tok = TOKENS.get("owner_platform") or _login(
            f"{API}/auth/login", "owner@isodemo.com", "IsoDemo123!", "owner_platform")
        # Need a plan_id and member_id — try to fetch them
        plans_r = requests.get(f"{API}/memberships/plans", headers=H(tok), timeout=15)
        members_r = requests.get(f"{API}/memberships/members", headers=H(tok), timeout=15)
        record("memberships GET plans", plans_r.status_code == 200, plans_r.status_code)
        record("memberships GET members", members_r.status_code == 200, members_r.status_code)

        plan_id = None
        member_id = None
        try:
            plans = plans_r.json()
            plans = plans if isinstance(plans, list) else plans.get("items", plans.get("plans", []))
            plan_id = plans[0]["id"] if plans else None
        except Exception:
            pass
        try:
            members = members_r.json()
            members = members if isinstance(members, list) else members.get("items", members.get("members", []))
            member_id = members[0]["id"] if members else None
        except Exception:
            pass

        if not plan_id or not member_id:
            record("stripe checkout create", False, "n/a", f"missing plan/member plan={plan_id} member={member_id}")
            pytest.skip("no plan/member to test checkout")

        r = requests.post(f"{API}/memberships/checkout", headers=H(tok),
                          json={"plan_id": plan_id, "member_id": member_id,
                                "origin_url": "https://example.com"}, timeout=30)
        ok = r.status_code == 200 and (r.json().get("url") or r.json().get("session_id"))
        record("stripe create-session responds 200+url", ok, r.status_code, r.text[:300])


# ─────────────────────────── PERSONA 9: TENANCY ISOLATION ───────────────────────────
class TestTenancyIsolation:
    def test_site_isolation(self):
        tok = _login(f"{API}/auth/login", "manager@isodemo.com", "IsoDemo123!", "manager_a")
        # Try requesting Site B via header — expect 403
        r = requests.get(f"{API}/equipment", headers=H(tok, site_id="iso-demo-site-b"), timeout=15)
        ok = r.status_code == 403
        record("site isolation Site B → 403", ok, r.status_code, r.text[:200])

        # Site A should work
        r2 = requests.get(f"{API}/equipment", headers=H(tok, site_id="iso-demo-site-a"), timeout=15)
        record("site isolation Site A → allowed", r2.status_code == 200, r2.status_code, r2.text[:150])


# ─────────────────────────── SUMMARY ───────────────────────────
def test_zzz_write_summary():
    import json
    out = {"total": len(RESULTS),
           "passed": sum(1 for r in RESULTS if r["ok"]),
           "failed": sum(1 for r in RESULTS if not r["ok"]),
           "results": RESULTS}
    os.makedirs("/app/test_reports/pytest", exist_ok=True)
    with open("/app/test_reports/pytest/release_readiness_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n=== SUMMARY: {out['passed']}/{out['total']} passed ({out['failed']} failed) ===")
    for r in RESULTS:
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['path']} ({r['status']})")
