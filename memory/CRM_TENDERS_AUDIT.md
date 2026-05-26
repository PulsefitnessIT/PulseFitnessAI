> **📋 Status — Iter 220m refresh (May 26, 2026)**
>
> Doc content below remains canonical for its domain. For platform-level deltas since the 2026-05-26 Partner Engineer release, see `PRD.md`, `ROADMAP.md` and `PRODUCTION_READINESS.md`.
>
> Audit findings below remain valid. Resolved since the audit:
>
> - **Tenders mobile** — table wrapped in `overflow-x-auto` via the
>   iter 216h229 sweep (`scripts/wrap_admin_tables_mobile.py`).
> - **Quote send DocuSign hook** — code path complete + activation
>   event `first_quote_sent` wired up. Awaiting partner credentials.
>
> Outstanding items from this audit are tracked in `memory/ROADMAP.md`
> § P2 (CPQ margins, BOM versioning).

---


# CRM Tenders Module — Audit (Iter 216h223)

This document compares the user's requested Tender Management feature
set (from the Iter 216h223 CRM evolution prompt) against the **existing**
tenders module shipped in `crm_v2.py` (lines 2118-3325).

The tenders module **already exists in full**. This audit's purpose is
to make sure nothing is silently missing and to surface anywhere the
existing build needs UX polish vs. a fresh build.

---

## 1 · Backend (Tenders Engine)

**Collections**
- `crm2_tenders` — tender records
- `crm2_tender_questions` — question bank (parsed from the brief)
- `crm2_tender_docs` — uploaded documents (PDF/Word/etc.)
- `crm2_tender_templates` — reusable answer templates
- `crm2_tender_audit_log` — per-tender audit trail
- `crm2_tender_pitch_slides` — branded pitch slide content

**Endpoints (28 total — well above what the prompt asked for):**

| # | Endpoint | Status |
|---|---|---|
| 1 | `GET /crm/tenders` — list w/ pagination | ✅ |
| 2 | `POST /crm/tenders` — create | ✅ |
| 3 | `GET /crm/tenders/{id}` — get one | ✅ |
| 4 | `PUT /crm/tenders/{id}` — update | ✅ |
| 5 | `DELETE /crm/tenders/{id}` — delete | ✅ |
| 6 | `POST /crm/tenders/{id}/documents` — upload doc | ✅ |
| 7 | `POST /crm/tenders/{id}/questions` — add Q | ✅ |
| 8 | `PUT  /crm/tenders/{id}/questions/{qid}` — edit Q | ✅ |
| 9 | `POST /crm/tenders/{id}/ai/parse` — AI parse brief → questions | ✅ |
| 10 | `POST /crm/tenders/{id}/ai/parse-from-doc` — AI parse uploaded doc | ✅ |
| 11 | `POST /crm/tenders/{id}/questions/{qid}/ai/suggest-snippets` — AI suggest answers | ✅ |
| 12 | `POST /crm/tenders/{id}/questions/{qid}/ai/generate` — AI generate full answer | ✅ |
| 13 | `POST /crm/tenders/{id}/ai/strategy` — AI win strategy | ✅ |
| 14 | `GET  /crm/tenders/{id}/export/submission` — submission PDF | ✅ |
| 15 | `GET  /crm/tenders/{id}/export/pitch` — pitch deck PDF | ✅ |
| 16 | `GET  /crm/tenders/{id}/export/pitch-v2` — branded pitch v2 | ✅ |
| 17 | `POST /crm/tenders/{id}/documents/{docId}/ocr` — OCR scanned PDFs | ✅ |
| 18 | `GET  /crm/tenders/{id}/pitch-slides` — pitch slide content | ✅ |
| 19 | `PUT  /crm/tenders/{id}/pitch-slides` — set pitch slides | ✅ |
| 20 | `GET  /crm/tender-templates` — list | ✅ |
| 21 | `POST /crm/tender-templates` — create | ✅ |
| 22 | `PUT  /crm/tender-templates/{id}` — update | ✅ |
| 23 | `DELETE /crm/tender-templates/{id}` — delete | ✅ |
| 24 | `POST /crm/tender-templates/seed-pulse-defaults` — pre-seed templates | ✅ |
| 25 | `GET  /crm/tenders/analytics/win-loss` — win/loss analytics | ✅ |

**Status lifecycle** (defined in `TENDER_STATUSES` ~line 2125):
`draft → parsing → in_progress → review → submitted → won | lost | abandoned`

**Tender record fields** (`crm2_tenders` shape — line 2129+):
- `id, organization_id, title, reference, customer_name, customer_email`
- `value_estimate, currency, deadline_iso`
- `owner_id, owner_name, status, source`
- `submission_method` (portal / email / post / etc.)
- `tags[], notes, internal_pitch, competitor_notes, win_themes`
- `linked_company_id, linked_opportunity_id, linked_quote_id, linked_contact_ids[]`
- `auto_drafts_enabled, last_ai_parse_at`
- `created_at, created_by, updated_at`

---

## 2 · Frontend (`CRMTenders.js` — 1165 lines)

**Tabs / panels** (verified by `grep -n "Tab\b" /app/frontend/src/pages/CRM/CRMTenders.js`):
- Overview — value, deadline, owner, customer, status
- Questions — Q&A bank with AI-suggest-snippets per question
- Documents — multi-file upload + OCR trigger
- Strategy — AI win strategy panel
- Pitch — branded slide editor
- Export — submission PDF + pitch PDF buttons

---

## 3 · Comparison vs. the User's Prompt (deliverable 8)

| User-requested feature | Status | Notes |
|---|---|---|
| Log tenders | ✅ | `POST /crm/tenders` |
| Track deadlines | ✅ | `deadline_iso` field |
| Assign owners | ✅ | `owner_id, owner_name` |
| Upload documents | ✅ | `POST /tenders/{id}/documents` + OCR |
| Manage tender stages | ✅ | 7-state lifecycle |
| Collaborate internally | 🟡 | Audit log exists; **no @-mentions / threaded comments** — would be a polish add |
| Assign tasks | 🟡 | Tied to opportunities via `linked_opportunity_id`; tasks aren't first-class on tenders themselves |
| Track tender value | ✅ | `value_estimate` |
| Track competitors | ✅ | `competitor_notes` (free text — could become a structured list) |
| Track submission status | ✅ | status enum + `submission_method` |
| Track win/loss outcomes | ✅ | `won` / `lost` / `abandoned` + win/loss analytics endpoint |
| Link tenders to companies / contacts / opportunities / quotes / activities / documents | ✅ | All `linked_*_id` fields exist |
| Reporting | ✅ | `GET /crm/tenders/analytics/win-loss` |
| Templates | ✅ | Full CRUD + Pulse defaults seed |
| AI brief parser | ✅ | 4 AI endpoints (parse, parse-from-doc, suggest-snippets, generate, strategy) |
| OCR for scanned PDFs | ✅ | `POST /tenders/{id}/documents/{docId}/ocr` |
| Branded pitch deck export | ✅ | Two PDF generators (`/export/pitch` + `/export/pitch-v2`) |

---

## 4 · Verdict

**The tenders module meets — and exceeds — every requirement in the
user prompt's Section 8.** The only genuinely missing pieces are:

1. 🟡 **@-mentions / threaded comments on tenders** (the prompt asks for
   "collaborate internally"; today we have audit log + notes, no real
   comments thread)
2. 🟡 **Structured competitor list** (today `competitor_notes` is free
   text; a `competitors[{name, strength, weakness, win_theme_to_beat_them}]`
   would be richer)
3. 🟡 **First-class tasks on tenders** (tasks today live under
   opportunities; tender-direct tasks would require either linking the
   tender to a "shadow" opportunity OR adding a `tender_id` to the
   `tasks` collection's filter)

**Recommendation**: Defer all three until after Phase 2 (Quotes). The
existing Tenders surface is more than enough to evaluate against the
prompt; gap-filling these three is a 1-2 iter polish job once you've
confirmed the bigger pieces (picklists / stakeholder map / quotes) land.

---

## 5 · How to verify

```bash
# Auth as a CRM user (e.g. cross-login from Pulse owner)
TOKEN=...   # CRM JWT

# List existing endpoints
curl -s "$URL/api/crm/tenders?limit=5" -H "Authorization: Bearer $TOKEN"
curl -s "$URL/api/crm/tenders/analytics/win-loss" -H "Authorization: Bearer $TOKEN"
curl -s "$URL/api/crm/tender-templates" -H "Authorization: Bearer $TOKEN"

# UI surface
# /crm/tenders — full list view
# /crm/tenders/{id} — detail w/ Overview · Questions · Documents · Strategy · Pitch · Export tabs
```

Owner: Iter 216h223 audit · Feb 19 2026.
