# 📚 GymAxisAI — Documentation Index

The single place to find every document in this project. Most docs live in this
`/docs` folder. A few must stay where they are because **code, tests, CI or the
platform read them at their current path** — those are listed below with their
real location so you can still find them from here.

*Last tidied: June 2026.*

---

## 🗂 In this `/docs` folder

### Commercial & Sales
| Document | What it is |
|---|---|
| [COST_TO_BUILD.md](COST_TO_BUILD.md) | Build / replacement cost of the platform (what an agency would charge to recreate it) |
| [PARTNERSHIP_PROPOSAL.md](PARTNERSHIP_PROPOSAL.md) | GymAxisAI × Pulse Fitness self-service portal partnership proposal |
| [RESPONSE_TO_CRAIG_PULSE_FITNESS.md](RESPONSE_TO_CRAIG_PULSE_FITNESS.md) ([PDF](RESPONSE_TO_CRAIG_PULSE_FITNESS.pdf)) | Formal response letter to the Pulse Fitness MD |
| [SECURITY_BRIEFING_PULSE_FITNESS.md](SECURITY_BRIEFING_PULSE_FITNESS.md) ([PDF](SECURITY_BRIEFING_PULSE_FITNESS.pdf)) | Customer-facing security briefing |

### Product modules
| Document | What it is |
|---|---|
| [GYMAXIS_MEMBERSHIPS.md](GYMAXIS_MEMBERSHIPS.md) | Memberships module reference (members, classes, plans) |
| [MOD_SERVICE_PORTAL.md](MOD_SERVICE_PORTAL.md) | Ministry of Defence service portal documentation |
| [TRUST_AND_SUPPORT_ENGINE.md](TRUST_AND_SUPPORT_ENGINE.md) | Trust & in-app support engine design |
| [SEO_P0_ACTIVATION.md](SEO_P0_ACTIVATION.md) | SEO activation plan |

### Integrations
| Document | What it is |
|---|---|
| [STRIPE_INTEGRATION_GUIDE.md](STRIPE_INTEGRATION_GUIDE.md) | Stripe payments integration guide |
| [SICON_INTEGRATION_PROOF.md](SICON_INTEGRATION_PROOF.md) | Sicon / Sage ledger integration proof |
| [sicon/pulse_swagger_v1.json](sicon/pulse_swagger_v1.json) | Pulse/Sicon API OpenAPI (Swagger) spec |

### Engineering & Ops
| Document | What it is |
|---|---|
| [CDN_INFRA.md](CDN_INFRA.md) | CDN / asset hosting infrastructure |
| [CI_REQUIRED_CHECKS.md](CI_REQUIRED_CHECKS.md) | Required CI checks for merges |
| [PRE_COMMIT.md](PRE_COMMIT.md) | Pre-commit hook setup |

### Archive
| Document | What it is |
|---|---|
| [archive/AUDIT_PORTAL_LINKS.md](archive/AUDIT_PORTAL_LINKS.md) | Point-in-time portal-linkage audit (Feb 2026) — kept for record |

---

## 📌 Canonical files that stay at the repo root
These are read by tests, the brand tooling, CI or the live app, so they cannot move.

| File | Why it stays at root |
|---|---|
| `/README.md` | Repo readme (GitHub convention) |
| `/SECURITY.md` | Served by the live app (`/security` page + `security_document` route) |
| `/DESIGN_SYSTEM.md` | Read by brand canon tests |
| `/BRAND_PALETTE.md` | Read by `scripts/build_brand_preview.py`, tests & the CI quality gate |
| `/PULSE_BRAND_PALETTE.md` | Read by brand tooling, tests & CI |
| `/test_result.md` | Test-run log used by the automated testing workflow |

---

## 🧠 Working memory — `/app/memory/`
Internal product/architecture/ops working docs maintained alongside development.
**Do not move** (platform tooling reads them), but they're browsable. Highlights:

- **Product & roadmap:** `PRD.md`, `ROADMAP.md`, `CHANGELOG.md`, `STATE.md`, `PLATFORM_DOCUMENTATION.md`, `PRODUCTION_READINESS.md`, `PRE_LAUNCH_CHECKLIST.md`
- **Architecture:** `CRM_ARCHITECTURE.md`, `CRM_INTEGRATION_ARCHITECTURE.md`, `SERVICE_OPS_ARCHITECTURE.md`, `MARKETING_SUITE_PRD.md`, `SVC_FIELD_MAPPING.md`, `INTEGRATION_FIELD_MAPPING.md`, `SICON_INTEGRATION_SPEC.md`, `SUPPLIER_INTEGRATION_GUIDE.md`
- **Cost (running):** `COST_BREAKDOWN.md` — monthly hosting/email/AI/Stripe costs
- **Ops runbooks:** `OPS_RUNBOOK.md`, `DOMAIN_CUTOVER_RUNBOOK.md`, `MASTER_ADMIN_RECOVERY.md`, `OPS/` (backup, email deliverability, incident response)
- **Security & legal:** `SECURITY_OPS.md`, `SECURITY_AUDIT_2026Q1.md`, `SECURITY_AUDIT/` (pen-test scope/findings/risk register), `LEGAL/` (Terms, Privacy, DPA, SLA, Sub-processors)
- **Quality:** `KNOWN_BUGS.md`, `CODE_REVIEW.md`, `PERF_AUDIT.md`, `UX_AND_PROCESS_BACKLOG.md`, `hubspot_parity_audit.md`

---

## 🧩 Code-adjacent READMEs (stay next to their code)
- `backend/SYSTEM_DEPS.md` · `backend/integrations/sicon/specs/README.md` · `backend/routes/svc/integrations/INTEGRATIONS_README.md` · `backend/tests/regression/README.md`
- `frontend/README.md` · `frontend/src/pages/Marketing/MARKETING_README.md` · `frontend/tests/mobile-regression/README.md`
- `ops/README.md` · `scripts/README.md`

---

## 📣 Marketing collateral & sales decks
- **Sales decks (source + output):** `/app/sales/` — `gymaxisai_operators.html`, `gymaxisai_engineers.html`, `render_pdf.py`. Output PDFs: `/app/frontend/public/downloads/GymAxisAI-Operators-Presentation.pdf` & `GymAxisAI-Suppliers-Presentation.pdf`
- **Public downloads:** `/app/frontend/public/downloads/` — `gymaxis-executive-review.(md/pdf)`, `security-audit-remediation.md`
- **Campaign assets:** `/app/marketing/` — `instagram_campaign/`, `partner_engineer_launch/`, `mod-presentation/`

---

### Convention for new docs
Put new project documentation in `/docs` (use a sub-folder or `archive/` where it
helps) and add a row to the relevant table above. Keep README files next to the
code they describe, and leave `/app/memory/` for live development working notes.
