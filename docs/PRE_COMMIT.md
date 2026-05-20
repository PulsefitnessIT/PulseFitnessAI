> **📋 Status — Iter 216h232 update (Feb 19, 2026)**
>
> The hooks below remain accurate but the **CI workflow** that enforces
> them has been hardened. Three bugs were fixed Feb 19 that had been
> silently failing CI on every push since the workflow first landed:
>
> 1. **`bandit --exit-zero-on-skipped`** — flag never existed in
>    bandit's CLI; bandit aborted immediately on every CI run.
>    Removed.
> 2. **Secret-detection regex matched test fixtures** —
>    `backend/tests/test_stripe_prices_guard_216o.py` and
>    `test_secrets_audit_215ae.py` legitimately reference `sk_live_…`
>    and `sk_test_…` as string literals the code guards against.
>    Added `--exclude-dir=tests` to the grep.
> 3. **Pytest couldn't import `tests.shared_loop`** — conftest uses
>    `from tests.shared_loop import …` which works locally with
>    `python -m pytest` (adds CWD to sys.path) but breaks with bare
>    `pytest` as used in CI. Added `[tool.pytest.ini_options]
>    pythonpath = ["."]` to `backend/pyproject.toml`.
>
> Additionally, tool versions are now pinned in both `ci.yml` and
> `quality-gate.yml` (`ruff==0.15.10`, `bandit==1.9.4`, `xenon==0.9.3`,
> `radon==6.0.1`, `pre-commit==4.0.1`) to prevent the tool-version-drift
> failures we hit through Feb 19.
>
> The Quality Gate's `python-quality` job now also runs a `mongo:7`
> sidecar so the regression suite has a working DB to connect to.

---


# Pre-commit Hooks

This repo ships with a `.pre-commit-config.yaml` that catches the same issues
as the automated code-review bots **before** you push a commit.

## One-time setup

```bash
pip install pre-commit radon xenon
pre-commit install
```

That's it — every `git commit` will now run:

| Hook | What it catches |
|------|-----------------|
| `ruff` | Undefined vars (F821), unused locals (F841), `== True`/`== False` anti-patterns (E712), mutable default args (B006), and other bugbears |
| `eslint` | Syntax errors, unused imports, bad JSX patterns |
| `complexity-gate-staged` | Any **staged** Python function with cyclomatic complexity > 10 (radon rank C or worse). Existing legacy files are grandfathered — only blocks when *you touch them* |
| `complexity-gate-repo-safety-net` | Catastrophic regression gate: blocks if any function crosses rank F (cc > 40), any module average drops below B, or repo-wide average drops below B |
| `check-added-large-files` | Accidental commits > 500 KB |
| `detect-private-key` | Leaked SSH/TLS keys |
| `check-yaml` / `check-json` | Malformed config files |
| `trailing-whitespace` / `end-of-file-fixer` | Cosmetic drift |

## Complexity gates explained

**Strict gate (`complexity-gate-staged`)** — runs `scripts/check_complexity.sh`,
which inspects only files you've actually staged. New code must be rank B or
better (cc ≤ 10). If you edit an old high-complexity file, you own bringing it
under the threshold before commit. This is intentional — it prevents the
"tragedy of the commons" where complexity creeps up forever.

**Lenient gate (`complexity-gate-repo-safety-net`)** — runs `xenon` across the
whole backend. Current thresholds (tightened Apr 19 2026 after the first batch
of known-debt refactors):

- `--max-absolute D` → nothing can have cc > 20 (rank E / F / G blocked)
- `--max-modules C` → per-module average must stay below rank C
- `--max-average B` → repo-wide average must stay at rank B or better

These thresholds ratchet upward as more code gets refactored. Next milestone
(when remaining C-rank functions drop below 10): tighten `--max-absolute` from
D → C.

## Current known-debt functions (>10 cc)

As of Apr 19, 2026 (post-refactor batch 3), **all D and E-rank functions have
been cleared**. The remaining known debt is all at rank C (cc 11–17):

| Rank | Function | File |
|------|----------|------|
| C (17) | `_prefill_from_crm` | `routes/onboarding_packets.py:59` |
| C (17) | `_provision_plan_summary` | `routes/onboarding_packets.py:826` |
| C (15) | `_build_org_leaderboard` | `routes/admin_analytics.py:81` |
| C (14) | `list_global_documents` | `routes/admin_documents.py:98` |
| C (14) | `_calc_ppm_compliance` | `routes/kpi_engine.py:58` |
| C (13) | `analytics_equipment` | `routes/admin_analytics.py:227` |
| C (13) | `_validate_staff_block` | `routes/onboarding_packets.py:441` |
| C (12) | `get_lifecycle_alerts` | `routes/equipment.py:250` |
| C (12) | `analytics_faults` | `routes/admin_analytics.py:332` |
| C (12) | `add_supplier_comment` | `routes/supplier_portal.py:387` |
| …     | (plus ~15 other C-rank, cc 11–12)     | |

Run `radon cc -s -n C backend/routes backend/utils` for the current full list.

## Run against the whole repo right now

```bash
pre-commit run --all-files           # runs ruff + eslint + config checks
./scripts/check_complexity.sh        # runs the staged-files complexity gate
```

## Bypass (emergencies only)

```bash
git commit --no-verify -m "…"
```

## Update hook versions

```bash
pre-commit autoupdate
```

## Security hooks (added iteration 152)

Two new SAST/secret-scanner hooks have been added to catch the exact class
of issues the external code-review tool flagged (most of which were false
positives). These run on every `git commit` and are **fast** (<5 s).

### Bandit — Python SAST

Scans `backend/routes`, `backend/utils`, `backend/models`, `backend/scripts`
for real security issues:

- `eval()` / `exec()` calls
- `pickle.loads` on untrusted data
- `subprocess(..., shell=True)`
- hard-coded passwords / API keys
- weak crypto (`md5`, `sha1`)
- insecure SSL / TLS contexts

Severity gate: **Medium and above block the commit**. LOW findings are
informational (shown but do not fail the hook).

Tests are excluded — they legitimately use fixture data the scanner
would otherwise misread as secrets.

### Gitleaks — secret scanner

Intercepts accidental commits of:

- AWS / GCP / Azure access keys
- Stripe `sk_live_…` / `rk_live_…` keys
- OpenAI `sk-…` keys
- Resend `re_…` keys
- Turnstile / hCaptcha secrets
- SSH private keys
- JWT signing secrets
- Generic high-entropy strings

If you hit a false positive on a legitimate test vector, add a
`.gitleaksignore` entry or annotate the line with `# gitleaks:allow`.

### Why these were added

The Feb 2026 external code review flagged "eval() in test_csp_headers.py"
and "hard-coded secrets in 3 test files". Both were false positives — but
in future we want those findings caught **before** they reach the
reviewer, not during a review cycle. The cost of running both hooks is
negligible (<5 s combined) compared to the signal they provide.

