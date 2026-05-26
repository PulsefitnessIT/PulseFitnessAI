# GymAxis — Full-stack workforce operations platform for fitness

A React + FastAPI + MongoDB platform that runs the back-office of a
modern fitness business: CRM, memberships, service operations,
partner engineers, marketing automation, and master-admin governance.

**Production**: [gymaxisai.com](https://gymaxisai.com)
**Preview / dev**: see `frontend/.env::REACT_APP_BACKEND_URL`

---

## Repo map

```
backend/                  FastAPI + Motor (async Mongo) + Stripe Connect
  routes/                 Modular routers — one file per domain
  utils/                  Cross-cutting helpers (email, auth, attention, …)
  route_registry/         Single source of truth for which routers are mounted
  tests/                  Pytest — `test_iter_*.py` per shipped feature
frontend/                 React 18 + Vite-style CRA + Tailwind + Shadcn UI
  src/pages/              Domain-grouped (CRM, ServiceOps, PartnerEngineer, …)
  src/components/ui/      Shadcn primitives
marketing/                ★ Marketing campaigns (root, NOT inside backend/)
  partner_engineer_launch/  ★ Iter 220m — 32 Instagram tiles (current launch)
  instagram_campaign/       Gym-operator "9 Reasons" mosaic (earlier)
  sicon-access/             Sicon partner access request hand-off PDF
  mod-presentation/         MOD briefing deck
memory/                   ★ The source-of-truth product docs (READ FIRST)
  PRD.md                  Full session-by-session changelog
  ROADMAP.md              Prioritised backlog (P0 → P3)
  STATE.md                Current platform state — modules, routes, owners
  PRODUCTION_READINESS.md Quality-gate dashboard
  KNOWN_BUGS.md           Mocked integrations + recurring footguns
  SICON_INTEGRATION_SPEC.md, INTEGRATION_FIELD_MAPPING.md, …
docs/                     Public-facing integration proofs + hand-off packs
scripts/                  Codemod helpers + uptime monitor
Makefile                  `make regression`, `make lint-*`, `make ci-mirror`
```

---

## Quick start

```bash
# Backend (auto-managed by supervisor on the preview env)
sudo supervisorctl status backend frontend

# Tests
make regression                # full iter-220 suite — 103 passed, 3 skipped
make lint-frontend             # eslint --max-warnings 0
make lint-backend              # ruff
```

All env vars come from `backend/.env` and `frontend/.env`. **Never** commit
defaults — missing config should fail fast.

---

## Recent highlights (May 2026)

| Iter | What |
|---|---|
| 220i | Engineer branding on PDFs · per-machine custom fields · interactive Upcoming list · fixed broken email logo |
| 220j | Pulsing attention badge — single endpoint aggregates compliance + subscription + Stripe Connect signals |
| 220k | Release-blocking P0s sealed — compliance-to-claim gate + mid-job cancellation recovery |
| 220l | Pre-launch polish — VAT-exempt toggle · My Ratings view · "Request engineer again" · job grant max-age |
| 220m | Monthly Reputation Report email — auto-fires on the 1st · LinkedIn-share CTA · idempotent loop |
| 220m | Marketing campaign assets — 32 Instagram tiles + 8 stories + 5 highlight covers rendered via Playwright |

Full detail in `/memory/PRD.md`.

---

## Marketing campaign assets

The Partner Engineer launch ships with a fully-rendered Instagram
campaign in `marketing/partner_engineer_launch/`:

```
marketing/partner_engineer_launch/
├── README.md            Brand system + how to regenerate
├── CAPTIONS.md          4-week schedule + ready-to-paste copy
├── generate.py          Playwright renderer (re-run any time)
└── instagram/
    ├── feed/        (19 × 1080×1080)
    ├── stories/     (8  × 1080×1920)
    └── highlights/  (5  × 1080×1080)
```

Regenerate any tile after a copy tweak:

```bash
cd /app && python3 marketing/partner_engineer_launch/generate.py
```

Earlier campaigns live alongside it:

* `marketing/instagram_campaign/` — gym-operator "9 Reasons" mosaic.
* `marketing/sicon-access/` — Sicon partner hand-off PDF.
* `marketing/mod-presentation/` — MOD briefing deck.

---

## Quality gates

- ESLint: **0 warnings budget** (`--max-warnings 0`).
- Ruff / Bandit / Xenon: clean, versions pinned.
- `make regression`: 103 passed, 3 skipped (iter-220 suite).
- All new tests added to `Makefile::regression` (TAB-indented).
- Don't commit emojis to source unless asked.
- All new `POST` endpoints must mirror their `PATCH` validation.

---

## Pending integrations (blocked on credentials)

- **Sicon Service** — CAPEX / parts / labour live sync. Spec + admin
  field-mapping UI shipped. Waiting on Pulse IT credentials. See
  `memory/SICON_INTEGRATION_SPEC.md`.
- **Microsoft Graph (Outlook)** — calendar push + ICS fallback.
  Awaiting `MS_CLIENT_ID` + `MS_CLIENT_SECRET`.
- **DocuSign** — e-signature on CRM quote PDFs. Awaiting credentials.
- **Sage 200** — ledger posting on payment + CRM lead conversion (P2).
- **Twilio SMS** — real delivery (currently MOCKED).

---

## License & contact

Proprietary · GymAxis Ltd · support@gymaxisai.com
