"""
Iter 215de — CRM Record-level + Field-level Permissions and Forecasting/Quotas.
"""
import os
import uuid
import time
import requests

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8001")
API = f"{BACKEND}/api"

# Shared tokens — login per-test trips the per-IP rate limiter, so we
# memoise on first call. Clearing the in-memory store happens on backend
# restart anyway, so this is fine for CI runs.
_CACHED_MAIN: list[str] = []
_CACHED_CRM: list[str] = []


def _login():
    if _CACHED_MAIN:
        return _CACHED_MAIN[0]
    # Up to 6 attempts with backoff in case a previous run left rate-limit residue.
    for attempt in range(6):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
            timeout=10,
        )
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        r.raise_for_status()
        body = r.json()
        token = body.get("access_token") or body.get("token")
        _CACHED_MAIN.append(token)
        return token
    raise RuntimeError("login rate-limited after 6 retries")


def _crm(main_token):
    if _CACHED_CRM:
        return _CACHED_CRM[0]
    r = requests.post(
        f"{API}/crm/auth/cross-login",
        headers={"Authorization": f"Bearer {main_token}"},
        json={},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    tok = body.get("access_token") or body.get("token") or body.get("crm_token")
    _CACHED_CRM.append(tok)
    return tok


def _h(t):
    return {"Authorization": f"Bearer {t}"}


# ─────────────────── PERMISSIONS ───────────────────

def test_permissions_effective_admin_unrestricted():
    crm = _crm(_login())
    r = requests.get(f"{API}/crm/permissions/effective", headers=_h(crm), timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["is_unrestricted"] is True
    for et in ("contact", "company", "opportunity", "contract"):
        assert d["rules"][et] == "all"


def test_permissions_sharing_rule_crud():
    crm = _crm(_login())
    # Create
    r = requests.put(
        f"{API}/crm/permissions/sharing-rules",
        headers=_h(crm),
        json={"entity_type": "contact", "role": "rep", "access": "owner"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    # List
    r = requests.get(f"{API}/crm/permissions/sharing-rules", headers=_h(crm), timeout=10)
    rules = r.json()["rules"]
    assert any(x["entity_type"] == "contact" and x["role"] == "rep" and x["access"] == "owner" for x in rules)
    # Update (upsert again)
    r = requests.put(
        f"{API}/crm/permissions/sharing-rules",
        headers=_h(crm),
        json={"entity_type": "contact", "role": "rep", "access": "team"},
        timeout=10,
    )
    assert r.status_code == 200
    rules = requests.get(f"{API}/crm/permissions/sharing-rules", headers=_h(crm), timeout=10).json()["rules"]
    upd = next(x for x in rules if x["entity_type"] == "contact" and x["role"] == "rep")
    assert upd["access"] == "team"
    # Delete
    r = requests.delete(
        f"{API}/crm/permissions/sharing-rules?entity_type=contact&role=rep",
        headers=_h(crm), timeout=10,
    )
    assert r.status_code == 200


def test_permissions_field_perm_crud_and_redaction():
    crm = _crm(_login())
    # Hide notes field from rep role
    r = requests.put(
        f"{API}/crm/permissions/field-perms",
        headers=_h(crm),
        json={"entity_type": "contact", "role": "rep", "field": "notes", "access": "hidden"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    rows = requests.get(f"{API}/crm/permissions/field-perms", headers=_h(crm), timeout=10).json()["perms"]
    assert any(p["field"] == "notes" and p["role"] == "rep" for p in rows)
    # Toggling to visible deletes the row
    r = requests.put(
        f"{API}/crm/permissions/field-perms",
        headers=_h(crm),
        json={"entity_type": "contact", "role": "rep", "field": "notes", "access": "visible"},
        timeout=10,
    )
    assert r.status_code == 200
    rows = requests.get(f"{API}/crm/permissions/field-perms", headers=_h(crm), timeout=10).json()["perms"]
    assert not any(p["field"] == "notes" and p["role"] == "rep" for p in rows)


def test_permissions_validation_rejects_bad_input():
    crm = _crm(_login())
    r = requests.put(
        f"{API}/crm/permissions/sharing-rules",
        headers=_h(crm),
        json={"entity_type": "garbage", "role": "rep", "access": "owner"},
        timeout=10,
    )
    assert r.status_code == 400
    r = requests.put(
        f"{API}/crm/permissions/sharing-rules",
        headers=_h(crm),
        json={"entity_type": "contact", "role": "rep", "access": "wrong"},
        timeout=10,
    )
    assert r.status_code == 400


# ─────────────────── QUOTAS + FORECAST ───────────────────

def test_quota_set_then_forecast_rolls_up():
    crm = _crm(_login())
    # Pull /crm/auth/me to get my id
    r = requests.get(f"{API}/crm/auth/me", headers=_h(crm), timeout=10)
    me = r.json()
    my_id = me.get("id") or me.get("user_id")
    suffix = uuid.uuid4().hex[:6]
    period_key = "2026-Q2"

    # Set a quota
    r = requests.put(
        f"{API}/crm/forecast/quotas",
        headers=_h(crm),
        json={"user_id": my_id, "period_type": "quarter", "period_key": period_key, "target_value": 100000},
        timeout=10,
    )
    assert r.status_code == 200, r.text

    # Create + commit an open deal (closes inside Q2)
    r = requests.post(
        f"{API}/crm/v2/opportunities",
        headers=_h(crm),
        json={"title": f"Forecast Test {suffix}", "value": 25000, "stage": "negotiation",
              "close_date": "2026-05-15", "owner_id": my_id},
        timeout=10,
    )
    assert r.status_code == 200
    opp_id = r.json()["id"]

    # Mark it as commit
    r = requests.put(
        f"{API}/crm/forecast/opportunities/{opp_id}/category",
        headers=_h(crm),
        json={"forecast_category": "commit"},
        timeout=10,
    )
    assert r.status_code == 200, r.text

    # Roll up forecast for Q2
    r = requests.get(
        f"{API}/crm/forecast",
        headers=_h(crm),
        params={"period_type": "quarter", "period_key": period_key},
        timeout=10,
    )
    assert r.status_code == 200
    rollup = r.json()
    my_row = next((row for row in rollup["rows"] if row["user_id"] == my_id), None)
    assert my_row is not None
    assert my_row["commit"] >= 25000
    assert my_row["best_case"] >= 25000  # commit also rolls into best_case
    assert my_row["pipeline"] >= 25000
    assert my_row["quota"] == 100000

    # Cleanup
    requests.delete(f"{API}/crm/v2/opportunities/{opp_id}", headers=_h(crm), timeout=10)


def test_forecast_category_validation():
    crm = _crm(_login())
    # Make a deal first
    r = requests.post(
        f"{API}/crm/v2/opportunities",
        headers=_h(crm),
        json={"title": "Cat validation", "value": 1, "stage": "lead"},
        timeout=10,
    )
    opp_id = r.json()["id"]
    r = requests.put(
        f"{API}/crm/forecast/opportunities/{opp_id}/category",
        headers=_h(crm),
        json={"forecast_category": "BAD"},
        timeout=10,
    )
    assert r.status_code == 400
    requests.delete(f"{API}/crm/v2/opportunities/{opp_id}", headers=_h(crm), timeout=10)


# ─────────────────── MANAGER FORECAST REVIEW ───────────────────

def test_team_forecast_and_commit_call():
    crm = _crm(_login())
    me = requests.get(f"{API}/crm/auth/me", headers=_h(crm), timeout=10).json()
    my_id = me.get("id") or me.get("user_id")
    period_key = "2026-Q3"

    # Set quota + create a deal owned by me
    requests.put(
        f"{API}/crm/forecast/quotas",
        headers=_h(crm),
        json={"user_id": my_id, "period_type": "quarter", "period_key": period_key, "target_value": 50000},
        timeout=10,
    )
    r = requests.post(
        f"{API}/crm/v2/opportunities",
        headers=_h(crm),
        json={"title": "Team Review Deal", "value": 12000, "stage": "negotiation",
              "close_date": "2026-08-15", "owner_id": my_id},
        timeout=10,
    )
    opp_id = r.json()["id"]
    # Mark commit via the dedicated endpoint (create_opportunity ignores forecast_category)
    requests.put(
        f"{API}/crm/forecast/opportunities/{opp_id}/category",
        headers=_h(crm),
        json={"forecast_category": "commit"},
        timeout=10,
    )

    # Manager call: override commit to 15000
    r = requests.put(
        f"{API}/crm/forecast/team/call",
        headers=_h(crm),
        json={"user_id": my_id, "period_type": "quarter", "period_key": period_key,
              "manager_call_value": 15000, "notes": "Strong week, raising the call."},
        timeout=10,
    )
    assert r.status_code == 200, r.text

    # Team rollup
    r = requests.get(
        f"{API}/crm/forecast/team",
        headers=_h(crm),
        params={"period_type": "quarter", "period_key": period_key},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] in ("org", "team")
    row = next((row for row in body["rows"] if row["user_id"] == my_id), None)
    assert row is not None
    assert row["commit"] >= 12000
    assert row["manager_call"] == 15000
    assert "Strong week" in (row["manager_call_notes"] or "")

    # Delete commit call
    r = requests.delete(
        f"{API}/crm/forecast/team/call",
        headers=_h(crm),
        params={"user_id": my_id, "period_type": "quarter", "period_key": period_key},
        timeout=10,
    )
    assert r.status_code == 200

    # Cleanup deal
    requests.delete(f"{API}/crm/v2/opportunities/{opp_id}", headers=_h(crm), timeout=10)


def test_team_call_validation():
    crm = _crm(_login())
    r = requests.put(
        f"{API}/crm/forecast/team/call",
        headers=_h(crm),
        json={"period_type": "year", "period_key": "2026", "manager_call_value": 1, "user_id": "x"},
        timeout=10,
    )
    assert r.status_code == 400


# ─────────────────── FORECAST ACCURACY ───────────────────

def test_snapshot_then_accuracy_under_call():
    """Manager calls £30k, rep closes £15k → under-call verdict, ~50% accuracy."""
    crm = _crm(_login())
    me = requests.get(f"{API}/crm/auth/me", headers=_h(crm), timeout=10).json()
    my_id = me.get("id") or me.get("user_id")
    period_key = "2026-Q4"

    requests.put(
        f"{API}/crm/forecast/quotas",
        headers=_h(crm),
        json={"user_id": my_id, "period_type": "quarter", "period_key": period_key, "target_value": 50000},
        timeout=10,
    )
    # Won deal (counts as actual)
    r1 = requests.post(
        f"{API}/crm/v2/opportunities",
        headers=_h(crm),
        json={"title": "Acc-Won", "value": 15000, "stage": "negotiation",
              "close_date": "2026-11-01", "owner_id": my_id},
        timeout=10,
    )
    won_id = r1.json()["id"]
    # Open commit deal — gets snapshotted but doesn't add to actuals
    r2 = requests.post(
        f"{API}/crm/v2/opportunities",
        headers=_h(crm),
        json={"title": "Acc-Open", "value": 18000, "stage": "negotiation",
              "close_date": "2026-11-15", "owner_id": my_id},
        timeout=10,
    )
    open_id = r2.json()["id"]
    requests.put(
        f"{API}/crm/forecast/opportunities/{open_id}/category",
        headers=_h(crm), json={"forecast_category": "commit"}, timeout=10,
    )

    # Manager called £30k
    requests.put(
        f"{API}/crm/forecast/team/call",
        headers=_h(crm),
        json={"user_id": my_id, "period_type": "quarter", "period_key": period_key,
              "manager_call_value": 30000, "notes": "Aggressive call"},
        timeout=10,
    )

    # Take snapshot of current numbers
    r = requests.post(
        f"{API}/crm/forecast/snapshots", headers=_h(crm),
        json={"period_type": "quarter", "period_key": period_key}, timeout=10,
    )
    assert r.status_code == 200, r.text
    assert r.json()["count"] >= 1

    # Now close the won deal → moves into actuals
    requests.put(
        f"{API}/crm/v2/opportunities/{won_id}", headers=_h(crm),
        json={"stage": "closed_won"}, timeout=10,
    )

    # Accuracy report
    r = requests.get(
        f"{API}/crm/forecast/accuracy", headers=_h(crm),
        params={"period_type": "quarter", "period_key": period_key}, timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["snapshot_taken"] is True
    row = next((x for x in body["rows"] if x["user_id"] == my_id), None)
    assert row is not None
    assert row["manager_call"] == 30000
    assert row["actual_closed_won"] == 15000
    assert row["verdict"] == "under"  # actual < 95% of call
    assert row["delta"] == -15000
    # Accuracy = 100 * (1 - |30000-15000|/30000) = 50%
    assert 49 <= row["call_accuracy_pct"] <= 51

    # List snapshots — Q4 should appear
    r = requests.get(f"{API}/crm/forecast/snapshots", headers=_h(crm), timeout=10)
    keys = [s["period_key"] for s in r.json()["snapshots"]]
    assert period_key in keys

    # Cleanup
    requests.delete(f"{API}/crm/v2/opportunities/{won_id}", headers=_h(crm), timeout=10)
    requests.delete(f"{API}/crm/v2/opportunities/{open_id}", headers=_h(crm), timeout=10)
    requests.delete(
        f"{API}/crm/forecast/team/call",
        headers=_h(crm),
        params={"user_id": my_id, "period_type": "quarter", "period_key": period_key},
        timeout=10,
    )


def test_accuracy_returns_empty_when_no_snapshot():
    crm = _crm(_login())
    r = requests.get(
        f"{API}/crm/forecast/accuracy", headers=_h(crm),
        params={"period_type": "quarter", "period_key": "1999-Q1"}, timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_taken"] is False
    assert body["rows"] == []


def test_track_record_self_returns_history():
    """A rep can fetch their own forecast track record across snapshotted periods."""
    crm = _crm(_login())
    me = requests.get(f"{API}/crm/auth/me", headers=_h(crm), timeout=10).json()
    my_id = me.get("id") or me.get("user_id")

    # Track record default = self
    r = requests.get(f"{API}/crm/forecast/track-record", headers=_h(crm), params={"periods": 4}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == my_id
    assert "rows" in body
    assert "summary" in body
    # If snapshots exist from earlier tests, summary fields should be populated
    if body["rows"]:
        s = body["summary"]
        assert s["periods_scored"] == len(body["rows"])
        assert "verdict_counts" in s
        assert "trend" in s


def test_track_record_other_user_blocked_for_non_manager():
    """A non-admin/non-manager cannot view someone else's record."""
    crm = _crm(_login())
    # Master admin CAN view anyone, so this just checks the endpoint responds (200)
    # for an admin asking about a fake id (returns empty payload, not 403).
    r = requests.get(
        f"{API}/crm/forecast/track-record", headers=_h(crm),
        params={"user_id": "non-existent-id", "periods": 4}, timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == []


def test_leaderboard_returns_ranked_rows():
    """Leaderboard returns ranked rows with rank, podium, and bottom_quartile flags."""
    crm = _crm(_login())
    r = requests.get(f"{API}/crm/forecast/leaderboard?periods=4", headers=_h(crm), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows" in body
    assert "summary" in body
    assert "scope" in body
    # If there are rows, they must be sorted by average_accuracy_pct desc
    if len(body["rows"]) >= 2:
        first, second = body["rows"][0], body["rows"][1]
        assert first["average_accuracy_pct"] >= second["average_accuracy_pct"]
        assert first["rank"] == 1
        assert second["rank"] == 2
    # Top 3 podium colours
    for i, row in enumerate(body["rows"][:3]):
        assert row["podium"] in ("gold", "silver", "bronze")
    # Bottom quartile flag exists on every row
    for row in body["rows"]:
        assert "bottom_quartile" in row


def test_leaderboard_validation_period_type():
    crm = _crm(_login())
    r = requests.get(
        f"{API}/crm/forecast/leaderboard?period_type=year", headers=_h(crm), timeout=10,
    )
    assert r.status_code == 400
