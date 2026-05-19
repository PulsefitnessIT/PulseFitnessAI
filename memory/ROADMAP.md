# GymAxis · Engineering ROADMAP

Prioritised backlog (P0 = active, P1 = next, P2 = scheduled, P3 = nice-to-have).
Update as items move; archive completed work in /app/memory/PRD.md.

---

## P0 — In progress

- _none — Phase 3 CRM polish + all three lint sweeps landed._

## P1 — Quality-Gate warning cleanup (final stretch)

ESLint baseline after iter 216h226-polish-4: **0 errors / 86 warnings**
(budget 200). One sweep remains.

- **react-hooks/exhaustive-deps** — 86 warnings. Each needs a real
  review (genuine missing-dep bug vs intentional capture for
  one-shot effects / closures over stable refs). Don't auto-disable.
  Should drop budget 200 → 0.

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
- `eslint-plugin-import/order` — auto-fixable import grouping.
