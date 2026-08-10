# Mobile UI Regression Suite (Playwright)

Catches mobile-layout regressions before they reach production. Each spec
opens a list of pages at iPhone-13-Pro viewport and asserts that:

1. The document doesn't scroll horizontally.
2. No `[data-testid]` element extends beyond the viewport (with a 6px
   tolerance for sub-pixel rounding) — except elements inside an
   `overflow-x: auto` container (those are intentional swipe-tables) and
   decorative `gx-orbit-*` marketing animations.
3. A critical test-id on each page is present (logged as a warning if
   missing — not a hard fail, since some testids are role-gated).
4. **Navigation parity** — every action available in the desktop
   user-menu is also reachable from the mobile hamburger menu
   (iter 216h236, `nav-parity.spec.js`). Catches the class of bug
   Lee found in iter 216h235 where Help & Tutorials had been
   silently dropped from the mobile menu.

## Pages covered

See `MOBILE_PAGES` in `master-admin.spec.js`. Currently:

- Master Admin · Overview, Organizations, Users
- GymAxis Operations · Dashboard, Faults, Suppliers, Reports, Documents
- Pulse Fitness · Operations Dashboard

Add a new page by appending `{ path, testid, name }` to the array.

`nav-parity.spec.js` separately covers:
- `/dashboard?as=operator` and `/pulse-dashboard`. Add more by
  appending to `NAV_PARITY_PAGES`. Adjust the action set under test
  via the `PARITY_PAIRS` array — each entry maps a desktop testid
  to its mobile counterpart.

## Running locally

```bash
cd /app/frontend

# One-time: install the browser binaries (Chromium ~290MB)
PLAYWRIGHT_BROWSERS_PATH=/pw-browsers \
  npx playwright install chromium

# Run the suite against the preview environment
PLAYWRIGHT_BROWSERS_PATH=/pw-browsers \
E2E_BASE_URL="https://multi-eng-booking.preview.emergentagent.com" \
  yarn test:mobile-regression
```

Default credentials are read from env vars (fall back to the master admin):

- `E2E_ADMIN_EMAIL`    (default: `admin@gymaxisai.com`)
- `E2E_ADMIN_PASSWORD` (default: `MasterAdmin123!`)
- `E2E_BASE_URL`       (default: `process.env.REACT_APP_BACKEND_URL` or `http://localhost:3000`)

## How auth works

`global-setup.js` logs in **once** as the master admin, dismisses the
cookie banner, and writes the resulting browser storage state to
`.playwright/state.json`. Every test reuses that state via `storageState`
in `playwright.config.js`. This avoids hammering the rate-limited login
endpoint with 9× concurrent logins per run.

## Reports

- **stdout** — concise list reporter (default).
- **JSON** — `/app/test_reports/mobile-regression-latest.json` (parity
  with `iteration_*.json` pattern). Stats include `expected`,
  `unexpected`, `flaky`, and `duration`.
- **Failure artifacts** — `frontend/test-results/<test>/` contains
  screenshot, video, and trace zip on retry. View a trace with:

  ```bash
  cd /app/frontend && yarn playwright show-trace test-results/<…>/trace.zip
  ```

## CI integration

Add this step to your CI pipeline after a successful frontend deploy to
the preview environment:

```yaml
- name: Mobile UI regression
  run: |
    cd frontend
    npx playwright install chromium
    yarn test:mobile-regression
  env:
    E2E_BASE_URL: ${{ env.PREVIEW_URL }}
    E2E_ADMIN_EMAIL: ${{ secrets.E2E_ADMIN_EMAIL }}
    E2E_ADMIN_PASSWORD: ${{ secrets.E2E_ADMIN_PASSWORD }}
```

The suite returns exit code `1` on any failure so CI fails the build
automatically.
