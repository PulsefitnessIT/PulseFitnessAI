# Backend Regression Suite

> **The single command before shipping**: `pytest backend/tests/regression -q`
>
> 84 tests · ~2 min runtime · 100% green.

This is the **pre-deployment gate**. Every test in this directory is
isolated (no live uvicorn, no admin tokens, no DB seeding needed) so it
runs anywhere — local laptop, CI, the deployment pipeline.

## Running

```bash
# Full critical-path sweep (recommended before any deployment).
cd /app/backend && pytest tests/regression -q

# Per-module:
pytest tests/regression/test_critical_auth.py -q
pytest tests/regression/test_critical_memberships.py -q
pytest tests/regression/test_critical_operations.py -q
pytest tests/regression/test_critical_service_desk.py -q
pytest tests/regression/test_critical_mod.py -q
pytest tests/regression/test_critical_crm.py -q
```

## Coverage (current)

| Module       | Suite                             | Tests | What it protects |
|--------------|-----------------------------------|-------|------------------|
| Auth         | `test_critical_auth.py`           | 6     | h210 — login-failure reason classification, audit-trail shape, login-events + client-errors diagnostics endpoints, master-admin gating |
| Memberships  | `test_critical_memberships.py`    | 15    | h201/h207 — instructor create/edit email+phone+GDPR validation, member edit drawer parity, consent audit stamping |
| Operations   | `test_critical_operations.py`     | 4     | h208 — issues inherit site_id from equipment, coverage resolver surfaces equipment_site_id |
| Service Desk | `test_critical_service_desk.py`   | 20    | h199 — issue→svc_case mirror routes Contract/Warranty/Chargeable correctly. h133 — engineer mileage log, parts consume, invoice draft generation |
| MOD          | `test_critical_mod.py`            | 19    | h113f/h117/h120 — portal isolation (MOD↔/MODService, non-MOD↔/pulse), HQ rollup contract (equipment/issues/capex/health), drilldown 403 boundary, bulk-import contract |
| CRM          | `test_critical_crm.py`            | 20    | h195/h197/h198 — coverage resolver (warranty + contract), portal pills entitlement, CRM ↔ platform cross-credential auth fallback, tags aggregation |
| **TOTAL**    |                                   | **84**| |

## What lives elsewhere (intentionally)

These two test classes need a running uvicorn + master-admin token, so
they stay out of the regression directory:

- `test_iter_216h152_svc_crm_sync.py` (admin_sess fixture)
- `test_service_desk_create_iteration199.py` (admin_headers fixture)
- `test_crm_contracts.py`, `test_crm_team_management.py` (live-server)
- `test_mod_portal.py` (mod_user_token / admin_token live-server)

Run those via `pytest tests/ -q` against a started backend if you need
the wider net.

## Adding to the suite

When you ship a new critical feature:
1. Write the per-iter test in `tests/test_iter_NNN_foo.py` as today.
2. Make sure it's an **isolated unit test** (no `admin_sess`,
   `master_admin_token_session`, or `crm_sess` fixtures).
3. `from tests.test_iter_NNN_foo import test_xxx` in the matching
   `test_critical_*.py`.
4. Run `pytest tests/regression -q` and confirm green.

## CI / Pre-deployment gate

The `deployment_agent` (and any pre-deploy hook) should run this
directory. Any failure = deployment blocked.
