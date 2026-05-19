"""Iter 216h26 — Master Admin → End-user portal linkage audit.

Run via:  cd /app/backend && python3 tests/test_iter_216h26_audit.py

Walks every Master Admin write surface and asserts the downstream
visibility in the end-user (Operations / CRM / Memberships / Member
portal / LiteDashboard) endpoints. Fails loudly on any broken link
so the audit report stays honest.
"""
import asyncio
import os
import sys
import uuid
import time
import json
import httpx

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip()
                break
API = f"{BASE}/api"

# Rate-limit bypass header so we can hammer login during the audit.
SECRET = None
with open("/app/backend/.env") as f:
    for line in f:
        if line.startswith("RATE_LIMIT_BYPASS_SECRET="):
            SECRET = line.split("=", 1)[1].strip()
            break
BYPASS = {"X-Rate-Limit-Bypass": SECRET} if SECRET else {}

results = []


def record(check: str, passed: bool, detail: str = ""):
    icon = "✅" if passed else "❌"
    results.append({"check": check, "passed": passed, "detail": detail})
    print(f"{icon} {check}" + (f"  — {detail}" if detail else ""))


async def login(client, email, password):
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": password}, headers=BYPASS)
    r.raise_for_status()
    return r.json()["token"]


async def me(client, token):
    r = await client.get(f"{API}/auth/me", headers={**BYPASS, "Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


async def main():
    async with httpx.AsyncClient(timeout=30) as client:
        admin = await login(client, "admin@gymaxisai.com", "MasterAdmin123!")

        def h(t=admin):
            return {**BYPASS, "Authorization": f"Bearer {t}"}

        # ── A1 — /auth/me carries is_pulse_admin flag ─────────────────────
        pulse_t = await login(client, "pulse.scope.test@pulsefitness.com", "TestPulse2026!")
        pulse_me = await me(client, pulse_t)
        record("A1 /auth/me returns is_pulse_admin for Pulse Master Admin",
               pulse_me.get("is_pulse_admin") is True,
               f"role={pulse_me.get('role')} flag={pulse_me.get('is_pulse_admin')}")

        # ── A2 — Brand scope is honoured on protected endpoints ───────────
        r = await client.get(f"{API}/master-admin/all-sites", params={"brand": "gymaxis"}, headers=h(pulse_t))
        record("A2 Pulse admin forced to brand=pulse on all-sites",
               r.json().get("brand") == "pulse",
               f"requested gymaxis, got {r.json().get('brand')}")

        r = await client.get(f"{API}/master-admin/audit-log", params={"brand": "gymaxis"}, headers=h(pulse_t))
        record("A2b Pulse admin forced to brand=pulse on audit-log",
               r.json().get("brand") == "pulse",
               f"requested gymaxis, got {r.json().get('brand')}")

        r = await client.get(f"{API}/master-admin/marketing/analytics", params={"brand": "gymaxis"}, headers=h(pulse_t))
        record("A2c Pulse admin forced to brand=pulse on marketing analytics",
               r.json().get("brand") == "pulse" and r.json().get("scoped") is True)

        # ── B1 — Onboard staff wizard → user actually exists ─────────────
        orgs = (await client.get(f"{API}/master-admin/organizations", headers=h())).json().get("organizations", [])
        gymaxis_orgs = [o for o in orgs if o.get("brand") != "pulse"]
        target_org = gymaxis_orgs[0] if gymaxis_orgs else orgs[0]
        new_email = f"audit-staff-{uuid.uuid4().hex[:8]}@example.com"
        r = await client.post(f"{API}/master-admin/organizations/{target_org['id']}/users",
                              json={"email": new_email, "full_name": "Audit Staff", "role": "staff"}, headers=h())
        body = r.json()
        record("B1 Wizard creates staff user", r.status_code == 200 and body.get("invite_url"),
               f"status={r.status_code} invite_url={'yes' if body.get('invite_url') else 'no'}")
        invite_url = body.get("invite_url", "")
        token_param = invite_url.split("token=")[-1] if "token=" in invite_url else ""

        # ── B2 — Reset password via invite link ──────────────────────────
        if token_param:
            r = await client.post(f"{API}/auth/reset-password",
                                  json={"token": token_param, "password": "AuditStaff2026!"}, headers=BYPASS)
            record("B2 Invite link redeems via /reset-password", r.status_code in (200, 201),
                   f"status={r.status_code}")

            # ── B3 — Logging in lands the new user in correct portal ────
            try:
                new_t = await login(client, new_email, "AuditStaff2026!")
                new_me = await me(client, new_t)
                record("B3 New user can log in immediately",
                       new_me.get("email") == new_email,
                       f"account_type={new_me.get('account_type')} role={new_me.get('role')}")
                record("B3b New user has correct org",
                       new_me.get("organization_id") == target_org["id"])
                record("B3c New user has module_access dict",
                       isinstance(new_me.get("module_access"), dict),
                       f"keys={list((new_me.get('module_access') or {}).keys())}")
            except Exception as ex:
                record("B3 New user can log in immediately", False, str(ex))
                new_t = None

        # ── C1 — Module override toggle removes runtime access ──────────
        if token_param and new_t:
            await client.put(f"{API}/master-admin/users/{body['id']}/edit",
                             json={"module_overrides": {"crm": False}}, headers=h())
            # User must re-fetch /me after a change
            re_me = await me(client, new_t)
            record("C1 module_overrides crm=False zeroes module_access.crm at /me",
                   re_me.get("module_access", {}).get("crm") is False,
                   f"crm={re_me.get('module_access', {}).get('crm')}")

        # ── C2 — Allowed sites lock persists & is queryable ─────────────
        if token_param:
            # Find a real site for this org.
            sites = (await client.get(f"{API}/master-admin/organizations/{target_org['id']}/sites", headers=h())).json()
            sites_list = sites.get("sites") if isinstance(sites, dict) else sites
            if sites_list:
                pinned = sites_list[0]
                await client.put(f"{API}/master-admin/users/{body['id']}/edit",
                                 json={"allowed_site_ids": [pinned["id"]]}, headers=h())
                # Verify via the user-edit GET (re-fetch the user via the list).
                listing = (await client.get(f"{API}/master-admin/users", headers=h())).json()
                found = next((u for u in listing.get("users", []) if u.get("id") == body["id"]), None)
                record("C2 allowed_site_ids round-trip via /master-admin/users",
                       found and pinned["id"] in (found.get("allowed_site_ids") or []))

        # ── D1 — Operator can fetch their site's equipment list ──────────
        # Equipment Catalogue (master data) is intentionally master-admin
        # only. The customer-facing surface is /api/equipment which is
        # filtered by the operator's org+site. We assert the operator
        # can read it.
        if token_param and new_t:
            r = await client.get(f"{API}/equipment", headers=h(new_t))
            record("D1 New operator can fetch /equipment list",
                   r.status_code in (200, 204),
                   f"status={r.status_code}")

        # ── E1 — Marketing subscription change shows in /marketing/usage ─
        sub_r = await client.put(
            f"{API}/master-admin/marketing/subscriptions/{target_org['id']}",
            json={"plan_id": "starter", "status": "active"}, headers=h())
        record("E1 Master Admin can set a marketing subscription",
               sub_r.status_code in (200, 201),
               f"status={sub_r.status_code}")

        # ── F1 — Onboarded customer org wizard creates real org ─────────
        new_org_name = f"Audit Org {uuid.uuid4().hex[:6]}"
        owner_email = f"audit-owner-{uuid.uuid4().hex[:8]}@example.com"
        r = await client.post(f"{API}/master-admin/organizations",
                              json={"name": new_org_name,
                                    "primary_contact_email": owner_email,
                                    "primary_contact_name": "Audit Owner",
                                    "account_type": "lite", "brand": "gymaxis"}, headers=h())
        record("F1 Customer-onboarding org create endpoint",
               r.status_code in (200, 201),
               f"status={r.status_code}")
        if r.status_code in (200, 201):
            org_payload = r.json()
            owner_invite = (org_payload.get("owner") or {}).get("invite_url") or org_payload.get("invite_url")
            record("F1b Owner invite link generated",
                   bool(owner_invite),
                   f"invite={'yes' if owner_invite else 'no'}")

        # ── G1 — Stripe Connect status reachable from owner ────────────
        # Skipping a full Stripe flow — just verify the platform endpoint
        # returns 200 for Master Admin.
        r = await client.get(f"{API}/master-admin/integrations-hub", headers=h())
        record("G1 Integrations Hub aggregate endpoint", r.status_code == 200,
               f"summary={r.json().get('summary')}")

        # ── H1 — Duplicate user 409 carries structured payload ─────────
        r = await client.post(f"{API}/master-admin/organizations/{target_org['id']}/users",
                              json={"email": "admin@gymaxisai.com", "full_name": "Dup Test", "role": "staff"},
                              headers=h())
        detail = r.json().get("detail", {})
        record("H1 Duplicate-email 409 is structured",
               r.status_code == 409 and isinstance(detail, dict) and detail.get("code") == "user_exists" and detail.get("user_id"),
               f"status={r.status_code} code={detail.get('code') if isinstance(detail, dict) else 'flat'}")

    # ── Summary ───────────────────────────────────────────────────────
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print()
    print("=" * 70)
    print(f"AUDIT SUMMARY: {passed}/{total} checks passed")
    print("=" * 70)
    failures = [r for r in results if not r["passed"]]
    if failures:
        print()
        print("BROKEN LINKS:")
        for f in failures:
            print(f"  ❌ {f['check']}  — {f['detail']}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
