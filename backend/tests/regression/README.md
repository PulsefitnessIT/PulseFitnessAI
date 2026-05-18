# Backend Regression Suite

Every iteration's test files live in `/app/backend/tests/`. This directory
provides a **curated, ordered "core flows" suite** that must remain green
before any deployment or major feature rollout.

## Running

```bash
# Full regression sweep (every iteration test, fast subset only)
cd /app/backend && pytest tests/ -q --ignore=tests/regression

# Critical-path only (this directory)
cd /app/backend && pytest tests/regression -q
```

## What lives here

These suites are *symlinked or imported* from per-iteration test files so
we have a single entry point per critical journey. They are:

- `test_critical_auth.py` — login, refresh, MFA, cross-login (CRM/Memberships/Service Desk)
- `test_critical_operations.py` — log fault (single + batch), site_id inheritance, multi-machine job
- `test_critical_memberships.py` — plans CRUD, credit packs, member create+edit+GDPR, instructor create+edit+GDPR, class template create
- `test_critical_service_desk.py` — case create, mirror from issue, engineer assignment, quote-accept, invoice
- `test_critical_mod.py` — MOD tier LITE+PRO login, scope filter, fault from kiosk
- `test_critical_crm.py` — contract create, asset link, coverage resolve (Operations + Service Desk)

Each suite is a thin wrapper that imports the relevant per-iter test
functions. Adding tests to a per-iter file → automatically picked up if
the suite already imports it.

## Adding to the suite

When you ship a new critical feature:
1. Write the iteration test in `tests/test_iter_NNN_foo.py` (as today).
2. Import the test functions into the matching critical-suite file.
3. Run `pytest tests/regression -q` and ensure green.

## CI / Pre-deployment gate

This directory is what the `deployment_agent` (and any pre-deploy hook)
should run. Any failure = deployment blocked.
