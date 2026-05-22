# Required CI checks — branch protection setup

> **Owner**: Repo admin (anyone with `Settings → Branches` access).
> **Time**: ~5 minutes.
> **Iter**: 216h295 — closes the last gap from h291–h294 lint &
> CI tightening. Without flipping these toggles, a maintainer can
> still merge a red PR and undo every hardening pass.

## Why this matters

Through iters 216h289 → 216h294 we tightened the local + CI
pipeline:

| Layer | What it enforces |
|---|---|
| `.githooks/pre-commit` (h291) | Strict ESLint on staged JS/JSX |
| `make lint` (h289 + h292) | Strict ruff + ESLint, no `\|\| true` |
| GitHub Actions on `pull_request` (h293) | All of the above + tests |
| `make pre-deploy` (h294) | Hard-depends on `make lint` |

**But** GitHub Actions running and **going red** isn't enough on
its own — without "Required" branch protection a maintainer can
hit "Merge anyway" and ship the regression. This guide flips the
toggles that make merging mechanically impossible while a check
is red.

---

## Step-by-step

1. Open the repo in GitHub.
2. **Settings → Branches → Branch protection rules**.
3. Edit the rule for `main` (create one if it doesn't exist).
4. Tick **Require status checks to pass before merging**.
5. Tick **Require branches to be up to date before merging**.
6. In the **Status checks that are required** search box, paste
   each name below in turn and click "Add" on the suggestion that
   appears:

   ### From `.github/workflows/ci.yml`
   - `pre-commit gates (ruff · bandit · eslint · complexity)`
   - `Backend regression suite (make regression)`

   ### From `.github/workflows/quality-gate.yml`
   - `Python — ruff + bandit + pytest`
   - `Secret scan (gitleaks)`
   - `Frontend — eslint + yarn build`
   - `pip-audit`

   > GitHub only surfaces a check name in the dropdown after it has
   > run on at least one PR or push. If a check isn't appearing,
   > push a no-op commit to a PR first, wait for the workflow to
   > start, then come back and search again.

7. (Recommended) Tick **Require pull request reviews before
   merging** with at least 1 approver. Belt-and-braces — a green
   CI on a self-merged PR by a single dev is still risky.
8. (Recommended) Tick **Do not allow bypassing the above settings**
   so even repo admins can't merge red.
9. Tick **Require linear history** if your team prefers
   rebase-merging. Optional.
10. Click **Save changes**.

Repeat for `develop` if you protect that branch too.

---

## Verifying it worked

1. Open the most recent merged PR.
2. Scroll to the bottom — you should see a green "All required
   status checks have passed" panel listing the six checks above.
3. Open a fresh test PR with a deliberate ESLint warning
   (`bg-white` without a `dark:` variant works — that's the
   `gymaxis/no-dark-mode-leakage` rule). The "Merge" button
   should now be greyed out with "Required statuses must pass".

---

## What to do when a check legitimately can't pass

- **`pip-audit`** is configured `continue-on-error: true` on PRs
  but blocks on `main` pushes. New CVEs land randomly — accept
  this as informational and patch the dependency in a follow-up.
- **`gitleaks`** false-positives on test fixtures should be added
  to `.gitleaksignore`, not bypassed.
- **`Backend regression suite`** failures are never a CI flake —
  they mean a previously-fixed bug has regressed. Do not retry
  the run; reproduce locally with `make regression`.
- For a real emergency hotfix, a repo admin can temporarily
  uncheck a single status, merge, and re-check it within the
  same minute. Document the bypass in the PR description.

---

## Related docs

- **`docs/PRE_COMMIT.md`** — local pre-commit hook configuration
- **`Makefile`** — `make help` lists every gate target
- **`.github/workflows/ci.yml`** — fast pre-commit gates
- **`.github/workflows/quality-gate.yml`** — heavier mongo:7 +
  build smoke + dependency CVE scan
