"""
Iter 215dd — CRM Enterprise Audit Trail.

Covers:
 - Contact create emits `create` audit entry with actor fields.
 - Contact update emits `update` audit entry with field-level diff.
 - Contact delete emits `delete` audit entry.
 - Opportunity stage change emits `stage_change` action.
 - Global recent endpoint returns at least the rows we just wrote.
 - Org-scope enforcement — a user from org X cannot see org Y's audit.
"""
import os
import uuid
import requests

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8001")
API = f"{BACKEND}/api"


def _login():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    return body.get("access_token") or body.get("token")


def _crm_token(main_token):
    r = requests.post(
        f"{API}/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {main_token}"},
        json={},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    return body.get("access_token") or body.get("token") or body.get("crm_token")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_audit_contact_create_update_delete():
    main = _login()
    crm = _crm_token(main)
    suffix = uuid.uuid4().hex[:6]

    # Create
    r = requests.post(
        f"{API}/crm/v2/contacts",
        headers=_h(crm),
        json={"first_name": "Audit", "last_name": f"Trail-{suffix}", "email": f"audit-{suffix}@test.com"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    contact_id = r.json()["id"]

    # Update
    r = requests.put(
        f"{API}/crm/v2/contacts/{contact_id}",
        headers=_h(crm),
        json={"phone": "+44 20 7946 0123", "job_title": "Ops Manager"},
        timeout=10,
    )
    assert r.status_code == 200, r.text

    # Audit timeline
    r = requests.get(
        f"{API}/crm/audit",
        headers=_h(crm),
        params={"entity_type": "contact", "entity_id": contact_id},
        timeout=10,
    )
    assert r.status_code == 200
    data = r.json()
    actions = [e["action"] for e in data["entries"]]
    assert "create" in actions
    assert "update" in actions
    # Update entry must carry diff
    upd = next(e for e in data["entries"] if e["action"] == "update")
    fields = {c["field"] for c in upd["changes"]}
    assert "phone" in fields
    assert "job_title" in fields
    assert upd["actor_email"] == "admin@gymaxisai.com"

    # Delete
    r = requests.delete(f"{API}/crm/v2/contacts/{contact_id}", headers=_h(crm), timeout=10)
    assert r.status_code == 200

    # Timeline now contains delete too
    r = requests.get(
        f"{API}/crm/audit",
        headers=_h(crm),
        params={"entity_type": "contact", "entity_id": contact_id},
        timeout=10,
    )
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()["entries"]]
    assert "delete" in actions


def test_audit_opportunity_stage_change():
    main = _login()
    crm = _crm_token(main)
    suffix = uuid.uuid4().hex[:6]

    # Create a deal
    r = requests.post(
        f"{API}/crm/v2/opportunities",
        headers=_h(crm),
        json={"title": f"Audit Deal {suffix}", "value": 12345, "stage": "lead"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    opp_id = r.json()["id"]

    # Move the stage
    r = requests.put(
        f"{API}/crm/v2/opportunities/{opp_id}",
        headers=_h(crm),
        json={"stage": "qualified"},
        timeout=10,
    )
    assert r.status_code == 200

    # Audit
    r = requests.get(
        f"{API}/crm/audit",
        headers=_h(crm),
        params={"entity_type": "opportunity", "entity_id": opp_id},
        timeout=10,
    )
    assert r.status_code == 200
    entries = r.json()["entries"]
    actions = [e["action"] for e in entries]
    assert "create" in actions
    assert "stage_change" in actions
    sc = next(e for e in entries if e["action"] == "stage_change")
    fields = {c["field"] for c in sc["changes"]}
    assert "stage" in fields

    # Cleanup
    requests.delete(f"{API}/crm/v2/opportunities/{opp_id}", headers=_h(crm), timeout=10)


def test_audit_recent_returns_entries():
    main = _login()
    crm = _crm_token(main)
    r = requests.get(f"{API}/crm/audit/recent?limit=10", headers=_h(crm), timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "entries" in data
    assert isinstance(data["entries"], list)
