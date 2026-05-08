"""
Security hardening regression tests (P0-P2 pass, Feb 2026).
Covers rate limiter, JWT revocation, LLM budget, supplier token rotation,
HMAC verification, audit-required writer, CORS resolver.

Uses ``asyncio.run`` rather than pytest-asyncio because the rest of the
repo's test suite is synchronous and we don't want to add a plugin
dependency just for this file.
"""
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi import HTTPException  # noqa: E402

from utils.database import db  # noqa: E402
from utils.security_plus import (  # noqa: E402
    DAILY_USER_ASK_LIMIT,
    audit_required,
    check_and_record_llm_budget,
    ensure_security_indexes,
    generate_supplier_token,
    is_jwt_revoked,
    new_jti,
    rate_limit_async,
    resolve_cors_origins,
    revoke_jwt,
    rotate_supplier_token,
    validate_supplier_token,
    verify_hmac_signature,
)


# Motor (the async MongoDB driver) binds to the event loop on first use; if
# each test creates a fresh loop via ``asyncio.run`` the Motor client blows up
# with "Event loop is closed". Use the shared session loop from the canonical
# ``tests/shared_loop`` module — see Iter 238g notes.
from tests.shared_loop import run_async as run


@pytest.fixture(scope="module", autouse=True)
def _prep_indexes():
    run(ensure_security_indexes())
    yield


# ─── Rate limiter ────────────────────────────────────────────────

def test_rate_limit_allows_under_cap():
    key = f"test:rl:{uuid.uuid4()}"

    async def _go():
        for _ in range(3):
            await rate_limit_async(key, max_requests=5, window_seconds=60)

    run(_go())


def test_rate_limit_blocks_over_cap():
    key = f"test:rl:{uuid.uuid4()}"

    async def _go():
        for _ in range(3):
            await rate_limit_async(key, max_requests=3, window_seconds=60)
        await rate_limit_async(key, max_requests=3, window_seconds=60)

    with pytest.raises(HTTPException) as exc:
        run(_go())
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


# ─── JWT revocation ──────────────────────────────────────────────

def test_jwt_revocation_roundtrip():
    async def _go():
        jti = new_jti()
        assert await is_jwt_revoked(jti) is False
        exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        await revoke_jwt(jti, exp, reason="unit-test")
        assert await is_jwt_revoked(jti) is True

    run(_go())


def test_jwt_revocation_missing_jti_is_noop():
    async def _go():
        await revoke_jwt("", 0)
        assert await is_jwt_revoked(None) is False
        assert await is_jwt_revoked("") is False

    run(_go())


# ─── LLM budget ──────────────────────────────────────────────────

def test_llm_budget_blocks_at_daily_cap():
    user_id = f"u-{uuid.uuid4()}"

    async def _fill():
        for _ in range(DAILY_USER_ASK_LIMIT):
            await check_and_record_llm_budget(user_id, None)

    run(_fill())

    async def _over():
        await check_and_record_llm_budget(user_id, None)

    with pytest.raises(HTTPException) as exc:
        run(_over())
    assert exc.value.status_code == 429
    assert "Daily" in exc.value.detail


# ─── Supplier token rotation ─────────────────────────────────────

def test_supplier_token_valid_then_expired():
    case_id = f"case-{uuid.uuid4()}"
    token = generate_supplier_token()

    async def _seed():
        await db.supplier_cases.insert_one({
            "id": case_id, "issue_id": "issue-stub",
            "token": token,
            "token_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        case = await validate_supplier_token(token)
        assert case["id"] == case_id

    run(_seed())

    async def _expire_and_check():
        await db.supplier_cases.update_one(
            {"id": case_id},
            {"$set": {"token_expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}},
        )
        await validate_supplier_token(token)

    with pytest.raises(HTTPException) as exc:
        run(_expire_and_check())
    assert exc.value.status_code == 410

    async def _rotate_and_verify():
        new_tok = await rotate_supplier_token(case_id)
        assert new_tok != token
        case = await validate_supplier_token(new_tok)
        assert case["id"] == case_id
        await db.supplier_cases.delete_one({"id": case_id})

    run(_rotate_and_verify())


# ─── HMAC verifier ───────────────────────────────────────────────

def test_hmac_verifier_happy_path():
    # nosec B105 — test fixture, not a real secret
    secret = "shhh"
    body = b'{"event":"ping"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_hmac_signature(body, sig, secret) is True
    assert verify_hmac_signature(body, f"sha256={sig}", secret) is True


def test_hmac_verifier_rejects_bad_sig():
    assert verify_hmac_signature(b"x", "bad", "shhh") is False
    assert verify_hmac_signature(b"", "", "shhh") is False


# ─── Fail-closed audit writer ───────────────────────────────────

def test_audit_required_writes_row():
    coll = f"test_audit_{uuid.uuid4().hex[:8]}"

    async def _go():
        await audit_required(coll, {"event": "unit-test", "actor": "pytest"})
        rows = await db[coll].find({}, {"_id": 0}).to_list(5)
        assert len(rows) == 1
        assert rows[0]["event"] == "unit-test"
        assert "created_at" in rows[0]
        await db.drop_collection(coll)

    run(_go())


def test_audit_required_raises_when_mongo_down(monkeypatch):
    from utils import security_plus
    coll = f"audit_fail_{uuid.uuid4().hex[:8]}"

    class _FailingCollection:
        async def insert_one(self, *_a, **_kw):
            raise RuntimeError("mongo unreachable")

    class _FailingDB:
        def __getitem__(self, _name):
            return _FailingCollection()

    monkeypatch.setattr(security_plus, "db", _FailingDB())

    async def _go():
        await audit_required(coll, {"event": "x"}, retries=0)

    with pytest.raises(HTTPException) as exc:
        run(_go())
    assert exc.value.status_code == 503


# ─── CORS resolver ───────────────────────────────────────────────

def test_cors_fails_fast_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.raises(RuntimeError):
        resolve_cors_origins()


def test_cors_dev_default_permissive(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert resolve_cors_origins() == ["*"]


def test_cors_comma_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.com, https://b.com ")
    assert resolve_cors_origins() == ["https://a.com", "https://b.com"]
