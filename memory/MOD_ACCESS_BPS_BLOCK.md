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

## DECISION (2026-08-10): Option 2 — second deployment for modservice.pulsefitness.com
Keep pulsefitness.ai live; stand up a SECOND Emergent deployment (same repo/codebase)
and link the vanity domain modservice.pulsefitness.com to it. ~100 credits/mo total.

### Code readiness (DONE — shared across both deployments)
- CORS: `https://modservice.pulsefitness.com` added to _BRAND_DEFAULT_ORIGINS in
  backend/utils/security_plus.py, so the new deployment accepts it even without a
  CORS_ORIGINS env override. Verified (direct-to-app curl): MOD origin echoed WITH
  credentials; pulsefitness.ai still works; unknown origins rejected.
- Auth + refresh cookies are HOST-ONLY (no domain= attribute) in utils/auth.py and
  utils/refresh_tokens.py, so sessions work on modservice.pulsefitness.com with no change.
  SameSite=None; Secure (fine over HTTPS; each deployment serves its own FE+BE on one host).

### Per-deployment env to set on the MOD deployment (in the Emergent deploy settings)
- EMAIL_PUBLIC_BASE_URL=https://modservice.pulsefitness.com  (so MOD emails link to .com)
- (Optional) FRONTEND_URL=https://modservice.pulsefitness.com
- Leave CORS_ORIGINS unset to use the brand defaults above, OR set it explicitly to
  include the new domain. Do NOT set it to "*".
- Do NOT change EMAIL_PUBLIC_BASE_URL on the ORIGINAL .ai deployment.

### Deploy steps (from platform support)
1. Home tab → deploy the same app to a NEW deployment slot (no new project; same GitHub repo).
2. On the new deployment: Link domain → modservice.pulsefitness.com → Entri → follow DNS steps.
3. At the DNS provider: remove any existing A records for the `modservice` subdomain;
   Entri sets the required CNAME/A. TLS is automatic. Propagation ~5–15 min (up to 24h).
4. Set the per-deployment env above; redeploy/restart if prompted.
5. Verify: open https://modservice.pulsefitness.com/MODService and log in.

