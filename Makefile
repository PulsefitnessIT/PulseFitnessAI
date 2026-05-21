# GymAxis · convenience targets
#
# Common tasks the engineering team runs locally / in CI.
# Keep this file lean — actual logic lives in scripts/.

.PHONY: help lint-integrations lint-backend lint-frontend lint smoke regression regression-full security-scan pre-deploy

help:
	@echo "GymAxis make targets:"
	@echo "  make lint-integrations   # validate Sicon/Sage field mapping docs"
	@echo "  make lint-backend        # ruff over backend/"
	@echo "  make lint-frontend       # eslint over frontend/src/"
	@echo "  make lint                # all of the above"
	@echo "  make smoke               # quick health curl against \$$REACT_APP_BACKEND_URL"
	@echo "  make security-scan       # ruff + bandit baseline (fail on Medium+)"
	@echo "  make regression          # iter-216 regression suite (branding, site-lock, brand inheritance)"
	@echo "  make regression-full     # h211 trust-recovery suite (84 tests, 6 modules)"
	@echo "  make pre-deploy          # full deploy gate — regressions + security + Stripe + lint"

lint-integrations:
	@python3 /app/backend/scripts/check_integration_mapping.py

lint-backend:
	@cd /app/backend && ruff check . || true

lint-frontend:
	@cd /app/frontend && yarn -s eslint src --ext .js,.jsx --max-warnings 0 || true

lint: lint-integrations lint-backend lint-frontend

smoke:
	@URL=$$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d'=' -f2); \
	  curl -fsS "$$URL/api/health" >/dev/null && echo "OK: backend reachable at $$URL/api/health" || echo "FAIL: backend not reachable"

# Iter 216c — focused regression suite that pins the most-recent
# production bug fixes. Cheap (~3s), no env deps. Run this before every
# deploy to make sure no fixed bug has silently come back.
regression:
	@cd /app/backend && python3 -m pytest \
	  tests/test_iter_216c_branding_org_sync.py \
	  tests/test_iter_216d_multi_machine_fault_job.py \
	  tests/test_iter_216e_pulse_spec_auto_pull.py \
	  tests/test_iter_216bl_site_lock.py \
	  tests/test_iter_216af_brand_inheritance.py \
	  tests/test_iter_216h216_activation_module_filter.py \
	  tests/test_iter_216h227_module_tailored_onboarding.py \
	  tests/test_iter_216h238_mapping_coverage_badge.py \
	  tests/test_iter_216h240_integration_field_capture.py \
	  tests/test_iter_216h241_staffing_polish.py \
	  tests/test_iter_216h243_subheaders_and_custom_roles.py \
	  tests/test_iter_216h244_pageheader_suppression.py \
	  tests/test_iter_216h245_memberships_marketing_subheaders.py \
	  tests/test_iter_216h247_memberships_polish.py \
	  tests/test_iter_216h248_instructor_route_fix.py \
	  tests/test_iter_216h249_module_tailored_signup.py \
	  tests/test_iter_216h250_events_modal_and_polish.py \
	  tests/test_iter_216h251_event_bootstrap_template.py \
	  tests/test_iter_216h252_wizard_redesign.py \
	  tests/test_iter_216h253_member_signup_contact.py \
	  tests/test_iter_216h254_member_drawer_date_consistency.py \
	  tests/test_iter_216h255_memberships_date_sweep.py \
	  tests/test_iter_216h256_marketing_resend_engineerapp_mobile.py \
	  tests/test_iter_216h257_engineer_dashboard_uploads_reports.py \
	  tests/test_iter_216h258_email_pipeline_all_senders.py \
	  tests/test_iter_216h259_engineer_lite_crm.py \
	  tests/test_iter_216h260_engineer_customers_csv_history.py \
	  tests/test_iter_216h261_engineer_customer_suggest.py \
	  tests/test_iter_216h262_supplier_inline_email.py \
	  tests/test_iter_216h263_fault_card_ux.py \
	  tests/test_iter_216h264_staff_portal_creds.py \
	  tests/test_iter_216h265_crm_customer_feedback.py \
	  tests/test_iter_216h266_company_360_ui.py \
	  tests/test_iter_216h267_crm_bundles.py \
	  tests/test_iter_216h268_website_recognise.py \
	  tests/test_iter_216h269_quote_bundle_expand.py \
	  tests/test_iter_216h270_miller_heiman_fields.py \
	  tests/test_iter_216h271_membership_admin_and_trial_btn.py \
	  tests/test_iter_216h272_module_trials_org_resolve.py \
	  tests/test_iter_216h273_org_integrity_audit.py \
	  tests/test_iter_216h274_crm_banner_clipping.py \
	  tests/test_iter_216h275_tenders_and_email_packs.py \
	  tests/test_iter_216h276_tenant_mirror.py \
	  tests/test_iter_216h277_crm_orgs_filter_sync.py \
	  tests/test_iter_216h278_territory_map.py \
	  tests/test_iter_216h279_map_autoassign_heatmap.py \
	  tests/test_iter_216h280_link_audit.py \
	  tests/test_iter_216h281_partner_emails_compliance.py \
	  tests/test_iter_216h282_engineer_route_consolidation.py \
	  tests/test_iter_216h283_compliance_docs.py \
	  -q --tb=line --no-header

# Iter 216c — ruff + bandit baseline. Medium+ findings fail.
security-scan:
	@bash /app/backend/scripts/security-scan.sh

# Iter 216h211 — full trust-recovery regression suite. 84 isolated
# tests across 6 modules (Auth, Memberships, Operations, Service Desk,
# MOD, CRM). No live server, no admin tokens, ~1 min runtime. This is
# the broadest pre-deployment gate — every PR should keep it green.
regression-full:
	@cd /app/backend && python3 -m pytest tests/regression -q --tb=line --no-header

# Iter 216c — full deploy gate. Runs:
#   regression suite → ruff/bandit → Stripe live keys → Mongo ping → frontend lint.
# In preview / staging where Stripe is in test mode, prefix with
#   SKIP_LIVE_CHECK=1 make pre-deploy
pre-deploy:
	@bash /app/scripts/pre-deploy.sh
