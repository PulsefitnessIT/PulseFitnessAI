# GymAxis · convenience targets
#
# Common tasks the engineering team runs locally / in CI.
# Keep this file lean — actual logic lives in scripts/.

.PHONY: help lint-integrations lint-backend lint-frontend lint smoke regression regression-full security-scan pre-deploy post-deploy lint-health uptime-check install-hooks docs-verify brand-preview

help:
	@echo "GymAxis make targets:"
	@echo "  make install-hooks       # install git pre-commit hook (lint staged JS/JSX strictly)"
	@echo "  make lint-integrations   # validate Sicon/Sage field mapping docs"
	@echo "  make lint-backend        # ruff over backend/"
	@echo "  make lint-frontend       # eslint over frontend/src/"
	@echo "  make docs-verify         # fail if any /memory or /docs MD is stamped against a stale Iter"
	@echo "  make brand-preview       # regenerate /app/BRAND_PALETTE_PREVIEW.html from canonical brand docs"
	@echo "  make lint                # all of the above"
	@echo "  make smoke               # quick health curl against \$$REACT_APP_BACKEND_URL"
	@echo "  make security-scan       # ruff + bandit baseline (fail on Medium+)"
	@echo "  make regression          # iter-216 regression suite (branding, site-lock, brand inheritance)"
	@echo "  make regression-full     # h211 trust-recovery suite (84 tests, 6 modules)"
	@echo "  make pre-deploy          # full deploy gate — regressions + security + Stripe + lint"
	@echo "  make post-deploy         # 6-probe HTTP smoke against \$$POST_DEPLOY_BASE_URL (Resend on result)"
	@echo "  make lint-health         # weekly codebase-health snapshot to /app/reports/ (Resend opt-in)"
	@echo "  make uptime-check        # single uptime probe (state-change-only emails; cron-friendly)"

# Iter 216h291 — install the git pre-commit hook so ESLint warnings
# can't sneak past local commits. Idempotent — re-running just
# refreshes the symlink.
install-hooks:
	@bash /app/scripts/install_hooks.sh
	@echo "  Tip: run 'git commit --no-verify' to bypass in emergencies"

lint-integrations:
	@python3 /app/backend/scripts/check_integration_mapping.py

lint-backend:
	@cd /app/backend && ruff check .

lint-frontend:
	@cd /app/frontend && yarn -s eslint src --ext .js,.jsx --max-warnings 0

# Iter 220m — fail CI if any shipped Markdown doc carries a stale
# `Iter XXX` status banner. Canonical current iter lives in
# /app/memory/.current_iter — bump it when you cut a release.
docs-verify:
	@cd /app && python3 scripts/docs_verify.py

# Iter 220m — regenerate /app/BRAND_PALETTE_PREVIEW.html from the
# canonical brand docs. Run any time BRAND_PALETTE.md or
# PULSE_BRAND_PALETTE.md changes so the live preview stays in sync.
brand-preview:
	@cd /app && python3 scripts/build_brand_preview.py

lint: lint-integrations lint-backend lint-frontend docs-verify brand-preview

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
	  tests/test_iter_216h284_activation_checklist.py \
	  tests/test_iter_216h285_collateral_kit.py \
	  tests/test_iter_216h286_customer_reviews.py \
	  tests/test_iter_216h287_engineer_referrals.py \
	  tests/test_iter_216h288_engineer_availability.py \
	  tests/test_iter_216h290_unavailable_autoreply.py \
	  tests/test_iter_216h291_precommit_hook.py \
	  tests/test_iter_216h293_ci_gating.py \
	  tests/test_iter_216h294_predeploy_lint_gate.py \
	  tests/test_iter_216h295_required_checks_doc.py \
	  tests/test_iter_216h296_post_deploy_smoke.py \
	  tests/test_iter_216h297_lint_health_report.py \
	  tests/test_iter_216h298_uptime_monitor.py \
	  tests/test_iter_216h299_lite_dashboard_bugs.py \
	  tests/test_iter_216h300_ai_triage_persistence.py \
	  tests/test_iter_216h301_pulse_lite_fault_submission.py \
	  tests/test_iter_217_pulse_score_merge.py \
	  tests/test_iter_217_engineer_app_full.py \
	  tests/test_iter_218_partner_application_approve.py \
	  tests/test_iter_219_partner_application_drawer.py \
	  tests/test_iter_219b_partner_application_ai_suggest.py \
	  tests/test_iter_219c_partner_application_emails.py \
	  tests/test_iter_219d_resend_approval_email.py \
	  tests/test_iter_219e_stripe_guided_approval.py \
	  tests/test_iter_219f_partner_activation_flow.py \
	  tests/test_iter_219g_send_signin_link.py \
	  tests/test_iter_220_work_report_custom_fields.py \
	  tests/test_iter_220c_engineer_draft_autosave.py \
	  tests/test_iter_220d_per_machine_reports.py \
	  tests/test_iter_220e_per_machine_photos.py \
	  tests/test_iter_220f_customer_typeahead.py \
	  tests/test_iter_220g_scheduling_suggestions.py \
	  tests/test_iter_220h_new_customer_prompt.py \
	  tests/test_iter_220i_branding_and_email.py \
	  tests/test_iter_220j_engineer_attention.py \
	  tests/test_iter_220k_release_gates.py \
	  tests/test_iter_220l_pre_launch_polish.py \
	  tests/test_iter_220m_reputation_reports.py \
	  tests/test_iter_220m_brand_canon.py \
	  tests/test_iter_220n_supplier_auto_dispatch.py \
	  tests/test_iter_220o_instagram_attribution.py \
	  tests/test_iter_220p_my_gyms_queue.py \
	  tests/test_iter_220q_attribution_dashboard.py \
	  tests/test_iter_220r_welcome_back_digest.py \
	  tests/test_iter_220s_incidents_riddor.py \
	  tests/test_iter_220x_digest_hs_channel.py \
	  tests/test_iter_220y_engineer_reviews_wall.py \
	  tests/test_iter_220z_partner_wall_share.py \
	  tests/test_iter_220aa_widget_embed.py \
	  tests/test_iter_220ad_seo_autopilot.py \
	  tests/test_iter_220ae_seo_distribution.py \
	  tests/test_iter_220af_seo_autopilot_scheduler.py \
	  tests/test_iter_220ag_growth_hub.py \
	  tests/test_iter_220ah_journey_templates.py \
	  tests/test_iter_220ai_seo_autopilot_ux.py \
	  tests/test_iter_220aj_growth_sparklines.py \
	  tests/test_iter_220ak_public_demo_request.py \
	  tests/test_iter_220al_crm_journey_enrol.py \
	  tests/test_iter_220am_per_article_view_trend.py \
	  tests/test_iter_220an_tender_deep_linking.py \
	  tests/test_iter_220ao_gdpr_erasure.py \
	  tests/test_iter_220ap_gdpr_erased_list_filter.py \
	  tests/test_iter_220aq_growth_hub_fixes.py \
	  tests/test_iter_220as_security_wave_1.py \
	  tests/test_iter_220at_ai_guardrails.py \
	  tests/test_iter_220au_auth_hardening.py \
	  tests/test_iter_220av_web_security.py \
	  tests/test_iter_220aw_ssrf_av_vault.py \
	  tests/test_iter_220ax_audit_log.py \
	  tests/test_iter_220ay_pen_test_handover.py \
	  tests/test_iter_220az_engineer_horizontal_access.py \
	  tests/test_iter_220ba_pre_pentest_polish.py \
	  tests/test_iter_220bc_homepage_modules_consolidation.py \
	  tests/test_iter_220be_pentest_final_hardening.py \
	  tests/test_iter_220bf_handover_pack_hygiene.py \
	  tests/test_iter_220bg_handover_pack_consistency.py \
	  tests/test_iter_220bh_doc_consistency_polish.py \
	  tests/test_iter_220bi_sicon_field_mapping.py \
	  tests/test_iter_220bj_blog_freshness.py \
	  tests/test_iter_220bk_keyword_auto_discovery.py \
	  tests/test_iter_220bl_social_autopilot.py \
	  tests/test_iter_220bm_sora_video_and_legacy_cleanup.py \
	  tests/test_iter_220bn_social_scheduler.py \
	  tests/test_iter_220bo_no_double_api_prefix.py \
	  tests/test_iter_220bp_security_hardening.py \
	  tests/test_iter_220bq_gdpr_polish.py \
	  tests/test_iter_220br_prelaunch_ops.py \
	  tests/test_iter_220bs_crm_evolution.py \
	  tests/test_iter_220bt_picklist_ux.py \
	  tests/test_iter_220bu_unified_timeline.py \
	  tests/test_iter_220bv_timeline_panel.py \
	  tests/test_iter_220bw_launch_campaigns_and_tracker.py \
	  tests/test_iter_220bx_social_tone_check.py \
	  tests/test_iter_220by_security_document.py \
	  tests/test_iter_220bz_profile_completion.py \
	  tests/test_iter_220ca_competitor_blocklist.py \
	  tests/test_iter_220cb_companies_house_signup.py \
	  tests/test_iter_220ce_branded_card_polish.py \
	  tests/test_iter_220cf_seo_autopilot_cron_catchup.py \
	  tests/test_iter_220cg_social_card_text_fit.py \
	  tests/test_iter_220ch_engineer_pound_icon.py \
	  tests/test_iter_220ci_engineer_equipment.py \
	  tests/test_iter_220ci_engineer_equipment_frontend.py \
	  tests/test_iter_220ci_engineer_equipment_api.py \
	  tests/test_iter_220cj_engineer_extras.py \
	  tests/test_iter_220cj_engineer_extras_frontend.py \
	  tests/test_iter_220cj_api.py \
	  tests/test_iter_220ck_customer_wizard.py \
	  tests/test_iter_220cl_engineer_csv_move.py \
	  tests/test_iter_220cm_service_history.py \
	  tests/test_iter_220cn_parts_machine_tag.py \
	  tests/test_iter_220co_parts_cost_rollup.py \
	  tests/test_iter_220cp_channel_unification.py \
	  tests/test_iter_220cq_channel_performance.py \
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
#   make lint → regression suite → ruff/bandit → Stripe live keys → Mongo ping → frontend lint.
# Iter 216h294 — `lint` is now a hard prerequisite. Previously you
# could ship lint-dirty code through `pre-deploy` because the
# script's own frontend-lint step only scanned files changed in
# HEAD (so a stale warning in an untouched file slid through). The
# Makefile-level dependency runs strict ruff + ESLint over the
# whole tree first, then hands off to the script for the heavier
# Stripe / Mongo / regression checks.
# In preview / staging where Stripe is in test mode, prefix with
#   SKIP_LIVE_CHECK=1 make pre-deploy
pre-deploy: lint
	@bash /app/scripts/pre-deploy.sh

# Iter 216h296 — Post-deploy smoke. Fires 6 HTTP probes against
# `$$POST_DEPLOY_BASE_URL` (or `$$REACT_APP_BACKEND_URL` as fallback)
# immediately after a deploy, with optional email-on-result via the
# existing Resend integration. Exits 0 only if every required probe
# is green.
#
# Probes covered:
#   /api/health, public referral lookup, public reviews,
#   POST /api/auth/login (when creds set), CRM capex catalogue read,
#   marketing site root.
#
# Optional probes that depend on env vars are SKIPPED rather than
# failed when the var is missing — the operator can roll the smoke
# out incrementally.
#
# Configure recipient: export POST_DEPLOY_NOTIFY_EMAIL=ops@your.co
post-deploy:
	@cd /app/backend && python3 /app/scripts/post-deploy.py

# Iter 216h297 — Lint-health weekly snapshot. Captures the current
# state of the repo's lint/test/complexity metrics, computes trend
# arrows vs the most recent previous snapshot in /app/reports/, and
# fires a Resend email if `LINT_HEALTH_NOTIFY_EMAIL` is set.
#
# Designed to be run weekly via cron / scheduled GitHub Action,
# but safe to run on-demand any time:
#     make lint-health
#
# Output:
#   /app/reports/lint-health-YYYY-WNN.md   (committable Markdown)
#   /app/reports/lint-health-YYYY-WNN.json  (raw metrics; powers next week's trends)
lint-health:
	@cd /app/backend && python3 /app/scripts/lint_health_report.py

# Iter 216h298 — Uptime monitor. Re-uses the same 6 probes as
# `make post-deploy` but emails only on state CHANGE (green→red
# or red→green). Designed for a 5-minute cron — exits 0 on probe
# failure (so cron doesn't itself email about non-zero scripts);
# state lives at `/app/reports/uptime-state.json`.
#
# Suggested cron:
#   */5 * * * * cd /app && UPTIME_NOTIFY_EMAIL=ops@yourco.com make uptime-check
uptime-check:
	@cd /app/backend && python3 /app/scripts/uptime_monitor.py
