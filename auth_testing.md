# Auth testing — Release C (custom JWT auth, kept)
- Read /app/memory/test_credentials.md. Master admin has ENFORCE_MASTER_ADMIN_MFA on: for API tests mint tokens as tests/test_sage_sicon_customer_import._token does (create_token(user_id, mfa_verified=True)).
- Invitation emails are HELD (INVITATION_EMAILS_LIVE not set). Creating an invitation returns a one-time `link` (`/accept-invite#token=...`).
- Owner flow: POST /api/master-admin/customer-activation/{org_id}/owner-invite → open link → confirm email, name, password (≥12 chars, upper/lower/digit/symbol) → POST /api/invitations/accept → login returns requires_mfa_enrolment.
- Staff flow: POST /api/organization/invite {email, role, allowed_site_ids} as owner/manager.
- Send header x-ratelimit-bypass: <RATE_LIMIT_BYPASS_SECRET from backend/.env> on invitation/login calls to avoid the rate limiter.
