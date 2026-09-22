# Fire-station engineer service/calibration — production go-live runbook

Rehearsed end-to-end in preview (all steps green). To go live in production:

## One-time setup (admin, in production UI)
1. **Provision the engineer as INTERNAL** (unblocks the engineer app; skips Partner Network + DBS/RTW claim gate):
   - Easiest: Master Admin → the operator org (Pulse Fitness Ltd, 3ece2d0c-57ea-4acd-a6b4-d748478ed117) → Add user with **role = "engineer"** for William.ollis@pulsefitness.com. This auto-creates the active `svc_engineers` row.
   - Or if William already has a login: Service Desk → **Engineers** tab → add him to the roster (POST /svc/engineers by email).
2. **Devon & Somerset estate**: confirm their `crm2_companies` record has `linked_organization_id` set (cert attaches to that org). Deployer is verifying this.
3. **Fire-station portal accounts** (so they can VIEW the cert in their portal): Master Admin → their org → Add user, **role = "staff"** (or manager), email of their contact. Without this, the cert still publishes to their org's Documents but no one can log in to see it yet.

## Operating flow (each job)
- Schedule the PPM/calibration (PPM calendar) → **dispatch/assign** to William (sets scheduled_at + assigned_engineer_id). Job must have a scheduled date to appear in his app.
- William logs in → sees the job → H&S sign-off → start timer → **capture calibration** (8 treadmill params pre-filled) → complete.
- Service desk **closes** the case → certificate auto-publishes to the fire station's Documents; office can also Download/Email it from the case drawer.

## Dependencies to confirm in production (deployer checking)
- New endpoints live (calibration email, tender AI, rate cards).
- William.ollis user exists + svc_engineers row active.
- DSFR crm company linked_organization_id set; DSFR org login accounts (for portal viewing).
- Email delivery (if used): valid RESEND_API_KEY + verified sender service@service.pulsefitness.ai.
- EMERGENT_LLM_KEY present/funded (tender AI only; not needed for calibration).
