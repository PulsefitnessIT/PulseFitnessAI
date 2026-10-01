# Crash Pack feature — 2026-06

Employee crash-reporting wizard + manager review/print, from the physical "Crash Pack" PDF.

## Backend — /app/backend/routes/crash_packs.py (registered in route_registry/features.py _UNGATED_ROUTERS)
Collections: db.crash_packs (status draft|submitted), db.crash_pack_settings (per-org insurance, editable).
Photos reuse db.files category "vehicle-photos" so existing dual-auth proxy GET /api/vehicle-checks/photo/{file_id}?auth= serves them.
Driver (portal, get_current_user_portal):
- GET  /new-starter/portal/crash-packs/bootstrap  → assigned vehicles + prefill + insurance (only drivers with an assigned vehicle)
- GET  /new-starter/portal/crash-packs            → my packs
- POST /new-starter/portal/crash-packs            → create draft (vehicle must be assigned to me)
- GET/PUT /new-starter/portal/crash-packs/{id}    → load/save draft (editable while draft; can return later e.g. for sketch)
- POST /new-starter/portal/crash-packs/{id}/submit → submit; in-app alert + email to LINE MANAGER only (_line_manager_user_id)
- POST /new-starter/portal/crash-packs/photo      → multipart upload (reuses compress+put_object), returns {file_id}
Manager (get_current_user, _is_manager; master admin bypasses org scope):
- GET /crash-packs, GET /crash-packs/{id}, GET/PUT /crash-packs/insurance-settings

## Frontend
- Employee wizard: /app/frontend/src/pages/staffing/CrashPackWizard.js (8 steps: Safe?→Your details→Accident→Photos→Other drivers→Witnesses→Police→Review; autosave, phone camera capture, insurance info shown AT END per user). Entry card added in StaffPortal.js VehicleTab (CrashPackEntryCard, "Report a crash", lists drafts/submitted).
- Manager: /app/frontend/src/pages/LiteDashboard/staffing/CrashPacksManager.js — new "Crash Packs" sub-tab in VehiclesTab.js; printable A4 report (window.print) with photos + editable insurance details.

## User decisions
- Insurance details editable per org, shown at END of wizard. Notify line manager only (in-app + email). Sketch = photo of hand sketch + note, can return later. Prefill Your details. Only drivers with an assigned vehicle can start.

## Verified
Backend E2E via curl: bootstrap/create/save/submit → status submitted, line_manager_user_id set, staff_notification created for manager, manager list+detail OK, insurance defaults (QBE 0808 100 8181, policy Y157953FLT0125A). Frontend compiles. Photo pipeline reuses proven vehicle-photo endpoints.
NOT yet browser-tested: the wizard UI flow + live photo capture (needs a staff_jwt portal session).

## Update 2026-06 — Server PDF + GPS location
- Server PDF: GET /api/crash-packs/{id}/pdf (manager; master-admin bypasses org). ReportLab via utils.pulse_doc_template,
  mirrors vehicle-check PDF; embeds photos through get_object; sections A–F incl GPS + Google Maps link. Verified: returns
  application/pdf, %PDF- magic, ~6.5KB with an embedded photo. Download buttons added to CrashPacksManager list row + report modal.
- GPS capture: wizard accident step auto-captures navigator.geolocation (manual Capture/Update button, graceful denied state),
  stored at data.accident.gps {lat,lng,accuracy,captured_at}. Shown in manager HTML report (Section B, "View on map") and PDF.

