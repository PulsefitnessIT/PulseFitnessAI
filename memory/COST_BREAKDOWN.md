# GymAxis AI — Monthly Running Cost Breakdown & CRM Licensing

*Prepared: April 2026 | Updated with confirmed details*

---

## Your Setup

- **Hosting**: Names.co.uk — £34.99/year (£2.92/mo)
- **Scale target**: ~500 Pulse Fitness sites
- **CRM**: 20 users, per-seat licensing, standalone product within the platform
- **Stripe**: Standard UK pricing (1.5% + 20p domestic / 2.5% + 20p EU)
- **Email**: Higher volume (Resend Pro)
- **AI**: Priced per-call below so you can forecast as usage grows

---

## 1. Fixed Monthly Costs (Do Not Scale With Users)

| Item | Cost/month | Notes |
|------|-----------|-------|
| Hosting (Names.co.uk) | **£2.92** | £34.99/year |
| MongoDB Atlas (M30 dedicated) | **£150–200** | 500 sites needs a production cluster. M30 handles ~10k connections, 30GB+ |
| Resend Pro (email) | **£16** | 50,000 emails/mo — covers digests, alerts, expiry reminders for 500 sites |
| Domain / DNS | **£0** | Included with Names.co.uk |
| SSL | **£0** | Free via Let's Encrypt or Cloudflare |
| File Storage (PDFs, images) | **£20–40** | ~50–100GB at 500 sites (invoices, spec sheets, photos, manuals) |
| **Fixed subtotal** | **~£190–260/mo** | |

---

## 2. AI Costs — Per Call Pricing

All AI features use the Emergent Universal Key (OpenAI GPT-5.2 / GPT-4o). Here's the cost per individual call so you can forecast based on actual usage:

| AI Feature | Model | Cost per call | What triggers it |
|------------|-------|--------------|-----------------|
| Invoice Parsing (single PDF) | GPT-5.2 | **£0.06** | User uploads a supplier invoice |
| Bulk Invoice Parsing (per PDF) | GPT-5.2 | **£0.06** | Each PDF in a bulk upload |
| AI Fault Diagnosis (chat message) | GPT-5.2 | **£0.04** | User asks AI to diagnose a fault |
| AI Triage (before logging fault) | GPT-5.2 | **£0.03** | Pulse Pro user gets AI suggestion before engineer call |
| Equipment Audit Report | GPT-5.2 | **£0.07** | User generates an AI audit |
| Predictive Maintenance | GPT-5.2 | **£0.06** | User requests maintenance prediction |
| CAPEX Justifications | GPT-5.2 | **£0.08** | Owner generates board-ready CAPEX report |
| Spec Sheet Extraction | GPT-5.2 | **£0.05** | Admin uploads a spec sheet PDF |
| Gym Floor Plan Detection | GPT-4o (vision) | **£0.15** | User uploads gym layout image |
| CRM AI Assistant | GPT-5.2 | **£0.04** | CRM user asks AI for help |
| Risk Assessment Generation | GPT-5.2 | **£0.06** | User generates a risk assessment |
| Document Q&A | GPT-5.2 | **£0.05** | User asks a question about uploaded documents |

### Estimated Monthly AI Cost at Scale

| Usage scenario | Calls/month | AI cost/month |
|----------------|------------|--------------|
| Light (most sites rarely use AI) | 2,000 | **£100** |
| Medium (regular AI usage across sites) | 5,000 | **£250** |
| Heavy (daily AI usage, lots of imports) | 10,000 | **£500** |
| Very heavy | 20,000 | **£1,000** |

> **Recommendation**: Set a soft cap or fair-use policy (e.g. 50 AI calls/site/month included, then £0.05 per additional call) to protect margins.

---

## 3. Stripe Payment Processing Fees

| Scenario | Monthly revenue | Stripe fees (~1.7% avg) | Net after Stripe |
|----------|----------------|------------------------|-----------------|
| 100 Lite + 50 Pro | £6,850 | **£136** | £6,714 |
| 200 Lite + 150 Pro + 50 Ent | £25,150 | **£448** | £24,702 |
| 300 Lite + 150 Pro + 50 Ent (+ CRM) | £28,750* | **£509** | £28,241 |
| 500 sites (blended) | ~£40,000* | **£700** | £39,300 |

*Includes CRM per-seat revenue — see Section 6*

---

## 4. Email Costs at Volume (Resend)

| Monthly emails | Plan | Cost |
|---------------|------|------|
| Up to 3,000 | Free | £0 |
| Up to 50,000 | Pro | £16/mo |
| Up to 100,000 | Business | £65/mo |

At 500 sites with weekly digests + expiry alerts + fault notifications: estimate **15,000–30,000 emails/month** → **Resend Pro (£16/mo)** is sufficient. May need Business tier (£65/mo) if you add marketing emails.

---

## 5. Total Monthly Running Cost — By Growth Stage

### Stage 1: Early Growth (50 sites)
| Category | Cost |
|----------|------|
| Hosting (Names.co.uk) | £2.92 |
| MongoDB Atlas (M10) | £45 |
| AI (~500 calls) | £25 |
| Stripe fees | £35 |
| Email (Resend free) | £0 |
| Storage | £5 |
| **TOTAL COST** | **~£113/mo** |
| **Revenue** (30 Lite + 15 Pro + 5 Ent) | **£2,830/mo** |
| **Profit** | **£2,717/mo (96%)** |

### Stage 2: Growth (200 sites)
| Category | Cost |
|----------|------|
| Hosting | £2.92 |
| MongoDB Atlas (M20) | £100 |
| AI (~3,000 calls) | £150 |
| Stripe fees | £250 |
| Email (Resend Pro) | £16 |
| Storage | £15 |
| **TOTAL COST** | **~£534/mo** |
| **Revenue** (120 Lite + 60 Pro + 20 Ent) | **£11,200/mo** |
| **Profit** | **£10,666/mo (95%)** |

### Stage 3: Target Scale (500 sites + 20 CRM seats)
| Category | Cost |
|----------|------|
| Hosting | £2.92 |
| MongoDB Atlas (M30) | £200 |
| AI (~8,000 calls) | £400 |
| Stripe fees | £700 |
| Email (Resend Pro) | £16 |
| Storage | £40 |
| **TOTAL COST** | **~£1,359/mo** |
| **Pulse Revenue** (300 Lite + 150 Pro + 50 Ent) | **£28,200/mo** |
| **CRM Revenue** (20 seats — see below) | **£590/mo** |
| **Total Revenue** | **£28,790/mo** |
| **Profit** | **£27,431/mo (95%)** |

---

## 6. CRM Per-Seat Pricing — Recommendation

Since you want per-seat, standalone (all features in one tier), here's my recommendation:

### Recommended CRM Price: **£29.50/user/month**

| What's included | Details |
|----------------|---------|
| Contacts & Companies | Unlimited |
| Deal Pipeline | Drag-and-drop Kanban |
| Inbox / Conversations | Unified communications |
| Workflows & Automation | Rule-based triggers |
| Quotes (CPQ) | Generate, send, track quotes |
| AI Assistant | AI-powered reply suggestions, lead scoring |
| Reports & Analytics | Pipeline, activity, revenue dashboards |
| Sage 200 Integration | Two-way ERP sync (when live) |
| Team Management | Role-based access |
| Document Management | Upload, organise, share |

### Why £29.50/user/month

| Factor | Reasoning |
|--------|-----------|
| **Market positioning** | HubSpot Starter is £18/seat, Professional is £90/seat. Salesforce Essentials is £20/seat. You're offering Pro-level features at Starter price |
| **Margin** | At 20 users: £590/mo revenue, ~£20/mo AI cost for CRM features = **97% margin** |
| **Round number with VAT** | £29.50 + 20% VAT = £35.40 — or price at £25 ex-VAT (£30 inc) for cleaner marketing |
| **Scales well** | 50 CRM users = £1,475/mo; 100 users = £2,950/mo |
| **Competitive** | You're undercutting major CRM platforms while offering gym-industry specialisation |

### CRM Revenue Projections

| CRM Users | Monthly revenue | Annual revenue |
|-----------|----------------|---------------|
| 10 | £295 | £3,540 |
| 20 | £590 | £7,080 |
| 50 | £1,475 | £17,700 |
| 100 | £2,950 | £35,400 |

### Optional: Volume Discounts
| Users | Price/seat | Discount |
|-------|-----------|----------|
| 1–10 | £29.50 | — |
| 11–25 | £24.50 | 17% off |
| 26–50 | £19.50 | 34% off |
| 50+ | Custom | Contact sales |

---

## 7. Complete Revenue Model (500 Sites + CRM)

### Monthly
| Revenue stream | Calculation | Monthly |
|---------------|------------|---------|
| Pulse Lite (300 sites) | 300 × £29 | £8,700 |
| Pulse Pro (150 sites) | 150 × £79 | £11,850 |
| GymAxis Enterprise (50 sites) | 50 × £149 | £7,450 |
| CRM Seats (20 users) | 20 × £29.50 | £590 |
| **Total Revenue** | | **£28,590/mo** |
| Total Costs | | -£1,359/mo |
| Stripe Fees | | -£700/mo |
| **Net Profit** | | **£26,531/mo** |
| **Profit Margin** | | **92.8%** |

### Annual
| | Amount |
|--|--------|
| **Annual Revenue** | **£343,080** |
| **Annual Costs** | **-£24,708** |
| **Annual Net Profit** | **£318,372** |

---

## 8. Break-Even Analysis

| Your fixed costs | ~£250/mo (hosting + DB + email + storage + domain) |
|-----------------|------------------------------------------------------|
| Break-even | **9 Lite sites** (9 × £29 = £261) |
| Profitable from | **4 Pro sites** (4 × £79 = £316) |
| Or | **2 Enterprise sites** (2 × £149 = £298) |

---

## 9. Key Recommendations

1. **AI Cost Control**: Implement a fair-use policy — e.g. 50 AI calls/site/month included, overage at £0.05/call. This protects you if a single site hammers the AI.

2. **Monitor Emergent LLM Key balance**: Enable auto top-up at Profile → Universal Key to prevent service interruption.

3. **MongoDB**: Start on Atlas M10 (£45/mo). Upgrade to M20/M30 as you pass 100/300 sites. The platform already has indexes and bulk queries optimised.

4. **Email**: Resend free tier covers you to ~50 sites. Upgrade to Pro (£16/mo) once you pass that.

5. **CRM Upsell**: Position CRM as a separate product from day one, even if initial users are small. It establishes the revenue stream and lets you market it independently.

6. **Annual Plans**: Offer 2 months free on annual billing (e.g. £290/year for Lite instead of £348). Improves cash flow and reduces churn.
