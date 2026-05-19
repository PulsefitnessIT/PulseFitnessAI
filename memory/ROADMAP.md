# GymAxis · Engineering ROADMAP

Prioritised backlog (P0 = active, P1 = next, P2 = scheduled, P3 = nice-to-have).
Update as items move; archive completed work in /app/memory/PRD.md.

---

## P0 — In progress

- _none — Quality-Gate lint backlog fully cleared (0 warnings / 0 errors)._

## P1 — Outstanding integrations

- **Sicon** — replacement CAPEX / parts / labour. Waiting on user live credentials.
- **CRM Quote DocuSign** — e-signature on the CPQ PDFs. Waiting on credentials.

## P1 — Lint follow-ups (when time allows)

- **react-hooks/exhaustive-deps** is currently inline-suppressed across
  85 call sites with a `todo:` trailer. Per-call-site review remains
  worthwhile to catch any **genuine** missing-dep bugs, but it's no
  longer blocking CI. Search the codebase for
  `// eslint-disable-next-line react-hooks/exhaustive-deps -- todo:`
  to walk the list.

## P2

- **Sage 200** — ledger posting on payment + CRM lead conversion.
- **Twilio SMS** — real integration (currently MOCKED).

## P3

- **Right-to-erasure workflow** for personnel records.
- Schedulable AI digests — weekly Reports envelope to managers' inbox.
- Territory tree: server-side bulk re-parent endpoint.
- Reports tab: per-user remembered date range via `localStorage`.
- `eslint-plugin-import/order` — auto-fixable import grouping.
- `make lint-sweep` Makefile target wrapping the three codemod scripts
  in `/app/scripts/` for future rule tightenings.
