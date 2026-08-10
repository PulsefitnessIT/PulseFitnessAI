# MOD Access — BPS "AI/ML" web-filter block (pulsefitness.ai)

## Symptom
MoDNET users hitting `http(s)://www.pulsefitness.ai/modservice` see a BPS page:
"Content blocked ... Category: Other AI ML Applications."

## Root cause
NOT an app fault. The MoD Boundary Protection Service (BPS) auto-categorises the
`.ai` TLD as "AI/ML Applications" and blanket-blocks that category on MoDNET. The
app itself is domain-agnostic (it runs fine on the non-`.ai` preview domain and
would run fine on any domain). No server-side change can bypass a MoD network filter.

## Resolution options (ranked)

### 1) BPS allow-list / reclassification request (sanctioned, do this first)
MoD sponsor / site IT raises a BPS request (MoDNET: defnet → Boundary Protection
Service) to reclassify/allow-list the domain. Draft justification:

---
Subject: BPS URL reclassification request — pulsefitness.ai (mis-categorised as AI/ML)

The URL https://www.pulsefitness.ai (and /MODService) is currently blocked by BPS
under "Other AI ML Applications". This is a mis-categorisation based solely on the
".ai" domain suffix. The site is a business web application for managing fitness
facility equipment servicing, bookings and maintenance records for our site — it is
not an AI/ML tool or public AI service. Please reclassify to a business/SaaS category
and allow-list the domain (including subdomains *.pulsefitness.ai) so authorised staff
can access the MOD service portal from MoDNET. Point of contact: <name/role/email>.
---

### 2) Alternate non-.ai vanity domain (durable, in our control)
Point a neutral domain (e.g. mod.pulse-fitness.co.uk / pulsefitnessservice.com) at the
same app. The `.ai` TLD is the trigger; a .co.uk/.com sidesteps the AI/ML category.
The app is ALREADY configurable for this — no code change, just DNS + env:
  - DNS: point the new domain/subdomain at the same host as pulsefitness.ai.
  - Backend env: add the new origin to `CORS_ORIGINS`
      CORS_ORIGINS=https://pulsefitness.ai,https://www.pulsefitness.ai,https://mod.pulse-fitness.co.uk
  - Email/portal links honour `EMAIL_PUBLIC_BASE_URL` (falls back to `FRONTEND_URL`).
      Set EMAIL_PUBLIC_BASE_URL=https://mod.pulse-fitness.co.uk so MOD-facing emails
      link to the non-.ai domain (and won't re-trigger the filter).
  - Frontend build: `REACT_APP_BACKEND_URL` should resolve to the backend behind the
    new domain (or a shared API host).
  - Restart backend after env changes.
  (TLS cert for the new domain is handled by the hosting/deploy layer.)

### 3) Interim workaround (today)
Access from a personal device on 4G/5G or non-MoDNET WiFi (per the BPS notice).

## Notes
- CORS loader: backend/utils/security_plus.py resolve_cors_origins() — `CORS_ORIGINS`
  env always wins (comma-separated, no wildcard).
- Email base URL: backend/utils/email.py PUBLIC_BASE_URL (EMAIL_PUBLIC_BASE_URL || FRONTEND_URL).
- MOD route: frontend /modservice -> /MODService (AppRoutes.js) — page is healthy.
