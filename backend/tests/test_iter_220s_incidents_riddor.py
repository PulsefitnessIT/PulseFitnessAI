"""Iter 220s — Unified Incidents + RIDDOR module tests.

Pins the behaviour of:

* ``utils.riddor.assess`` decision engine (10-question wizard,
  conservative "potential" fallback, statutory deadline mapping)
* ``routes.incidents`` end-to-end through the FastAPI HTTPX client
  (create → RIDDOR assess → investigation → corrective action →
  audit trail → role-based access)

All tests are local-only — they hit the live backend running on this
host via ``TEST_API_URL`` (same pattern as the other regression tests).
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

from utils import riddor


API = os.environ.get("TEST_API_URL", "https://pulse-mod-estate--6ncsuzra.preview.emergentagent.com")
MASTER_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
MASTER_PASS = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")


def _login(email: str = MASTER_EMAIL, password: str = MASTER_PASS) -> str:
    r = requests.post(f"{API}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def _hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── RIDDOR engine (pure unit, no HTTP) ────────────────────────────


def test_riddor_assess_no_answers_returns_non_riddor():
    v = riddor.assess({})
    assert v.status == "non_riddor"
    assert v.deadline_days is None
    assert v.form is None


def test_riddor_assess_arose_from_work_false_short_circuits():
    """Context gate — without 'arose from work' RIDDOR doesn't engage
    even when other triggers are ticked."""
    v = riddor.assess({"arose_from_work": False, "fatality": True})
    assert v.status == "non_riddor"
    assert "did not arise" in v.reasons[0].lower()


def test_riddor_assess_fatality_returns_confirmed_with_10_day_deadline():
    v = riddor.assess({"arose_from_work": True, "fatality": True})
    assert v.status == "confirmed"
    assert v.form == "F2508"
    assert v.deadline_days == 10
    assert "fatality" in v.qualifying_questions


def test_riddor_assess_over_7_day_returns_15_day_deadline():
    v = riddor.assess({"arose_from_work": True, "over_7_day_incapacitation": True})
    assert v.status == "confirmed"
    assert v.deadline_days == 15
    assert v.form == "F2508"


def test_riddor_assess_occupational_disease_uses_f2508a():
    v = riddor.assess({"arose_from_work": True, "occupational_disease": True})
    assert v.status == "confirmed"
    assert v.form == "F2508A"
    assert v.deadline_days == 10


def test_riddor_assess_gas_incident_uses_f2508g_14_days():
    v = riddor.assess({"arose_from_work": True, "gas_incident": True})
    assert v.status == "confirmed"
    assert v.form == "F2508G"
    assert v.deadline_days == 14


def test_riddor_assess_multiple_triggers_picks_tightest_deadline_and_f2508():
    v = riddor.assess({
        "arose_from_work": True,
        "specified_injury": True,        # F2508 / 10 days
        "over_7_day_incapacitation": True,  # F2508 / 15 days
    })
    assert v.status == "confirmed"
    assert v.deadline_days == 10  # tightest wins
    assert v.form == "F2508"
    assert len(v.qualifying_questions) == 2


def test_riddor_assess_unknown_answer_becomes_potential():
    v = riddor.assess({
        "arose_from_work": True,
        "specified_injury": None,  # don't-know
    })
    assert v.status == "potential"
    assert v.deadline_days == 10
    assert v.form == "F2508"
    assert "specified injury" in v.reasons[0]


def test_riddor_wizard_questions_have_stable_keys_and_help_text():
    """The frontend depends on stable keys + help-text. Pin them."""
    keys = {q["key"] for q in riddor.WIZARD_QUESTIONS}
    assert keys >= {
        "arose_from_work", "person_at_work", "fatality",
        "specified_injury", "over_7_day_incapacitation",
        "non_worker_to_hospital", "dangerous_occurrence",
        "occupational_disease", "gas_incident",
    }
    # Every question must have human-readable prompt + help text.
    for q in riddor.WIZARD_QUESTIONS:
        assert q["prompt"] and len(q["prompt"]) > 5
        assert q["help"] and len(q["help"]) > 20


# ── HTTP route tests ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def master_token() -> str:
    return _login()


def test_picklists_endpoint_returns_kinds_and_riddor_questions(master_token):
    r = requests.get(f"{API}/api/incidents/picklists", headers=_hdrs(master_token), timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert "accident" in body["kinds"]
    assert "near_miss" in body["kinds"]
    assert "hazard" in body["kinds"]
    assert "dangerous_occurrence" in body["kinds"]
    assert len(body["riddor_questions"]) >= 9
    assert "minor" in body["severities"]
    assert "fatal" in body["severities"]


def test_create_incident_assigns_reference_and_audit_row(master_token):
    payload = {
        "kind": "accident",
        "severity": "moderate",
        "category": "slip_trip_fall",
        "description": f"Test incident {uuid.uuid4().hex[:8]} - member slipped near treadmill.",
    }
    r = requests.post(f"{API}/api/incidents", json=payload, headers=_hdrs(master_token), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reference"].startswith("IR-")
    assert body["kind"] == "accident"
    assert body["severity"] == "moderate"
    assert body["status"] == "reported"
    # Detail endpoint returns the audit log with the 'created' row.
    detail = requests.get(f"{API}/api/incidents/{body['id']}", headers=_hdrs(master_token), timeout=20).json()
    assert detail["incident"]["reference"] == body["reference"]
    actions = [a for a in detail["audit"] if a["action"] == "created"]
    assert len(actions) == 1


def test_create_serious_incident_auto_escalates(master_token):
    payload = {
        "kind": "accident", "severity": "serious", "category": "trapping_crush",
        "description": "Serious test incident: worker caught hand in cable machine.",
    }
    r = requests.post(f"{API}/api/incidents", json=payload, headers=_hdrs(master_token), timeout=20)
    body = r.json()
    assert body["status"] == "escalated"
    assert body["auto_escalated"] is True


def test_riddor_assess_endpoint_persists_verdict_and_status(master_token):
    # Create then assess as Confirmed.
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "moderate", "category": "equipment_failure",
        "description": "Treadmill belt detached mid-use causing user fall and fracture.",
    }, headers=_hdrs(master_token), timeout=20).json()
    incident_id = create["id"]
    r = requests.post(
        f"{API}/api/incidents/{incident_id}/riddor/assess",
        json={"answers": {"arose_from_work": True, "specified_injury": True}},
        headers=_hdrs(master_token), timeout=20,
    )
    assert r.status_code == 200
    verdict = r.json()["verdict"]
    assert verdict["status"] == "confirmed"
    assert verdict["form"] == "F2508"
    assert verdict["deadline_days"] == 10
    # Status auto-escalates + RIDDOR persists on the incident.
    detail = requests.get(f"{API}/api/incidents/{incident_id}", headers=_hdrs(master_token), timeout=20).json()
    assert detail["incident"]["riddor"]["status"] == "confirmed"
    assert detail["incident"]["status"] == "escalated"


def test_investigation_and_corrective_action_workflow(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "near_miss", "severity": "minor", "category": "slip_trip_fall",
        "description": "Near miss: cleaning fluid spill left unattended for 5 minutes.",
    }, headers=_hdrs(master_token), timeout=20).json()
    incident_id = create["id"]

    inv = requests.post(f"{API}/api/incidents/{incident_id}/investigation", json={
        "findings": "Cleaner left aisle unattended without wet-floor sign.",
        "root_causes": ["process_failure", "training_gap"],
    }, headers=_hdrs(master_token), timeout=20).json()
    assert inv["status"] == "investigating"
    assert "process_failure" in inv["investigation"]["root_causes"]

    action = requests.post(f"{API}/api/incidents/{incident_id}/actions", json={
        "description": "Update cleaning SOP to require wet-floor sign before walking away.",
        "priority": "high",
    }, headers=_hdrs(master_token), timeout=20).json()
    assert action["status"] == "open"
    assert action["priority"] == "high"
    action_id = action["id"]

    upd = requests.patch(
        f"{API}/api/incidents/{incident_id}/actions/{action_id}",
        json={"status": "completed"},
        headers=_hdrs(master_token), timeout=20,
    ).json()
    assert upd["status"] == "completed"
    assert upd["completed_at"] is not None

    # Audit trail must contain investigation_started + action_added + action_updated.
    detail = requests.get(f"{API}/api/incidents/{incident_id}", headers=_hdrs(master_token), timeout=20).json()
    actions_taken = {row["action"] for row in detail["audit"]}
    assert {"created", "investigation_started", "action_added", "action_updated"}.issubset(actions_taken)


def test_quick_log_endpoint_accepts_thin_payload(master_token):
    r = requests.post(
        f"{API}/api/incidents/quick",
        json={"description": "Quick-log test: barbell dropped on foot in free weight area."},
        headers=_hdrs(master_token), timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "accident"  # default
    assert body["severity"] == "minor"
    assert body["reference"].startswith("IR-")


def test_summary_stats_endpoint_returns_aggregates(master_token):
    r = requests.get(f"{API}/api/incidents/stats/summary", headers=_hdrs(master_token), timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert "total" in body and isinstance(body["total"], int)
    assert "by_status" in body
    assert "by_severity" in body
    assert "by_kind" in body


def test_create_rejects_unknown_kind(master_token):
    r = requests.post(f"{API}/api/incidents", json={
        "kind": "bogus", "description": "This should fail because kind is invalid",
    }, headers=_hdrs(master_token), timeout=20)
    assert r.status_code == 400


def test_create_rejects_short_description(master_token):
    r = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "description": "too short",
    }, headers=_hdrs(master_token), timeout=20)
    assert r.status_code in {400, 422}


# ── Phase 2 — PDFs, signatures, witness workflow, HSE dashboard ──


def test_pdf_accident_returns_pdf(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "moderate", "category": "slip_trip_fall",
        "description": "PDF test incident — member slipped on wet floor near reception.",
    }, headers=_hdrs(master_token), timeout=20).json()
    r = requests.get(f"{API}/api/incidents/{create['id']}/pdf/accident",
                     headers=_hdrs(master_token), timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1500


def test_pdf_management_summary(master_token):
    r = requests.get(f"{API}/api/incidents/pdf/management-summary?days=30",
                     headers=_hdrs(master_token), timeout=30)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_pdf_actions_log(master_token):
    r = requests.get(f"{API}/api/incidents/pdf/actions-log",
                     headers=_hdrs(master_token), timeout=30)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_pdf_riddor_requires_assessment_first(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "minor", "category": "other",
        "description": "PDF RIDDOR test - no assessment yet.",
    }, headers=_hdrs(master_token), timeout=20).json()
    r = requests.get(f"{API}/api/incidents/{create['id']}/pdf/riddor",
                     headers=_hdrs(master_token), timeout=20)
    assert r.status_code == 400


def test_signature_capture_appends_to_incident(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "minor", "category": "other",
        "description": "Signature capture test incident description.",
    }, headers=_hdrs(master_token), timeout=20).json()
    r = requests.post(
        f"{API}/api/incidents/{create['id']}/signatures",
        json={"name": "Test Manager", "role": "manager", "image_b64": ""},
        headers=_hdrs(master_token), timeout=20,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["signature"]["role"] == "manager"


def test_signature_capture_rejects_invalid_role(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "minor", "category": "other",
        "description": "Signature role validation test incident.",
    }, headers=_hdrs(master_token), timeout=20).json()
    r = requests.post(
        f"{API}/api/incidents/{create['id']}/signatures",
        json={"name": "Test", "role": "imaginary_role"},
        headers=_hdrs(master_token), timeout=20,
    )
    assert r.status_code == 400


def test_witness_invite_returns_token_and_landing_pulls_minimal_context(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "minor", "category": "other",
        "description": "Witness workflow test incident — member fell on the stairs.",
    }, headers=_hdrs(master_token), timeout=20).json()
    invite = requests.post(
        f"{API}/api/incidents/{create['id']}/witness-invite",
        json={"name": "Sarah Witness", "role": "member"},
        headers=_hdrs(master_token), timeout=20,
    )
    assert invite.status_code == 200
    token = invite.json()["token"]
    # Public landing — NO auth header
    landing = requests.get(f"{API}/api/incidents/witness-statement/{token}", timeout=20)
    assert landing.status_code == 200
    body = landing.json()
    assert body["name"] == "Sarah Witness"
    assert body["incident_reference"] == create["reference"]
    # Submitting too-short statement → 400
    bad = requests.post(f"{API}/api/incidents/witness-statement/{token}",
                        json={"statement": "tiny"}, timeout=20)
    assert bad.status_code == 400


def test_witness_statement_submit_and_idempotency(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "minor", "category": "other",
        "description": "Witness submit idempotency test incident here.",
    }, headers=_hdrs(master_token), timeout=20).json()
    token = requests.post(
        f"{API}/api/incidents/{create['id']}/witness-invite",
        json={"name": "Bob Witness", "role": "staff"},
        headers=_hdrs(master_token), timeout=20,
    ).json()["token"]
    submit = requests.post(
        f"{API}/api/incidents/witness-statement/{token}",
        json={"statement": "I saw the fall happen exactly as described in the incident note."},
        timeout=20,
    )
    assert submit.status_code == 200
    # Re-use same token → 410
    again = requests.post(
        f"{API}/api/incidents/witness-statement/{token}",
        json={"statement": "Replay attempt that should be blocked completely."},
        timeout=20,
    )
    assert again.status_code == 410
    # Witness appears on the incident.
    detail = requests.get(f"{API}/api/incidents/{create['id']}", headers=_hdrs(master_token), timeout=20).json()
    names = [w.get("name") for w in detail["incident"].get("witnesses") or []]
    assert "Bob Witness" in names
    # Audit log carries the witness_statement_received row.
    actions = [r["action"] for r in detail["audit"]]
    assert "witness_invited" in actions
    assert "witness_statement_received" in actions


def test_witness_invalid_token_returns_404(master_token):
    r = requests.get(f"{API}/api/incidents/witness-statement/NOPE", timeout=20)
    assert r.status_code == 404


def test_hse_dashboard_returns_aggregates(master_token):
    r = requests.get(f"{API}/api/incidents/hse/dashboard?days=30",
                     headers=_hdrs(master_token), timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert "period_days" in body and body["period_days"] == 30
    assert "by_status" in body and isinstance(body["by_status"], dict)
    assert "by_day" in body and isinstance(body["by_day"], list)
    assert "by_severity" in body
    assert "by_category" in body



# ── Phase 3 — Repeat-incident detection · Heatmap · Filter expansion ──


def test_hse_heatmap_returns_7x24_grid(master_token):
    r = requests.get(f"{API}/api/incidents/hse/heatmap?days=30",
                     headers=_hdrs(master_token), timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert len(body["grid_counts"]) == 7
    assert len(body["grid_counts"][0]) == 24
    assert body["day_labels"] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert isinstance(body["total"], int)


def test_repeat_detection_returns_rollup(master_token):
    r = requests.get(
        f"{API}/api/incidents/hse/repeat-detection?window_days=90&threshold=2",
        headers=_hdrs(master_token), timeout=20,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["window_days"] == 90
    assert body["threshold"] == 2
    assert isinstance(body["flagged"], list)


def test_repeat_detection_flags_asset_after_three_incidents(master_token):
    asset_id = f"asset-phase3-{uuid.uuid4().hex[:10]}"
    refs = []
    for i in range(3):
        r = requests.post(f"{API}/api/incidents", json={
            "kind": "accident", "severity": "moderate", "category": "equipment_failure",
            "description": f"Phase 3 repeat-detection test incident {i+1} on the test asset.",
            "asset_id": asset_id,
        }, headers=_hdrs(master_token), timeout=20)
        assert r.status_code == 200, r.text
        refs.append(r.json()["reference"])
    try:
        # Iter 230 — limit=2000 (API max): the flagged list is sorted by
        # severity score, and with many tied score-6 assets the default
        # 200-row cap can truncate the newest asset out of the response.
        rollup = requests.get(
            f"{API}/api/incidents/hse/repeat-detection?window_days=90&threshold=3&limit=2000",
            headers=_hdrs(master_token), timeout=20,
        ).json()
        hit = next((row for row in rollup["flagged"] if row["asset_id"] == asset_id), None)
        assert hit is not None
        assert hit["count"] == 3
        assert hit["severity_score"] >= 6
        assert hit["last_incident_ref"] in refs
    finally:
        # Clean up so repeated regression runs don't accumulate hundreds
        # of flagged phantom assets in the rollup.
        import pymongo
        client = pymongo.MongoClient(os.environ["MONGO_URL"])
        client[os.environ["DB_NAME"]].incidents.delete_many({"asset_id": asset_id})


def test_list_filters_by_date_range(master_token):
    payload = {
        "kind": "accident", "severity": "minor", "category": "other",
        "description": "Date filter test incident text here.",
        "occurred_at": "2020-01-15T12:00:00Z",
    }
    requests.post(f"{API}/api/incidents", json=payload, headers=_hdrs(master_token), timeout=20)
    r = requests.get(f"{API}/api/incidents?date_from=2020-01-01&date_to=2020-01-31&limit=10",
                     headers=_hdrs(master_token), timeout=20).json()
    assert r["count"] >= 1
    r2 = requests.get(f"{API}/api/incidents?date_from=2019-01-01&date_to=2019-12-31&limit=10",
                      headers=_hdrs(master_token), timeout=20).json()
    refs = {row["reference"] for row in r2["incidents"]}
    in_range_refs = {row["reference"] for row in r["incidents"]}
    assert not (in_range_refs & refs)


def test_list_filters_by_category_csv(master_token):
    r = requests.get(f"{API}/api/incidents?category=slip_trip_fall&limit=20",
                     headers=_hdrs(master_token), timeout=20).json()
    for row in r["incidents"]:
        assert row["category"] == "slip_trip_fall"
    r2 = requests.get(f"{API}/api/incidents?category=slip_trip_fall,equipment_failure&limit=50",
                      headers=_hdrs(master_token), timeout=20).json()
    for row in r2["incidents"]:
        assert row["category"] in {"slip_trip_fall", "equipment_failure"}


def test_equipment_incident_flag_persists_after_third_incident(master_token):
    """After 3 incidents on the same asset, the equipment doc should
    carry an ``incident_flag`` with ``capex_recommended=True``."""
    import pymongo
    asset_id = f"asset-flag-{uuid.uuid4().hex[:10]}"
    r = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "serious", "category": "equipment_failure",
        "description": "Flag-persistence test incident text - 1.",
        "asset_id": asset_id,
    }, headers=_hdrs(master_token), timeout=20).json()
    org_id = r["organization_id"]
    mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("DB_NAME") or "gymaxis_db"
    client = pymongo.MongoClient(mongo_url)
    client[db_name]["equipment"].update_one(
        {"id": asset_id, "organization_id": org_id},
        {"$set": {"id": asset_id, "organization_id": org_id, "name": "Phase 3 test rig"}},
        upsert=True,
    )
    for i in range(2):
        requests.post(f"{API}/api/incidents", json={
            "kind": "accident", "severity": "moderate", "category": "equipment_failure",
            "description": f"Flag-persistence test incident text - {i+2}.",
            "asset_id": asset_id,
        }, headers=_hdrs(master_token), timeout=20)
    doc = client[db_name]["equipment"].find_one({"id": asset_id, "organization_id": org_id})
    assert doc is not None
    flag = doc.get("incident_flag") or {}
    assert flag.get("count_90d") >= 3
    assert flag.get("capex_recommended") is True
    assert flag.get("severity_score", 0) >= 1
    client.close()



# ── Phase 4 — AI assistance + Whisper voice-to-text ──────────────


def test_ai_summarise_returns_prose(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "moderate", "category": "slip_trip_fall",
        "description": "Member slipped on wet floor near treadmill row 3 after the morning cleaning crew left the area without putting up a wet floor sign.",
    }, headers=_hdrs(master_token), timeout=20).json()
    r = requests.post(
        f"{API}/api/incidents/{create['id']}/ai/summarise",
        headers=_hdrs(master_token), timeout=60,
    )
    if r.status_code == 503:
        pytest.skip("AI service unavailable (Emergent LLM key may be empty)")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("summary"), str)
    assert len(body["summary"]) >= 30
    assert "." in body["summary"]


def test_ai_root_causes_returns_canonical_keys(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "moderate", "category": "equipment_failure",
        "description": "Treadmill emergency stop failed mid-session because the maintenance team never replaced the worn safety key after last month's service call.",
    }, headers=_hdrs(master_token), timeout=20).json()
    r = requests.post(
        f"{API}/api/incidents/{create['id']}/ai/root-causes",
        headers=_hdrs(master_token), timeout=60,
    )
    if r.status_code == 503:
        pytest.skip("AI service unavailable")
    assert r.status_code == 200
    causes = r.json()["root_causes"]
    assert isinstance(causes, list) and 1 <= len(causes) <= 3
    canonical = {
        "equipment_failure", "maintenance_issue", "user_error",
        "training_gap", "environmental", "process_failure",
        "contractor_issue", "communication", "inadequate_supervision",
        "other",
    }
    assert all(c in canonical for c in causes)


def test_ai_riddor_hint_returns_only_wizard_keys(master_token):
    create = requests.post(f"{API}/api/incidents", json={
        "kind": "accident", "severity": "moderate", "category": "manual_handling",
        "description": "Member of public lifted a heavy weight off the rack, dropped it on their foot, and was taken to hospital A&E for treatment of a suspected fracture.",
    }, headers=_hdrs(master_token), timeout=20).json()
    r = requests.post(
        f"{API}/api/incidents/{create['id']}/ai/riddor-hint",
        headers=_hdrs(master_token), timeout=60,
    )
    if r.status_code == 503:
        pytest.skip("AI service unavailable")
    assert r.status_code == 200
    answers = r.json()["answers"]
    wizard_keys = {
        "arose_from_work", "person_at_work", "fatality", "specified_injury",
        "over_7_day_incapacitation", "non_worker_to_hospital",
        "dangerous_occurrence", "occupational_disease", "gas_incident",
    }
    assert set(answers.keys()) == wizard_keys
    for v in answers.values():
        assert v is True or v is False or v is None


def test_ai_transcribe_rejects_empty_upload(master_token):
    r = requests.post(
        f"{API}/api/incidents/ai/transcribe",
        files={},
        headers=_hdrs(master_token), timeout=20,
    )
    assert r.status_code in {400, 422}
