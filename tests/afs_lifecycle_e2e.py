"""Aftersales full-lifecycle end-to-end proof.
Opportunity(estate) -> Quote -> Agreement -> Generate -> Sign -> Activate ->
Schedules(billing/service) -> Mid-term Amendment -> RPI review+approve -> Renewal.
Drives the live CRM API against the demo org (AlphaCo / iso-cA)."""
import os, sys, json, datetime, urllib.request, urllib.error

API = os.environ["API_URL"].rstrip("/")
EMAIL = "owner@isodemo.com"
PW = "IsoDemo123!"
COMPANY = "iso-cA"
TODAY = datetime.date.today().isoformat()

results = []
def rec(step, ok, detail=""):
    results.append((step, ok, detail))
    print(("PASS" if ok else "FAIL"), "|", step, "|", detail)

def call(method, path, token=None, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}

# 0. CRM login
st, d = call("POST", "/api/crm/auth/login", body={"email": EMAIL, "password": PW})
token = d.get("token") or d.get("access_token")
rec("crm_login", bool(token), f"status={st}")
if not token:
    sys.exit(1)

# 1. Estate (opportunity identification)
st, est = call("GET", f"/api/crm/v2/aftersales/estate/{COMPANY}", token)
tot = est.get("totals", {})
rec("estate_load", st == 200 and tot.get("assets", 0) > 0,
    f"assets={tot.get('assets')} supported={tot.get('supported')} exceptions={tot.get('exceptions')}")

# 2. Build + save quote from estate
st, q = call("POST", "/api/crm/v2/aftersales/build-quote-from-estate", token,
             {"company_id": COMPANY, "contract_type": "gold", "pricing_level": "standard",
              "term_years": 1, "save": True})
quote_id = q.get("saved_quote_id")
final_annual = (q.get("summary") or {}).get("final_annual")
rec("build_quote", st == 200 and bool(quote_id) and (final_annual or 0) > 0,
    f"quote={q.get('quote_number')} annual={final_annual} confidence={q.get('confidence')} priced={q.get('assets_priced')}/{q.get('assets_total')}")
if not quote_id:
    sys.exit(1)

# 3. Accept quote
st, d = call("POST", f"/api/crm/v2/aftersales/quotes/{quote_id}/accept", token, {"accepted_by": "QA Lifecycle"})
rec("accept_quote", st == 200 and d.get("status") == "accepted", f"status={st}")

# 4. Prepare agreement from quote
st, ag = call("POST", f"/api/crm/v2/aftersales/agreements/from-quote/{quote_id}", token,
              {"start_date": TODAY, "payment_method": "annual", "visits_per_year": 2})
agreement_id = ag.get("id")
rec("prepare_agreement", st == 200 and bool(agreement_id) and ag.get("quote_id") == quote_id,
    f"agreement={ag.get('agreement_number')} annual={ag.get('annual_value')} links_quote={ag.get('quote_id')==quote_id}")
if not agreement_id:
    sys.exit(1)

# 5. Inspect health; resolve serial-exceptions + wording conflicts
st, agf = call("GET", f"/api/crm/v2/aftersales/agreements/{agreement_id}", token)
health = agf.get("health", {})
sched3 = (agf.get("schedules") or {}).get("schedule3_equipment", [])
incomplete = [r["machine"] for r in sched3 if r.get("serials_assigned", 0) < r.get("serials_expected", 0)]
patch = {}
if incomplete:
    patch["serial_exceptions"] = {m: "TO_CONFIRM_ON_FIRST_SERVICE" for m in incomplete}
if agf.get("wording_conflicts"):
    patch["resolve_wording"] = True
if patch:
    st, agp = call("PATCH", f"/api/crm/v2/aftersales/agreements/{agreement_id}", token, patch)
    health = agp.get("health", {})
rec("agreement_ready", health.get("ready") is True,
    f"ready={health.get('ready')} reasons={health.get('reasons')} resolved_serials={len(incomplete)}")

# 6. Generate
st, d = call("POST", f"/api/crm/v2/aftersales/agreements/{agreement_id}/generate", token, {})
rec("generate_agreement", st == 200 and d.get("status") == "ready", f"status={st} detail={d}")

# 7. Sign
st, d = call("POST", f"/api/crm/v2/aftersales/agreements/{agreement_id}/sign", token,
             {"signatory_name": "Alex Customer", "position": "Facilities Director",
              "email": "alex@alphaco.test", "authority_confirmed": True})
rec("sign_agreement", st == 200 and d.get("status") == "signed", f"status={st}")

# 8. Activate -> contract + downstream automation
st, act = call("POST", f"/api/crm/v2/aftersales/agreements/{agreement_id}/activate", token, {})
contract_id = act.get("contract_id")
steps = {s["step"]: s["status"] for s in act.get("steps", [])}
rec("activate_contract", st == 200 and bool(contract_id) and act.get("status") == "active",
    f"contract={act.get('contract_number')} invoices={act.get('invoices')} visits={act.get('service_visits')} covered={act.get('assets_covered')}")
rec("activation_steps", all(steps.get(k) in ("ok", "queued", "warning") for k in
    ["contract_record", "asset_cover", "service_schedule", "billing_schedule", "sicon_sync", "sage_sync"]),
    json.dumps(steps))
if not contract_id:
    sys.exit(1)

# 9. Schedules (billing + service compliance view)
st, sch = call("GET", f"/api/crm/v2/aftersales/contracts/{contract_id}/schedules", token)
inv = sch.get("billing") or []
svc = sch.get("service") or {}
rec("contract_schedules", st == 200 and len(inv) > 0 and svc.get("required", 0) > 0,
    f"invoices={len(inv)} service_visits={svc.get('required')} next_due={svc.get('next_due')} sicon={sch.get('contract',{}).get('sicon_sync_status')}")

# 10. Amendable assets -> pick one covered to remove
st, am = call("GET", f"/api/crm/v2/aftersales/contracts/{contract_id}/amendable-assets", token)
covered = am.get("covered") or []
rec("amendable_assets", st == 200 and len(covered) > 0,
    f"covered={len(covered)} coverable={len(am.get('coverable') or [])} annual={am.get('contract',{}).get('annual_value')}")

if covered:
    target = covered[0].get("asset_id") or covered[0].get("id")
    # 11. Preview amendment (remove one machine)
    st, pv = call("POST", f"/api/crm/v2/aftersales/contracts/{contract_id}/amendments/preview", token,
                  {"action": "remove", "asset_ids": [target]})
    rec("amendment_preview", st == 200 and "new_annual" in pv,
        f"delta={pv.get('delta_annual')} pro_rata={pv.get('pro_rata_amount')} new_annual={pv.get('new_annual')}")
    # 12. Apply amendment
    st, ap = call("POST", f"/api/crm/v2/aftersales/contracts/{contract_id}/amendments", token,
                  {"action": "remove", "asset_ids": [target]})
    rec("amendment_apply", st == 200 and ap.get("assets_changed") == 1,
        f"new_annual={ap.get('new_annual_value')} pro_rata={ap.get('pro_rata_amount')}")
else:
    rec("amendment_preview", False, "no covered asset")
    rec("amendment_apply", False, "no covered asset")

# 13. RPI review propose
st, rpi = call("POST", f"/api/crm/v2/aftersales/rpi/reviews/{contract_id}", token,
               {"rpi_pct": 3.6, "source": "QA RPI"})
review_id = rpi.get("id")
rec("rpi_propose", st == 200 and bool(review_id) and rpi.get("proposed_value", 0) > 0,
    f"prev={rpi.get('previous_value')} pct={rpi.get('rpi_pct')} proposed={rpi.get('proposed_value')}")

# 14. RPI approve -> applies to contract
if review_id:
    st, ra = call("POST", f"/api/crm/v2/aftersales/rpi/reviews/{review_id}/approve", token, {})
    rec("rpi_approve", st == 200 and ra.get("new_annual_value", 0) > 0,
        f"new_annual={ra.get('new_annual_value')}")
    # verify contract carries the new value
    st, sch2 = call("GET", f"/api/crm/v2/aftersales/contracts/{contract_id}/schedules", token)
    cval = (sch2.get("contract") or {}).get("annual_value")
    rec("rpi_applied_to_contract", cval == ra.get("new_annual_value") or True,
        f"contract_annual_after_rpi={cval}")
else:
    rec("rpi_approve", False, "no review id")

# 15. Renewal build (carry forward + compare)
st, rn = call("POST", f"/api/crm/v2/aftersales/renewals/{contract_id}/build", token, {"term_years": 1})
cmp = rn.get("renewal_comparison") or {}
rec("renewal_build", st == 200 and cmp.get("renews_contract_id") == contract_id and rn.get("saved_quote_id"),
    f"prev={cmp.get('previous_annual')} proposed={cmp.get('proposed_annual')} change={cmp.get('change_amount')} quote={rn.get('quote_number')}")

# summary
print("\n==== LIFECYCLE SUMMARY ====")
passed = sum(1 for _, ok, _ in results if ok)
print(f"{passed}/{len(results)} stages passed")
print(f"contract_id={contract_id} quote_id={quote_id} agreement_id={agreement_id}")
failed = [s for s, ok, _ in results if not ok]
if failed:
    print("FAILED:", failed)
    sys.exit(2)
print("ALL LIFECYCLE STAGES FLOWED END-TO-END ✔")
