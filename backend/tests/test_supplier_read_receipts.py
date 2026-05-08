"""Read-receipts for supplier case comments.

When a supplier opens the public case page (no gym JWT), any gym-authored
comments on that case must be stamped with `read_at_supplier`. When a gym
user opens the same page from inside their dashboard (JWT present), the
stamp must NOT be applied.
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from tests.conftest import rate_limit_bypass_headers, _test_backend_url


def _load_backend_env():
    """Load MONGO_URL / DB_NAME from backend/.env on demand."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return {}
    out = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _get_db():
    from pymongo import MongoClient
    env = _load_backend_env()
    mongo_url = os.environ.get("MONGO_URL") or env.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME") or env.get("DB_NAME")
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL / DB_NAME not configured")
    return MongoClient(mongo_url)[db_name]


API_BASE = _test_backend_url() + "/api"


def _seed_case_with_gym_comment(db):
    """Insert a supplier_case + one gym-authored unread comment, return (token, comment_id)."""
    org_id = str(uuid.uuid4())
    issue_id = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    token = uuid.uuid4().hex

    db.organizations.insert_one({
        "id": org_id,
        "name": "Read-Receipt Test Gym",
        "account_type": "pulse_pro",
    })
    db.issues.insert_one({
        "id": issue_id,
        "organization_id": org_id,
        "machine_type": "Treadmill",
        "serial_number": "RR-TEST-001",
        "issue_description": "Belt slipping test",
        "severity": "medium",
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.supplier_cases.insert_one({
        "id": case_id,
        "token": token,
        "issue_id": issue_id,
        "organization_id": org_id,
        "supplier_name": "Test Supplier",
        "organization_name": "Read-Receipt Test Gym",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1)).isoformat(),
    })
    comment_id = str(uuid.uuid4())
    db.supplier_case_comments.insert_one({
        "id": comment_id,
        "case_id": case_id,
        "author_name": "Lee Somers",
        "author_role": "gym",
        "message": "Any update from your engineer?",
        "attachments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return org_id, issue_id, case_id, token, comment_id


def test_supplier_visit_marks_gym_comment_as_read():
    """A supplier visit (no JWT) must stamp read_at_supplier on gym comments."""
    db = _get_db()
    org_id, issue_id, case_id, token, comment_id = _seed_case_with_gym_comment(db)
    try:
        # Verify unread at start
        c = db.supplier_case_comments.find_one({"id": comment_id})
        assert c.get("read_at_supplier") is None

        # Supplier visits public case page (no Authorization header)
        r = requests.get(
            f"{API_BASE}/supplier/case/{token}",
            headers=rate_limit_bypass_headers(),
            timeout=10,
        )
        assert r.status_code == 200, r.text

        # Gym comment is now stamped
        c = db.supplier_case_comments.find_one({"id": comment_id})
        assert c.get("read_at_supplier") is not None
        # Parseable ISO timestamp
        datetime.fromisoformat(c["read_at_supplier"].replace("Z", "+00:00"))
    finally:
        db.supplier_case_comments.delete_many({"case_id": case_id})
        db.supplier_cases.delete_many({"id": case_id})
        db.issues.delete_many({"id": issue_id})
        db.organizations.delete_many({"id": org_id})


def test_gym_visit_does_not_mark_gym_comment_as_read(regular_user_token):
    """If a gym user (JWT) opens the public page from their dashboard, no stamp."""
    db = _get_db()
    org_id, issue_id, case_id, token, comment_id = _seed_case_with_gym_comment(db)
    try:
        headers = {
            **rate_limit_bypass_headers(),
            "Authorization": f"Bearer {regular_user_token}",
        }
        r = requests.get(f"{API_BASE}/supplier/case/{token}", headers=headers, timeout=10)
        assert r.status_code == 200, r.text

        # Gym comment still unread — the gym user viewing doesn't count
        c = db.supplier_case_comments.find_one({"id": comment_id})
        assert c.get("read_at_supplier") is None
    finally:
        db.supplier_case_comments.delete_many({"case_id": case_id})
        db.supplier_cases.delete_many({"id": case_id})
        db.issues.delete_many({"id": issue_id})
        db.organizations.delete_many({"id": org_id})


def test_comments_endpoint_also_marks_as_read():
    """The /comments sibling endpoint (used by the polling UI) must also stamp."""
    db = _get_db()
    org_id, issue_id, case_id, token, comment_id = _seed_case_with_gym_comment(db)
    try:
        r = requests.get(
            f"{API_BASE}/supplier/case/{token}/comments",
            headers=rate_limit_bypass_headers(),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body.get("comments"), list)
        gym = next((c for c in body["comments"] if c["id"] == comment_id), None)
        assert gym is not None
        assert gym.get("read_at_supplier") is not None

        # And it's persisted in mongo
        c = db.supplier_case_comments.find_one({"id": comment_id})
        assert c.get("read_at_supplier") is not None
    finally:
        db.supplier_case_comments.delete_many({"case_id": case_id})
        db.supplier_cases.delete_many({"id": case_id})
        db.issues.delete_many({"id": issue_id})
        db.organizations.delete_many({"id": org_id})


def _seed_case_with_supplier_comment(db, owner_user_id: str, owner_org_id: str):
    """Insert a case + supplier-authored unread comment tied to a real user's org."""
    issue_id = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    token = uuid.uuid4().hex

    db.issues.insert_one({
        "id": issue_id,
        "organization_id": owner_org_id,
        "user_id": owner_user_id,
        "machine_type": "Treadmill",
        "serial_number": "RR-MIRROR-001",
        "issue_description": "Belt slipping (mirror receipt test)",
        "severity": "medium",
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.supplier_cases.insert_one({
        "id": case_id,
        "token": token,
        "issue_id": issue_id,
        "organization_id": owner_org_id,
        "supplier_name": "Test Supplier",
        "organization_name": "Read-Receipt Test Gym",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    comment_id = str(uuid.uuid4())
    db.supplier_case_comments.insert_one({
        "id": comment_id,
        "case_id": case_id,
        "author_name": "Test Supplier",
        "author_role": "supplier",
        "message": "Engineer dispatched, ETA 09:00",
        "attachments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return issue_id, case_id, token, comment_id


def test_gym_opens_issue_marks_supplier_comment_as_read(regular_user_token):
    """When a gym user hits GET /api/issues/{id}, all supplier-authored comments
    on the attached supplier_case must be stamped `read_at_gym` so the supplier
    sees "Seen ✓✓" on their public case page."""
    db = _get_db()
    # Pull the logged-in user's real org_id + user_id
    r = requests.get(
        f"{API_BASE}/auth/me",
        headers={
            **rate_limit_bypass_headers(),
            "Authorization": f"Bearer {regular_user_token}",
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    me = r.json()
    owner_user_id = me.get("id") or me.get("user_id")
    owner_org_id = me.get("organization_id") or me.get("org_id")
    assert owner_user_id and owner_org_id, f"Expected id + organization_id in /auth/me: {me}"

    issue_id, case_id, _token, comment_id = _seed_case_with_supplier_comment(
        db, owner_user_id, owner_org_id,
    )
    try:
        # Ensure initially unread
        c = db.supplier_case_comments.find_one({"id": comment_id})
        assert c.get("read_at_gym") is None

        r = requests.get(
            f"{API_BASE}/issues/{issue_id}",
            headers={
                **rate_limit_bypass_headers(),
                "Authorization": f"Bearer {regular_user_token}",
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text

        c = db.supplier_case_comments.find_one({"id": comment_id})
        assert c.get("read_at_gym") is not None
        datetime.fromisoformat(c["read_at_gym"].replace("Z", "+00:00"))
    finally:
        db.supplier_case_comments.delete_many({"case_id": case_id})
        db.supplier_cases.delete_many({"id": case_id})
        db.issues.delete_many({"id": issue_id})
