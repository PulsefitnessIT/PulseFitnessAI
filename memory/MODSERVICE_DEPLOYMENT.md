# MODService standalone domain — deployment checklist

**Goal:** MOD sites reach the app on a non-`.ai` URL (`MODService.pulsefitness.com`)
while commercial/staff users stay on `pulsefitness.ai`. One codebase, one database.

## Architecture (agreed June 2026)
- ONE codebase (this repo, kept in GitHub).
- TWO Emergent deployments off the same repo:
  - **A — pulsefitness.ai** → normal app (no special env). Commercial + staff + MOD all work as today.
  - **B — MODService.pulsefitness.com** → same code with `REACT_APP_PORTAL_MODE=modservice`.
    Public landing becomes the MOD Service sign-in; only MOD accounts + master admin can sign in;
    commercial/staff get a "Go to Pulse Fitness" block.
- ONE shared MongoDB (single source of truth). For two deployments to share a DB reliably you must
  use YOUR OWN MongoDB Atlas cluster and allowlist BOTH deployments' egress IPs
  (https://app.emergent.sh/ip-addresses). Set the SAME `MONGO_URL` + `DB_NAME` in each deployment's Secrets.

## What is already built in code (no duplication)
- `frontend/src/utils/portalMode.js` — `isModServiceMode()` detection:
  1. `REACT_APP_PORTAL_MODE=modservice` (the deployment flag), OR
  2. host starts with `modservice.`, OR
  3. `?portal=modservice` preview override (sticky per browser session; `?portal=pulse` clears it).
- `frontend/src/routes/AppRoutes.js` — root `/` renders the MOD sign-in in MODService mode; `/login` bounces to `/`.
- `frontend/src/pages/MODPortal/MODServiceLogin.js` — commercial/staff account → friendly "Go to Pulse Fitness"
  block (`data-testid=mod-login-commercial-block`, CTA → `REACT_APP_COMMERCIAL_URL` default `https://pulsefitness.ai`).
- `backend/routes/auth.py` — `portal='mod'` gate now allows master admins in addition to MOD users.

## Steps for the founder
1. **Save to GitHub** (chat input → Save to Github) so both deployments share one repo.
2. **Deployment A (pulsefitness.ai):** deploy normally. Manage Publishes → Domain → add `pulsefitness.ai`.
   Add `REACT_APP_BACKEND_URL` + `CORS_ORIGINS` for that domain. Redeploy.
3. **Deployment B (MODService.pulsefitness.com):** create a second job/chat from the SAME GitHub repo.
   In Manage Publishes → Secrets set:
   - `REACT_APP_PORTAL_MODE=modservice`
   - (optional) `REACT_APP_COMMERCIAL_URL=https://pulsefitness.ai`
   - same `MONGO_URL` + `DB_NAME` as Deployment A (your Atlas cluster)
   - `REACT_APP_BACKEND_URL` + `CORS_ORIGINS` for the MODService domain
   Manage Publishes → Domain → add `MODService.pulsefitness.com` (A records `162.159.142.117`, `172.66.2.113`;
   if on Cloudflare set the record to "DNS only" / grey cloud). Redeploy.
4. **Keep in sync:** push code once to GitHub → Republish both deployments.

## Preview testing (before the domain exists)
- MODService experience: open `<preview>/?portal=modservice` → MOD sign-in is the landing.
- Back to normal: open `<preview>/?portal=pulse` (or clear the tab session).

## Cost note
Second deployment = +50 credits/month min (Starter). See support guidance in chat.

## Update — hide /MODService on the commercial domain (done)
Now that the MOD deployment is live, the commercial (pulsefitness.ai) deployment forwards
its MOD login routes to the dedicated MOD domain so there is ONE canonical MOD entry point:
- /MODService, /MODService/login, /modservice  → 302 to REACT_APP_MODSERVICE_URL
  (default https://modservice.pulsefitness.com) — only when NOT in MODService mode.
- On the MOD deployment itself these still render the branded MOD login (unchanged).
- /mod/confirm-fix/:token (email action deep-link) is intentionally left working on BOTH domains.
Code: frontend/src/utils/portalMode.js (MODSERVICE_URL) + routes/AppRoutes.js (ExternalRedirect).
Activate: Save to Github → Re-publish the pulsefitness.ai deployment.

## Update — zero ".ai" MOD build (Nov 2026)
MOD web filtering blocks any ".ai" reference, so the MODService BUILD is sanitised
(only when REACT_APP_PORTAL_MODE=modservice; the commercial build is untouched):
- `frontend/modservice/index.html` — clean HTML template (no pulsefitness.ai, no "AI"), swapped in by craco.config.js.
- `frontend/modservice/sanitize.js` — webpack plugin: pulsefitness.ai / gymaxis.ai URLs → modservice.pulsefitness.com,
  x@pulsefitness.ai → x@pulsefitness.com, "Pulse Fitness AI" → "Pulse Fitness".
- `frontend/modservice/postbuild.js` (runs from `yarn build`) — drops commercial-only public files (sitemap, llms.txt,
  decks, briefs), writes MOD robots.txt / security.txt / manifest.json, then FAILS the build if any .ai domain remains.
- `frontend/src/utils/modServiceSeo.js` — runtime safety net for <head> (wired in AppRoutes.js).
Verified: MOD build 0 .ai domain refs across all files; commercial build unchanged (7 in index.html, 80 in JS).

## Update — MOD fault emails + fault titles (9 Nov 2026)
- ROOT CAUSE of "no emails": each deployment has its OWN RESEND_API_KEY secret. MODService's was invalid
  ("API key is invalid"); pulsefitness.ai's was valid (Master Admin resends worked because the .ai backend sent them).
  Fixed by saving the working key into this job's RESEND_API_KEY (live, 2026-11-09T12:08Z). Keep the two in sync.
- Supplier-thread emails (_send_comment_notification) use the MOD sender for MOD cases, log every attempt to
  email_send_events and return delivered addresses; issues store auto_dispatch_delivered_to; MOD Pulse alert falls back
  when the thread didn't reach Pulse; fault card shows amber "Email to X not delivered" when applicable.
- Fault cards: title = make + model (model ignored when it is just a serial prefix → make + name), serial underneath.
