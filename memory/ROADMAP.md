# GymAxis · Engineering ROADMAP

Prioritised backlog (P0 = active, P1 = next, P2 = scheduled, P3 = nice-to-have).
Update as items move; archive completed work in /app/memory/PRD.md.

---

## P0 — In progress

- _none — Phase 3 CRM polish landed in iter 216h226._

## P1 — Quality-Gate cleanup (Iter 216h226-tech-debt)

> Quality Gate was re-greened by temporarily downgrading the
> `gymaxis/no-inline-hex` and `gymaxis/no-dark-mode-leakage` ESLint
> rules from `error` → `warn`. Restore to `error` once each sweep is
> complete.

- **Inline-hex sweep** — replace ~560 raw `#xxxxxx` literals with
  `var(--color-…)` or `/theme/tokens.js` imports.
  - 65 errors in `src/pages/MasterAdmin/**`
  - 60 errors in `src/components/shared/**`
  - 52 errors in `src/pages/Marketing/**`
  - 38 errors in `src/pages/Memberships/**`
  - 26 errors in `src/pages/CRM/**`
  - Trigger: re-enable `"gymaxis/no-inline-hex": "error"` in `eslint.config.js`.

- **Light-mode leakage sweep** — ~297 `bg-white` / `text-slate-900`
  classes outside `dark:` variants. Add the `dark:` variants or swap to
  `style={{ background: 'var(--theme-surface)' }}`. Trigger: re-enable
  `"gymaxis/no-dark-mode-leakage": "error"`.

- **ESLint warning budget** — currently `--max-warnings 8500`. Tighten
  by 500/week as the two sweeps land until the budget reaches 0.

## P1 — Outstanding integrations

- **Sicon** — replacement CAPEX / parts / labour. Waiting on user live credentials.
- **CRM Quote DocuSign** — e-signature on the CPQ PDFs. Waiting on credentials.

## P2

- **Sage 200** — ledger posting on payment + CRM lead conversion.
- **Twilio SMS** — real integration (currently MOCKED).

## P3

- **Right-to-erasure workflow** for personnel records.
- Schedulable AI digests — weekly Reports envelope to managers' inbox.
- Territory tree: server-side bulk re-parent endpoint.
