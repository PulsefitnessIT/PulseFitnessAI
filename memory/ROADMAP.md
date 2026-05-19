# GymAxis · Engineering ROADMAP

Prioritised backlog (P0 = active, P1 = next, P2 = scheduled, P3 = nice-to-have).
Update as items move; archive completed work in /app/memory/PRD.md.

---

## P0 — In progress

- _none — Inline-hex sweep + Phase 3 CRM polish landed in iter 216h226._

## P1 — Quality-Gate warning cleanup (continuation)

ESLint baseline after iter 216h226-polish: **0 errors / 547 warnings** (budget 600).
Tighten the `--max-warnings` ceiling by ~100 with each cleanup PR.

- **Unused-vars sweep** — 164 `unused-imports/no-unused-vars` warnings.
  These are runtime variables (state, destructured fields, function args)
  that are no longer referenced. File-by-file fix; mostly safe to delete.
- **Light-mode leakage sweep** — 297 `gymaxis/no-dark-mode-leakage`
  warnings. Add `dark:` Tailwind variants or swap to
  `style={{ background: 'var(--theme-surface)' }}`. Restore the rule to
  `error` once cleared.
- **react-hooks/exhaustive-deps** — 86 warnings. Each needs a real
  review (missing dep vs intentional capture). Don't auto-disable.

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
- Reports tab: per-user remembered date range via `localStorage`.
